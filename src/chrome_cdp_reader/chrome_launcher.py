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

    def _find_debug_chrome_pid(self) -> Optional[int]:
        """Return the PID of the Chrome instance that OWNS this launcher's debug
        port AND debug profile (verified via Get-NetTCPConnection + Win32_Process
        on Windows). Returns None if the port is free, occupied by a different
        process, or by a Chrome instance with a different user-data-dir.
        """
        try:
            ps = (
                "$pids = (Get-NetTCPConnection -LocalPort {port} -State Listen "
                "-ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique; "
                "$debugPid = $null; "
                "foreach ($p in $pids) {{ "
                "  $proc = Get-CimInstance Win32_Process -Filter \"ProcessId = $p\"; "
                "  if ($proc -and $proc.Name -eq 'chrome.exe' -and "
                "      $proc.CommandLine -match '--remote-debugging-port={port}' -and "
                "      $proc.CommandLine -match '{profile}') {{ $debugPid = $p }} "
                "}}; "
                "if ($debugPid -ne $null) {{ $debugPid | ConvertTo-Json -Compress }} "
                "else {{ 'null' }}"
            ).format(port=self.debug_port, profile=self.debug_profile_name)
            out = self._run_powershell(ps)
            if not out or out.strip() == "null":
                return None
            return int(out.strip())
        except Exception:
            return None

    def _find_intruder_on_port(self) -> Optional[dict]:
        """Return info about a process occupying the debug port that is NOT this
        launcher's debug Chrome (verified by Name + command line). None if the
        only occupant is our own debug Chrome or the port is free.
        """
        try:
            import json as _json
            ps = (
                "$pids = (Get-NetTCPConnection -LocalPort {port} -State Listen "
                "-ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique; "
                "$out = @(); "
                "foreach ($p in $pids) {{ "
                "  $proc = Get-CimInstance Win32_Process -Filter \"ProcessId = $p\"; "
                "  if ($proc) {{ $out += [pscustomobject]@{{ PID = $p; Name = $proc.Name; "
                "CommandLine = $proc.CommandLine }} }} "
                "}}; "
                "$out | ConvertTo-Json -Compress -Depth 3"
            ).format(port=self.debug_port)
            out = self._run_powershell(ps)
            if not out:
                return None
            data = _json.loads(out)
            items = data if isinstance(data, list) else [data]
            for it in items:
                cl = it.get("CommandLine") or ""
                if not (it.get("Name") == "chrome.exe"
                        and f"--remote-debugging-port={self.debug_port}" in cl
                        and self.debug_profile_name in cl):
                    return it
            return None
        except Exception:
            return None

    def _run_powershell(self, script: str, timeout: int = 25) -> str:
        """Execute a PowerShell script via a temp .ps1 file (avoids f-string /
        quote-escaping pitfalls). Returns stripped stdout.
        """
        import tempfile
        import os
        fd, path = tempfile.mkstemp(suffix=".ps1", prefix="crc_launch_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script)
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", path],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0 and proc.stderr.strip():
                raise RuntimeError(proc.stderr.strip())
            return proc.stdout.strip()
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    def kill_chrome(self, only_debug_profile: bool = True) -> bool:
        """
        Kill ONLY the Chrome instance that owns this launcher's debug port AND
        debug profile. Verifies process Name + command line (port + profile)
        before killing — never `taskkill /IM chrome.exe`.

        If the port is occupied by a DIFFERENT process (e.g. Python/Node/Docker),
        FAIL-FAST: refuse to kill it and return False so the caller does NOT
        launch a debug Chrome on top of it.

        Returns:
            True if the debug Chrome was killed (or was not running).
            False if an intruder occupies the port (fail-fast, no launch).
        """
        try:
            if only_debug_profile:
                intruder = self._find_intruder_on_port()
                if intruder and not (
                    intruder.get("Name") == "chrome.exe"
                    and self.debug_profile_name in (intruder.get("CommandLine") or "")
                ):
                    print(
                        f"[FAIL-FAST] Port {self.debug_port} occupied by "
                        f"{intruder.get('Name')} PID={intruder.get('PID')}"
                    )
                    print(f"  CommandLine: {intruder.get('CommandLine')}")
                    print("  Refusing to kill / launch Chrome debug.")
                    return False
                pid = self._find_debug_chrome_pid()
                if pid is None:
                    return True  # nothing to kill
                proc = subprocess.run(
                    ["taskkill.exe", "/F", "/PID", str(pid)],
                    capture_output=True, text=True, timeout=15,
                )
                if proc.returncode not in (0, 1):
                    print(f"Warning: taskkill PID {pid} returned {proc.returncode}")
                    return False
                # poll until the port is actually free
                import time as _time
                deadline = _time.monotonic() + 15
                while _time.monotonic() < deadline:
                    if (self._find_intruder_on_port() is None
                            and self._find_debug_chrome_pid() is None):
                        return True
                    _time.sleep(1.0)
                print(f"Warning: port {self.debug_port} still occupied after kill")
                return False
            else:
                # Legacy path kept for API compatibility but made SAFE:
                # still verify it is the debug Chrome before killing.
                pid = self._find_debug_chrome_pid()
                if pid is None:
                    return True
                proc = subprocess.run(
                    ["taskkill.exe", "/F", "/PID", str(pid)],
                    capture_output=True, text=True, timeout=15,
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
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
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
