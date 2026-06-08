"""
Gmail Reader
"""

from typing import Dict, Any, List


class GmailReader:
    """
    Read Gmail inbox via Chrome CDP.
    """
    
    def __init__(self, chrome_reader):
        """
        Initialize with a ChromeReader instance.
        
        Args:
            chrome_reader: ChromeReader instance
        """
        self.reader = chrome_reader
    
    def read_inbox(self, search: str = "") -> Dict[str, Any]:
        """
        Read Gmail inbox.
        
        Args:
            search: Search query (optional)
            
        Returns:
            Dictionary with Gmail content
        """
        return self.reader.read_gmail(search=search)
    
    def search(self, query: str) -> Dict[str, Any]:
        """
        Search Gmail.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with search results
        """
        return self.reader.read_gmail(search=query)


__all__ = ["GmailReader"]
