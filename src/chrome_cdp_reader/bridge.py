"""
Chrome CDP Bridge - Connect to Windows Chrome from WSL
"""

import json
import time
import base64
from typing import Optional, Dict, Any, List
from urllib.request import urlopen
from urllib.error import URLError


class ChromeReader:
    """
    Main class for reading web content from Windows Chrome via CDP.
    
    Usage:
        reader = ChromeReader()
        content = reader.read("https://gmail.com")
    """
    
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        """
        Initialize ChromeReader.
        
        Args:
            cdp_url: Chrome DevTools Protocol URL (default: http://127.0.0.1:9222)
        """
        self.cdp_url = cdp_url
        self._browser_ws_url = None
        self._tabs = []
        
    def _get_json(self, endpoint: str) -> Dict[str, Any]:
        """Fetch JSON from CDP HTTP endpoint."""
        url = f"{self.cdp_url}{endpoint}"
        try:
            with urlopen(url, timeout=5) as response:
                return json.loads(response.read().decode())
        except URLError as e:
            raise ConnectionError(
                f"Cannot connect to Chrome at {self.cdp_url}. "
                "Make sure Chrome is running with --remote-debugging-port=9222. "
                f"Error: {e}"
            )
    
    def is_connected(self) -> bool:
        """Check if Chrome is reachable."""
        try:
            version = self._get_json("/json/version")
            return "Browser" in version
        except Exception:
            return False
    
    def get_version(self) -> Dict[str, str]:
        """Get Chrome version info."""
        return self._get_json("/json/version")
    
    def get_tabs(self) -> List[Dict[str, Any]]:
        """Get list of open tabs."""
        return self._get_json("/json/list")
    
    def create_tab(self, url: str = "about:blank") -> str:
        """
        Create a new tab.
        
        Args:
            url: Initial URL for the tab
            
        Returns:
            Target ID of the new tab
        """
        import websocket
        import urllib.request
        
        # Get browser WebSocket URL
        version = self._get_json("/json/version")
        browser_ws = version.get("webSocketDebuggerUrl", "")
        
        if not browser_ws:
            raise ConnectionError("Cannot get WebSocket URL from Chrome")
        
        # Connect and create tab
        ws = websocket.create_connection(browser_ws, timeout=10)
        ws.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": url}
        }))
        resp = json.loads(ws.recv())
        ws.close()
        
        target_id = resp.get("result", {}).get("targetId", "")
        if not target_id:
            raise RuntimeError(f"Failed to create tab: {resp}")
        
        return target_id
    
    def _get_tab_ws(self, tab_id: str) -> str:
        """Get WebSocket URL for a specific tab."""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get("id") == tab_id:
                return tab.get("webSocketDebuggerUrl", "")
        raise ValueError(f"Tab {tab_id} not found")
    
    def read(self, url: str, wait: int = 3) -> Dict[str, Any]:
        """
        Read content from a URL.
        
        Args:
            url: URL to read
            wait: Seconds to wait for page load
            
        Returns:
            Dictionary with page content
        """
        import websocket
        
        # Create tab
        tab_id = self.create_tab(url)
        ws_url = self._get_tab_ws(tab_id)
        
        try:
            ws = websocket.create_connection(ws_url, timeout=15)
            time.sleep(wait)
            
            # Get page content
            ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    JSON.stringify({
                        title: document.title,
                        url: window.location.href,
                        text: document.body.innerText,
                        links: Array.from(document.querySelectorAll('a')).slice(0, 50).map(a => ({
                            text: a.innerText.trim(),
                            href: a.href
                        })),
                        images: Array.from(document.querySelectorAll('img')).slice(0, 20).map(img => ({
                            alt: img.alt,
                            src: img.src
                        }))
                    })
                    """,
                    "returnByValue": True
                }
            }))
            resp = json.loads(ws.recv())
            content = json.loads(resp.get("result", {}).get("result", {}).get("value", "{}"))
            
            ws.close()
            return content
            
        finally:
            # Close tab
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{self.cdp_url}/json/close/{tab_id}",
                    method="PUT"
                )
                urlopen(req, timeout=5)
            except Exception:
                pass
    
    def screenshot(self, url: str, output: str = "screenshot.png", wait: int = 3) -> str:
        """
        Take a screenshot of a URL.
        
        Args:
            url: URL to screenshot
            output: Output file path
            wait: Seconds to wait for page load
            
        Returns:
            Path to saved screenshot
        """
        import websocket
        
        tab_id = self.create_tab(url)
        ws_url = self._get_tab_ws(tab_id)
        
        try:
            ws = websocket.create_connection(ws_url, timeout=15)
            time.sleep(wait)
            
            # Take screenshot
            ws.send(json.dumps({
                "id": 1,
                "method": "Page.captureScreenshot",
                "params": {"format": "png", "quality": 90}
            }))
            resp = json.loads(ws.recv())
            
            if "result" in resp and "data" in resp["result"]:
                img_data = base64.b64decode(resp["result"]["data"])
                with open(output, "wb") as f:
                    f.write(img_data)
                return output
            
            ws.close()
            
        finally:
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{self.cdp_url}/json/close/{tab_id}",
                    method="PUT"
                )
                urlopen(req, timeout=5)
            except Exception:
                pass
        
        raise RuntimeError("Failed to take screenshot")
    
    def read_gmail(self, search: str = "") -> Dict[str, Any]:
        """
        Read Gmail inbox.
        
        Args:
            search: Search query (optional)
            
        Returns:
            Dictionary with Gmail content
        """
        if search:
            url = f"https://mail.google.com/mail/u/0/#search/{search}"
        else:
            url = "https://mail.google.com/mail/u/0/#inbox"
        
        return self.read(url, wait=5)
    
    def read_zalo(self) -> Dict[str, Any]:
        """Read Zalo messages."""
        return self.read("https://chat.zalo.me/", wait=5)


__all__ = ["ChromeReader"]
