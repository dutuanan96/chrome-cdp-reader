# Contributing to chrome-cdp-reader

Thank you for your interest in contributing! This document provides guidelines and information for contributors.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/dutuanan96/chrome-cdp-reader/issues)
2. If not, create a new issue with:
   - A clear, descriptive title
   - Steps to reproduce the issue
   - Expected behavior
   - Actual behavior
   - Your environment (OS, Python version, Chrome version)

### Suggesting Features

1. Check existing [Issues](https://github.com/dutuanan96/chrome-cdp-reader/issues) for similar suggestions
2. Create a new issue with the "enhancement" label
3. Describe the feature and its use case

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Update documentation if needed
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.10+
- Git
- Chrome installed on Windows
- WSL2 (for testing)

### Setup

```bash
# Clone your fork
git clone https://github.com/your-username/chrome-cdp-reader.git
cd chrome-cdp-reader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints
- Write docstrings for public functions
- Keep functions focused and small

## Project Structure

```text
chrome-cdp-reader/
├── src/
│   └── chrome_cdp_reader/
│       ├── __init__.py
│       ├── cli.py              # CLI interface
│       ├── bridge.py           # CDP bridge
│       ├── cookie_manager.py   # Debug profile directory helper
│       ├── chrome_launcher.py  # Chrome launcher
│       ├── readers/            # Site reader wrappers (extensible)
│       └── utils/              # Utilities (detect_windows_user)
├── tests/                      # Test files
└── docs/                       # Documentation
```

## Adding a Site Reader

The CLI uses `ChromeReader` directly. The classes in `readers/` are thin
wrappers today; a *real* reader should parse structured data instead of
returning raw `document.body.innerText`.

1. Create a new file in `src/chrome_cdp_reader/readers/` (e.g. `mysite.py`).
2. Implement a method that navigates + waits for the right selector, then
   extracts a **typed schema** (list of dicts), not raw text.
3. Add the class to `readers/__init__.py`.
4. Add a CLI command in `cli.py` (or a shortcut in `ChromeReader`) if needed.
5. Update README.md with usage examples.

Example skeleton:

```python
# src/chrome_cdp_reader/readers/mysite.py
from typing import Dict, Any, List

class MySiteReader:
    """Read structured content from MySite via Chrome CDP."""

    def __init__(self, chrome_reader):
        self.reader = chrome_reader

    def read_items(self) -> List[Dict[str, Any]]:
        # 1. open / wait for load (ChromeReader.wait_for_load)
        # 2. poll for the content selector (ChromeReader.wait_for_selector)
        # 3. cdp_js to extract a typed list, e.g.:
        #    [{ "title": ..., "url": ..., "author": ... }, ...]
        result = self.reader.read("https://mysite.com")
        return [{"raw_text": result.get("text", "")}]
```

## Questions?

Feel free to open an issue for any questions about contributing!
