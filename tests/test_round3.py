"""
Round-3 regression tests — prove the blocker fixes are wired into the real
code paths (not just dataclass defaults / issubclass assertions).

Covers:
  B1  CLI --max-chars flows end-to-end into read() (normal URL + gmail/zalo/
      facebook aliases), and --json uses textLength/truncated, not len(text).
  B2  TargetHandle is the runtime source of truth: _prepare_tab attaches
      ws._handle with owned=True for created tabs and owned=False for reused
      tabs; _close_tab consumes the handle.
  B3  Error taxonomy is connected to runtime: navigate timeout -> Navigation
      TimeoutError, create/attach failure -> TargetError, _connect failure ->
      ConnectionError, evaluate failure -> EvaluationError.
  B4  create_tab() validates the URL at the boundary (file:/javascript:/bad
      HTTP are rejected); only about:blank / http(s) with a host pass.
  B6  Screenshot hardening: quality must be a real int (bool/str/float
      rejected), output path confined to CWD root, .bmp rejected, overwrite
      semantics enforced.
"""

import json
import time
from collections import deque
from unittest.mock import Mock

import pytest
import websocket

from chrome_cdp_reader.bridge import ChromeReader
from chrome_cdp_reader.errors import (
    ConnectionError,
    EvaluationError,
    ExtractionError,
    InvalidInputError,
    NavigationTimeoutError,
    NavigationError,
    TargetError,
)
from chrome_cdp_reader.models import TargetHandle
from chrome_cdp_reader.url_validation import validate_scheme


