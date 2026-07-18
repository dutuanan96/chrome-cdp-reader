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
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Iterator
from urllib.request import urlopen
from urllib.error import URLError

import websocket

from chrome_cdp_reader.errors import (
    ChromeCDPReaderError,
    ConnectionError,
    DownloadNavigationError,
    EvaluationError,
    ExtractionError,
    InvalidInputError,
    NavigationError,
    NavigationTimeoutError,
    TargetError,
    UnsupportedMethodError,
)

from chrome_cdp_reader.models import TargetHandle
from chrome_cdp_reader.deadlines import Deadline

logger = logging.getLogger("chrome_cdp_reader")
if os.environ.get("CRC_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)


# Backward compatibility: keep the old names importable from bridge.
# CDPError = ChromeCDPReaderError so `except CDPError` still works everywhere.
CDPError = ChromeCDPReaderError
TabNotFoundError = TargetError


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
        self._owned_target_ids = set()  # targets we created, for stale cleanup
        # Confined root for screenshot output. Defaults to CWD but is resolved
        # to a realpath so symlink/junction escapes are blocked (B4/R4).
        self.screenshot_root: Optional[str] = None

    def _get_json(self, endpoint: str, *, timeout: float = 5.0) -> Dict[str, Any]:
        """Fetch JSON from CDP HTTP endpoint."""
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        url = f"{self.cdp_url}{endpoint}"
        try:
            with urlopen(url, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except URLError as e:
            raise ConnectionError(
                f"Cannot connect to Chrome at {self.cdp_url}. "
                f"Make sure Chrome is running with --remote-debugging-port=9222. "
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

    def get_tabs(self, *, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Get list of open tabs."""
        return self._get_json("/json/list", timeout=timeout)

    def find_tab(self, url_fragment: str) -> Optional[Dict[str, Any]]:
        """Find a tab by URL fragment."""
        for tab in self.get_tabs():
            if url_fragment in tab.get("url", ""):
                return tab
        return None

    def _connect(self, ws_url: str, timeout: float = 15) -> websocket.WebSocket:
        """
        Connect to a WebSocket URL.

        suppress_origin=True: websocket-client sends an `Origin` header by
        default, which Chromium 147+ rejects (403) unless allowlisted. A
        non-browser CDP client should suppress it — no --remote-allow-origins
        flag needed, and it works for localhost / 127.0.0.1 / IPv6 alike.
        """
        try:
            return websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        except websocket.WebSocketException as exc:
            raise ConnectionError(f"Cannot connect to {ws_url}: {exc}") from exc
        except OSError as exc:
            raise ConnectionError(f"Cannot connect to {ws_url}: {exc}") from exc

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

        Error taxonomy (method-aware, B2/R5):
          - ws.send / socket failure        -> ConnectionError
          - malformed (non-JSON) response    -> ExtractionError
          - Runtime.evaluate error/timeout   -> EvaluationError
          - Page.navigate error/timeout      -> NavigationError / NavigationTimeoutError
          - Target.* / Page.close error/timeout -> TargetError
          - any other method error/timeout   -> EvaluationError (generic)
        """
        if not hasattr(ws, '_cdp_msg_id'):
            ws._cdp_msg_id = 0
        ws._cdp_msg_id += 1
        msg_id = ws._cdp_msg_id

        try:
            ws.send(json.dumps({
                "id": msg_id,
                "method": method,
                "params": params or {}
            }))
        except websocket.WebSocketException as exc:
            raise ConnectionError(f"CDP send failed on {method}: {exc}") from exc
        logger.debug("CDP send id=%s method=%s", msg_id, method)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ws.settimeout(min(deadline - time.monotonic(), 5.0))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketException as exc:
                raise ConnectionError(f"CDP socket error on {method}: {exc}") from exc
            try:
                msg = json.loads(raw)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ExtractionError(
                    f"malformed CDP response on {method}: {exc}") from exc
            if msg.get("id") == msg_id:
                if "error" in msg:
                    err = msg["error"]
                    text = err.get("message", err)
                    code = err.get("code")
                    # Protocol-aware: -32601 = method not found. Raise a typed
                    # UnsupportedMethodError (carries the code) so callers can
                    # decide on a safe fallback without guessing from text.
                    if code == -32601:
                        raise UnsupportedMethodError(
                            f"CDP method {method} not supported: {text}")
                    # Method-aware error taxonomy (B2/R5).
                    if method == "Runtime.evaluate":
                        raise EvaluationError(f"CDP error on {method}: {text}")
                    if method == "Page.navigate":
                        raise NavigationError(f"CDP error on {method}: {text}")
                    if method in ("Target.createTarget", "Target.attachToTarget",
                                  "Target.closeTarget", "Target.attachToBrowserTarget",
                                  "Page.close"):
                        raise TargetError(f"CDP error on {method}: {text}")
                    # Fallback for any other method.
                    raise EvaluationError(f"CDP error on {method}: {text}")
                return msg.get("result", {})
            # No matching id → it's an event; buffer it for waiters.
            if msg.get("method"):
                self._get_event_queue(ws).append(msg)

        # Timed out waiting for the response.
        if method == "Runtime.evaluate":
            raise EvaluationError(f"CDP method {method} timed out after {timeout}s")
        if method == "Page.navigate":
            raise NavigationTimeoutError(f"CDP method {method} timed out after {timeout}s")
        if method in ("Target.createTarget", "Target.attachToTarget",
                      "Target.closeTarget", "Target.attachToBrowserTarget", "Page.close"):
            raise TargetError(f"CDP method {method} timed out after {timeout}s")
        raise EvaluationError(f"CDP method {method} timed out after {timeout}s")

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
            raise EvaluationError(f"JS exception: {result['exceptionDetails']}")
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

    def create_tab(self, url: str = "about:blank", *, timeout: float = 15) -> str:
        """
        Create a new tab. The URL is validated at this boundary so callers
        cannot open dangerous schemes (file/javascript/data/...).

        Args:
            url: Initial URL. Must be http/https/about:blank (validated).
            timeout: Per-step budget (connect + createTarget). Bounded by the
                caller's overall Deadline via remaining().

        Returns:
            Target ID of the new tab
        """
        # B4: validate before Target.createTarget — dangerous schemes are
        # blocked here, not just in _prepare_tab / CLI.
        from chrome_cdp_reader.url_validation import validate_scheme
        validate_scheme(url)

        # R5: a single shared Deadline for the whole create_tab operation.
        # Each step consumes from the same remaining budget, so the total
        # time cannot exceed `timeout` even when steps run sequentially.
        budget = Deadline(timeout)
        version = self._get_json("/json/version", timeout=budget.bounded(5.0))
        browser_ws = version.get("webSocketDebuggerUrl", "")

        if not browser_ws:
            raise ConnectionError("Cannot get WebSocket URL from Chrome")

        ws = self._connect(browser_ws, timeout=budget.bounded(5.0))
        try:
            try:
                result = self.cdp_send(
                    ws, "Target.createTarget", {"url": url},
                    timeout=budget.bounded(20.0))
            except EvaluationError as exc:
                raise TargetError(f"Failed to create tab: {exc}") from exc
        finally:
            ws.close()

        target_id = result.get("targetId", "")
        if not target_id:
            raise TargetError(f"Failed to create tab: {result}")

        return target_id

    def _drain_old_events(self, ws: websocket.WebSocket) -> None:
        """Drop stale buffered events (e.g. from about:blank) before navigating
        a fresh URL, so a leftover load event cannot satisfy the next wait."""
        queue = self._get_event_queue(ws)
        queue.clear()

    def _wait_navigation_ready(self, ws: websocket.WebSocket,
                               nav_frame: Optional[str],
                               nav_loader: Optional[str],
                               timeout: float = 15,
                               lifecycle_enabled: bool = False) -> bool:
        """Wait for navigation completion via lifecycle events, correlated by
        frameId + loaderId (cross-document) or navigatedWithinDocument
        (same-document / fragment / History API).

        STRICT correlation: when lifecycle events ARE enabled (modern Chrome),
        only a matching lifecycle/within-document event counts. A stray
        ``Page.loadEventFired`` from a previous document is NOT accepted.

        The legacy ``Page.loadEventFired`` fallback is used ONLY when lifecycle
        events were genuinely unavailable (older protocol) — i.e.
        ``lifecycle_enabled`` is False.

        Uses a single overall deadline (no stacked timeouts).
        """
        if timeout <= 0:
            raise NavigationTimeoutError("Navigation deadline already expired")

        deadline = time.monotonic() + timeout
        saw_lifecycle = False
        queue = self._get_event_queue(ws)

        def _accept(msg) -> bool:
            nonlocal saw_lifecycle
            method = msg.get("method")
            if not method:
                return False
            params = msg.get("params", {})
            if method == "Page.lifecycleEvent":
                saw_lifecycle = True
                # Lifecycle only counts for cross-document (nav_loader set).
                if not nav_loader:
                    return False
                if params.get("frameId") != nav_frame:
                    return False
                if params.get("loaderId") != nav_loader:
                    return False
                if params.get("name") in ("DOMContentLoaded", "load"):
                    return True
                return False
            if method == "Page.navigatedWithinDocument":
                # Same-document (fragment/History) navigation: only valid when
                # this is a same-document wait (nav_loader empty).
                return (not nav_loader) and params.get("frameId") == nav_frame
            if method == "Page.loadEventFired":
                # Strict: only accept as fallback when lifecycle was OFF.
                return not lifecycle_enabled
            return False

        # Drain already-buffered events first.
        while queue:
            msg = queue.popleft()
            if _accept(msg):
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
            if _accept(msg):
                return True

        # Legacy protocol: lifecycle never arrived at all → try plain loadEvent.
        if not saw_lifecycle and not lifecycle_enabled:
            return self._wait_load_event(ws, timeout=max(0.1, deadline - time.monotonic()))
        return False

    def _find_reusable_tab(
        self, url: str, *, url_prefix: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[Dict[str, Any]]:
        """Find a reusable page target by exact URL or URL prefix.

        Only `type == "page"` targets are considered. A prefix match lets
        SPA URLs (Gmail changes its `#fragment` constantly) reuse one tab
        instead of spawning a new one on every navigation.
        """
        for tab in self.get_tabs(timeout=timeout):
            if tab.get("type") != "page":
                continue
            tab_url = tab.get("url", "")
            if url_prefix is not None:
                if tab_url.startswith(url_prefix):
                    return tab
            elif url in tab_url:
                return tab
        return None

    def _prepare_tab(self, url: str, timeout: int = 15,
                     selector: Optional[str] = None,
                     reuse_existing: bool = False,
                     reuse_url_prefix: Optional[str] = None) -> websocket.WebSocket:
        """
        Robust tab lifecycle (core reliability primitive).

        SECURITY: the URL is validated at this core boundary so every caller
        (read / screenshot / open_tab / CLI) is protected, not just one CLI
        command. Dangerous schemes (file/javascript/data/...) are rejected
        before any navigation.

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
        # 0. Validate the URL scheme at the core boundary (B1/security).
        from chrome_cdp_reader.url_validation import validate_scheme
        from chrome_cdp_reader.deadlines import Deadline
        from chrome_cdp_reader.models import TargetHandle
        validate_scheme(url)

        # B5: start the single Deadline BEFORE any tab lookup / create / connect
        # so the total operation (including those setup steps) is bounded.
        deadline = Deadline(timeout)
        remaining = deadline.remaining

        # 1. Tab selection
        created_target = False
        if reuse_existing:
            tab = self._find_reusable_tab(
                url, url_prefix=reuse_url_prefix, timeout=min(5, remaining()))
            if tab:
                ws_url = tab.get("webSocketDebuggerUrl", "")
                tab_id = tab.get("id", "")
                navigate = tab.get("url", "") != url
            else:
                tab_id = self.create_tab("about:blank", timeout=remaining())
                ws_url = self._get_tab_ws(tab_id, timeout=min(5, remaining()))
                created_target = True
                navigate = True
        else:
            tab_id = self.create_tab("about:blank", timeout=remaining())
            ws_url = self._get_tab_ws(tab_id, timeout=min(5, remaining()))
            created_target = True
            navigate = True

        ws = None
        try:
            ws = self._connect(ws_url, timeout=min(5, remaining()))
        except Exception:
            # Gap: createTarget succeeded but connect failed. Close by id so
            # the about:blank tab is not leaked.
            if created_target and tab_id:
                self._close_target_by_id(tab_id, timeout=2.0)
            raise

        # B2: explicit, typed ownership. Created tabs are owned=True; reused
        # user tabs are owned=False. This is the source of truth (no dynamic
        # _target_id / _owns_target attributes on the socket).
        ws._handle = TargetHandle(target_id=tab_id, owned=created_target)
        if created_target:
            self._owned_target_ids.add(tab_id)

        try:
            # 2. Enable events BEFORE navigating
            self.cdp_send(ws, "Page.enable", timeout=min(5, remaining()))
            self.cdp_send(ws, "Runtime.enable", timeout=min(5, remaining()))
            # B5: enable lifecycle events; remember whether it actually worked
            # so the wait loop can enforce STRICT correlation (a stray
            # loadEventFired is only accepted as a fallback when lifecycle
            # events were NOT available).
            lifecycle_enabled = False
            try:
                self.cdp_send(ws, "Page.setLifecycleEventsEnabled",
                              {"enabled": True}, timeout=min(5, remaining()))
                lifecycle_enabled = True
            except UnsupportedMethodError:
                # Protocol confirms the method is not implemented on this
                # target/Chrome version → safe to use the legacy
                # loadEventFired fallback. Any other error (ConnectionError,
                # timeout, malformed response, unexpected) propagates.
                lifecycle_enabled = False

            # 3. Navigate exactly once (no reload)
            if navigate:
                # B2: drain stale events from about:blank so they cannot satisfy
                # the upcoming navigation wait.
                self._drain_old_events(ws)
                nav = self.cdp_send(ws, "Page.navigate", {"url": url},
                                    timeout=min(20, remaining()))
                # B2: surface navigation failures / downloads immediately.
                if nav.get("errorText"):
                    raise NavigationError(f"Navigation failed for {url}: {nav['errorText']}")
                if nav.get("isDownload"):
                    raise DownloadNavigationError(
                        f"Navigation for {url} became a download (isDownload=true)")
                nav_frame = nav.get("frameId")
                nav_loader = nav.get("loaderId")  # empty for same-document

                # 4. Wait for navigation completion (correlated, single deadline)
                ready = self._wait_navigation_ready(
                    ws, nav_frame, nav_loader,
                    timeout=remaining(), lifecycle_enabled=lifecycle_enabled)
                if not ready:
                    raise NavigationTimeoutError(
                        f"Navigation not ready for {url} within {timeout}s"
                    )
            else:
                # Reusing an existing tab that already shows the URL: just
                # confirm it is settled.
                if not self._wait_ready_state(ws, timeout=remaining()):
                    raise NavigationTimeoutError(
                        f"Page readyState never reached interactive/complete "
                        f"for {url} within {timeout}s"
                    )

            # 5. Poll readyState (must reach interactive/complete)
            if not self._wait_ready_state(ws, timeout=remaining()):
                raise NavigationTimeoutError(
                    f"Page readyState never reached interactive/complete "
                    f"for {url} within {timeout}s"
                )

            # 6. Optional selector wait (SPA), with DOM fallback on timeout
            if selector:
                found = self.wait_for_selector(ws, selector, timeout=remaining())
                if not found:
                    text_len = self.cdp_js(
                        ws, "document.body ? document.body.innerText.length : 0",
                        timeout=min(2, remaining()),
                    ) or 0
                    if text_len < 10:
                        raise NavigationTimeoutError(
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

    def _target_exists(self, target_id: str, *, timeout: float = 0.8) -> bool:
        """Return True if a target with target_id is still listed by Chrome."""
        try:
            targets = self._get_json("/json/list", timeout=timeout)
        except Exception:
            # Unknown -> treat as still present so we never claim false success.
            return True
        return any(
            isinstance(t, dict) and t.get("id") == target_id for t in targets
        )

    def _close_target_by_id(self, target_id: str, *, timeout: float = 2.0) -> bool:
        """Close a target by id WITHOUT a page WebSocket (for the create->connect
        gap, or stale cleanup). Uses Target.closeTarget over a browser WebSocket.
        """
        if not target_id:
            return False
        try:
            browser_ws = self._get_json("/json/version", timeout=min(timeout, 1.0)
                                        ).get("webSocketDebuggerUrl", "")
            if not browser_ws:
                return False
            bw = self._connect(browser_ws, timeout=max(0.5, timeout))
            try:
                self.cdp_send(bw, "Target.closeTarget",
                              {"targetId": target_id}, timeout=max(0.5, timeout))
            finally:
                bw.close()
            return True
        except Exception as exc:
            logger.debug("closeTarget by id failed for %s: %s", target_id, exc)
            return False

    def _close_tab(self, ws: websocket.WebSocket, *,
                   timeout: float = 3.0,
                   handle: Optional["TargetHandle"] = None) -> bool:
        """Close an OWNED page and verify it disappeared.

        Ownership is taken from the explicit ``TargetHandle`` (source of
        truth). A caller may pass ``handle``; otherwise it is read from
        ``ws._handle`` set by ``_prepare_tab``. Reused/user tabs
        (owned=False) are never closed.

        Args:
            ws: The tab WebSocket (used for Page.close).
            timeout: Max seconds for the close handshake.
            handle: Explicit ``TargetHandle``. If the resolved handle is not a
                ``TargetHandle`` instance, it is rejected (wrong metadata
                type) rather than silently trusted.

        Returns True if the target is gone (or was never owned), False on failure.
        Logs a warning with the target id when closure fails (never silent).
        """
        from chrome_cdp_reader.models import TargetHandle
        handle = handle or getattr(ws, "_handle", None)
        if not isinstance(handle, TargetHandle):
            logger.warning(
                "Cannot close tab: handle is not a TargetHandle (%r). "
                "Use open_tab() instead of manual create_tab/_connect.",
                type(handle).__name__,
            )
            return False
        target_id = handle.target_id
        owns = bool(handle.owned)

        if not target_id:
            logger.warning(
                "Cannot close tab: TargetHandle has no target_id."
            )
            return False
        if not owns:
            logger.debug("Leaving target %s open (not owned by this op).", target_id)
            return True
        if not self._target_exists(target_id, timeout=0.5):
            return True  # already gone

        # Step 1: graceful Page.close on the tab's own WebSocket.
        try:
            self.cdp_send(ws, "Page.close", timeout=min(0.8, max(0.1, timeout)))
        except Exception as exc:
            # Socket may close before the response arrives; not proof of failure.
            logger.debug("Page.close raised for %s: %s", target_id, exc)

        if not self._target_exists(target_id, timeout=0.5):
            return True

        # Step 2: fallback via browser WebSocket.
        if self._close_target_by_id(target_id, timeout=max(0.5, timeout)):
            if not self._target_exists(target_id, timeout=0.5):
                return True

        logger.warning("Target %s could not be closed within %.1fs.", target_id, timeout)
        return False

    def read(self, url: str, wait: int = 15,
             selector: Optional[str] = None, *,
             reuse_existing: bool = False,
             reuse_url_prefix: Optional[str] = None,
             close_after: bool = True,
             max_chars: int = 4000) -> Dict[str, Any]:
        """
        Read content from a URL using the reliable tab lifecycle.

        Args:
            url: URL to read
            wait: Max seconds for load event + selector wait
            selector: Optional CSS selector to wait for (SPA content)
            reuse_existing: Reuse an existing matching tab instead of opening
                a new one (generic read keeps this False by default).
            reuse_url_prefix: When reuse_existing, match by URL prefix (SPA
                URLs change their fragment, so exact match would reopen).
            close_after: Close the tab we opened after reading. A reused tab
                is never closed regardless of this flag.
            max_chars: Bound the returned text INSIDE the browser before it
                leaves via CDP (B3: no full innerText crosses the wire).

        Returns:
            Dictionary with page content, including ``textLength`` and
            ``truncated`` metadata.
        """
        ws = self._prepare_tab(url, timeout=wait, selector=selector,
                               reuse_existing=reuse_existing,
                               reuse_url_prefix=reuse_url_prefix)
        try:
            # B3: bounded text extraction happens in JS (bridge.read_text).
            text_info = self.read_text(ws, max_chars=max_chars)
            # Lightweight metadata (title/url/links) — links are sliced in JS.
            meta = self.cdp_js(ws, """
                JSON.stringify({
                    title: document.title,
                    url: window.location.href,
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
            meta = json.loads(meta) if meta else {}
            return {
                "title": meta.get("title", ""),
                "url": meta.get("url", ""),
                "text": text_info.get("text", ""),
                "textLength": text_info.get("textLength", 0),
                "truncated": text_info.get("truncated", False),
                "links": meta.get("links", []),
                "images": meta.get("images", []),
            }
        finally:
            if close_after:
                self._close_tab(ws)
            ws.close()

    @contextmanager
    def open_tab(self, url: str, *, timeout: int = 15,
                 selector: Optional[str] = None,
                 reuse_existing: bool = False,
                 reuse_url_prefix: Optional[str] = None,
                 close_after: bool = True) -> Iterator[Any]:
        """Open/reuse a page and guarantee cleanup on the normal path.

        - A target created by this op is closed when close_after=True.
        - A reused target is never closed by this manager.
        - close_after=False keeps a newly created managed target open
          (e.g. one persistent Gmail tab reused by later calls).

        Use this instead of manually calling create_tab()/_connect()/_close_tab().
        """
        ws = self._prepare_tab(
            url, timeout=timeout, selector=selector,
            reuse_existing=reuse_existing, reuse_url_prefix=reuse_url_prefix,
        )
        handle = getattr(ws, "_handle", None)
        owns_target = bool(handle.owned) if handle else False
        target_id = handle.target_id if handle else None
        try:
            yield ws
        finally:
            try:
                if close_after and owns_target and handle is not None:
                    # Pass the captured handle explicitly so cleanup uses the
                    # original ownership decision even if ws._handle is later
                    # mutated in the caller's context.
                    self._close_tab(ws, timeout=3.0, handle=handle)
            finally:
                try:
                    ws.close()
                except Exception:
                    logger.debug("Failed to close page WebSocket for %s", target_id)

    def cleanup_stale_tabs(self, *, stale_after: float = 60.0,
                           dry_run: bool = False) -> Dict[str, Any]:
        """Small stale-tab cleanup. Only closes about:blank targets that THIS
        package created but left behind (tracked in ``_owned_target_ids``), and
        only once their owner is gone / they are older than ``stale_after``.

        Does NOT close user tabs, does NOT close Gmail tabs, does NOT use a
        registry file or PID tracking.
        """
        if stale_after < 0:
            raise ValueError("stale_after must be non-negative")
        targets = {t.get("id"): t for t in self.get_tabs()
                   if isinstance(t, dict) and t.get("id")}
        report: Dict[str, Any] = {"closed": [], "wouldClose": [],
                                  "skipped": [], "errors": []}

        for target_id in list(self._owned_target_ids):
            if target_id not in targets:
                self._owned_target_ids.discard(target_id)
                continue
            item = targets[target_id]
            if item.get("type") != "page":
                self._owned_target_ids.discard(target_id)
                continue
            if item.get("url") != "about:blank":
                # Only about:blank leftovers are safe to auto-close.
                report["skipped"].append({"targetId": target_id,
                                          "reason": "not_about_blank"})
                continue
            if dry_run:
                report["wouldClose"].append(target_id)
                continue
            if self._close_target_by_id(target_id, timeout=1.5):
                if not self._target_exists(target_id, timeout=0.5):
                    self._owned_target_ids.discard(target_id)
                    report["closed"].append(target_id)
                else:
                    report["errors"].append({"targetId": target_id,
                                             "reason": "close_failed"})
            else:
                report["errors"].append({"targetId": target_id,
                                         "reason": "close_failed"})
        return report

    def screenshot(self, url: str, output: str = "screenshot.jpg",
                   wait: int = 15, quality: int = 80,
                   *, overwrite: bool = False,
                   return_metadata: bool = False) -> Any:
        """
        Take a screenshot of a URL using the same lifecycle as read().

        Args:
            url: URL to screenshot (validated at the core boundary).
            output: Output file path. ONLY .png, .jpg, .jpeg are accepted;
                    any other extension (e.g. .bmp) is rejected — we never
                    write a JPEG payload under a wrong extension.
            wait: Max seconds for page load.
            quality: JPEG quality (1-100), ignored for PNG. Must be a real int;
                     bool/str/float are rejected (InvalidInputError).
            overwrite: If False (default), the destination is created with a
                    no-replace (O_EXCL) mechanism — an existing file causes
                    FileExistsError -> InvalidInputError (no TOCTOU check-then-
                    create race). If True, a temp file + atomic rename is used.
            return_metadata: If True, return a metadata dict
                    {path, format, byteSize}. If False (default), return the
                    output path string — preserving the original pre-Phase-1
                    API for backward compatibility. The CLI uses
                    return_metadata=True.

        Returns:
            str path (default) or dict with path/format/byteSize.
        """
        import os
        from pathlib import Path
        import os.path as _osp

        # --- B6: strict quality validation (real int only) ---
        if isinstance(quality, bool) or not isinstance(quality, int):
            raise InvalidInputError("quality must be an integer 1-100")
        if not (1 <= quality <= 100):
            raise InvalidInputError("quality must be between 1 and 100")

        # --- B6: output extension allowlist ---
        ext = _osp.splitext(output)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            raise InvalidInputError(
                f"screenshot output must end with .png/.jpg/.jpeg, got {ext!r}")

        # --- B4: screenshot root confinement (realpath + commonpath) ---
        # Resolve both the configured root and the requested output to real
        # paths so symlink/junction escapes are blocked. The root is a dedicated
        # screenshot root (defaults to CWD), never an arbitrary trust anchor.
        root = Path(self.screenshot_root).resolve() if self.screenshot_root \
            else Path(os.getcwd()).resolve()
        abs_out = Path(output).resolve()
        try:
            abs_out.relative_to(root)
        except ValueError:
            raise InvalidInputError(
                f"output path escapes the allowed screenshot root {root}: "
                f"{output}")

        out_dir = abs_out.parent
        if out_dir and not out_dir.is_dir():
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise InvalidInputError(f"cannot create output directory: {e}")

        is_png = ext == ".png"
        capture_format = "png" if is_png else "jpeg"

        ws = self._prepare_tab(url, timeout=wait, reuse_existing=False)
        try:
            params: Dict[str, Any] = {"format": capture_format}
            if not is_png:
                params["quality"] = quality
            result = self.cdp_send(ws, "Page.captureScreenshot", params,
                                   timeout=min(15, wait))

            if "data" in result:
                img_data = base64.b64decode(result["data"])
                out_str = str(abs_out)
                if overwrite:
                    # Atomic temp + exclusive-create + rename.
                    tmp = out_str + f".{os.getpid()}.tmp"
                    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        with os.fdopen(fd, "wb") as f:
                            f.write(img_data)
                        os.replace(tmp, out_str)
                    except Exception:
                        if _osp.exists(tmp):
                            os.unlink(tmp)
                        raise
                else:
                    # No-replace: create the destination with O_EXCL directly.
                    # An existing file raises FileExistsError -> InvalidInputError
                    # (no check-then-create TOCTOU window).
                    try:
                        fd = os.open(out_str, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                     0o600)
                    except FileExistsError:
                        raise InvalidInputError(
                            f"output already exists (use overwrite=True): {output}")
                    with os.fdopen(fd, "wb") as f:
                        f.write(img_data)
                meta = {
                    "path": out_str,
                    "format": capture_format,
                    "byteSize": len(img_data),
                }
                return meta if return_metadata else out_str
        finally:
            self._close_tab(ws)
            ws.close()

        raise TargetError("Failed to take screenshot")

    def read_gmail(self, search: str = "", wait: int = 15,
                   max_chars: int = 4000) -> Dict[str, Any]:
        """
        Read Gmail inbox, reusing ONE persistent Gmail tab.

        Reuses an existing tab whose URL starts with
        ``https://mail.google.com/mail/`` (Gmail is an SPA and changes its
        ``#fragment`` constantly, so we match by prefix, not exact URL). If no
        such tab exists, one is created. The tab is intentionally kept open
        after reading so the next call reuses it — no tab buildup.

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
        # reuse_existing + prefix match keeps a single tab alive across calls;
        # close_after=False leaves that tab open for the next invocation.
        return self.read(
            url, wait=wait, selector='div[role="main"]',
            reuse_existing=True,
            reuse_url_prefix="https://mail.google.com/mail/",
            close_after=False,
            max_chars=max_chars,
        )

    def read_zalo(self, wait: int = 15, max_chars: int = 4000) -> Dict[str, Any]:
        """Read Zalo messages (SPA: wait for app mount)."""
        return self.read("https://chat.zalo.me/", wait=wait, selector="#app",
                        max_chars=max_chars)

    def read_facebook(self, wait: int = 15, max_chars: int = 4000) -> Dict[str, Any]:
        """Read Facebook (SPA: wait for main content)."""
        return self.read("https://www.facebook.com/", wait=wait,
                         selector='[role="main"]', max_chars=max_chars)

    def _get_tab_ws(self, tab_id: str, *, timeout: float = 5.0) -> str:
        """Get WebSocket URL for a specific tab."""
        tabs = self.get_tabs(timeout=timeout)
        for tab in tabs:
            if tab.get("id") == tab_id:
                return tab.get("webSocketDebuggerUrl", "")
        raise TargetError(f"Tab {tab_id} not found")


__all__ = ["ChromeReader", "CDPError", "TabNotFoundError"]
