"""
Regression tests for B1 (safe process kill), B2 (navigation correlation) and
B3 (bounded text read).

These run on Linux/CI WITHOUT a real Chrome. B1/B2/B3 logic is exercised via
mocks. The real Windows/Chrome behaviour (intruder on port 9222, 302 redirect,
bad URL, fragment nav, no tab leak) is covered by tests/test_integration.py
when run on a machine with Chrome + port 9222, and by the live skill tests.
"""

import json
from collections import deque
from unittest.mock import Mock, patch

import pytest

from chrome_cdp_reader.bridge import ChromeReader, CDPError
from chrome_cdp_reader.chrome_launcher import ChromeLauncher


# ---------------------------------------------------------------------------
# B3: read_text bounds + schema
# ---------------------------------------------------------------------------

class TestReadTextB3:
    def test_read_text_validates_type(self):
        reader = ChromeReader()
        ws = Mock()
        for bad in (0, -1, True, "x", 3.5):
            with pytest.raises((TypeError, ValueError)):
                reader.read_text(ws, max_chars=bad)

    def test_read_text_builds_slicing_expression(self):
        """The browser must slice before JSON leaves; verify the expression."""
        reader = ChromeReader()
        ws = Mock()
        captured = {}

        def spy_cdp_js(ws_arg, expr, timeout=10):
            captured["expr"] = expr
            return json.dumps({"text": "x", "textLength": 1, "truncated": False})

        reader.cdp_js = spy_cdp_js
        reader.read_text(ws, max_chars=1234)
        expr = captured["expr"]
        assert "slice(0, maxChars)" in expr
        assert "maxChars = 1234" in expr
        # Must not return the full innerText un-sliced at top level.
        assert "return document.body.innerText;" not in expr.replace(" ", "")

    def test_read_text_parses_schema(self):
        reader = ChromeReader()
        ws = Mock()

        def fake_cdp_js(ws_arg, expr, timeout=10):
            return json.dumps({"text": "A" * 50, "textLength": 5000,
                                "truncated": True})

        reader.cdp_js = fake_cdp_js
        res = reader.read_text(ws, max_chars=4000)
        assert res["textLength"] == 5000
        assert res["truncated"] is True
        assert isinstance(res["text"], str)


# ---------------------------------------------------------------------------
# B1: launcher must NOT kill by image name; verifies PID+port+profile
# ---------------------------------------------------------------------------

class TestLauncherB1:
    def test_no_taskkill_by_imagename(self):
        """kill_chrome must never invoke `taskkill /IM chrome.exe`."""
        launcher = ChromeLauncher(win_user="TestUser")
        with patch.object(launcher, "_run_powershell", return_value="null"), \
             patch("subprocess.run") as mock_run:
            launcher.kill_chrome()
        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else []
            cmd = " ".join(str(a) for a in args)
            assert "/IM" not in cmd or "chrome.exe" not in cmd.split("/IM")[-1], \
                f"taskkill /IM chrome.exe found: {cmd}"

    def test_kills_only_owned_debug_chrome(self):
        """If the port is owned by our debug Chrome, kill by PID only."""
        launcher = ChromeLauncher(win_user="TestUser")
        fake_proc = Mock()
        fake_proc.returncode = 0
        with patch.object(launcher, "_find_intruder_on_port", return_value=None), \
             patch.object(launcher, "_find_debug_chrome_pid",
                          side_effect=[4242, None]), \
             patch("subprocess.run", return_value=fake_proc) as mock_run:
            ok = launcher.kill_chrome()
            assert ok is True
            kill_args = mock_run.call_args_list[-1].args[0]
            assert str(4242) in kill_args
            assert "/PID" in kill_args

    def test_failfast_when_intruder_occupies_port(self):
        """If another process holds the port, fail-fast (no kill, no launch)."""
        launcher = ChromeLauncher(win_user="TestUser")
        intruder = {"Name": "python.exe", "PID": 9999,
                    "CommandLine": "python -m http.server 9222"}
        with patch.object(launcher, "_find_intruder_on_port", return_value=intruder), \
             patch("subprocess.run") as mock_run:
            ok = launcher.kill_chrome()
            assert ok is False
            for call in mock_run.call_args_list:
                args = call.args[0] if call.args else []
                assert "taskkill" not in " ".join(str(a) for a in args).lower()


