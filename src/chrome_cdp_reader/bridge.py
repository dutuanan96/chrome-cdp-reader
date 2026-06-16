"""
Chrome CDP Bridge - Connect to Windows Chrome from WSL
v1.1.0 — Fixed: auto-increment ID, drain loop, JPEG screenshots, error handling
"""

import json
import time
import base64
from typing import Optional, Dict, Any, List
from urllib.request import urlopen
from urllib.error import URLError

import websocket


class CDPError(Exception):
    """Base CDP error."""
    pass

class TabNotFoundError(CDPError):
    """Tab not found."""
    pass

class ConnectionError(CDPError):
    """Cannot connect to Chrome."""
    pass


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
    
    def find_tab(self, url_fragment: str) -> Optional[Dict[str, Any]]:
        """Find a tab by URL fragment."""
        for tab in self.get_tabs():
            if url_fragment in tab.get("url", ""):
                return tab
        return None
    
    def _connect(self, ws_url: str, timeout: int = 15) -> websocket.WebSocket:
        """Connect to a WebSocket URL."""
        return websocket.create_connection(ws_url, timeout=timeout)
    
    def cdp_send(self, ws: websocket.WebSocket, method: str,
                 params: Optional[Dict] = None, timeout: int = 10) -> Dict:
        """
        Send CDP command with auto-increment ID and drain loop.
        
        Fixes the id-collision bug: old code used hardcoded id=1,2,3
        which broke when Chrome sent events between send/recv.
        """
        if not hasattr(ws, '_cdp_msg_id'):
            ws._cdp_msg_id = 0
        ws._cdp_msg_id += 1
        msg_id = ws._cdp_msg_id
        
        ws.send(json.dumps({
            "id": msg_id,
            "method": method,
            "params": params or {}
        }))
        
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(min(deadline - time.time(), 5.0))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise CDPError(f"CDP error: {msg['error']}")
                return msg.get("result", {})
        
        raise CDPError(f"CDP method {method} timed out after {timeout}s")
    
    def cdp_js(self, ws: websocket.WebSocket, expression: str) -> Any:
        """Evaluate JS and return primitive value."""
        result = self.cdp_send(ws, "Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        })
        if result.get("exceptionDetails"):
            raise CDPError(f"JS exception: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")
    
    def create_tab(self, url: str = "about:blank") -> str:
        """
        Create a new tab.
        
        Args:
            url: Initial URL for the tab
            
        Returns:
            Target ID of the new tab
        """
        version = self._get_json("/json/version")
        browser_ws = version.get("webSocketDebuggerUrl", "")
        
        if not browser_ws:
            raise ConnectionError("Cannot get WebSocket URL from Chrome")
        
        ws = self._connect(browser_ws)
        result = self.cdp_send(ws, "Target.createTarget", {"url": url})
        ws.close()
        
        target_id = result.get("targetId", "")
        if not target_id:
            raise CDPError(f"Failed to create tab: {result}")
        
        return target_id
    
    def read(self, url: str, wait: int = 3) -> Dict[str, Any]:
        """
        Read content from a URL.
        
        Args:
            url: URL to read
            wait: Seconds to wait for page load
            
        Returns:
            Dictionary with page content
        """
        # Find existing tab or create new one
        tab = self.find_tab(url)
        if not tab:
            tab_id = self.create_tab(url)
            ws_url = self._get_tab_ws(tab_id)
            time.sleep(wait)
        else:
            ws_url = tab.get("webSocketDebuggerUrl", "")
            tab_id = tab.get("id", "")
        
        ws = self._connect(ws_url)
        try:
            # Batch read title + text + links in one JS call (faster)
            content = self.cdp_js(ws, """
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
            """)
            return json.loads(content) if content else {}
        finally:
            ws.close()
    
    def screenshot(self, url: str, output: str = "screenshot.jpg",
                   wait: int = 3, quality: int = 80) -> str:
        """
        Take a screenshot of a URL.
        
        Args:
            url: URL to screenshot
            output: Output file path
            wait: Seconds to wait for page load
            quality: JPEG quality (1-100)
            
        Returns:
            Path to saved screenshot
        """
        tab = self.find_tab(url)
        if not tab:
            tab_id = self.create_tab(url)
            ws_url = self._get_tab_ws(tab_id)
            time.sleep(wait)
        else:
            ws_url = tab.get("webSocketDebuggerUrl", "")
        
        ws = self._connect(ws_url)
        try:
            # JPEG format — much smaller than PNG, no timeout on large pages
            result = self.cdp_send(ws, "Page.captureScreenshot", {
                "format": "jpeg",
                "quality": quality
            }, timeout=15)
            
            if "data" in result:
                img_data = base64.b64decode(result["data"])
                with open(output, "wb") as f:
                    f.write(img_data)
                return output
        
        finally:
            ws.close()
        
        raise CDPError("Failed to take screenshot")
    
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
    
    def _get_tab_ws(self, tab_id: str) -> str:
        """Get WebSocket URL for a specific tab."""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get("id") == tab_id:
                return tab.get("webSocketDebuggerUrl", "")
        raise TabNotFoundError(f"Tab {tab_id} not found")


__all__ = ["ChromeReader", "CDPError", "TabNotFoundError"]
