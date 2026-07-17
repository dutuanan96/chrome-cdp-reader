# Troubleshooting

## Common Issues

### 1. Chrome won't start with debug port

**Symptom:** `curl http://127.0.0.1:9222/json/version` returns connection refused

**Solutions:**

1. Kill the debug Chrome (only the instance that owns the debug port + profile).
   Prefer `crc setup`, which verifies the process by PID, name and command line
   before killing — it never uses `taskkill /IM chrome.exe`. If another process
   holds port 9222, `crc setup` fails fast instead of killing it.
   To kill manually and safely on Windows (verify first):
   ```powershell
   # find the debug-chrome PID listening on 9222 with the right profile
   $p = (Get-NetTCPConnection -LocalPort 9222 -State Listen).OwningProcess | Select-Object -Unique
   foreach ($pid in $p) {
     $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid"
     if ($proc.Name -eq 'chrome.exe' -and $proc.CommandLine -match '--remote-debugging-port=9222' -and $proc.CommandLine -match 'chrome-debug-profile') {
       taskkill /F /PID $pid
     }
   }
   ```
   Do NOT run `taskkill.exe /F /IM chrome.exe` — it kills every Chrome window.

2. Check if port 9222 is already in use:
   ```bash
   netstat.exe -an | grep 9222
   ```

3. Try a different port:
   ```bash
   chrome.exe --remote-debugging-port=9333 ...
   ```

### 2. WSL can't connect to localhost:9222

**Symptom:** Connection times out or refused from WSL

**Solutions:**

1. Enable mirrored networking in `.wslconfig`:
   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

2. Restart WSL:
   ```bash
   wsl --shutdown
   ```

3. Verify Chrome is listening:
   ```bash
   curl http://localhost:9222/json/version
   ```

### 3. Chrome 147+ IPv6 Issues

**Symptom:** Port shows LISTENING but returns empty response

**Solution:** Chrome 147+ binds to IPv6 only. Use port forwarding:

```powershell
netsh interface portproxy add v4tov6 listenport=9222 listenaddress=127.0.0.1 connectport=9222 connectaddress=::1
```

### 4. Cookies not working

**Symptom:** Website shows login page instead of content

**Solutions:**

1. The debug profile is separate from your default profile — log in once in
   the debug-profile Chrome window, then the session persists.
2. Make sure Chrome debug is running (`crc status` shows "Connected").
3. Check if the site session is still valid (re-log-in if expired):
   ```bash
   ls /mnt/c/Users/<YOUR_WINDOWS_USERNAME>/chrome-debug-profile/Default/Cookies
   ```

### 5. Permission Denied

**Symptom:** Cannot access Windows files from WSL

**Solutions:**

1. Check WSL file system permissions:
   ```bash
   ls -la /mnt/c/Users/
   ```

2. Run WSL as administrator if needed

3. Check Windows file permissions

### 6. Chrome crashes or won't start

**Symptom:** Chrome process exits immediately

**Solutions:**

1. Delete corrupted profile:
   ```bash
   rm -rf /mnt/c/Users/<YOUR_WINDOWS_USERNAME>/chrome-debug-profile
   ```

2. Check Chrome version:
   ```bash
   chrome.exe --version
   ```

3. Update Chrome to latest version

## Debug Mode

Enable debug logging (CDP commands sent/received are printed):

```bash
export CRC_DEBUG=1
crc read gmail
```

## Getting Help

If you're still having issues:

1. Check the [GitHub Issues](https://github.com/dutuanan96/chrome-cdp-reader/issues)
2. Run `crc status` to see connection details
3. Open a new issue with:
   - Your OS version
   - Python version
   - Chrome version
   - Error messages
