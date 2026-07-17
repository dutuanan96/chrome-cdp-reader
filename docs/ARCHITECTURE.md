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

### 2. ChromeProfileManager — `cookie_manager.py`

> Note: historically named `CookieManager`. It no longer synchronizes cookies.
> Chrome 136+ encrypts each profile with a separate key, so a copied cookie
> database cannot be decrypted by the debug profile. The class now only
> **creates and inspects the dedicated debug profile directory**; you log in
> once and cookies persist inside that profile. It never reads your default
> profile, passwords (Login Data) or any cookies.

### 2b. ChromeLauncher — `chrome_launcher.py` (process safety)

Manages Chrome lifecycle with defense-in-depth:
- `kill_chrome()` kills ONLY the Chrome instance that owns the debug port AND
  debug profile. It verifies process name + command line (`--remote-debugging-port`
  and `--user-data-dir=...chrome-debug-profile`) before killing — never
  `taskkill /IM chrome.exe`. If another process holds the port, it FAILS FAST
  (returns False) so a debug Chrome is not launched on top of it.
- `launch()` polls until `/json/version` is reachable (verifies the real CDP
  endpoint, not just the listening socket).

### 2c. Navigation correlation — `bridge.py`

`ChromeReader._prepare_tab` drives a robust tab lifecycle:
- Enables `Page.setLifecycleEventsEnabled`.
- Drains stale events (e.g. from `about:blank`) before navigating.
- Navigates exactly once, capturing `frameId` + `loaderId` from `Page.navigate`
  and surfacing `errorText` / `isDownload` immediately.
- Waits for completion via `Page.lifecycleEvent` correlated by `frameId` +
  `loaderId`, or `Page.navigatedWithinDocument` for same-document navigation.
  Falls back to `Page.loadEventFired` on older protocol.
- `read_text(max_chars=...)` truncates `document.body.innerText` INSIDE the
  browser before the JSON leaves via CDP.

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
3. **Origin check (WebSocket)**: Chrome 147+ rejects CDP WebSocket
   connections that send an `Origin` header Chromium doesn't allowlist. The
   client suppresses its Origin header (`suppress_origin=True`), so no
   `--remote-allow-origins` flag is needed and the port stays localhost-only.
   The wildcard `--remote-allow-origins=*` is never used (it would let any
   page open in the debug profile drive CDP).
4. **User Control**: User must manually run setup scripts

## Error Handling

The library provides clear error messages for common issues:

- Connection refused → Chrome not running or wrong port
- Timeout → Page load too slow or network issue
- Cookie errors → Default profile not found or access denied
- Permission errors → WSL file system access issues
