"""
Chrome Launcher - Launch Chrome with debug mode enabled
"""

import subprocess
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
            True if the targeted process was killed (or was not running);
            False if the kill command failed.
        """
        try:
            if only_debug_profile:
                # Kill only the process listening on the debug port (netstat + taskkill by PID)
                proc = subprocess.run(
                    ["cmd.exe", "/c",
                     f"for /f \"tokens=5\" %p in ('netstat -ano ^| findstr :{self.debug_port} ^| findstr LISTENING') do taskkill /F /PID %p"],
                    capture_output=True, text=True, timeout=15
                )
                # returncode 0/1 both okay: 1 just means "nothing matched"
                return proc.returncode in (0, 1)
            else:
                # Legacy: kill ALL Chrome (use with care)
                proc = subprocess.run(
                    ["taskkill.exe", "/F", "/IM", "chrome.exe"],
                    capture_output=True, text=True, timeout=10
                )
                return proc.returncode in (0, 1)
        except Exception as e:
            print(f"Warning: Could not kill Chrome: {e}")
            return False

    def _build_launch_args(self, headless: bool = False) -> list:
        """
        Build the Chrome command-line arguments for debug mode.

        SECURITY: Chrome 147+ enforces an Origin-check on the CDP WebSocket.
        websocket-client sends an `Origin: http://127.0.0.1:9222` header by
        default; Chromium rejects it unless the origin is allowlisted. Instead
        of opening an allowlist, we suppress the Origin header entirely
        (non-browser CDP client). No --remote-allow-origins flag needed, and
        no mismatch whether the debugger URL is localhost / 127.0.0.1 / IPv6.
        """
        debug_profile_path = f"C:\\Users\\{self.win_user}\\{self.debug_profile_name}"
        args = [
            self.chrome_path,
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={debug_profile_path}",
        ]
        if headless:
            args.append("--headless=new")
        return args

    def launch(self, headless: bool = False, timeout: int = 15) -> bool:
        """
        Launch Chrome with remote debugging.

        Args:
            headless: Run Chrome in headless mode
            timeout: Seconds to wait for CDP to become reachable

        Returns:
            True only if Chrome started AND CDP is reachable on the debug port.
        """
        args = self._build_launch_args(headless=headless)

        try:
            # Launch Chrome via Windows
            subprocess.Popen(
                ["cmd.exe", "/c", "start", ""] + args,
                shell=False
            )
        except Exception as e:
            print(f"Error launching Chrome: {e}")
            return False

        # Wait until CDP is actually reachable (no blind sleep)
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            status = self.verify_connection()
            if status.get("connected"):
                return True
            _time.sleep(0.5)
        print(f"Warning: Chrome launched but CDP not reachable on port {self.debug_port} after {timeout}s")
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
