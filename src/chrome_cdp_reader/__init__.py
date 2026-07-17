"""
chrome-cdp-reader: Read your logged-in websites from WSL via Chrome DevTools Protocol

Alpha CDP reader for a dedicated Chrome debug profile (you log in once).
No cookie/password copying. No wildcard origin. Localhost only.
"""

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("chrome-cdp-reader")
except Exception:
    __version__ = "0.0.0"  # package not installed; single source of truth is pyproject.toml

__author__ = "dutuanan96"

from chrome_cdp_reader.bridge import ChromeReader, CDPError, TabNotFoundError
from chrome_cdp_reader.cookie_manager import CookieManager
from chrome_cdp_reader.chrome_launcher import ChromeLauncher

__all__ = ["ChromeReader", "CDPError", "TabNotFoundError", "CookieManager", "ChromeLauncher"]
