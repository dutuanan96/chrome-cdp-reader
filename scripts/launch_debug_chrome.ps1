<#
.SYNOPSIS
    Open or reuse a dedicated Chrome Debug instance safely.
    Does NOT kill all Chrome. Verifies the process by name + command line
    (port + debug profile) before touching it. Writes PID/state to %LOCALAPPDATA%\Temp.

.DESCRIPTION
    - If Chrome debug (correct profile) is already listening on the port, reuse it.
    - If the port is free, launch a dedicated debug Chrome.
    - If another process holds the port, fail fast (do not launch on top of it).
    - Verifies the real CDP endpoint (/json/version), not just the socket.
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 9222,

    [string]$ProfileName = "chrome-debug-profile",

    [int]$Wait = 15
)

$ErrorActionPreference = "Stop"
$ChromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$UserDataDir = Join-Path $env:USERPROFILE $ProfileName
$StateDir = Join-Path ([IO.Path]::GetTempPath()) "chrome-cdp-reader"
$StatePath = Join-Path $StateDir "state.json"

function Get-DebugChromePid {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($p in $pids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $p" -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -eq 'chrome.exe' -and
            $proc.CommandLine -match "--remote-debugging-port=$Port" -and
            $proc.CommandLine -match [regex]::Escape($ProfileName)) {
            return $p
        }
    }
    return $null
}

function Get-Intruder {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($p in $pids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $p" -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $cl = $proc.CommandLine
        $isOurs = ($proc.Name -eq 'chrome.exe' -and
                   $cl -match "--remote-debugging-port=$Port" -and
                   $cl -match [regex]::Escape($ProfileName))
        if (-not $isOurs) {
            return [pscustomobject]@{ PID = $p; Name = $proc.Name; CommandLine = $cl }
        }
    }
    return $null
}

function Test-Endpoint {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 -ErrorAction Stop
        return [bool]($r.Browser)
    } catch { return $false }
}

function Save-State([int]$chromePid) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    [ordered]@{
        chromePid    = $chromePid
        port         = $Port
        profileName  = $ProfileName
        userDataDir  = $UserDataDir
        launchedAt   = (Get-Date).ToString("o")
        endpoint     = "http://127.0.0.1:$Port"
    } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

# --- Already up? Reuse. ---
if (Test-Endpoint) {
    $chromePid = Get-DebugChromePid
    Save-State $chromePid
    Write-Host "Reusing existing Chrome debug (PID $chromePid) on port $Port" -ForegroundColor Green
    exit 0
}

# --- Intruder check (fail-fast) ---
$intruder = Get-Intruder
if ($intruder) {
    Write-Host "[FAIL-FAST] Port $Port occupied by $($intruder.Name) PID=$($intruder.PID)" -ForegroundColor Red
    Write-Host "  $($intruder.CommandLine)"
    Write-Host "  Refusing to launch Chrome debug." -ForegroundColor Red
    exit 1
}

# --- Launch ---
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $ChromeExe
$psi.Arguments = "--remote-debugging-port=$Port --user-data-dir=`"$UserDataDir`""
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc) { Write-Host "Failed to start Chrome." -ForegroundColor Red; exit 1 }

# Poll until the real CDP endpoint answers
$deadline = [DateTime]::UtcNow.AddSeconds($Wait)
$ready = $false
while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-Endpoint) { $ready = $true; break }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Write-Host "Chrome debug started (PID $($proc.Id)) but /json/version not reachable within $Wait`s." -ForegroundColor Yellow
    Save-State $proc.Id
    exit 1
}

Save-State $proc.Id
Write-Host "Chrome debug launched OK (PID $($proc.Id)) on port $Port" -ForegroundColor Green
exit 0
