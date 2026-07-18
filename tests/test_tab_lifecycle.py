"""Tab lifecycle tests (unit + mock). Live Chrome integration for Gmail reuse
and generic close lives in tests/test_tab_reuse_live.py and is skipped when
Chrome is not reachable.

These run on Linux/CI without a real Chrome.
"""

from unittest.mock import Mock

import pytest

from chrome_cdp_reader.bridge import ChromeReader


def _reader_with_tabs(tabs):
    r = ChromeReader()
    r._owned_target_ids = set()
    r.get_tabs = Mock(return_value=tabs)
    return r


def _ws(target_id=None, owns=True):
    ws = Mock()
    ws._target_id = target_id
    ws._owns_target = owns
    return ws


class TestCloseTab:
    def test_rejects_missing_target_metadata(self):
        r = _reader_with_tabs([])
        ws = _ws(target_id=None)
        assert r._close_tab(ws) is False

    def test_does_not_close_reused_target(self):
        r = _reader_with_tabs([])
        ws = _ws(target_id="T1", owns=False)
        assert r._close_tab(ws) is True  # leaves it open, reports success

    def test_page_close_success_verified(self):
        r = _reader_with_tabs([{"id": "T1", "type": "page", "url": "x"}])
        ws = _ws(target_id="T1", owns=True)
        r.cdp_send = Mock(return_value={})
        r._target_exists = Mock(return_value=False)
        assert r._close_tab(ws) is True

    def test_page_close_socket_drop_still_verified(self):
        r = _reader_with_tabs([{"id": "T1", "type": "page", "url": "x"}])
        ws = _ws(target_id="T1", owns=True)
        r.cdp_send = Mock(side_effect=Exception("socket closed"))
        r._target_exists = Mock(return_value=False)
        assert r._close_tab(ws) is True

    def test_fallback_browser_ws_when_page_close_fails(self):
        r = _reader_with_tabs([{"id": "T1", "type": "page", "url": "x"}])
        ws = _ws(target_id="T1", owns=True)
        r.cdp_send = Mock(side_effect=Exception("boom"))  # Page.close raises
        # target still present after Page.close, but browser_ws close works
        r._target_exists = Mock(side_effect=[True, True, False])
        r._close_target_by_id = Mock(return_value=True)
        assert r._close_tab(ws) is True
        r._close_target_by_id.assert_called_once()

    def test_close_failure_is_logged_not_silent(self):
        r = _reader_with_tabs([{"id": "T1", "type": "page", "url": "x"}])
        ws = _ws(target_id="T1", owns=True)
        r.cdp_send = Mock(side_effect=Exception("boom"))
        r._target_exists = Mock(return_value=True)  # never disappears
        r._close_target_by_id = Mock(return_value=False)  # fallback fails too
        # Failure surfaced (False), not silently True.
        assert r._close_tab(ws) is False


class TestPrepareGap:
    def test_prepare_gap_closes_target_by_id(self):
        """If create_tab succeeds but _connect fails, the about:blank target
        must be closed by id (not leaked)."""
        r = _reader_with_tabs([])
        r.create_tab = Mock(return_value="T_NEW")
        r._get_tab_ws = Mock(return_value="ws://new")
        r._connect = Mock(side_effect=ConnectionError("cannot connect"))
        r._close_target_by_id = Mock(return_value=True)
        with pytest.raises(ConnectionError):
            r._prepare_tab("https://example.com", timeout=5)
        r._close_target_by_id.assert_called_once_with("T_NEW", timeout=2.0)


class TestReadGmailReuse:
    def test_reuse_single_existing_gmail_tab(self):
        r = _reader_with_tabs([
            {"id": "G1", "type": "page",
             "url": "https://mail.google.com/mail/u/0/#inbox",
             "webSocketDebuggerUrl": "ws://g1"},
        ])
        r.create_tab = Mock()  # must NOT be called when reusing
        ws = _ws(target_id="G1", owns=False)
        r._connect = Mock(return_value=ws)
        r.cdp_send = Mock(return_value={})
        r._wait_ready_state = Mock(return_value=True)
        r.wait_for_selector = Mock(return_value=True)
        r.cdp_js = Mock(
            return_value='{"title":"x","url":"y","text":"z","links":[],"images":[]}'
        )

        res = r.read_gmail()
        assert r.create_tab.call_count == 0, "must reuse, not create new"
        assert res.get("url") == "y"


class TestCleanupStale:
    def test_dry_run_does_not_close(self):
        r = _reader_with_tabs(
            [{"id": "B1", "type": "page", "url": "about:blank"}]
        )
        r._owned_target_ids = {"B1"}
        r._close_target_by_id = Mock(return_value=True)
        r._target_exists = Mock(return_value=False)
        report = r.cleanup_stale_tabs(dry_run=True)
        assert "B1" in report["wouldClose"]
        r._close_target_by_id.assert_not_called()

    def test_skips_user_tab_not_owned(self):
        r = _reader_with_tabs(
            [{"id": "U1", "type": "page", "url": "https://example.com"}]
        )
        r._owned_target_ids = set()  # not owned -> skip
        report = r.cleanup_stale_tabs()
        assert report["closed"] == []
        assert report["skipped"] == []

    def test_skips_non_blank_owned(self):
        r = _reader_with_tabs(
            [{"id": "G1", "type": "page",
              "url": "https://mail.google.com/mail/u/0/#inbox"}]
        )
        r._owned_target_ids = {"G1"}
        report = r.cleanup_stale_tabs()
        # Gmail tab must NOT be auto-closed
        assert "G1" not in report["closed"]
        assert any(d.get("targetId") == "G1" for d in report["skipped"])
