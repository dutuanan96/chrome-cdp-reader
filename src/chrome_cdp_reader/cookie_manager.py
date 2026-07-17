"""
Cookie Manager - Create a dedicated Chrome debug profile directory.

NOTE: This tool NO LONGER copies cookies or any data from your default
Chrome profile. Chrome 136+ encrypts each profile with a separate key, so a
copied cookie database cannot be decrypted by the debug profile. Instead we
create an empty, dedicated debug profile and you log in ONCE; subsequent runs
reuse that same profile (cookies persist inside it).

This avoids ever touching your passwords (Login Data) or main cookies.
"""

import os
from typing import Optional

from chrome_cdp_reader.utils import detect_windows_user


class CookieManager:
    """
    Manages the dedicated Chrome debug profile directory.

    Usage:
        manager = CookieManager()
        manager.create_debug_profile()
        print(manager.debug_profile)
    """

    def __init__(
        self,
        win_user: Optional[str] = None,
        debug_profile_name: str = "chrome-debug-profile"
    ):
        """
        Initialize CookieManager.

        Args:
            win_user: Windows username (auto-detected if None)
            debug_profile_name: Name of the debug profile directory
        """
        self.win_user = win_user or detect_windows_user()
        self.debug_profile_name = debug_profile_name

        # Windows path to the dedicated debug profile.
        self.debug_profile = f"C:\\Users\\{self.win_user}\\{debug_profile_name}"

    def create_debug_profile(self) -> bool:
        """
        Create the dedicated debug profile directory structure.

        Returns:
            True if the directory exists (created or already present)
        """
        try:
            os.makedirs(self.debug_profile, exist_ok=True)
            return os.path.isdir(self.debug_profile)
        except Exception as e:
            print(f"Error creating debug profile: {e}")
            return False

    def profile_exists(self) -> bool:
        """Return True if the debug profile directory already exists."""
        return os.path.isdir(self.debug_profile)

    def get_status(self) -> dict:
        """
        Get debug profile status.

        Returns:
            Dictionary with status info
        """
        return {
            "win_user": self.win_user,
            "debug_profile": self.debug_profile,
            "exists": self.profile_exists(),
        }


__all__ = ["CookieManager"]
