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
from collections import deque
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

    def _get_event_queue(self, ws: websocket.WebSocket) -> "deque":
        """Per-connection backlog of CDP events (messages without an id).

        cdp_send() only returns responses whose id matches; events such as
        Page.loadEventFired would otherwise be discarded. We buffer them here
        so the load-wait loop can drain them without racing the
        response-matching loop of an in-flight cdp_send().
        """
        if not hasattr(ws, "_cdp_event_queue"):
            ws._cdp_event_queue = deque()
        return ws._cdp_event_queue

    def cdp_send(self, ws: websocket.WebSocket, method: str,
                 params: Optional[Dict] = None, timeout: float = 10) -> Dict:
        """
        Send CDP command with auto-increment ID and drain loop.

        Fixes the id-collision bug: old code used hardcoded id=1,2,3
        which broke when Chrome sent events between send/recv. Events
        (messages without a matching id) are buffered in the per-connection
        event queue instead of being discarded.
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

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ws.settimeout(min(deadline - time.monotonic(), 5.0))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise CDPError(f"CDP error: {msg['error']}")
                return msg.get("result", {})
            # No matching id → it's an event; buffer it for waiters.
            if msg.get("method"):
                self._get_event_queue(ws).append(msg)

        raise CDPError(f"CDP method {method} timed out after {timeout}s")

    def cdp_js(self, ws: websocket.WebSocket, expression: str,
               timeout: float = 10) -> Any:
        """Evaluate JS and return primitive value."""
        result = self.cdp_send(
            ws,
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
            timeout=timeout,
        )
        if result.get("exceptionDetails"):
            raise CDPError(f"JS exception: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def read_text(self, ws: websocket.WebSocket, max_chars: int = 4000,
                  timeout: float = 10) -> Dict[str, Any]:
        """Read document.body.innerText, truncated INSIDE the browser before
        the JSON leaves via CDP (reduces WebSocket payload, serialization cost
        and Python memory on large pages).

        Args:
            ws: An open tab WebSocket (Page + Runtime already enabled).
            max_chars: Max characters to keep. Must be a positive int.
            timeout: Per-evaluate bound.

        Returns:
            {"text": str, "textLength": int, "truncated": bool}

        Raises:
            TypeError: if max_chars is not an int (bool is rejected).
            ValueError: if max_chars < 1.
        """
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise TypeError("max_chars must be an integer")
        if max_chars < 1:
            raise ValueError("max_chars must be > 0")
        expr = (
            "(() => {"
            f"  const maxChars = {max_chars};"
            "  const raw = document.body ? document.body.innerText : '';"
            "  return JSON.stringify({"
            "    text: raw.slice(0, maxChars),"
            "    textLength: raw.length,"
            "    truncated: raw.length > maxChars"
            "  });"
            "})()"
        )
        raw = self.cdp_js(ws, expr, timeout=timeout)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                return {
                    "text": raw[:max_chars],
                    "textLength": len(raw),
                    "truncated": len(raw) > max_chars,
                }
        return raw

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

    def _drain_old_events(self, ws: websocket.WebSocket) -> None:
        """Drop stale buffered events (e.g. from about:blank) before navigating
        a fresh URL, so a leftover load event cannot satisfy the next wait."""
        queue = self._get_event_queue(ws)
        queue.clear()

    def _wait_navigation_ready(self, ws: websocket.WebSocket,
                               nav_frame: Optional[str],
                               nav_loader: Optional[str],
                               timeout: float = 15) -> bool:
        """Wait for navigation completion via lifecycle events, correlated by
        frameId + loaderId (cross-document) or navigatedWithinDocument
        (same-document / fragment / History API).

        Falls back to the legacy _wait_load_event when lifecycle events were
        not enabled (older protocol) or produced no events.

        Uses a single overall deadline (no stacked timeouts).
        """
        deadline = time.monotonic() + timeout
        saw_lifecycle = False
        queue = self._get_event_queue(ws)
        # Also inspect already-buffered events first.
        while queue:
            msg = queue.popleft()
            method = msg.get("method")
            if not method:
                continue
            params = msg.get("params", {})
            if method == "Page.lifecycleEvent":
                saw_lifecycle = True
                if params.get("frameId") != nav_frame:
                    continue
                if nav_loader and params.get("loaderId") != nav_loader:
                    continue
                if params.get("name") in ("DOMContentLoaded", "load"):
                    return True
            elif method == "Page.navigatedWithinDocument":
                if params.get("frameId") == nav_frame:
                    return True
            elif method == "Page.loadEventFired":
                # Legacy fallback: a plain load event still indicates the page
                # finished loading. Accept it (lifecycle correlation is best
                # effort; loadEventFired is the pre-lifecycle signal).
                return True
        while time.monotonic() < deadline:
            ws.settimeout(min(deadline - time.monotonic(), 5.0))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            try:
                msg = json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                continue
            method = msg.get("method")
            if not method:
                continue
            params = msg.get("params", {})
            if method == "Page.lifecycleEvent":
                saw_lifecycle = True
                if params.get("frameId") != nav_frame:
                    continue
                if nav_loader and params.get("loaderId") != nav_loader:
                    continue
                if params.get("name") in ("DOMContentLoaded", "load"):
                    return True
            elif method == "Page.navigatedWithinDocument":
                if params.get("frameId") == nav_frame:
                    return True
            elif method == "Page.loadEventFired":
                # Legacy fallback: a plain load event still indicates the page
                # finished loading. Accept it (lifecycle correlation is best
                # effort; loadEventFired is the pre-lifecycle signal).
                return True
        if not saw_lifecycle:
            return self._wait_load_event(ws, timeout=max(0.1, deadline - time.monotonic()))
        return False

    def _prepare_tab(self, url: str, timeout: int = 15,
                     selector: Optional[str] = None,
                     reuse_existing: bool = False) -> websocket.WebSocket:
        """
        Robust tab lifecycle (core reliability primitive).

        Flow:
          1. Reuse an existing matching tab OR create a new one on about:blank.
          2. Connect the tab WebSocket, enable Page + Runtime events.
          3. If a new tab, enable lifecycle events, drain stale events, then
             navigate exactly ONCE via Page.navigate.
          4. Wait for navigation completion correlated by frameId + loaderId
             (Page.lifecycleEvent) or same-document navigation
             (Page.navigatedWithinDocument). Legacy loadEventFired fallback
             when lifecycle events are unavailable.
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
        ws._target_id = tab_id  # remember for cleanup (close tab after read)
        ws._owns_target = True  # only close tabs we created
        deadline = time.monotonic() + timeout

        def remaining():
            return max(0.0, deadline - time.monotonic())

        try:
            # 2. Enable events BEFORE navigating
            self.cdp_send(ws, "Page.enable", timeout=min(5, remaining()))
            self.cdp_send(ws, "Runtime.enable", timeout=min(5, remaining()))
            # B2: enable lifecycle events (best-effort; older protocol may lack it)
            try:
                self.cdp_send(ws, "Page.setLifecycleEventsEnabled",
                              {"enabled": True}, timeout=min(5, remaining()))
            except Exception:
                pass

            # 3. Navigate exactly once (no reload)
            if navigate:
                # B2: drain stale events from about:blank so they cannot satisfy
                # the upcoming navigation wait.
                self._drain_old_events(ws)
                nav = self.cdp_send(ws, "Page.navigate", {"url": url},
                                    timeout=min(20, remaining()))
                # B2: surface navigation failures / downloads immediately.
                if nav.get("errorText"):
                    raise CDPError(f"Navigation failed for {url}: {nav['errorText']}")
                if nav.get("isDownload"):
                    raise CDPError(f"Navigation for {url} became a download (isDownload=true)")
                nav_frame = nav.get("frameId")
                nav_loader = nav.get("loaderId")  # empty for same-document

                # 4. Wait for navigation completion (correlated, single deadline)
                ready = self._wait_navigation_ready(
                    ws, nav_frame, nav_loader, timeout=remaining())
                if not ready:
                    raise CDPError(
                        f"Navigation not ready for {url} within {timeout}s"
                    )
            else:
                # Reusing an existing tab that already shows the URL: just
                # confirm it is settled.
                if not self._wait_ready_state(ws, timeout=remaining()):
                    raise CDPError(
                        f"Page readyState never reached interactive/complete "
                        f"for {url} within {timeout}s"
                    )

            # 5. Poll readyState (must reach interactive/complete)
            if not self._wait_ready_state(ws, timeout=remaining()):
                raise CDPError(
                    f"Page readyState never reached interactive/complete "
                    f"for {url} within {timeout}s"
                )

            # 6. Optional selector wait (SPA), with DOM fallback on timeout
            if selector:
                found = self.wait_for_selector(ws, selector, timeout=remaining())
                if not found:
                    text_len = self.cdp_js(
                        ws, "document.body ? document.body.innerText.length : 0"
                    ) or 0
                    if text_len < 10:
                        raise CDPError(
                            f"Selector {selector!r} not found and DOM text is "
                            f"too short after {timeout}s for {url}"
                        )
        except Exception:
            self._close_tab(ws)
            ws.close()
            raise

        return ws

    def _wait_load_event(self, ws: websocket.WebSocket, timeout: float = 15) -> bool:
        """
        Wait for Page.loadEventFired, checking the buffered event queue first
        (events pushed there by cdp_send) before draining raw ws messages.

        This avoids the race where the load event arrives while cdp_send is
        draining responses for Page.navigate and would otherwise swallow it.
        """
        queue = self._get_event_queue(ws)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # 1. Drain any buffered events first
            while queue:
                msg = queue.popleft()
                if msg.get("method") == "Page.loadEventFired":
                    return True
            # 2. Then read live messages
            ws.settimeout(min(deadline - time.monotonic(), 5.0))
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
            # non-load events buffered for other waiters
            if msg.get("method"):
                queue.append(msg)
        # Final drain of buffered events before giving up
        while queue:
            if queue.popleft().get("method") == "Page.loadEventFired":
                return True
        return False

    def _wait_ready_state(self, ws: websocket.WebSocket, timeout: float = 15) -> bool:
        """Poll document.readyState until interactive/complete.

        Uses the supplied `timeout` as an overall budget; each Runtime.evaluate
        gets at most min(2.0, remaining) so a hung evaluate cannot blow the
        overall deadline.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            left = max(0.0, deadline - time.monotonic())
            if left <= 0:
                return False
            try:
                state = self.cdp_js(
                    ws, "document.readyState", timeout=min(2.0, left)
                )
            except Exception:
                state = None
            if state in ("interactive", "complete"):
                return True
            time.sleep(0.3)
        return False

    def wait_for_selector(self, ws: websocket.WebSocket, selector: str,
                          timeout: float = 15) -> bool:
        """
        Poll the DOM for a selector to appear. Returns True when found.
        Used for SPA sites (Gmail, Zalo, Facebook) where content renders
        after the load event. Each evaluate is bounded by min(2.0, remaining).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            left = max(0.0, deadline - time.monotonic())
            if left <= 0:
                return False
            found = self.cdp_js(
                ws, f"!!document.querySelector({json.dumps(selector)})",
                timeout=min(2.0, left),
            )
            if found:
                return True
            time.sleep(0.5)
        return False

    def _close_tab(self, ws: websocket.WebSocket) -> None:
        """Close the tab we opened (best-effort) to avoid target buildup."""
        target_id = getattr(ws, "_target_id", None)
        if target_id:
            try:
                browser_ws = self._get_json("/json/version").get(
                    "webSocketDebuggerUrl", "")
                if browser_ws:
                    bw = self._connect(browser_ws, timeout=5)
                    try:
                        self.cdp_send(bw, "Target.closeTarget",
                                      {"targetId": target_id}, timeout=5)
                    finally:
                        bw.close()
            except Exception:
                pass

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
            self._close_tab(ws)
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
            self._close_tab(ws)
            ws.close()

        raise CDPError("Failed to take screenshot")

    def read_gmail(self, search: str = "", wait: int = 15) -> Dict[str, Any]:
        """
        Read Gmail inbox.

        Args:
            search: Search query (optional, URL-encoded automatically)
            wait: Max seconds for load + selector wait

        Returns:
            Dictionary with Gmail content
        """
        from urllib.parse import quote
        if search:
            url = f"https://mail.google.com/mail/u/0/#search/{quote(search, safe='')}"
        else:
            url = "https://mail.google.com/mail/u/0/#inbox"

        # Gmail is an SPA: wait for its main content selector, fall back to DOM.
        return self.read(url, wait=wait, selector='div[role="main"]')

    def read_zalo(self, wait: int = 15) -> Dict[str, Any]:
        """Read Zalo messages (SPA: wait for app mount)."""
        return self.read("https://chat.zalo.me/", wait=wait, selector="#app")

    def read_facebook(self, wait: int = 15) -> Dict[str, Any]:
        """Read Facebook (SPA: wait for main content)."""
        return self.read("https://www.facebook.com/", wait=wait,
                         selector='[role="main"]')

    def _get_tab_ws(self, tab_id: str) -> str:
        """Get WebSocket URL for a specific tab."""
        tabs = self.get_tabs()
        for tab in tabs:
            if tab.get("id") == tab_id:
                return tab.get("webSocketDebuggerUrl", "")
        raise TabNotFoundError(f"Tab {tab_id} not found")


__all__ = ["ChromeReader", "CDPError", "TabNotFoundError"]
