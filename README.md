# chrome-cdp-reader

**Read your logged-in websites from WSL via Chrome DevTools Protocol (CDP)**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%2B%20WSL2-lightgrey.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

> **Status: Alpha** — a CDP reader for a *dedicated* Chrome debug profile.
> Not a "read every logged-in site with one command" magic tool.

---

## What is this?

`chrome-cdp-reader` connects from your WSL terminal to a **dedicated Chrome
debug profile** running on Windows, and reads page content (text, links,
images) or takes screenshots via the Chrome DevTools Protocol (CDP).

It does **NOT**:
- copy cookies or passwords from your default Chrome profile,
- use `--remote-allow-origins=*` by default,
- expose the CDP port to the LAN.

You log in **once** to the debug profile; cookies persist there for later runs.

## Why a dedicated debug profile?

Chrome 136+ encrypts each profile with a **separate key**. Copying the cookie
database from your default profile into a debug profile does **not** work —
the debug profile cannot decrypt it. So instead we:

1. Create an empty debug profile (`C:\Users\<you>\chrome-debug-profile`).
2. Launch Chrome on it with `--remote-debugging-port=9222`.
3. You log in once. Cookies stay in that profile.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔌 **One command setup** | `crc setup` creates the debug profile and launches Chrome |
| 🌉 **WSL ↔ Windows bridge** | Connects to `127.0.0.1:9222` (mirrored networking / portproxy) |
| 📖 **Read any page** | Extract text, links, images from any page in the debug profile |
| 🤖 **Site shortcuts** | `gmail`, `zalo`, `facebook` URL shortcuts (not full parsers) |
| 🖼️ **Screenshot capture** | Save `.jpg` or `.png` (format chosen from the file extension) |
| 🔧 **CLI interface** | `crc read gmail`, `crc read <url>`, `crc screenshot` |
| 🐍 **Python library** | `from chrome_cdp_reader import ChromeReader` |
| 🔒 **Safe by default** | No cookie copy, no password touch, localhost-only |
| 🛡️ **Safe process kill** | `crc setup` kills ONLY the Chrome instance that owns the debug port + debug profile (verified by PID, process name and command line). Never `taskkill /IM chrome.exe`. If the port is held by another process it FAILS FAST instead of launching on top of it. |
| 🧭 **Correlated navigation** | Waits for `Page.lifecycleEvent` correlated by `frameId` + `loaderId` (or `navigatedWithinDocument` for same-document nav). Surfaces `errorText` / `isDownload` immediately. |
| ✂️ **Bounded reads** | `read_text(max_chars=...)` truncates `document.body.innerText` INSIDE the browser before the JSON leaves via CDP, reducing payload and memory. |

## 🚀 Quick Start

### Prerequisites

- Windows 11 with WSL2 (Ubuntu recommended)
- Google Chrome installed on Windows
- Python 3.10+ in WSL

### Installation

```bash
git clone https://github.com/dutuanan96/chrome-cdp-reader.git
cd chrome-cdp-reader
pip install -e .
```

### Setup (run once)

```bash
crc setup
```

This will:
1. Kill the Chrome instance bound to the debug port (other Chrome windows untouched).
2. Create the **empty** debug profile directory.
3. Launch Chrome on that profile with CDP enabled.
4. Wait until CDP is reachable, then verify.

On first launch, **log in once** to the sites you want to read. Cookies persist
in the debug profile.

### WSL ↔ Windows networking helpers (`scripts/`)

When driving Chrome CDP from WSL2, the debug port is on the **Windows** side.
Use the helpers in [`scripts/`](scripts/) so you never hand-edit paths or read
`/etc/resolv.conf`:

| Script | Purpose |
|--------|---------|
| `scripts/launch_debug_chrome.ps1` | Open **or reuse** a dedicated debug Chrome. Verifies PID + name + command line, fails fast on an intruder, writes `state.json` to `%LOCALAPPDATA%\Temp`. |
| `scripts/check_chrome_debug_wsl.sh` | WSL-side discovery. Probes mirrored `127.0.0.1:9222`, then NAT `gateway:9223`. Short timeouts. `--url` / `--export` / `--json`. |
| `scripts/setup_wsl_portproxy.ps1` | Persistent `9223 → 9222` NAT portproxy **fallback** (admin only, firewall scoped to `vEthernet (WSL*)`). Only needed when mirrored networking is unavailable. |
| `scripts/ROOT_CAUSE_AND_SETUP.md` | Why WSL NAT mode breaks `127.0.0.1`, and the run order. |

Typical flow on Win11 + WSL2 (mirrored networking in `.wslconfig`):

```powershell
# Windows PowerShell
.\scripts\launch_debug_chrome.ps1
```
```bash
# WSL
./scripts/check_chrome_debug_wsl.sh --export   # prints: export CRC_CDP_URL='http://127.0.0.1:9222'
```



```bash
# Read Gmail inbox
crc read gmail

# Search Gmail (query is URL-encoded automatically)
crc read gmail --search "from:github label:work"

# Read Zalo messages
crc read zalo

# Read any URL
crc read https://example.com

# Limit printed text and output raw JSON
crc read https://example.com --max-chars 2000 --json

# Screenshot (format from extension: .jpg -> JPEG, .png -> PNG)
crc screenshot https://example.com -o shot.png
crc screenshot https://example.com -o shot.jpg

# Check connection
crc status
```

## 🏗️ How It Works

```
WSL Python CLI (crc)
      │  connect 127.0.0.1:9222
Windows Chrome (debug profile)
      ├── custom debug profile (C:\Users\<you>\chrome-debug-profile)
      ├── you log in ONCE; cookies persist
      ├── NO cookie / password copy
      ├── NO wildcard origin (unless explicit)
      └── NO LAN exposure (localhost only)
```

## 🔧 Python API

```python
from chrome_cdp_reader import ChromeReader

reader = ChromeReader()
content = reader.read("https://example.com")
print(content["title"], len(content["text"]))

# Screenshot with explicit format
reader.screenshot("https://example.com", output="shot.png")  # real PNG
reader.screenshot("https://example.com", output="shot.jpg")  # real JPEG
```

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **CDP Client:** websocket-client
- **CLI:** click
- **Platform:** Windows 11 + WSL2 (Ubuntu)

## 🔒 Security

- **No cookie/password copy.** The debug profile is separate; you log in once.
- **Localhost only.** CDP listens on `127.0.0.1`. If portproxy is needed, bind
  to `127.0.0.1` (never `0.0.0.0`):
  ```powershell
  netsh interface portproxy add v4tov6 listenport=9222 listenaddress=127.0.0.1 connectport=9222 connectaddress=::1
  ```
- **No wildcard origin.** `--remote-allow-origins=*` is never used. The CDP
  client suppresses its `Origin` header (`suppress_origin=True`) so Chromium
  147+ accepts the connection without an allowlist.
- CDP can read/control any tab in the debug profile — only use it on a profile
  you control.

## 🗺️ Roadmap

- [x] CDP bridge with auto-increment ID + drain loop (reliable)
- [x] JPEG/PNG screenshot by extension
- [x] Dedicated debug profile (no cookie copy)
- [ ] Structured site parsers (Gmail/Zalo/Facebook schema)
- [ ] Integration tests against Chrome for Testing
- [ ] PyPI publish + Beta status

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License — see [LICENSE](LICENSE).
