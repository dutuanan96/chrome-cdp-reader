"""
chrome-cdp-reader: Read your logged-in websites from WSL via Chrome DevTools Protocol
v1.1.0 — Fixed: auto-increment ID, drain loop, JPEG screenshots, error handling
"""

__version__ = "1.1.0"
__author__ = "dutuanan96"

from chrome_cdp_reader.bridge import ChromeReader, CDPError, TabNotFoundError
from chrome_cdp_reader.cookie_manager import CookieManager
from chrome_cdp_reader.chrome_launcher import ChromeLauncher

__all__ = ["ChromeReader", "CDPError", "TabNotFoundError", "CookieManager", "ChromeLauncher"]