# ===========================================================================
# B1 — CLI --max-chars bounded read end-to-end
# ===========================================================================
def test_cli_read_passes_max_chars_to_read(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from chrome_cdp_reader.cli import cli

    captured = {}
    def fake_read(self, target, wait=15, max_chars=4000, **kw):
        captured["target"] = target
        captured["max_chars"] = max_chars
        return {"text": "x" * 10, "textLength": 10, "truncated": False,
                "title": "T", "url": "https://example.com",
                "links": [], "images": []}
    monkeypatch.setattr(ChromeReader, "read", fake_read)
    monkeypatch.setattr(ChromeReader, "is_connected", lambda self: True)

    r = CliRunner()
    res = r.invoke(cli, ["read", "https://example.com", "--max-chars", "123"])
    assert res.exit_code == 0, res.output
    assert captured["target"] == "https://example.com"
    assert captured["max_chars"] == 123


def test_cli_alias_gmail_passes_max_chars(monkeypatch):
    from click.testing import CliRunner
    from chrome_cdp_reader.cli import cli

    captured = {}
    def fake_read_gmail(self, search="", wait=15, max_chars=4000):
        captured["max_chars"] = max_chars
        return {"text": "x", "textLength": 1, "truncated": False,
                "title": "T", "url": "u", "links": [], "images": []}
    monkeypatch.setattr(ChromeReader, "read_gmail", fake_read_gmail)
    monkeypatch.setattr(ChromeReader, "is_connected", lambda self: True)

    r = CliRunner()
    res = r.invoke(cli, ["read", "gmail", "--max-chars", "555"])
    assert res.exit_code == 0, res.output
    assert captured["max_chars"] == 555


def test_cli_alias_zalo_facebook_pass_max_chars(monkeypatch):
    from click.testing import CliRunner
    from chrome_cdp_reader.cli import cli

    seen = []
    def fake_read(self, target, wait=15, max_chars=4000, **kw):
        seen.append(max_chars)
        return {"text": "x", "textLength": 1, "truncated": False,
                "title": "T", "url": "u", "links": [], "images": []}
    monkeypatch.setattr(ChromeReader, "read", fake_read)
    monkeypatch.setattr(ChromeReader, "is_connected", lambda self: True)

    r = CliRunner()
    for alias in ("zalo", "facebook"):
        res = r.invoke(cli, ["read", alias, "--max-chars", "777"])
        assert res.exit_code == 0, res.output
    # both zalo and facebook forwarded --max-chars
    assert seen == [777, 777]


def test_cli_json_uses_textlength_not_len(monkeypatch, capsys):
    from click.testing import CliRunner
    from chrome_cdp_reader.cli import cli

    # text is long (50) but the bounded extraction reported 10 chars.
    def fake_read(self, target, wait=15, max_chars=4000, **kw):
        return {"text": "y" * 50, "textLength": 10, "truncated": True,
                "title": "T", "url": "https://example.com",
                "links": [], "images": []}
    monkeypatch.setattr(ChromeReader, "read", fake_read)
    monkeypatch.setattr(ChromeReader, "is_connected", lambda self: True)

    r = CliRunner()
    res = r.invoke(cli, ["read", "https://example.com", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    # textLength/truncated come from the bounded extractor, NOT len(text).
    assert data["textLength"] == 10
    assert data["truncated"] is True


# ===========================================================================
# B2 — TargetHandle is the runtime source of truth
# ===========================================================================
def _ws(handle):
    import websocket as _ws_mod
    w = Mock()
    w._handle = handle
    w.recv = Mock(side_effect=_ws_mod.WebSocketTimeoutException)
    w.settimeout = Mock()
    w.close = Mock()
    return w


def test_prepare_tab_created_target_is_owned_true():
    import json
    reader = ChromeReader()
    reader._get_json = lambda ep, *a, **k: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://b"}
        if ep == "/json/version" else []
    )
    reader.create_tab = Mock(return_value="T_NEW")
    reader._get_tab_ws = Mock(return_value="ws://new")
    reader._connect = Mock(return_value=_ws(None))
    reader.cdp_js = Mock(return_value='"complete"')
    # navigate returns frameId/loaderId; lifecycle event delivered on recv.
    def fake_send(s, method, params=None, timeout=10):
        if method == "Target.createTarget":
            return {"targetId": "T_NEW"}
        if method == "Page.navigate":
            return {"frameId": "F1", "loaderId": "L1"}
        return {}
    reader.cdp_send = fake_send
    reader._wait_ready_state = Mock(return_value=True)
    reader.wait_for_selector = Mock(return_value=True)
    # deliver a matching lifecycle load event once
    life = json.dumps({"method": "Page.lifecycleEvent",
                       "params": {"frameId": "F1", "loaderId": "L1",
                                  "name": "load"}})
    reader._get_event_queue = Mock(return_value=[])
    from unittest.mock import Mock as _M
    ws = reader._connect.return_value
    ws.recv = _M(return_value=life)  # first recv = lifecycle event

    out = reader._prepare_tab("https://example.com", timeout=5)
    assert isinstance(out._handle, TargetHandle)
    assert out._handle.target_id == "T_NEW"
    assert out._handle.owned is True  # created -> owned


def test_prepare_tab_reused_target_is_owned_false():
    existing = [{"id": "T0", "type": "page", "url": "https://example.com",
                 "webSocketDebuggerUrl": "ws://existing"}]
    reader = ChromeReader()
    reader._get_json = lambda ep, *a, **k: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://b"}
        if ep == "/json/version" else existing
    )
    reader._get_tab_ws = Mock(return_value="ws://existing")
    reader._connect = Mock(return_value=_ws(None))
    reader.cdp_js = Mock(return_value='"complete"')
    reader.cdp_send = Mock(return_value={})
    reader._wait_ready_state = Mock(return_value=True)
    reader.wait_for_selector = Mock(return_value=True)
    reader._get_event_queue = Mock(return_value=[])
    from unittest.mock import Mock as _M
    ws = reader._connect.return_value
    ws.recv = _M(return_value="")  # reuse path: no navigation, recv unused

    out = reader._prepare_tab("https://example.com", timeout=5,
                             reuse_existing=True)
    assert isinstance(out._handle, TargetHandle)
    assert out._handle.target_id == "T0"
    assert out._handle.owned is False  # reused -> not owned


def test_close_tab_consumes_handle():
    reader = ChromeReader()
    reader.get_tabs = Mock(return_value=[{"id": "T1", "type": "page", "url": "x"}])
    reader.cdp_send = Mock(return_value={})
    reader._target_exists = Mock(return_value=False)
    ws = _ws(TargetHandle(target_id="T1", owned=True))
    assert reader._close_tab(ws) is True
    # handle consumed -> second call with no metadata is safe
    ws2 = _ws(None)
    assert reader._close_tab(ws2) is False


# ===========================================================================
# B3 — error taxonomy connected to runtime
# ===========================================================================
def _reader_min():
    reader = ChromeReader()
    reader._get_json = lambda ep, *a, **k: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://b"}
        if ep == "/json/version" else []
    )
    return reader


