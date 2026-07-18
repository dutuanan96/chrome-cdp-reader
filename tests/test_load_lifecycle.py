"""
Load-lifecycle unit tests — run on Ubuntu without Chrome.

These mock the CDP transport layer (websocket + HTTP JSON) so the tab
lifecycle (_prepare_tab) can be verified deterministically:
  - no navigation before Page.enable
  - URL navigates exactly once (no Page.reload)
  - STRICT correlation: a stray Page.loadEventFired is NOT accepted when
    lifecycle events are enabled; only matching lifecycle/within-document
    events complete navigation
  - late selector is waited for
  - selector timeout falls back to DOM text
  - screenshot uses the same lifecycle as read
  - existing matching tab is reused without re-navigation
  - typed errors (NavigationTimeoutError) raised on timeout, not CDPError
"""

import json
import websocket
from unittest.mock import Mock

import pytest

from chrome_cdp_reader.bridge import ChromeReader
from chrome_cdp_reader.errors import (
    CDPError,
    NavigationTimeoutError,
)


def _lifecycle(frame, loader, name):
    return json.dumps({
        "method": "Page.lifecycleEvent",
        "params": {"frameId": frame, "loaderId": loader, "name": name},
    })


def _scripted_ws(script):
    """WebSocket whose recv returns a fixed scripted sequence, then hangs."""
    class _S:
        def __init__(self, s):
            self._script = list(s)
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
            raise websocket.WebSocketTimeoutException()
        def close(self):
            self.closed = True
    return _S(script)


