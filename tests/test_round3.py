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
from unittest.mock import Mock

import pytest

from chrome_cdp_reader.bridge import ChromeReader
from chrome_cdp_reader.errors import (
    ConnectionError,
    EvaluationError,
    InvalidInputError,
    NavigationTimeoutError,
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
    reader._get_json = lambda ep: (
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
    reader._get_json = lambda ep: (
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
    reader._get_json = lambda ep: (
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
    reader._prepare_tab = Mock(return_value=_ws(TargetHandle("T1", True)))
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
                            overwrite=True)
    assert isinstance(out, dict)
    assert out["format"] == "png"
    assert out["byteSize"] > 0


def test_screenshot_return_path_legacy():
    reader = _screenshot_reader()
    out = reader.screenshot("https://example.com", output="legacy.png",
                            overwrite=True, return_path=True)
    assert isinstance(out, str)
    assert out.endswith("legacy.png")