def test_connect_failure_is_typed_connection_error():
    reader = _reader_min()
    reader.create_tab = Mock(return_value="T1")
    reader._get_tab_ws = Mock(return_value="ws://t")
    reader._connect = Mock(side_effect=ConnectionError("cannot connect"))
    reader._close_target_by_id = Mock(return_value=True)
    with pytest.raises(ConnectionError):
        reader._prepare_tab("https://example.com", timeout=5)


def test_create_target_failure_is_typed_target_error():
    reader = _reader_min()
    reader.create_tab = Mock(side_effect=TargetError("create failed"))
    reader._close_target_by_id = Mock(return_value=True)
    with pytest.raises(TargetError):
        reader._prepare_tab("https://example.com", timeout=5)


def test_navigate_timeout_is_typed_navigation_timeout():
    reader = _reader_min()
    reader.create_tab = Mock(return_value="T1")
    reader._get_tab_ws = Mock(return_value="ws://t")
    ws = _ws(None)
    reader._connect = Mock(return_value=ws)
    from collections import deque
    reader._get_event_queue = Mock(return_value=deque())

    def fake_send(s, method, params=None, timeout=10):
        if method == "Target.createTarget":
            return {"targetId": "T1"}
        if method == "Page.navigate":
            return {"frameId": "F1", "loaderId": "L1"}
        return {}
    reader.cdp_send = fake_send
    # No lifecycle event delivered -> wait loop times out.
    reader.cdp_js = Mock(return_value='"complete"')
    with pytest.raises(NavigationTimeoutError):
        reader._prepare_tab("https://example.com", timeout=1)


def test_evaluate_failure_is_typed_evaluation_error():
    from collections import deque
    reader = _reader_min()
    reader.create_tab = Mock(return_value="T1")
    reader._get_tab_ws = Mock(return_value="ws://t")
    ws = _ws(None)
    reader._connect = Mock(return_value=ws)
    # deliver a matching lifecycle load event via the buffered queue
    life = {"method": "Page.lifecycleEvent",
            "params": {"frameId": "F1", "loaderId": "L1", "name": "load"}}
    reader._get_event_queue = Mock(side_effect=lambda ws: deque([life]))

    def fake_send(s, method, params=None, timeout=10):
        if method == "Target.createTarget":
            return {"targetId": "T1"}
        if method == "Page.navigate":
            return {"frameId": "F1", "loaderId": "L1"}
        return {}
    reader.cdp_send = fake_send
    reader._wait_ready_state = Mock(return_value=True)
    reader.wait_for_selector = Mock(return_value=True)
    # read_text -> cdp_js (Runtime.evaluate) raises typed error
    reader.cdp_js = Mock(side_effect=EvaluationError("evaluate failed"))
    with pytest.raises(EvaluationError):
        reader.read("https://example.com", wait=5)


# ===========================================================================
# B4 — create_tab URL validation at the boundary
# ===========================================================================
def test_create_tab_rejects_file_scheme():
    reader = ChromeReader()
    with pytest.raises(InvalidInputError):
        reader.create_tab("file:///etc/passwd")


def test_create_tab_rejects_javascript_scheme():
    reader = ChromeReader()
    with pytest.raises(InvalidInputError):
        reader.create_tab("javascript:alert(1)")


