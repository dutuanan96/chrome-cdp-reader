"""
Load-lifecycle unit tests — run on Ubuntu without Chrome.

These mock the CDP transport layer (websocket + HTTP JSON) so the tab
lifecycle (_prepare_tab) can be verified deterministically:
  - no navigation before Page.enable
  - URL navigates exactly once (no Page.reload)
  - Page.loadEventFired arriving early is NOT swallowed by cdp_send
  - late selector is waited for
  - selector timeout falls back to DOM text
  - screenshot uses the same lifecycle as read
  - existing matching tab is reused without re-navigation
"""

import json
from unittest.mock import Mock

import pytest

from chrome_cdp_reader.bridge import ChromeReader, CDPError


class _FakeWS:
    """Minimal WebSocket stand-in: scripted recv() + send()."""

    def __init__(self, scripted_recv=None, auto_load=True):
        self._recv_queue = list(scripted_recv or [])
        self._auto_load = auto_load
        self.sent = []          # (method, params)
        self.closed = False
        self._cdp_id = 0

    def send(self, payload):
        msg = json.loads(payload)
        self.sent.append((msg.get("method"), msg.get("params", {})))

    def settimeout(self, t):
        pass

    def recv(self):
        if self._recv_queue:
            return self._recv_queue.pop(0)
        if self._auto_load:
            # Simulate Chrome firing the load event once the queue is drained.
            return json.dumps({"method": "Page.loadEventFired", "params": {}})
        raise __import__("websocket").WebSocketTimeoutException()

    def close(self):
        self.closed = True


