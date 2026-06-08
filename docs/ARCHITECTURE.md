# Architecture

## Overview

chrome-cdp-reader bridges the gap between WSL2 and Windows Chrome using the Chrome DevTools Protocol (CDP). It allows reading content from websites you're already logged into, directly from your WSL terminal.

## Components

### 1. ChromeReader (bridge.py)

The main class that handles:
- Connecting to Chrome via CDP
- Creating and managing tabs
- Navigating to URLs
- Extracting page content
- Taking screenshots

### 2. CookieManager (cookie_manager.py)

Handles cookie synchronization between:
- Default Chrome profile (where you're logged in)
- Debug profile (used by chrome-cdp-reader)

### 3. ChromeLauncher (chrome_launcher.py)

Manages Chrome lifecycle:
- Killing existing Chrome processes
- Launching Chrome with debug mode
- Verifying CDP connection

### 4. CLI (cli.py)

Command-line interface providing:
- `crc read <target>` - Read content from a website
- `crc screenshot <url>` - Take a screenshot
- `crc status` - Check connection status
- `crc setup` - One-time setup
- `crc cookies` - Manage cookies

### 5. Readers (readers/)

Site-specific readers for:
- Gmail
- Zalo
- Facebook
- Generic pages

## Data Flow

```
User Command (CLI)
       │
       ▼
   ChromeReader
       │
       ▼
   CDP WebSocket ──────────────► Chrome (Windows)
       │                              │
       ▼                              ▼
   Page Content              Execute JavaScript
       │                              │
       ▼                              ▼
   Return to CLI             Extract DOM/Text
```

## Network Architecture

```
┌─────────────────────────────────────────────────────────┐
│ WSL2 (Ubuntu)                                           │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ chrome-cdp-reader                               │   │
│  │                                                 │   │
│  │   1. Connect to localhost:9222                  │   │
│  │   2. Create tab / navigate                      │   │
│  │   3. Execute JavaScript                         │   │
│  │   4. Extract content                            │   │
│  └───────────────────────┬─────────────────────────┘   │
│                          │                              │
└──────────────────────────┼──────────────────────────────┘
                           │ WebSocket (CDP)
                           ▼
┌─────────────────────────────────────────────────────────┐
│ Windows 11                                              │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Chrome (Debug Mode)                             │   │
│  │                                                 │   │
│  │   --remote-debugging-port=9222                  │   │
│  │   --remote-allow-origins=*                      │   │
│  │   --user-data-dir=C:\chrome-debug-profile       │   │
│  │                                                 │   │
│  │   Cookies: copied from default profile          │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## WSL2 Networking

### Mirrored Networking (Recommended)

In Windows 11, WSL2 supports mirrored networking mode, which allows WSL to access Windows localhost services directly.

Configuration in `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

### Fallback: Port Forwarding

If mirrored networking is not available, use port forwarding:

```powershell
netsh interface portproxy add v4tov6 listenport=9222 listenaddress=0.0.0.0 connectport=9222 connectaddress=::1
```

## Security Considerations

1. **Local Only**: CDP port is only accessible from localhost
2. **Cookie Isolation**: Debug profile is separate from default profile
3. **No Remote Access**: `--remote-allow-origins=*` only applies to localhost
4. **User Control**: User must manually run setup scripts

## Error Handling

The library provides clear error messages for common issues:

- Connection refused → Chrome not running or wrong port
- Timeout → Page load too slow or network issue
- Cookie errors → Default profile not found or access denied
- Permission errors → WSL file system access issues