def test_create_tab_rejects_data_scheme():
    reader = ChromeReader()
    with pytest.raises(InvalidInputError):
        reader.create_tab("data:text/html,<script>")


def test_create_tab_rejects_malformed_http():
    reader = ChromeReader()
    with pytest.raises(InvalidInputError):
        reader.create_tab("http://")  # no host


def test_create_tab_allows_about_blank_and_https():
    reader = ChromeReader()
    reader._get_json = Mock(return_value={
        "Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://b"})
    reader._connect = Mock(return_value=_ws(None))
    reader.cdp_send = Mock(return_value={"targetId": "T1"})
    assert reader.create_tab("about:blank") == "T1"
    assert reader.create_tab("https://example.com") == "T1"


def test_validate_scheme_allowlist():
    # http(s) with a host pass; dangerous schemes raise.
    validate_scheme("https://example.com")  # no raise
    validate_scheme("http://example.com")
    validate_scheme("about:blank")
    for bad in ("file:///x", "javascript:1", "data:text/html,x", "ftp://x"):
        with pytest.raises(InvalidInputError):
            validate_scheme(bad)


# ===========================================================================
# B6 — screenshot hardening
# ===========================================================================
def _screenshot_reader():
    reader = ChromeReader()
    reader._prepare_tab = Mock(return_value=_ws(TargetHandle("T1", owned=True)))
    reader._close_tab = Mock()
    reader.cdp_send = Mock(return_value={"data": "iVBORw0KGgo="})
    return reader


def test_screenshot_quality_must_be_int():
    reader = _screenshot_reader()
    for bad in (True, "80", 80.5, "high"):
        with pytest.raises(InvalidInputError):
            reader.screenshot("https://example.com", output="q.png",
                              quality=bad, overwrite=True)


def test_screenshot_rejects_bmp_extension():
    reader = _screenshot_reader()
    with pytest.raises(InvalidInputError):
        reader.screenshot("https://example.com", output="x.bmp", overwrite=True)


def test_screenshot_path_escape_rejected(tmp_path):
    reader = _screenshot_reader()
    evil = "../escape.png"
    with pytest.raises(InvalidInputError):
        reader.screenshot("https://example.com", output=evil, overwrite=True)


def test_screenshot_overwrite_false_refuses_existing():
    reader = _screenshot_reader()
    # first write
    reader.screenshot("https://example.com", output="dup.png", overwrite=True)
    # second without overwrite must refuse
    with pytest.raises(InvalidInputError):
        reader.screenshot("https://example.com", output="dup.png",
                          overwrite=False)


def test_screenshot_returns_metadata_dict():
    reader = _screenshot_reader()
    out = reader.screenshot("https://example.com", output="meta.png",
                            overwrite=True, return_metadata=True)
    assert isinstance(out, dict)
    assert out["format"] == "png"
    assert out["byteSize"] > 0


def test_screenshot_return_path_legacy():
    reader = _screenshot_reader()
    # Default (return_metadata=False) preserves the original str return.
    out = reader.screenshot("https://example.com", output="legacy.png",
                            overwrite=True)
    assert isinstance(out, str)
    assert out.endswith("legacy.png")


