# WSL2 ↔ Windows Chrome CDP — Root cause and setup

## Recommended order

1. **Use WSL mirrored networking** on supported Windows 11 systems.
2. Keep Chrome CDP on Windows loopback `127.0.0.1:9222` or `::1:9222`.
3. Use the persistent portproxy fallback only when mirrored mode is unavailable or broken.
4. In NAT fallback, WSL connects to the Windows default gateway on proxy port `9223`, not directly to Chrome port `9222`.

## One-time mirrored setup

Create or edit:

```text
C:\Users\<WindowsUser>\.wslconfig
```

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
firewall=true
autoProxy=true
```

Then run from Windows:

```powershell
wsl --update
wsl --shutdown
```

Restart WSL and verify:

```bash
wslinfo --networking-mode
curl --noproxy '*' --connect-timeout 1 --max-time 2 \
  http://127.0.0.1:9222/json/version
```

`127.0.0.1` is the supported host-loopback path in mirrored mode. Do not use `::1` from WSL for this purpose.

## One-time NAT fallback

1. Start WSL once so the `vEthernet (WSL*)` adapter exists.
2. Run `launch_debug_chrome.ps1` from Windows.
3. Run `setup_wsl_portproxy.ps1` as Administrator.
4. In WSL:

```bash
gateway="$(ip -4 route show default | awk 'NR==1 {print $3}')"
curl --noproxy '*' --connect-timeout 1 --max-time 2 \
  "http://${gateway}:9223/json/version"
```

The proxy is intentionally:

```text
0.0.0.0:9223 -> 127.0.0.1:9222
```

or, when Chrome binds IPv6 loopback:

```text
0.0.0.0:9223 -> ::1:9222
```

Do not use proxy port `9222`; Chrome already owns that port on loopback. Chrome itself does **not** need to bind `0.0.0.0`.

## Standard paths

```text
Skill:
/home/hp/.hermes-shared/skills/devops/chrome-cdp-reader/SKILL.md

Windows state:
%LOCALAPPDATA%\Temp\chrome-cdp-reader\state.json

Windows log:
%LOCALAPPDATA%\Temp\chrome-cdp-reader\launch.log

Persistent proxy summary:
%ProgramData%\chrome-cdp-reader\portproxy.json
```

## Fast terminal probes

```bash
curl --fail --silent --show-error --noproxy '*' \
  --connect-timeout 1 --max-time 2 \
  http://127.0.0.1:9222/json/version
```

Bounded file lookup:

```bash
timeout 5s find /home/hp/.hermes-shared/skills \
  -maxdepth 4 -type f -name SKILL.md -print -quit
```

Never run `find /` for this skill.

## Root causes 1–7

1. **60-second terminal timeout:** network and filesystem commands lacked explicit connect/overall timeouts and searched too broad a path.
2. **`10.255.255.254` was wrong:** it is commonly WSL DNS tunneling's resolver address, not the Windows application endpoint.
3. **Wrong skill path:** the missing `devops/` segment caused deterministic failure.
4. **PowerShell path failure:** Windows PowerShell cannot treat a Linux `/home/...` path as a local Windows file path. Use `%LOCALAPPDATA%\Temp` or an explicit `\\wsl.localhost\...` path.
5. **Writing to `C:\` failed:** the root of the system drive is not a normal per-user writable runtime directory. Use `%LOCALAPPDATA%\Temp`.
6. **WSL could not reach Windows loopback:** in NAT mode, Linux and Windows use separate loopbacks. Mirrored mode shares localhost; NAT requires a Windows-side proxy reachable through the WSL default gateway.
7. **No state synchronization:** there was no canonical runtime state file. The launcher now writes PID, listener address, ports, browser version, WebSocket URL and log path.
