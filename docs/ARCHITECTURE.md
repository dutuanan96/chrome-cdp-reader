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
│  │   (no --remote-allow-origins=* by default)      │   │
│  │   --user-data-dir=C:\Users\<you>\chrome-debug-profile │   │
│  │                                                 │   │
│  │   Dedicated profile: log in once, cookies persist│   │
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
netsh interface portproxy add v4tov6 listenport=9222 listenaddress=127.0.0.1 connectport=9222 connectaddress=::1
```

## Security Considerations

1. **Local Only**: CDP port listens on `127.0.0.1` (localhost). If you use
   `netsh portproxy`, bind to `127.0.0.1` — never `0.0.0.0`.
2. **Cookie Isolation**: Debug profile is separate from the default profile.
   You log in once; cookies stay in the debug profile. No copying.
3. **Origin check (WebSocket)**: By default Chrome rejects CDP WebSocket
   connections whose `Origin` header is not in the allowlist. The flag
   `--remote-allow-origins=*` disables that check, letting any page open in
   the debug profile (ads, phishing, compromised sites) drive CDP. It is OFF
   unless you pass `allow_all_origins=True` (e.g. for a trusted extension).
   This is unrelated to "remote access" — the port is still localhost-only;
   the flag governs which web pages may issue CDP commands.
4. **User Control**: User must manually run setup scripts

## Error Handling

The library provides clear error messages for common issues:

- Connection refused → Chrome not running or wrong port
- Timeout → Page load too slow or network issue
- Cookie errors → Default profile not found or access denied
- Permission errors → WSL file system access issues