# ===========================================================================
# Round 4 — deeper regression (deadline budget, method-aware errors,
# strict lifecycle edge cases, about: scheme, handle immutability)
# ===========================================================================
def test_deadline_budgets_helper_timeouts():
    """With timeout=1, tab lookup / create / connect must be called with a
    budget no larger than the remaining deadline (never a default large
    timeout). We patch the post-selection helpers so the test only inspects
    the budgets passed into create_tab / _get_tab_ws / _connect."""
    reader = _reader_min()
    seen = {}
    ct = []  # captured (helper, timeout) tuples
    # Track the budget passed to create_tab (and its inner helpers).
    def fake_create(url, *, timeout=15):
        seen["create_tab"] = timeout
        return "T1"
    reader.create_tab = fake_create
    reader._get_tab_ws = Mock(side_effect=lambda tid, *, timeout=5: (ct.append(("get_tab_ws", timeout)) or "ws://t"))
    reader._connect = Mock(side_effect=lambda u, timeout=15: (ct.append(("connect", timeout)) or _ws(None)))
    reader.cdp_send = Mock(return_value={})
    reader.cdp_js = Mock(return_value='"complete"')
    reader._wait_navigation_ready = Mock(return_value=True)
    reader._wait_ready_state = Mock(return_value=True)
    reader._get_event_queue = Mock(side_effect=lambda ws: deque())

    reader._prepare_tab("https://example.com", timeout=1)
    assert seen["create_tab"] is not None
    assert seen["create_tab"] <= 1.0
    caps = dict(ct)
    assert caps["get_tab_ws"] <= 1.0
    assert caps["connect"] <= 1.0


def _scripted_ws_with_response(resp_json: str):
    class _S:
        def __init__(self):
            self._script = [resp_json]
            self.sent = []
            self.closed = False
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
    return _S()


def test_cdp_error_runtime_evaluate_maps_to_evaluation_error():
    ws = _scripted_ws_with_response(
        json.dumps({"id": 1, "error": {"message": "boom"}}))
    reader = ChromeReader()
    with pytest.raises(EvaluationError):
        reader.cdp_send(ws, "Runtime.evaluate", {"expression": "1"}, timeout=5)


def test_cdp_error_navigate_maps_to_navigation_error():
    ws = _scripted_ws_with_response(
        json.dumps({"id": 1, "error": {"message": "bad"}}))
    reader = ChromeReader()
    with pytest.raises(NavigationError):
        reader.cdp_send(ws, "Page.navigate", {"url": "x"}, timeout=5)


def test_cdp_error_create_target_maps_to_target_error():
    ws = _scripted_ws_with_response(
        json.dumps({"id": 1, "error": {"message": "no"}}))
    reader = ChromeReader()
    with pytest.raises(TargetError):
        reader.cdp_send(ws, "Target.createTarget", {"url": "x"}, timeout=5)


def test_cdp_malformed_response_maps_to_extraction_error():
    ws = _scripted_ws_with_response("not-json{{")
    reader = ChromeReader()
    with pytest.raises(ExtractionError):
        reader.cdp_send(ws, "Runtime.evaluate", {}, timeout=5)


def test_strict_lifecycle_rejects_wrong_loader():
    from unittest.mock import Mock as _M
    reader = ChromeReader()
    ws = _ws(None)
    queue = deque([{"method": "Page.lifecycleEvent",
                    "params": {"frameId": "F1", "loaderId": "WRONG",
                               "name": "load"}}])
    reader._get_event_queue = Mock(return_value=queue)
    ws.recv = _M(side_effect=websocket.WebSocketTimeoutException)
    ready = reader._wait_navigation_ready(ws, "F1", "L1", timeout=1,
                                           lifecycle_enabled=True)
    assert ready is False


def test_strict_lifecycle_accepts_correct_loader():
    from unittest.mock import Mock as _M
    reader = ChromeReader()
    ws = _ws(None)
    queue = deque([{"method": "Page.lifecycleEvent",
                    "params": {"frameId": "F1", "loaderId": "L1",
                               "name": "load"}}])
    reader._get_event_queue = Mock(return_value=queue)
    ws.recv = _M(side_effect=websocket.WebSocketTimeoutException)
    ready = reader._wait_navigation_ready(ws, "F1", "L1", timeout=1,
                                           lifecycle_enabled=True)
    assert ready is True


def test_same_document_event_rejected_for_cross_document():
    from unittest.mock import Mock as _M
    reader = ChromeReader()
    ws = _ws(None)
    queue = deque([{"method": "Page.navigatedWithinDocument",
                    "params": {"frameId": "F1"}}])
    reader._get_event_queue = Mock(return_value=queue)
    ws.recv = _M(side_effect=websocket.WebSocketTimeoutException)
    ready = reader._wait_navigation_ready(ws, "F1", "L1", timeout=1,
                                           lifecycle_enabled=True)
    assert ready is False


