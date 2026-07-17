"""
Chrome CDP Bridge - Connect to Windows Chrome from WSL
v1.3.0-alpha — Reliable tab lifecycle: about:blank -> enable -> navigate once
-> Page.loadEventFired (drained, not swallowed) -> readyState -> selector wait
(SPA) with DOM fallback. No Page.reload, no blind sleep. suppress_origin=True.
"""

import json
import time
import base64
import logging
import os
from typing import Optional, Dict, Any, List
from urllib.request import urlopen
from urllib.error import URLError

import websocket

logger = logging.getLogger("chrome_cdp_reader")
if os.environ.get("CRC_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)


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
        """
        Connect to a WebSocket URL.

        suppress_origin=True: websocket-client sends an `Origin` header by
        default, which Chromium 147+ rejects (403) unless allowlisted. A
        non-browser CDP client should suppress it — no --remote-allow-origins
        flag needed, and it works for localhost / 127.0.0.1 / IPv6 alike.
        """
        return websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)

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
        logger.debug("CDP send id=%s method=%s", msg_id, method)

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
        Create a new tab (without navigating to a real URL yet).

        Args:
            url: Initial URL (default about:blank)

        Returns:
            Target ID of the new tab
        """
        version = self._get_json("/json/version")
        browser_ws = version.get("webSocketDebuggerUrl", "")

        if not browser_ws:
            raise ConnectionError("Cannot get WebSocket URL from Chrome")

        ws = self._connect(browser_ws)
        try:
            result = self.cdp_send(ws, "Target.createTarget", {"url": url})
        finally:
            ws.close()

        target_id = result.get("targetId", "")
        if not target_id:
            raise CDPError(f"Failed to create tab: {result}")

        return target_id

    def _prepare_tab(self, url: str, timeout: int = 15,
                     selector: Optional[str] = None,
                     reuse_existing: bool = False) -> websocket.WebSocket:
        """
        Robust tab lifecycle (core reliability primitive).

        Flow:
          1. Reuse an existing matching tab OR create a new one on about:blank.
          2. Connect the tab WebSocket, enable Page + Runtime events.
          3. If a new tab, navigate exactly ONCE via Page.navigate (no reload).
          4. Wait for Page.loadEventFired by draining raw ws messages (the
             load event is NOT swallowed by cdp_send's ID-matching loop).
          5. Poll document.readyState until interactive/complete.
          6. If `selector` given, wait for it (SPA render); on timeout fall
             back to DOM text instead of hanging.
          7. On overall timeout, raise CDPError — never silently read a
             half-loaded page.

        Args:
            url: URL to prepare
            timeout: Max seconds for load + selector wait
            selector: Optional CSS selector to wait for (SPA content)
            reuse_existing: If True, navigate the existing matching tab in
                place instead of opening a new one (and skip re-navigation
                if the tab already shows the URL).

        Returns:
            An open WebSocket connected to the prepared tab. Caller must
            close it (use a try/finally).
        """
        # 1. Tab selection
        if reuse_existing:
            tab = self.find_tab(url)
            if tab:
                ws_url = tab.get("webSocketDebuggerUrl", "")
                tab_id = tab.get("id", "")
                navigate = tab.get("url", "") != url
            else:
                tab_id = self.create_tab("about:blank")
                ws_url = self._get_tab_ws(tab_id)
                navigate = True
        else:
            tab_id = self.create_tab("about:blank")
            ws_url = self._get_tab_ws(tab_id)
            navigate = True

        ws = self._connect(ws_url)
        # 2. Enable events BEFORE navigating
        self.cdp_send(ws, "Page.enable", timeout=5)
        self.cdp_send(ws, "Runtime.enable", timeout=5)

        # 3. Navigate exactly once (no reload)
        if navigate:
            self.cdp_send(ws, "Page.navigate", {"url": url}, timeout=10)

        # 4. Wait for load event by draining raw messages (only when we
        #    actually navigated; a reused tab already at the URL is loaded).
        if navigate:
            load_ok = self._wait_load_event(ws, timeout=timeout)
            if not load_ok:
                ws.close()
                raise CDPError(
                    f"Page did not fire loadEventFired for {url} within {timeout}s"
                )

        # 5. Poll readyState
        self._wait_ready_state(ws, timeout=timeout)

        # 6. Optional selector wait (SPA), with DOM fallback on timeout
        if selector:
            found = self.wait_for_selector(ws, selector, timeout=timeout)
            if not found:
                # Fallback: ensure at least some DOM text is present
                text_len = self.cdp_js(
                    ws, "document.body ? document.body.innerText.length : 0"
                ) or 0
                if text_len < 10:
                    ws.close()
                    raise CDPError(
                        f"Selector {selector!r} not found and DOM text is "
                        f"too short after {timeout}s for {url}"
                    )

        return ws

    def _wait_load_event(self, ws: websocket.WebSocket, timeout: int = 15) -> bool:
        """
        Drain raw WebSocket messages waiting for Page.loadEventFired.

        Does NOT use cdp_send (which only returns matching IDs); the load
        event has no ID and would otherwise be discarded.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            ws.settimeout(min(deadline - time.time(), 5.0))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            try:
                msg = json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                continue
            if msg.get("method") == "Page.loadEventFired":
                return True
        return False

    def _wait_ready_state(self, ws: websocket.WebSocket, timeout: int = 15) -> bool:
        """Poll document.readyState until interactive/complete."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                state = self.cdp_js(
                    ws, "document.readyState"
                )
            except Exception:
                state = None
            if state in ("interactive", "complete"):
                return True
            time.sleep(0.3)
        return False

    def wait_for_selector(self, ws: websocket.WebSocket, selector: str,
                          timeout: int = 15) -> bool:
        """
        Poll the DOM for a selector to appear. Returns True when found.
        Used for SPA sites (Gmail, Zalo, Facebook) where content renders
        after the load event.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.cdp_js(ws, f"!!document.querySelector({json.dumps(selector)})")
            if found:
                return True
            time.sleep(0.5)
        return False

    def read(self, url: str, wait: int = 15,
             selector: Optional[str] = None) -> Dict[str, Any]:
        """
        Read content from a URL using the reliable tab lifecycle.

        Args:
            url: URL to read
            wait: Max seconds for load event + selector wait
            selector: Optional CSS selector to wait for (SPA content)

        Returns:
            Dictionary with page content
        """
        ws = self._prepare_tab(url, timeout=wait, selector=selector,
                               reuse_existing=False)
        try:
            content = self.cdp_js(ws, """
                JSON.stringify({
                    title: document.title,
                    url: window.location.href,
                    text: document.body ? document.body.innerText : '',
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
                   wait: int = 15, quality: int = 80) -> str:
        """
        Take a screenshot of a URL using the same lifecycle as read().

        Args:
            url: URL to screenshot
            output: Output file path. Format is chosen from the extension:
                    .jpg/.jpeg -> JPEG (uses `quality`), .png -> PNG.
            wait: Max seconds for page load
            quality: JPEG quality (1-100), ignored for PNG

        Returns:
            Path to saved screenshot
        """
        import os.path as _osp
        ext = _osp.splitext(output)[1].lower()
        is_png = ext in (".png",)
        capture_format = "png" if is_png else "jpeg"

        ws = self._prepare_tab(url, timeout=wait, reuse_existing=False)
        try:
            params = {"format": capture_format}
            if not is_png:
                params["quality"] = quality
            result = self.cdp_send(ws, "Page.captureScreenshot", params, timeout=15)

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
            search: Search query (optional, URL-encoded automatically)

        Returns:
            Dictionary with Gmail content
        """
        from urllib.parse import quote
        if search:
            url = f"https://mail.google.com/mail/u/0/#search/{quote(search, safe='')}"
        else:
            url = "https://mail.google.com/mail/u/0/#inbox"

        # Gmail is an SPA: wait for its main content selector, fall back to DOM.
        return self.read(url, wait=15, selector='div[role="main"]')

    def read_zalo(self) -> Dict[str, Any]:
        """Read Zalo messages (SPA: wait for app mount)."""
        return self.read("https://chat.zalo.me/", wait=15, selector="#app")

    def read_facebook(self) -> Dict[str, Any]:
        """Read Facebook (SPA: wait for main content)."""
        return self.read("https://www.facebook.com/", wait=15,
                         selector='[role="main"]')

    def _get_tab_ws(self, tab_id: str) -> str:
        """Get WebSocket URL for a specific tab."""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get("id") == tab_id:
                return tab.get("webSocketDebuggerUrl", "")
        raise TabNotFoundError(f"Tab {tab_id} not found")


__all__ = ["ChromeReader", "CDPError", "TabNotFoundError"]
