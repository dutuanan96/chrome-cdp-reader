"""
Generic page reader
"""

from typing import Dict, Any, List


class GenericReader:
    """
    Generic reader for any web page.
    """

    def __init__(self, chrome_reader):
        """
        Initialize with a ChromeReader instance.

        Args:
            chrome_reader: ChromeReader instance
        """
        self.reader = chrome_reader

    def read(self, url: str, wait: int = 3) -> Dict[str, Any]:
        """
        Read content from any URL.

        Args:
            url: URL to read
            wait: Seconds to wait for page load

        Returns:
            Dictionary with page content
        """
        return self.reader.read(url, wait=wait)

    def read_text(self, url: str, wait: int = 3) -> str:
        """
        Read text content from a URL.

        Args:
            url: URL to read
            wait: Seconds to wait for page load

        Returns:
            Page text content
        """
        content = self.read(url, wait=wait)
        return content.get("text", "")

    def read_links(self, url: str, wait: int = 3) -> List[Dict[str, str]]:
        """
        Read links from a URL.

        Args:
            url: URL to read
            wait: Seconds to wait for page load

        Returns:
            List of links with text and href
        """
        content = self.read(url, wait=wait)
        return content.get("links", [])


__all__ = ["GenericReader"]