def test_lifecycle_event_rejected_for_same_document():
    from unittest.mock import Mock as _M
    reader = ChromeReader()
    ws = _ws(None)
    queue = deque([{"method": "Page.lifecycleEvent",
                    "params": {"frameId": "F1", "loaderId": "",
                               "name": "load"}}])
    reader._get_event_queue = Mock(return_value=queue)
    ws.recv = _M(side_effect=websocket.WebSocketTimeoutException)
    ready = reader._wait_navigation_ready(ws, "F1", None, timeout=1,
                                           lifecycle_enabled=True)
    assert ready is False


def test_validate_scheme_rejects_other_about_urls():
    for bad in ("about:settings", "about:version", "about:blank/x", "about:"):
        with pytest.raises(InvalidInputError):
            validate_scheme(bad)
    assert validate_scheme("about:blank") == "about"


def test_close_tab_uses_captured_handle_not_mutated():
    reader = ChromeReader()
    reader.get_tabs = Mock(return_value=[{"id": "T1", "type": "page", "url": "x"}])
    reader.cdp_send = Mock(return_value={})
    reader._target_exists = Mock(return_value=False)
    handle = TargetHandle(target_id="T1", owned=True)
    ws = _ws(handle)
    ws._handle = TargetHandle(target_id="SOME_OTHER", owned=False)
    assert reader._close_tab(ws, handle=handle) is True


def test_close_tab_rejects_wrong_handle_type():
    reader = ChromeReader()
    ws = Mock()
    ws._handle = {"target_id": "T1", "owned": True}
    assert reader._close_tab(ws) is False


# ===========================================================================
# Round 5 — failure-path regression (create_tab shared deadline,
# method-aware timeout, send failure, lifecycle fallback)
# ===========================================================================

def test_create_tab_shared_deadline_does_not_exceed_budget():
    """create_tab must spend from ONE shared budget across _get_json /
    _connect / cdp_send. When an early step consumes most of the budget, the
    later step must receive only the real remaining time, so the TOTAL never
    exceeds `timeout`."""
    reader = ChromeReader()
    reader._get_json = Mock(
        side_effect=lambda ep, *a, **k: time.sleep(0.4) or
        {"Browser": "C/150", "webSocketDebuggerUrl": "ws://b"})
    seen = {}
    def fake_connect(u, timeout=15):
        seen["connect_timeout"] = timeout
        time.sleep(timeout)  # would blow the budget if given the full value
        return _ws(None)
    reader._connect = Mock(side_effect=fake_connect)
    reader.cdp_send = Mock(return_value={"targetId": "T1"})

    start = time.monotonic()
    # With a shared budget, all steps fit within `timeout` (early step consumes
    # 0.4s, the connect step receives only the ~0.1s remaining) -> no raise.
    result = reader.create_tab("about:blank", timeout=0.5)
    elapsed = time.monotonic() - start
    assert result == "T1"
    # Total must not approach 0.5 (get_json) + 0.5 (connect) = 1.0.
    # With a shared budget, connect receives ~0.1s, so total ~0.5.
    assert elapsed < 0.8, f"create_tab exceeded shared budget: {elapsed:.2f}s"
    # The connect step received only the remaining slice, not the full 0.5.
    assert seen["connect_timeout"] < 0.5


def _timeout_ws():
    """WebSocket whose recv always times out (drives the cdp_send timeout path)."""
    class _T:
        def __init__(self):
            self.sent = []
        def send(self, payload):
            self.sent.append(json.loads(payload))
        def settimeout(self, t):
            pass
        def recv(self):
            raise websocket.WebSocketTimeoutException()
        def close(self):
            pass
    return _T()


def test_cdp_send_runtime_evaluate_timeout_is_evaluation_error():
    reader = ChromeReader()
    with pytest.raises(EvaluationError):
        reader.cdp_send(_timeout_ws(), "Runtime.evaluate", {}, timeout=0.2)


