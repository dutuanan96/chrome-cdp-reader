# Troubleshooting

## Common Issues

### 1. Chrome won't start with debug port

**Symptom:** `curl http://127.0.0.1:9222/json/version` returns connection refused

**Solutions:**

1. Kill all Chrome processes first:
   ```bash
   taskkill.exe /F /IM chrome.exe
   ```

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
netsh interface portproxy add v4tov6 listenport=9222 listenaddress=0.0.0.0 connectport=9222 connectaddress=::1
```

### 4. Cookies not working

**Symptom:** Website shows login page instead of content

**Solutions:**

1. Re-run cookie copy script:
   ```bash
   cmd.exe /c scripts\\copy-cookies.bat
   ```

2. Make sure Chrome is closed before copying cookies

3. Check if cookies exist in debug profile:
   ```bash
   ls /mnt/c/Users/HP/chrome-debug-profile/Default/Cookies
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
   rm -rf /mnt/c/Users/HP/chrome-debug-profile
   ```

2. Check Chrome version:
   ```bash
   chrome.exe --version
   ```

3. Update Chrome to latest version

## Debug Mode

Enable debug logging:

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
