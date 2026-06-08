"""
chrome-cdp-reader: Read your logged-in websites from WSL via Chrome DevTools Protocol
"""

__version__ = "0.1.0"
__author__ = "dutuanan96"

from chrome_cdp_reader.bridge import ChromeReader
from chrome_cdp_reader.cookie_manager import CookieManager
from chrome_cdp_reader.chrome_launcher import ChromeLauncher

__all__ = ["ChromeReader", "CookieManager", "ChromeLauncher"]
