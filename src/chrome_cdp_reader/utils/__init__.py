"""
WSL Network Utilities
"""

import json
from urllib.request import urlopen
from urllib.error import URLError
from typing import Dict, Any


def check_cdp_connection(port: int = 9222) -> Dict[str, Any]:
    """
    Check if Chrome CDP is reachable.
    
    Args:
        port: Chrome debugging port
        
    Returns:
        Dictionary with connection status
    """
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {
                "connected": True,
                "browser": data.get("Browser", ""),
                "protocol": data.get("Protocol-Version", ""),
                "web_socket": data.get("webSocketDebuggerUrl", "")
            }
    except URLError:
        return {
            "connected": False,
            "error": "Cannot connect to Chrome CDP"
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e)
        }


def get_tabs(port: int = 9222) -> list:
    """
    Get list of open Chrome tabs.
    
    Args:
        port: Chrome debugging port
        
    Returns:
        List of tab info dictionaries
    """
    try:
        url = f"http://127.0.0.1:{port}/json/list"
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception:
        return []


__all__ = ["check_cdp_connection", "get_tabs"]