def test_cdp_send_page_navigate_timeout_is_navigation_timeout():
    reader = ChromeReader()
    with pytest.raises(NavigationTimeoutError):
        reader.cdp_send(_timeout_ws(), "Page.navigate", {"url": "x"}, timeout=0.2)


def test_cdp_send_create_target_timeout_is_target_error():
    reader = ChromeReader()
    with pytest.raises(TargetError):
        reader.cdp_send(_timeout_ws(), "Target.createTarget", {"url": "x"},
                        timeout=0.2)


def test_cdp_send_close_target_timeout_is_target_error():
    reader = ChromeReader()
    with pytest.raises(TargetError):
        reader.cdp_send(_timeout_ws(), "Target.closeTarget", {"targetId": "x"},
                        timeout=0.2)


def test_cdp_send_page_close_timeout_is_target_error():
    reader = ChromeReader()
    with pytest.raises(TargetError):
        reader.cdp_send(_timeout_ws(), "Page.close", {}, timeout=0.2)


def test_cdp_send_send_failure_is_connection_error():
    class _BadSend:
        def send(self, payload):
            raise websocket.WebSocketException("boom")
        def settimeout(self, t):
            pass
        def recv(self):
            raise websocket.WebSocketTimeoutException()
        def close(self):
            pass
    reader = ChromeReader()
    with pytest.raises(ConnectionError):
        reader.cdp_send(_BadSend(), "Runtime.evaluate", {}, timeout=0.2)


def _reader_for_lifecycle(raise_method, exc):
    """A reader whose _prepare_tab runs for real, but Page/Runtime/lifecycle
    cdp_send calls are scripted. `raise_method` is the method that should raise
    `exc` (only when enabling lifecycle); everything else returns {}."""
    reader = _reader_min()
    reader.create_tab = Mock(return_value="T1")
    reader._get_tab_ws = Mock(return_value="ws://t")
    reader._connect = Mock(return_value=_ws(None))
    reader.cdp_send = Mock(
        side_effect=lambda ws, method, params=None, timeout=10: (
            {} if method != raise_method
            else (_ for _ in ()).throw(exc)))
    reader.cdp_js = Mock(return_value='"complete"')
    reader._wait_navigation_ready = Mock(return_value=True)
    reader._wait_ready_state = Mock(return_value=True)
    reader._get_event_queue = Mock(side_effect=lambda ws: deque())
    return reader


def test_lifecycle_fallback_on_unsupported_protocol():
    """A protocol-confirmed 'not supported' error falls back to legacy
    loadEventFired (lifecycle_enabled stays False)."""
    reader = _reader_for_lifecycle(
        "Page.setLifecycleEventsEnabled",
        EvaluationError("Command Page.setLifecycleEventsEnabled is not supported"))
    # Should NOT raise — unsupported lifecycle is a benign fallback.
    ws = reader._prepare_tab("https://example.com", timeout=5)
    assert ws is not None


def test_lifecycle_propagation_on_socket_failure():
    """A ConnectionError while enabling lifecycle must propagate (not be
    swallowed into a legacy fallback)."""
    reader = _reader_for_lifecycle(
        "Page.setLifecycleEventsEnabled", ConnectionError("socket down"))
    with pytest.raises(ConnectionError):
        reader._prepare_tab("https://example.com", timeout=5)


def test_lifecycle_propagation_on_timeout():
    reader = _reader_for_lifecycle(
        "Page.setLifecycleEventsEnabled", NavigationTimeoutError("timed out"))
    with pytest.raises(NavigationTimeoutError):
        reader._prepare_tab("https://example.com", timeout=5)


def test_lifecycle_propagation_on_malformed_response():
    reader = _reader_for_lifecycle(
        "Page.setLifecycleEventsEnabled", ExtractionError("bad json"))
    with pytest.raises(ExtractionError):
        reader._prepare_tab("https://example.com", timeout=5)


