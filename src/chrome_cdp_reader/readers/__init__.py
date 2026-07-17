"""
Site-specific readers for chrome-cdp-reader.

NOTE: The reader classes below are thin wrappers that only call
ChromeReader.read_gmail / read_zalo / read (they do not parse structured
data). The CLI uses ChromeReader directly. This package is kept for
extensibility — implement structured parsers (schema'd output) here if you
want real Gmail/Zalo/Facebook readers.
"""

from chrome_cdp_reader.readers.generic import GenericReader
from chrome_cdp_reader.readers.gmail import GmailReader
from chrome_cdp_reader.readers.facebook import FacebookReader
from chrome_cdp_reader.readers.zalo import ZaloReader

__all__ = ["GenericReader", "GmailReader", "FacebookReader", "ZaloReader"]
