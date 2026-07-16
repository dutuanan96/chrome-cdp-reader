"""
Site-specific readers for chrome-cdp-reader.
"""

from chrome_cdp_reader.readers.generic import GenericReader
from chrome_cdp_reader.readers.gmail import GmailReader
from chrome_cdp_reader.readers.facebook import FacebookReader
from chrome_cdp_reader.readers.zalo import ZaloReader

__all__ = ["GenericReader", "GmailReader", "FacebookReader", "ZaloReader"]
