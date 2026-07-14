"""
Basic tests for chrome-cdp-reader (Extension architecture)
"""

import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock


class TestExtensionBridge:
    """Tests for ExtensionBridge class."""
    
    def test_import(self):
        """Test mcp_server module can be imported."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        assert spec is not None
    
    def test_auth_token_loaded(self):
        """Test AUTH_TOKEN is loaded from env or default."""
        import os
        os.environ.pop('MCP_AUTH_TOKEN', None)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert len(mod.AUTH_TOKEN) >= 32
    
    def test_create_ws_app(self):
        """Test create_ws_app returns valid aiohttp app."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        app = mod.create_ws_app()
        assert app is not None
        assert '/ws' in [r.get_info()['path'] for r in app.router.routes()]


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_handler_exists(self):
        """Test health_handler function exists."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, 'health_handler')


class TestWebSocketServer:
    """Tests for WebSocketServerThread."""
    
    def test_class_exists(self):
        """Test WebSocketServerThread class exists."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, 'WebSocketServerThread')
    
    def test_server_starts(self):
        """Test WebSocket server can start on port 8765."""
        import importlib.util
        import time
        import socket
        
        spec = importlib.util.spec_from_file_location(
            'mcp_server',
            'src/chrome_cdp_reader/mcp_server.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        # Kill any existing process on 8765
        import subprocess
        subprocess.run(['lsof', '-ti:8765', '|', 'xargs', 'kill', '-9'], 
                      shell=True, capture_output=True)
        time.sleep(1)
        
        server = mod.WebSocketServerThread(port=8766)  # Use different port for test
        server.start(timeout=5)
        
        time.sleep(2)
        
        # Check port is open
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = s.connect_ex(('127.0.0.1', 8766))
        s.close()
        
        assert result == 0, "Server port should be open"
        
        # Cleanup
        if server.loop:
            server.loop.call_soon_threadsafe(server.loop.stop)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
