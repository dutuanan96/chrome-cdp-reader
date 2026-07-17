"""
Integration tests — require a running Chrome with remote debugging on 9222.

Skipped automatically when Chrome is not available, so CI (ubuntu-latest)
stays green. Run locally on Windows+WSL with Chrome debug mode on to exercise
the real CDP path.
"""

import os
import pytest
import urllib.request
from chrome_cdp_reader.bridge import ChromeReader


def _chrome_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chrome_up(), reason="Chrome debug not running on :9222")


def test_connect_and_list_tabs():
    reader = ChromeReader()
    assert reader.is_connected()
    tabs = reader.get_tabs()
    assert isinstance(tabs, list)


def test_read_static_page():
    reader = ChromeReader()
    result = reader.read("https://example.com", wait=5)
    assert result.get("title")
    assert "example" in result.get("url", "")


def test_screenshot_png_is_real_png(tmp_path):
    reader = ChromeReader()
    out = str(tmp_path / "shot.png")
    saved = reader.screenshot("https://example.com", output=out, wait=6)
    assert os.path.exists(saved)
    with open(saved, "rb") as f:
        header = f.read(8)
    assert header.startswith(b"\x89PNG\r\n\x1a\n"), "file is not a real PNG"


def test_screenshot_jpg_is_real_jpeg(tmp_path):
    reader = ChromeReader()
    out = str(tmp_path / "shot.jpg")
    saved = reader.screenshot("https://example.com/", output=out, wait=10)
    assert os.path.exists(saved)
    with open(saved, "rb") as f:
        header = f.read(3)
    assert header.startswith(b"\xff\xd8\xff"), "file is not a real JPEG"