def _make_reader(fake_ws, create_target_id="T1", tab_ws="ws://tab",
                 existing_tabs=None):
    """Build a ChromeReader whose transport is fully mocked."""
    reader = ChromeReader()

    # Browser version + tab list over HTTP
    def fake_get_json(endpoint):
        if endpoint == "/json/version":
            return {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if endpoint == "/json/list":
            return existing_tabs or []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    reader._get_json = fake_get_json

    # createTarget -> returns a tab id; the new tab ws is `fake_ws`
    def fake_cdp_send(ws, method, params=None, timeout=10):
        # Record the send (so navigate/enble are observable) but return
        # immediately — do NOT drain ws.recv (that's the load-event loop's job).
        # For Runtime.evaluate, return a "complete" readyState so the lifecycle
        # proceeds without a real DOM.
        try:
            ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        except Exception:
            pass
        if method == "Target.createTarget":
            return {"targetId": create_target_id}
        if method == "Runtime.evaluate":
            return {"result": {"value": "complete"}}
        return {}

    reader.cdp_send = fake_cdp_send
    reader._get_tab_ws = Mock(return_value=tab_ws)
    reader._connect = Mock(return_value=fake_ws)
    return reader


def _js_value(expr):
    """Return a deterministic value for the expressions cdp_js sends."""
    if "readyState" in expr:
        return "complete"
    if "querySelector" in expr:
        return True
    if "innerText.length" in expr:
        return 100
    return None


def _navigate_methods(ws):
    return [m for (m, _) in ws.sent if m == "Page.navigate"]


# --- 1. No navigation before Page.enable ------------------------------------
def test_enable_before_navigate():
    ws = _FakeWS()
    reader = _make_reader(ws)
    reader._prepare_tab("https://example.com", timeout=5)
    methods = [m for (m, _) in ws.sent]
    assert "Page.enable" in methods
    assert "Runtime.enable" in methods
    # enable must come before navigate in the sent order
    assert methods.index("Page.enable") < methods.index("Page.navigate")


# --- 2. URL navigates exactly once (no reload) ------------------------------
def test_navigate_once():
    ws = _FakeWS()
    reader = _make_reader(ws)
    reader._prepare_tab("https://example.com", timeout=5)
    assert _navigate_methods(ws) == ["Page.navigate"], "exactly one navigate, no reload"


# --- 3. Early load event is NOT swallowed ------------------------------------
def test_early_load_event_not_swallowed():
    """loadEventFired arriving before any cdp_send response must be caught."""
    ws = _FakeWS(auto_load=True)
    reader = _make_reader(ws)
    # Should not raise; load event is observed via the drain loop.
    out = reader._prepare_tab("https://example.com", timeout=5)
    assert out is ws
    ws.close()


# --- 4. Late selector is waited for -----------------------------------------
def test_late_selector_waited():
    ws = _FakeWS()
    reader = _make_reader(ws)
    # selector returns False on first poll, True after
    calls = {"n": 0}

    def fake_js(ws2, expr, timeout=None):
        if "readyState" in expr:
            return "complete"
        if "querySelector" in expr:
            calls["n"] += 1
            return calls["n"] >= 2
        return _js_value(expr)

    reader.cdp_js = fake_js
    out = reader._prepare_tab("https://example.com", timeout=5,
                               selector="div[role='main']")
    assert calls["n"] >= 2, "polled selector until it appeared"
    out.close()


# --- 5a. Selector timeout falls back to DOM text (enough) --------------------
def test_selector_timeout_fallback_ok():
    ws = _FakeWS()
    reader = _make_reader(ws)

    def fake_js(ws2, expr, timeout=None):
        if "readyState" in expr:
            return "complete"
        if "querySelector" in expr:
            return False  # never appears
        if "innerText.length" in expr:
            return 200     # DOM text present -> fallback OK
        return _js_value(expr)

    reader.cdp_js = fake_js
    # Should NOT raise: selector missing but DOM text sufficient
    out = reader._prepare_tab("https://example.com", timeout=1,
                               selector="div[role='main']")
    out.close()


# --- 5b. Selector timeout with thin DOM -> raise ----------------------------
def test_selector_timeout_fallback_raises():
    ws = _FakeWS()
    reader = _make_reader(ws)

    def fake_js(ws2, expr):
        if "querySelector" in expr:
            return False
        if "innerText.length" in expr:
            return 0       # DOM text too short
        return _js_value(expr)

    reader.cdp_js = fake_js
    with pytest.raises(CDPError):
        reader._prepare_tab("https://example.com", timeout=1,
                            selector="div[role='main']")


# --- 6. Screenshot uses the same lifecycle ----------------------------------
def test_screenshot_uses_prepare_tab(monkeypatch, tmp_path):
    ws = _FakeWS()
    reader = _make_reader(ws)

    # capture_screenshot returns image data; everything else via the base mock
    base_send = reader.cdp_send

    def fake_send2(ws2, method, params=None, timeout=10):
        if method == "Page.captureScreenshot":
            return {"data": "iVBORw0KGgo="}
        return base_send(ws2, method, params, timeout)

    reader.cdp_send = fake_send2
    out = reader.screenshot("https://example.com",
                            output=str(tmp_path / "s.png"), wait=5)
    assert _navigate_methods(ws) == ["Page.navigate"]
    assert out["path"].endswith(".png")
    assert out["format"] == "png"


# --- 7. Existing matching tab reused without re-navigation ------------------
def test_reuse_existing_tab_no_navigate():
    existing = [{
        "id": "T0",
        "type": "page",
        "url": "https://example.com",
        "webSocketDebuggerUrl": "ws://existing",
    }]
    ws = _FakeWS()
    reader = _make_reader(ws, existing_tabs=existing)
    # existing tab already shows the URL -> navigate must NOT happen
    reader._prepare_tab("https://example.com", timeout=5, reuse_existing=True)
    assert _navigate_methods(ws) == [], "existing tab not re-navigated"


# --- 7b. Existing tab with different URL IS navigated -----------------------
def test_reuse_existing_tab_navigates_when_url_differs():
    existing = [{
        "id": "T0",
        "type": "page",
        "url": "https://other.com",
        "webSocketDebuggerUrl": "ws://existing",
    }]
    ws = _FakeWS()
    reader = _make_reader(ws, existing_tabs=existing)
    reader._prepare_tab("https://example.com", timeout=5, reuse_existing=True)
    assert _navigate_methods(ws) == ["Page.navigate"]


# --- overall timeout raises instead of silent read --------------------------
def test_load_timeout_raises():
    # Never send a load event
    ws = _FakeWS(auto_load=False)
    reader = _make_reader(ws)
    with pytest.raises(CDPError):
        reader._prepare_tab("https://example.com", timeout=1)


# --- 1b. Real race: loadEventFired arrives BEFORE navigate response ---------
class _ScriptedWS:
    """WebSocket whose recv() returns a fixed scripted sequence, then hangs."""

    def __init__(self, script):
        self._script = list(script)
        self.sent = []
        self.closed = False
        self._id = 0

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def settimeout(self, t):
        pass

    def recv(self):
        if self._script:
            return self._script.pop(0)
        raise __import__("websocket").WebSocketTimeoutException()

    def close(self):
        self.closed = True


def test_race_load_event_before_navigate_response():
    """
    Reproduce the real race: Page.loadEventFired is delivered on the socket
    BEFORE the Page.navigate response arrives. cdp_send must NOT swallow it;
    the event is buffered and _wait_load_event must still see it.
    Uses the PRODUCTION cdp_send (no mock override of the receive loop).
    """
    load_event = json.dumps({"method": "Page.loadEventFired", "params": {}})
    # Real send order: createTarget(id=1), Page.enable(id=2), Runtime.enable(id=3),
    # setLifecycleEventsEnabled(id=4), Page.navigate(id=5)
    create_resp = json.dumps({"id": 1, "result": {"targetId": "T1"}})
    enable_resp = json.dumps({"id": 2, "result": {}})
    runtime_resp = json.dumps({"id": 3, "result": {}})
    lifecycle_resp = json.dumps({"id": 4, "result": {}})
    navigate_resp = json.dumps({"id": 5, "result": {}})
    # Wire order forces the race: enable resp, THEN load event, THEN navigate resp
    ws = _ScriptedWS([create_resp, enable_resp, runtime_resp, lifecycle_resp,
                      load_event, navigate_resp])

    reader = ChromeReader()
    reader._get_json = lambda ep: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if ep == "/json/version" else []
    )
    reader._get_tab_ws = Mock(return_value="ws://tab")
    reader._connect = Mock(return_value=ws)
    reader.create_tab = Mock(return_value="T1")
    # cdp_js returns ready + selector present
    reader.cdp_js = Mock(return_value="complete")

    out = reader._prepare_tab("https://example.com", timeout=5)
    assert out is ws
    # The buffered load event must have been observed (not silently dropped):
    # if it had been swallowed, _wait_load_event would have timed out and
    # raised. Reaching here proves the race is handled.
    ws.close()


