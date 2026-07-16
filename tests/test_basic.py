"""
Basic tests for chrome-cdp-reader
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
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
        manager = CookieManager()
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
        launcher = ChromeLauncher()
        assert launcher.debug_port == 9222
    
    def test_init_custom(self):
        """Test ChromeLauncher initialization with custom values."""
        launcher = ChromeLauncher(debug_port=9333)
        assert launcher.debug_port == 9333


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
