"""
Facebook Reader
"""

from typing import Dict, Any


class FacebookReader:
    """
    Read Facebook via Chrome CDP.
    """
    
    def __init__(self, chrome_reader):
        """
        Initialize with a ChromeReader instance.
        
        Args:
            chrome_reader: ChromeReader instance
        """
        self.reader = chrome_reader
    
    def read_feed(self) -> Dict[str, Any]:
        """
        Read Facebook feed.
        
        Returns:
            Dictionary with Facebook content
        """
        return self.reader.read("https://www.facebook.com/", wait=5)


__all__ = ["FacebookReader"]