def _make_reader(ws, create_target_id="T1", tab_ws="ws://tab", existing_tabs=None,
                scripted_events=None):
    """Build a ChromeReader whose transport is fully mocked.

    scripted_events: list of JSON strings delivered by ws.recv() AFTER the
    navigate response (used to drive the wait loop with lifecycle events).
    """
    reader = ChromeReader()

    def fake_get_json(endpoint):
        if endpoint == "/json/version":
            return {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if endpoint == "/json/list":
            return existing_tabs or []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    reader._get_json = fake_get_json

    # Ordered responses for the setup sends.
    resp_id = {"n": 0}
    def fake_cdp_send(s, method, params=None, timeout=10):
        resp_id["n"] += 1
        try:
            s.send(json.dumps({"id": resp_id["n"], "method": method, "params": params or {}}))
        except Exception:
            pass
        if method == "Target.createTarget":
            return {"targetId": create_target_id}
        if method == "Page.navigate":
            return {"frameId": "F1", "loaderId": "L1"}
        if method == "Runtime.evaluate":
            return {"result": {"value": "complete"}}
        return {}

    reader.cdp_send = fake_cdp_send
    reader._get_tab_ws = Mock(return_value=tab_ws)
    reader._connect = Mock(return_value=ws)
    # Default script: navigate resp (id=5) + a matching lifecycle load event
    # so the wait loop completes without a real browser.
    if scripted_events is None:
        scripted_events = [
            json.dumps({"id": 5, "result": {"frameId": "F1", "loaderId": "L1"}}),
            _lifecycle("F1", "L1", "load"),
        ]
    # Prepend the standard setup responses (create/en/rt/lifecycle enabled).
    setup = [
        json.dumps({"id": 1, "result": {"targetId": create_target_id}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({"id": 4, "result": {}}),
    ]
    ws._script = setup + list(scripted_events)
    return reader


def _navigate_methods(ws):
    return [m.get("method") for m in ws.sent if m.get("method") == "Page.navigate"]


# --- 1. No navigation before Page.enable ------------------------------------
def test_enable_before_navigate():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    reader._prepare_tab("https://example.com", timeout=5)
    methods = [m.get("method") for m in ws.sent]
    assert "Page.enable" in methods
    assert "Runtime.enable" in methods
    assert methods.index("Page.enable") < methods.index("Page.navigate")


# --- 2. URL navigates exactly once (no reload) ------------------------------
def test_navigate_once():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    reader._prepare_tab("https://example.com", timeout=5)
    assert _navigate_methods(ws) == ["Page.navigate"], "exactly one navigate, no reload"


# --- 3. STRICT correlation: stray loadEventFired is NOT accepted -----------
def test_stray_load_event_rejected_when_lifecycle_enabled():
    """When lifecycle events are enabled, a plain loadEventFired (even if it
    matches nothing) must NOT complete navigation; only a matching
    lifecycleEvent does. Simulate: navigate resp, then a stray loadEventFired,
    then a CORRECT lifecycle event."""
    events = [
        json.dumps({"id": 5, "result": {}}),                      # navigate resp
        json.dumps({"method": "Page.loadEventFired", "params": {}}),  # stray
        _lifecycle("F1", "L1", "load"),                            # correct
    ]
    ws = _scripted_ws([
        json.dumps({"id": 1, "result": {"targetId": "T1"}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({"id": 4, "result": {}}),
    ])
    reader = _make_reader(ws, scripted_events=events)
    out = reader._prepare_tab("https://example.com", timeout=5,
                              reuse_existing=False)
    assert out is ws
    ws.close()


# --- 3b. Wrong frame lifecycle event is rejected ---------------------------
def test_wrong_frame_lifecycle_rejected():
    events = [
        json.dumps({"id": 5, "result": {"frameId": "F1", "loaderId": "L1"}}),
        _lifecycle("WRONG", "L1", "load"),   # wrong frame -> must be ignored
        _lifecycle("F1", "L1", "load"),      # correct -> completes
    ]
    ws = _scripted_ws([
        json.dumps({"id": 1, "result": {"targetId": "T1"}}),
        json.dumps({"id": 2, "result": {}}),
        json.dumps({"id": 3, "result": {}}),
        json.dumps({"id": 4, "result": {}}),
    ])
    reader = _make_reader(ws, scripted_events=events)
    out = reader._prepare_tab("https://example.com", timeout=5)
    assert out is ws
    ws.close()


# --- 4. Late selector is waited for -----------------------------------------
def test_late_selector_waited():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    calls = {"n": 0}
    def fake_js(s, expr, timeout=None):
        if "readyState" in expr:
            return "complete"
        if "querySelector" in expr:
            calls["n"] += 1
            return calls["n"] >= 2
        return "complete" if "innerText" in expr else None
    reader.cdp_js = fake_js
    out = reader._prepare_tab("https://example.com", timeout=5,
                              selector="div[role='main']")
    assert calls["n"] >= 2, "polled selector until it appeared"
    out.close()


# --- 5a. Selector timeout falls back to DOM text (enough) -------------------
def test_selector_timeout_fallback_ok():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    def fake_js(s, expr, timeout=None):
        if "readyState" in expr:
            return "complete"
        if "querySelector" in expr:
            return False
        if "innerText.length" in expr:
            return 200
        return None
    reader.cdp_js = fake_js
    out = reader._prepare_tab("https://example.com", timeout=1,
                              selector="div[role='main']")
    out.close()


# --- 5b. Selector timeout with thin DOM -> typed raise ----------------------
def test_selector_timeout_fallback_raises():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    def fake_js(s, expr, timeout=None):
        if "querySelector" in expr:
            return False
        if "innerText.length" in expr:
            return 0
        return "complete" if "readyState" in expr else None
    reader.cdp_js = fake_js
    with pytest.raises(NavigationTimeoutError):
        reader._prepare_tab("https://example.com", timeout=1,
                            selector="div[role='main']")


# --- 6. Screenshot uses the same lifecycle ----------------------------------
def test_screenshot_uses_prepare_tab():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws)
    base = reader.cdp_send
    def fake_send(s, method, params=None, timeout=10):
        if method == "Page.captureScreenshot":
            return {"data": "iVBORw0KGgo="}
        return base(s, method, params, timeout)
    reader.cdp_send = fake_send
    out = reader.screenshot("https://example.com", output="shot_test.png",
                            wait=5, overwrite=True)
    navs = [m.get("method") for m in ws.sent if m.get("method") == "Page.navigate"]
    assert navs == ["Page.navigate"]
    assert out["path"].endswith(".png")
    assert out["format"] == "png"


# --- 7. Existing matching tab reused without re-navigation ------------------
def test_reuse_existing_tab_no_navigate():
    existing = [{"id": "T0", "type": "page", "url": "https://example.com",
                 "webSocketDebuggerUrl": "ws://existing"}]
    ws = _scripted_ws([])
    reader = _make_reader(ws, existing_tabs=existing)
    reader._prepare_tab("https://example.com", timeout=5, reuse_existing=True)
    assert _navigate_methods(ws) == [], "existing tab not re-navigated"


# --- 7b. Existing tab with different URL IS navigated ----------------------
def test_reuse_existing_tab_navigates_when_url_differs():
    existing = [{"id": "T0", "type": "page", "url": "https://other.com",
                 "webSocketDebuggerUrl": "ws://existing"}]
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws, existing_tabs=existing)
    reader._prepare_tab("https://example.com", timeout=5, reuse_existing=True)
    assert _navigate_methods(ws) == ["Page.navigate"]


# --- overall timeout raises typed error instead of silent read --------------
def test_load_timeout_raises_typed():
    ws = _scripted_ws([json.dumps({"id": 1, "result": {"targetId": "T1"}})])
    reader = _make_reader(ws, scripted_events=[])  # no lifecycle event -> timeout
    with pytest.raises(NavigationTimeoutError):
        reader._prepare_tab("https://example.com", timeout=1)


# --- 3c. WebSocket is closed when enable/navigate raises --------------------
def test_ws_closed_on_prepare_exception():
    ws = _scripted_ws([])
    def boom(s, method, params=None, timeout=10):
        raise CDPError(f"boom on {method}")
    reader = ChromeReader()
    reader._get_json = lambda ep: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if ep == "/json/version" else []
    )
    reader._get_tab_ws = Mock(return_value="ws://tab")
    reader._connect = Mock(return_value=ws)
    reader.create_tab = Mock(return_value="T1")
    reader.cdp_send = boom
    with pytest.raises(CDPError):
        reader._prepare_tab("https://example.com", timeout=5)
    assert ws.closed is True, "socket must be closed on exception"
