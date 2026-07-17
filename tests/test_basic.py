"""
Basic tests for chrome-cdp-reader
"""

from unittest.mock import Mock, patch
from chrome_cdp_reader.bridge import ChromeReader
from chrome_cdp_reader.cookie_manager import CookieManager
from chrome_cdp_reader.chrome_launcher import ChromeLauncher


class TestChromeReader:
    """Tests for ChromeReader class."""

    def test_init_default(self):
        """Test ChromeReader initialization with defaults."""
        reader = ChromeReader()
        assert reader.cdp_url == "http://127.0.0.1:9222"

    def test_init_custom_url(self):
        """Test ChromeReader initialization with custom URL."""
        reader = ChromeReader(cdp_url="http://localhost:9333")
        assert reader.cdp_url == "http://localhost:9333"

    @patch('chrome_cdp_reader.bridge.urlopen')
    def test_is_connected_success(self, mock_urlopen):
        """Test is_connected returns True when Chrome is reachable."""
        mock_response = Mock()
        mock_response.read.return_value = b'{"Browser": "Chrome/120.0.0.0"}'
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        reader = ChromeReader()
        assert reader.is_connected() is True

    @patch('chrome_cdp_reader.bridge.urlopen')
    def test_is_connected_failure(self, mock_urlopen):
        """Test is_connected returns False when Chrome is not reachable."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        reader = ChromeReader()
        assert reader.is_connected() is False


class TestCookieManager:
    """Tests for CookieManager class."""

    def test_init_default(self):
        """Test CookieManager initialization with defaults."""
        manager = CookieManager(win_user="TestUser")
        assert manager.debug_profile_name == "chrome-debug-profile"

    def test_init_custom(self):
        """Test CookieManager initialization with custom values."""
        manager = CookieManager(win_user="TestUser", debug_profile_name="my-profile")
        assert manager.win_user == "TestUser"
        assert manager.debug_profile_name == "my-profile"


class TestChromeLauncher:
    """Tests for ChromeLauncher class."""

    def test_init_default(self):
        """Test ChromeLauncher initialization with defaults."""
        launcher = ChromeLauncher(win_user="TestUser")
        assert launcher.debug_port == 9222

    def test_init_custom(self):
        """Test ChromeLauncher initialization with custom values."""
        launcher = ChromeLauncher(win_user="TestUser", debug_port=9333)
        assert launcher.debug_port == 9333

    def test_default_launch_args_no_origin_flag(self):
        """
        Regression (Claude + live 403): with suppress_origin=True in
        _connect(), the launcher must NOT pass any --remote-allow-origins
        flag. Chromium accepts the connection because the client suppresses
        the Origin header (non-browser CDP client).
        """
        launcher = ChromeLauncher(win_user="TestUser")
        args = launcher._build_launch_args()
        assert not any(a.startswith("--remote-allow-origins") for a in args)


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_version(self):
        """Test CLI version command."""
        from click.testing import CliRunner
        from chrome_cdp_reader.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        # version must match the package version (single source of truth)
        from chrome_cdp_reader import __version__
        assert __version__ in result.output

    def test_cli_status_no_keyerror(self, monkeypatch):
        """crc status must not raise KeyError (regression P0#2)."""
        from click.testing import CliRunner
        from chrome_cdp_reader.cli import cli

        # CI runs on Ubuntu where detect_windows_user() would fail; pin it.
        monkeypatch.setenv("WIN_USER", "TestUser")
        runner = CliRunner()
        # Without Chrome, status still prints profile info (no exception)
        result = runner.invoke(cli, ['status'], env={"WIN_USER": "TestUser"})
        assert result.exit_code == 0, result.output
        assert "Debug Profile" in result.output

    def test_gmail_search_url_encoded(self, monkeypatch):
        """Production read_gmail must URL-encode the search query."""
        from chrome_cdp_reader.bridge import ChromeReader
        reader = ChromeReader()
        captured = {}

        def fake_read(url, wait=5):
            captured["url"] = url
            return {}

        monkeypatch.setattr(reader, "read", fake_read)
        reader.read_gmail("from:github work/foo#bar")
        url = captured["url"]
        assert "%2F" in url, "slash not encoded"
        assert "%23" in url, "hash not encoded"
        assert "work/foo#bar" not in url, "raw unsafe chars leaked"