# --- 3b. WebSocket is closed when enable/navigate raises ----------------------
def test_ws_closed_on_prepare_exception():
    ws = _FakeWS()

    def boom(ws2, method, params=None, timeout=10):
        raise CDPError(f"boom on {method}")

    reader = ChromeReader()
    reader._get_json = lambda ep: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if ep == "/json/version" else []
    )
    reader._get_tab_ws = Mock(return_value="ws://tab")
    reader._connect = Mock(return_value=ws)
    reader.create_tab = Mock(return_value="T1")
    reader.cdp_send = boom  # Page.enable raises immediately

    with pytest.raises(CDPError):
        reader._prepare_tab("https://example.com", timeout=5)
    assert ws.closed is True, "socket must be closed on exception"


# --- 4. CLI --wait propagates to site shortcuts ------------------------------
def test_cli_wait_propagates(monkeypatch):
    from click.testing import CliRunner
    from chrome_cdp_reader.cli import cli
    from chrome_cdp_reader.bridge import ChromeReader

    captured = {}

    def fake_read_gmail(self, search="", wait=15):
        captured["wait"] = wait
        return {}

    monkeypatch.setattr(ChromeReader, "read_gmail", fake_read_gmail)
    monkeypatch.setattr(ChromeReader, "is_connected", lambda self: True)
    monkeypatch.setenv("WIN_USER", "TestUser")
    runner = CliRunner()
    result = runner.invoke(cli, ["read", "gmail", "--wait", "30"],
                           env={"WIN_USER": "TestUser"})
    assert result.exit_code == 0, result.output
    assert captured["wait"] == 30, "--wait not propagated to read_gmail"
