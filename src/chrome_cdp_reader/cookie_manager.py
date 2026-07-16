"""
Cookie Manager - Copy cookies from default Chrome profile to debug profile
"""

import os
import shutil
import platform
from pathlib import Path
from typing import Optional

from chrome_cdp_reader.utils import detect_windows_user


class CookieManager:
    """
    Manages Chrome cookies between default and debug profiles.
    
    Usage:
        manager = CookieManager()
        manager.copy_cookies()
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
        
        # Paths
        self.win_home = f"/mnt/c/Users/{self.win_user}"
        self.default_profile = f"{self.win_home}/AppData/Local/Google/Chrome/User Data/Default"
        self.debug_profile = f"{self.win_home}/{debug_profile_name}/Default"
        
    def _detect_windows_user(self) -> str:
        """Deprecated: use chrome_cdp_reader.utils.detect_windows_user instead."""
        return detect_windows_user()

    def create_debug_profile(self) -> bool:
        """
        Create debug profile directory structure.
        
        Returns:
            True if successful
        """
        try:
            os.makedirs(self.debug_profile, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating debug profile: {e}")
            return False
    
    def copy_cookies(self) -> bool:
        """
        Copy cookies from default profile to debug profile.
        
        Returns:
            True if successful
        """
        files_to_copy = [
            "Cookies",
            "Preferences",
            "Local State"
        ]
        
        success = True
        for filename in files_to_copy:
            src = f"{self.default_profile}/{filename}"
            dst = f"{self.debug_profile}/{filename}"
            
            try:
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    print(f"✓ Copied {filename}")
                else:
                    print(f"⚠ {filename} not found in default profile")
            except Exception as e:
                print(f"✗ Failed to copy {filename}: {e}")
                success = False
        
        return success
    
    def verify_cookies(self) -> dict:
        """
        Verify cookie files exist in debug profile.
        
        Returns:
            Dictionary with verification results
        """
        results = {}
        files_to_check = ["Cookies", "Preferences", "Local State"]
        
        for filename in files_to_check:
            path = f"{self.debug_profile}/{filename}"
            results[filename] = {
                "exists": os.path.exists(path),
                "size": os.path.getsize(path) if os.path.exists(path) else 0
            }
        
        return results
    
    def get_status(self) -> dict:
        """
        Get cookie manager status.
        
        Returns:
            Dictionary with status info
        """
        return {
            "win_user": self.win_user,
            "default_profile": self.default_profile,
            "debug_profile": self.debug_profile,
            "default_exists": os.path.exists(self.default_profile),
            "debug_exists": os.path.exists(self.debug_profile),
            "cookies": self.verify_cookies()
        }


__all__ = ["CookieManager"]
