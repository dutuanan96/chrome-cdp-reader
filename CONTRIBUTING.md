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

```
chrome-cdp-reader/
├── src/
│   └── chrome_cdp_reader/
│       ├── __init__.py
│       ├── cli.py              # CLI interface
│       ├── bridge.py           # CDP bridge
│       ├── cookie_manager.py   # Cookie management
│       ├── chrome_launcher.py  # Chrome launcher
│       ├── readers/            # Site-specific readers
│       └── utils/              # Utilities
├── scripts/                    # Windows batch scripts
├── tests/                      # Test files
└── docs/                       # Documentation
```

## Adding a New Site Reader

1. Create a new file in `src/chrome_cdp_reader/readers/`
2. Implement the reader class
3. Add import in `readers/__init__.py`
4. Add CLI command in `cli.py` if needed
5. Update README.md with usage examples

Example:

```python
# src/chrome_cdp_reader/readers/my_site.py

from typing import Dict, Any


class MySiteReader:
    """
    Read MySite via Chrome CDP.
    """
    
    def __init__(self, chrome_reader):
        self.reader = chrome_reader
    
    def read_content(self) -> Dict[str, Any]:
        """Read content from MySite."""
        return self.reader.read("https://mysite.com", wait=5)
```

## Questions?

Feel free to open an issue for any questions about contributing!
