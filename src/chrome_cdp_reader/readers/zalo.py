"""
Zalo Reader
"""

from typing import Dict, Any


class ZaloReader:
    """
    Read Zalo messages via Chrome CDP.
    """

    def __init__(self, chrome_reader):
        """
        Initialize with a ChromeReader instance.

        Args:
            chrome_reader: ChromeReader instance
        """
        self.reader = chrome_reader

    def read_messages(self) -> Dict[str, Any]:
        """
        Read Zalo messages.

        Returns:
            Dictionary with Zalo content
        """
        return self.reader.read_zalo()


__all__ = ["ZaloReader"]
