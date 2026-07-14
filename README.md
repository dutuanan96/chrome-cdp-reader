# Chrome CDP Reader

Direct Chrome debugging via DevTools Protocol for AI agents.

## Features
- Direct CDP connection to Chrome (port 9222)
- Tab management, navigation, DOM analysis
- Works on ANY website (no CSP restrictions)
- Multiple readers: Gmail, Facebook, Zalo

## Setup
```bash
# Launch Chrome with debug mode
chrome.exe --remote-debugging-port=9222

# Install
pip install -e .

# Use
from chrome_cdp_reader.bridge import ChromeReader
reader = ChromeReader()
tabs = reader.get_tabs()
```

## License
MIT License
