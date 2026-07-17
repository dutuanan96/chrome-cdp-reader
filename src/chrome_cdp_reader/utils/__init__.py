"""
WSL utilities for chrome-cdp-reader.

Only `detect_windows_user()` is used by the package. The connection/tab
helpers were removed to avoid duplicating `ChromeReader.is_connected()` and
`ChromeReader.get_tabs()` in bridge.py.
"""

import os
import subprocess

__all__ = ["detect_windows_user"]


def detect_windows_user() -> str:
    """
    Detect the Windows username reliably.

    Order of preference:
        1. WIN_USER environment variable (explicit override)
        2. `cmd.exe /c echo %USERNAME%` (the real logged-in user)
        3. First real directory under /mnt/c/Users (fallback, may be wrong)
        4. Raise RuntimeError if nothing found (no silent "HP" guess)

    Returns:
        Windows username.

    Raises:
        RuntimeError: if no user can be determined.
    """
    # 1. Explicit override
    env_user = os.environ.get("WIN_USER")
    if env_user:
        return env_user

    # 2. Ask Windows for the real logged-in user
    try:
        proc = subprocess.run(
            ["cmd.exe", "/c", "echo", "%USERNAME%"],
            capture_output=True, text=True, timeout=10
        )
        out = proc.stdout.strip()
        if out and out.upper() != "%USERNAME%":
            return out
    except Exception:
        pass

    # 3. Fallback: first real directory under /mnt/c/Users
    try:
        users_dir = "/mnt/c/Users"
        if os.path.exists(users_dir):
            users = [u for u in os.listdir(users_dir)
                     if not u.startswith('.') and u not in ['Public', 'Default', 'Default User']]
            if users:
                return users[0]
    except Exception:
        pass

    # 4. No guess — require the user to set WIN_USER explicitly
    raise RuntimeError(
        "Could not detect Windows user. Set the WIN_USER environment variable "
        "(e.g. export WIN_USER=HP) and retry."
    )
