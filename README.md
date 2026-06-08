# chrome-cdp-reader

**Read your logged-in websites from WSL via Chrome DevTools Protocol**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%2B%20WSL2-lightgrey.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

---

## What is this?

`chrome-cdp-reader` lets you read content from websites you're already logged into — Gmail, Zalo, Facebook, Notion, GitHub... — directly from your WSL terminal. No re-authentication, no API keys, no browser extensions.

It bridges the gap between WSL2 and Windows Chrome using the Chrome DevTools Protocol (CDP), with automatic cookie management and one-click setup.

## Why?

If you're a developer using WSL2, you've probably faced these problems:

1. **WSL2 can't access Windows localhost** — Network isolation makes CDP connections fail silently
2. **Chrome debug mode is complex** — Port conflicts, profile setup, IPv6 changes in Chrome 147+
3. **Cookie management is manual** — You need to copy cookies between profiles yourself
4. **MCP servers don't auto-connect** — chrome-devtools-mcp fails from WSL without workarounds

**This tool solves all of these with a single command.**

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔌 **One-click setup** | `.bat` script configures Chrome debug mode automatically |
| 🍪 **Cookie management** | Copies cookies from your default profile to debug profile |
| 🌉 **WSL ↔ Windows bridge** | Handles mirrored networking, port conflicts, IPv6 changes |
| 📖 **Read any page** | Extract text, links, images from any logged-in page |
| 🤖 **Site-specific readers** | Pre-built readers for Gmail, Zalo, Facebook, Notion |
| 🖼️ **Screenshot capture** | Save screenshots of any page |
| 🔧 **CLI interface** | Simple commands: `crc read gmail`, `crc read <url>` |
| 🐍 **Python library** | Import and use in your own scripts |

## 🚀 Quick Start

### Prerequisites

- Windows 11 with WSL2 (Ubuntu recommended)
- Google Chrome installed on Windows
- Python 3.10+ in WSL

### Installation

```bash
# Install from PyPI (when published)
pip install chrome-cdp-reader

# Or install from source
git clone https://github.com/dutuanan96/chrome-cdp-reader.git
cd chrome-cdp-reader
pip install -e .
```

### Setup (Run once)

```bash
# Run the setup script in Windows (via WSL)
cmd.exe /c scripts\\setup-chrome.bat
```

This will:
1. Kill existing Chrome processes
2. Create debug profile directory
3. Copy cookies from your default profile
4. Launch Chrome with CDP enabled
5. Verify the connection

### Usage

```bash
# Read Gmail inbox
crc read gmail

# Search Gmail
crc read gmail --search "from:github"

# Read Zalo messages
crc read zalo

# Read any URL
crc read https://example.com

# Take a screenshot
crc screenshot https://example.com --output screenshot.png

# Interactive mode
crc interactive

# Check connection status
crc status
```

## 🏗️ How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ WSL2 (Ubuntu)                                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ chrome-cdp-reader                                   │   │
│  │                                                     │   │
│  │   1. Connect to localhost:9222                      │   │
│  │   2. Create new tab / navigate                      │   │
│  │   3. Extract content via JavaScript                 │   │
│  │   4. Return structured data                         │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │ WebSocket (CDP)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Windows 11                                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Chrome (Debug Mode)                                 │   │
│  │                                                     │   │
│  │   --remote-debugging-port=9222                      │   │
│  │   --remote-allow-origins=*                          │   │
│  │   --user-data-dir=C:\chrome-debug-profile           │   │
│  │                                                     │   │
│  │   Cookies copied from default profile               │   │
│  │   → Gmail, Zalo, Facebook... already logged in     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 📦 Project Structure

```
chrome-cdp-reader/
├── README.md                        # This file
├── LICENSE                          # MIT License
├── pyproject.toml                   # Python package config
├── src/
│   └── chrome_cdp_reader/
│       ├── __init__.py             # Package version
│       ├── cli.py                  # CLI interface (click)
│       ├── bridge.py               # WSL ↔ Windows Chrome bridge
│       ├── cookie_manager.py       # Cookie copy/management
│       ├── chrome_launcher.py      # Chrome debug mode launcher
│       ├── readers/                # Site-specific readers
│       │   ├── __init__.py
│       │   ├── gmail.py
│       │   ├── zalo.py
│       │   ├── facebook.py
│       │   └── generic.py          # Generic page reader
│       └── utils/
│           ├── __init__.py
│           └── ws_network.py       # WSL network utilities
├── scripts/
│   ├── setup-chrome.bat            # Windows: Setup Chrome debug mode
│   └── copy-cookies.bat            # Windows: Copy cookies
├── tests/
│   └── test_basic.py
└── docs/
    ├── ARCHITECTURE.md
    └── TROUBLESHOOTING.md
```

## 🔧 Python API

```python
from chrome_cdp_reader import ChromeReader

# Initialize reader
reader = ChromeReader()

# Read any page
content = reader.read("https://gmail.com")
print(content.text)

# Read Gmail
gmail = reader.read_gmail()
for email in gmail.inbox:
    print(f"From: {email.sender}")
    print(f"Subject: {email.subject}")
    print(f"Snippet: {email.snippet}")

# Take screenshot
reader.screenshot("https://example.com", output="screenshot.png")

# Read Zalo
zalo = reader.read_zalo()
for conv in zalo.conversations:
    print(f"{conv.name}: {conv.last_message}")
```

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **CDP Client:** websocket-client
- **CLI:** click
- **Network:** WSL2 mirrored networking
- **Platform:** Windows 11 + WSL2 (Ubuntu)

## 🗺️ Roadmap

- [x] Phase 1: Core functionality (CDP bridge, cookie management, CLI)
- [ ] Phase 2: Site-specific readers (Gmail, Zalo, Facebook, Notion)
- [ ] Phase 3: Advanced features (MCP server, interactive mode, multi-tab)
- [ ] Phase 4: Package publishing (PyPI)

## 🐛 Troubleshooting

### Chrome won't start with debug port

Make sure no other Chrome instances are running:
```bash
taskkill.exe /F /IM chrome.exe
```

### WSL can't connect to localhost:9222

1. Check if mirrored networking is enabled in `.wslconfig`:
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

### Cookies not working

Re-run the cookie copy script:
```bash
cmd.exe /c scripts\\copy-cookies.bat
```

### Chrome 147+ IPv6 issues

Chrome 147+ binds CDP to IPv6 only. Use the setup script which handles this automatically, or manually:
```powershell
netsh interface portproxy add v4tov6 listenport=9222 listenaddress=0.0.0.0 connectport=9222 connectaddress=::1
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/) documentation
- [WSL2 Mirrored Networking](https://learn.microsoft.com/en-us/windows/wsl/networking) guide
- All contributors and testers

---

<div align="center">

**Made with ❤️ for the WSL developer community**

[⬆ back to top](#chrome-cdp-reader)

</div>
