"""
Chrome Launcher - Launch Chrome with debug mode enabled
"""

import os
import subprocess
import time
from typing import Optional


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
        chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ):
        """
        Initialize ChromeLauncher.
        
        Args:
            win_user: Windows username (auto-detected if None)
            debug_port: Chrome debugging port
            debug_profile_name: Name of the debug profile directory
            chrome_path: Path to Chrome executable
        """
        self.win_user = win_user or self._detect_windows_user()
        self.debug_port = debug_port
        self.debug_profile_name = debug_profile_name
        self.chrome_path = chrome_path
        
    def _detect_windows_user(self) -> str:
        """Detect Windows username from WSL."""
        try:
            users_dir = "/mnt/c/Users"
            if os.path.exists(users_dir):
                users = [u for u in os.listdir(users_dir) 
                        if not u.startswith('.') and u not in ['Public', 'Default', 'Default User']]
                if users:
                    return users[0]
        except Exception:
            pass
        return os.environ.get("WIN_USER", "HP")
    
    def kill_chrome(self) -> bool:
        """
        Kill all Chrome processes.
        
        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["taskkill.exe", "/F", "/IM", "chrome.exe"],
                capture_output=True,
                timeout=10
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
            "--remote-allow-origins=*",
            f"--user-data-dir={debug_profile_path}"
        ]
        
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
