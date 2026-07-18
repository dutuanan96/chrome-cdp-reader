"""Live integration tests for single-tab Gmail reuse and generic tab close.

These run against a real Chrome debug instance on 127.0.0.1:9222 and are
skipped automatically when Chrome is not reachable (so CI without Chrome
stays green).
"""
import os

import pytest

from chrome_cdp_reader.bridge import ChromeReader

CDP = os.environ.get("CRC_CDP_URL", "http://127.0.0.1:9222")
GMAIL_PREFIX = "https://mail.google.com/mail/"


def _chrome_up() -> bool:
    try:
        ChromeReader().is_connected()
        return True
    except Exception:
        return False


live = pytest.mark.skipif(not _chrome_up(), reason="Chrome debug not reachable")


def _gmail_tab_count(reader: ChromeReader) -> int:
    return sum(
        1
        for t in reader.get_tabs()
        if t.get("type") == "page"
        and (t.get("url") or "").startswith(GMAIL_PREFIX)
    )


def _close_gmail_tabs(reader: ChromeReader) -> None:
    for t in reader.get_tabs():
        if (
            t.get("type") == "page"
            and (t.get("url") or "").startswith(GMAIL_PREFIX)
        ):
            reader._close_target_by_id(t.get("id"), timeout=2.0)


@live
def test_gmail_reuse_keeps_single_tab():
    reader = ChromeReader()
    _close_gmail_tabs(reader)  # start clean

    try:
        reader.read_gmail(wait=20)
        first = _gmail_tab_count(reader)
        assert first == 1, f"expected 1 Gmail tab after first read, got {first}"

        # Second read must reuse the same tab, not open a new one.
        reader.read_gmail(wait=20)
        second = _gmail_tab_count(reader)
        assert second == 1, f"expected still 1 Gmail tab (reuse), got {second}"
    finally:
        _close_gmail_tabs(reader)


@live
def test_generic_read_closes_tab():
    reader = ChromeReader()
    url = "https://example.com"
    # Ensure no leftover example.com tab from a prior crash.
    for t in reader.get_tabs():
        if (t.get("url") or "").startswith(url):
            reader._close_target_by_id(t.get("id"), timeout=2.0)

    ws = reader._prepare_tab(url, timeout=15)
    target_id = getattr(ws, "_target_id", None)
    try:
        reader.cdp_js(ws, "document.title")
    finally:
        reader._close_tab(ws)
        ws.close()

    assert not reader._target_exists(target_id, timeout=1.0), \
        "generic read must close the tab it opened"
