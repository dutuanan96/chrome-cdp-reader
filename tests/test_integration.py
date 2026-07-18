"""
Integration tests — require a running Chrome with remote debugging on 9222.

Marked `live` (registered in pyproject.toml) so the default CI matrix
(`pytest -m "not live"`) skips them. Run locally on Windows+WSL with Chrome
debug mode on to exercise the real CDP path.
"""

import os

import pytest

from chrome_cdp_reader.bridge import ChromeReader

CDP = os.environ.get("CRC_CDP_URL", "http://127.0.0.1:9222")


def _chrome_up() -> bool:
    # Correct probe: ask the reader whether the debug endpoint answers.
    # is_connected() returns False (does NOT raise) when Chrome is down, so
    # we return its value directly. This is what makes the live marker real.
    return ChromeReader(CDP).is_connected()


live = pytest.mark.live
pytestmark = pytest.mark.skipif(not _chrome_up(), reason="Chrome debug not reachable")


def test_connect_and_list_tabs():
    reader = ChromeReader(CDP)
    assert reader.is_connected()
    tabs = reader.get_tabs()
    assert isinstance(tabs, list)


def test_read_static_page():
    reader = ChromeReader(CDP)
    result = reader.read("https://example.com", wait=5)
    assert result.get("title")
    assert "example" in result.get("url", "")


def test_screenshot_png_is_real_png(tmp_path):
    reader = ChromeReader(CDP)
    # Output must stay inside the CWD root (screenshot root confinement).
    out = "shot.png"
    saved = reader.screenshot("https://example.com", output=out, wait=6, overwrite=True)
    assert saved["format"] == "png"
    assert os.path.exists(saved["path"])
    with open(saved["path"], "rb") as f:
        header = f.read(8)
    assert header.startswith(b"\x89PNG\r\n\x1a\n"), "file is not a real PNG"


def test_screenshot_jpg_is_real_jpeg(tmp_path):
    reader = ChromeReader(CDP)
    out = "shot.jpg"
    saved = reader.screenshot("https://example.com/", output=out, wait=10, overwrite=True)
    assert saved["format"] == "jpeg"
    assert os.path.exists(saved["path"])
    with open(saved["path"], "rb") as f:
        header = f.read(3)
    assert header.startswith(b"\xff\xd8\xff"), "file is not a real JPEG"