# ---------------------------------------------------------------------------
# B2: navigation correlation (frameId + loaderId, errorText, isDownload)
# ---------------------------------------------------------------------------

class _NavWS:
    """WebSocket stand-in that scripts the recv() sequence for navigation."""
    def __init__(self, script):
        self._script = list(script)
        self._cdp_event_queue = deque()
        self.closed = False

    def settimeout(self, t):
        pass

    def recv(self):
        if self._script:
            return self._script.pop(0)
        raise __import__("websocket").WebSocketTimeoutException()

    def close(self):
        self.closed = True


def _reader_nav(events_json, navigate_result):
    """Reader whose transport is mocked to drive _prepare_tab's nav path."""
    reader = ChromeReader()
    ws = Mock()
    ws._target_id = "T1"

    def fake_cdp_send(ws_arg, method, params=None, timeout=10):
        if method == "Page.navigate":
            return navigate_result
        if method in ("Page.enable", "Runtime.enable",
                      "Page.setLifecycleEventsEnabled"):
            return {}
        return {}

    reader.cdp_send = fake_cdp_send
    reader._get_event_queue = lambda w: deque()
    reader._get_json = lambda ep: (
        {"Browser": "Chrome/150", "webSocketDebuggerUrl": "ws://browser"}
        if ep == "/json/version" else []
    )
    reader._get_tab_ws = Mock(return_value="ws://tab")
    reader._connect = Mock(return_value=ws)
    reader.create_tab = Mock(return_value="T1")
    reader.cdp_js = Mock(return_value="complete")
    return reader, ws


class TestNavigationB2:
    def test_navigation_surfaces_errorText(self):
        reader, ws = _reader_nav([], {"frameId": "F1",
                                      "errorText": "net::ERR_NAME_NOT_RESOLVED"})
        with pytest.raises(CDPError) as exc:
            reader._prepare_tab("https://nope.example", timeout=5)
        assert "Navigation failed" in str(exc.value)

    def test_navigation_surfaces_isDownload(self):
        reader, ws = _reader_nav([], {"frameId": "F1", "isDownload": True})
        with pytest.raises(CDPError) as exc:
            reader._prepare_tab("https://x.example/file.zip", timeout=5)
        assert "download" in str(exc.value).lower()

    def test_lifecycle_wait_matches_frame_and_loader(self):
        reader = ChromeReader()
        ws = _NavWS([
            json.dumps({"method": "Page.lifecycleEvent",
                        "params": {"frameId": "F_OLD", "loaderId": "L_OLD",
                                   "name": "load"}}),
            json.dumps({"method": "Page.lifecycleEvent",
                        "params": {"frameId": "F1", "loaderId": "L1",
                                   "name": "load"}}),
        ])
        assert reader._wait_navigation_ready(ws, "F1", "L1", timeout=2) is True

    def test_same_document_navigated_within_document(self):
        reader = ChromeReader()
        ws = _NavWS([
            json.dumps({"method": "Page.navigatedWithinDocument",
                        "params": {"frameId": "F1"}}),
        ])
        assert reader._wait_navigation_ready(ws, "F1", "", timeout=2) is True

    def test_drain_old_events_clears_queue(self):
        reader = ChromeReader()
        ws = Mock()
        q = deque([{"method": "Page.loadEventFired"}])
        reader._get_event_queue = lambda w: q
        reader._drain_old_events(ws)
        assert len(q) == 0

    def test_legacy_load_event_accepted(self):
        reader = ChromeReader()
        ws = _NavWS([
            json.dumps({"method": "Page.loadEventFired", "params": {}}),
        ])
        # No lifecycle event -> the legacy loadEventFired is accepted.
        assert reader._wait_navigation_ready(ws, "F1", "L1", timeout=2) is True
