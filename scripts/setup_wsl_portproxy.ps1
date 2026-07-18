<#
Install a persistent Windows portproxy for WSL2 NAT mode.

Architecture:
  WSL -> Windows gateway:9223 -> Windows loopback:9222 -> Chrome CDP

Why port 9223?
Chrome already owns loopback port 9222. A separate proxy port avoids wildcard
binding conflicts and keeps Chrome's actual CDP listener loopback-only.

Run once from an elevated Windows PowerShell after Chrome CDP is running:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_wsl_portproxy.ps1

Remove:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_wsl_portproxy.ps1 -Remove
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$ChromePort = 9222,

    [ValidateRange(1, 65535)]
    [int]$ProxyPort = 9223,

    [switch]$Remove
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ListenAddress = "0.0.0.0"
$FirewallGroup = "Chrome CDP Reader WSL PortProxy"
$ConfigDir = Join-Path $env:ProgramData "chrome-cdp-reader"
$ConfigPath = Join-Path $ConfigDir "portproxy.json"
$StatePath = Join-Path ([IO.Path]::GetTempPath()) "chrome-cdp-reader\state.json"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this script from PowerShell opened with Run as Administrator."
    }
}

function Remove-OurRules {
    foreach ($mode in @("v4tov4", "v4tov6")) {
        & netsh interface portproxy delete $mode listenaddress=$ListenAddress listenport=$ProxyPort protocol=tcp 2>$null | Out-Null
    }
    Get-NetFirewallRule -Group $FirewallGroup -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue
}

function Get-WslAdapters {
    return @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "vEthernet (WSL*" -and $_.Status -ne "Disabled"
    })
}

function Get-ListenerTarget {
    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $ChromePort -ErrorAction SilentlyContinue)
    if (-not $connections) {
        throw "Chrome CDP is not listening on port $ChromePort. Run launch_debug_chrome.ps1 first."
    }

    $addresses = @($connections | Select-Object -ExpandProperty LocalAddress -Unique)
    $nonLoopback = @($addresses | Where-Object { $_ -notin @("127.0.0.1", "::1") })
    if ($nonLoopback) {
        throw "Unsafe Chrome CDP listener detected on $($nonLoopback -join ', '). Refusing to proxy it."
    }

    if ($addresses -contains "127.0.0.1") {
        return [pscustomobject]@{ Mode = "v4tov4"; Address = "127.0.0.1" }
    }
    if ($addresses -contains "::1") {
        return [pscustomobject]@{ Mode = "v4tov6"; Address = "::1" }
    }

    throw "Chrome listener address could not be classified."
}

function Assert-FirewallEnabled {
    $disabled = @(Get-NetFirewallProfile | Where-Object { -not $_.Enabled })
    if ($disabled) {
        throw "Windows Firewall is disabled for profile(s): $($disabled.Name -join ', '). Refusing to create a wildcard portproxy listener."
    }
}

Assert-Administrator

if ($ChromePort -eq $ProxyPort) {
    throw "ChromePort and ProxyPort must be different. Keep Chrome on 9222 and use 9223 for the WSL proxy."
}

if ($Remove) {
    Remove-OurRules
    if (Test-Path -LiteralPath $ConfigPath) { Remove-Item -LiteralPath $ConfigPath -Force }
    Write-Host "Removed portproxy $ListenAddress`:$ProxyPort and its firewall rules."
    exit 0
}

Assert-FirewallEnabled
$adapters = @(Get-WslAdapters)
if (-not $adapters) {
    throw "No active vEthernet (WSL*) adapter was found. Start a WSL distribution once, then rerun. If mirrored networking works, this proxy is unnecessary."
}

$target = Get-ListenerTarget
$service = Get-Service -Name iphlpsvc -ErrorAction Stop
if ($service.StartType -ne "Automatic") { Set-Service -Name iphlpsvc -StartupType Automatic }
if ($service.Status -ne "Running") { Start-Service -Name iphlpsvc }

$foreign = @(Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue)
$existingText = (& netsh interface portproxy show all | Out-String)
$expectedExisting = $existingText -match "(?m)^\s*0\.0\.0\.0\s+$ProxyPort\s+"
if ($foreign -and -not $expectedExisting) {
    $pids = $foreign | Select-Object -ExpandProperty OwningProcess -Unique
    throw "Proxy port $ProxyPort is already occupied by PID(s) $($pids -join ', '). Refusing to replace it."
}

Remove-OurRules

$output = & netsh interface portproxy add $($target.Mode) `
    listenaddress=$ListenAddress `
    listenport=$ProxyPort `
    connectaddress=$($target.Address) `
    connectport=$ChromePort `
    protocol=tcp 2>&1
if ($LASTEXITCODE -ne 0) { throw "netsh portproxy add failed: $($output | Out-String)" }

$ruleNames = @()
$index = 0
foreach ($adapter in $adapters) {
    $index += 1
    $name = "ChromeCDPReader-WSL-$ProxyPort-$index"
    New-NetFirewallRule `
        -Name $name `
        -DisplayName "Chrome CDP Reader WSL proxy $ProxyPort ($($adapter.Name))" `
        -Group $FirewallGroup `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Any `
        -Protocol TCP `
        -LocalPort $ProxyPort `
        -InterfaceAlias $adapter.Name `
        -RemoteAddress Any | Out-Null
    $ruleNames += $name
}

$deadline = [DateTime]::UtcNow.AddSeconds(5)
do {
    $ready = [bool](Get-NetTCPConnection -State Listen -LocalPort $ProxyPort -ErrorAction SilentlyContinue)
    if (-not $ready) { Start-Sleep -Milliseconds 250 }
} while (-not $ready -and [DateTime]::UtcNow -lt $deadline)
if (-not $ready) { throw "Portproxy was added, but no listener appeared on port $ProxyPort." }

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$config = [ordered]@{
    schemaVersion  = 1
    installedAt    = (Get-Date).ToString("o")
    mode           = $target.Mode
    listenAddress  = $ListenAddress
    proxyPort      = $ProxyPort
    connectAddress = $target.Address
    connectPort    = $ChromePort
    adapters       = @($adapters | Select-Object -ExpandProperty Name)
    firewallRules  = $ruleNames
    statePath      = $StatePath
}
$config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

Write-Host ""
Write-Host "Persistent WSL NAT portproxy installed." -ForegroundColor Green
Write-Host "  Windows listener: $ListenAddress`:$ProxyPort"
Write-Host "  Forward target:   $($target.Address):$ChromePort ($($target.Mode))"
Write-Host "  Firewall scope:   vEthernet (WSL*) only"
Write-Host "  Config:           $ConfigPath"
Write-Host ""
Write-Host "From WSL, do not read /etc/resolv.conf. Use:"
Write-Host "  gateway=`$(ip -4 route show default | awk 'NR==1 {print `$3}')"
Write-Host "  curl --noproxy '*' --connect-timeout 1 --max-time 2 http://`$gateway`:$ProxyPort/json/version"
