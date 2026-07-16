"""
Chrome Launcher - Launch Chrome with debug mode enabled
"""

import os
import subprocess
import time
from typing import Optional

from chrome_cdp_reader.utils import detect_windows_user


class ChromeLauncher:
    """
    Launch Chrome with remote debugging enabled.
    
    Usage:
        launcher = ChromeLauncher()
        launcher.launch()
    """
    
    def __init__(
        self,
        win_user: Optional[str] = None,
        debug_port: int = 9222,
        debug_profile_name: str = "chrome-debug-profile",
        chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        allow_all_origins: bool = False
    ):
        """
        Initialize ChromeLauncher.
        
        Args:
            win_user: Windows username (auto-detected if None)
            debug_port: Chrome debugging port
            debug_profile_name: Name of the debug profile directory
            chrome_path: Path to Chrome executable
        """
        self.win_user = win_user or detect_windows_user()
        self.debug_port = debug_port
        self.debug_profile_name = debug_profile_name
        self.chrome_path = chrome_path
        self.allow_all_origins = allow_all_origins
        
    def _detect_windows_user(self) -> str:
        """Deprecated: use chrome_cdp_reader.utils.detect_windows_user instead."""
        return detect_windows_user()

    def kill_chrome(self, only_debug_profile: bool = True) -> bool:
        """
        Kill Chrome processes.

        By default (only_debug_profile=True) only the Chrome instance bound to
        the debug port is killed, leaving other Chrome windows untouched.
        Pass only_debug_profile=False to kill every chrome.exe (legacy).

        Returns:
            True if successful
        """
        try:
            if only_debug_profile:
                # Kill only the process listening on the debug port (netstat + taskkill by PID)
                out = subprocess.run(
                    ["cmd.exe", "/c",
                     f"for /f \"tokens=5\" %p in ('netstat -ano ^| findstr :{self.debug_port} ^| findstr LISTENING') do taskkill /F /PID %p"],
                    capture_output=True, timeout=15
                )
            else:
                # Legacy: kill ALL Chrome (use with care)
                subprocess.run(
                    ["taskkill.exe", "/F", "/IM", "chrome.exe"],
                    capture_output=True, timeout=10
                )
            time.sleep(2)
            return True
        except Exception as e:
            print(f"Warning: Could not kill Chrome: {e}")
            return False
    
    def launch(self, headless: bool = False) -> bool:
        """
        Launch Chrome with remote debugging.
        
        Args:
            headless: Run Chrome in headless mode
            
        Returns:
            True if successful
        """
        debug_profile_path = f"C:\\Users\\{self.win_user}\\{self.debug_profile_name}"
        
        args = [
            self.chrome_path,
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={debug_profile_path}"
        ]
        
        # SECURITY: only enable --remote-allow-origins=* when explicitly requested
        # (e.g. cross-origin extension use). Default keeps Chrome's Origin-check
        # active to prevent arbitrary web pages from hijacking the CDP port.
        if self.allow_all_origins:
            args.append("--remote-allow-origins=*")
        
        if headless:
            args.append("--headless=new")
        
        try:
            # Launch Chrome via Windows
            subprocess.Popen(
                ["cmd.exe", "/c", "start", ""] + args,
                shell=False
            )
            
            # Wait for Chrome to start
            time.sleep(5)
            
            return True
            
        except Exception as e:
            print(f"Error launching Chrome: {e}")
            return False
    
    def verify_connection(self) -> dict:
        """
        Verify Chrome is running and CDP is accessible.
        
        Returns:
            Dictionary with connection status
        """
        import json
        from urllib.request import urlopen
        from urllib.error import URLError
        
        try:
            url = f"http://127.0.0.1:{self.debug_port}/json/version"
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                return {
                    "connected": True,
                    "browser": data.get("Browser", ""),
                    "protocol": data.get("Protocol-Version", "")
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
    
    def get_status(self) -> dict:
        """
        Get Chrome launcher status.
        
        Returns:
            Dictionary with status info
        """
        return {
            "win_user": self.win_user,
            "debug_port": self.debug_port,
            "debug_profile": f"C:\\Users\\{self.win_user}\\{self.debug_profile_name}",
            "chrome_path": self.chrome_path,
            "connection": self.verify_connection()
        }


__all__ = ["ChromeLauncher"]
