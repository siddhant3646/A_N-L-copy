"""
Profile Manager Module - Manage browser profile lifecycle.

This module handles the creation, cleanup, and management of browser
profile directories to prevent accumulation and stale session data.
"""

import os
import shutil
from pathlib import Path
from typing import Optional


class ProfileManager:
    """
    Manages browser profile folder lifecycle.
    
    Handles profile directory cleanup at cycle start/end to prevent
    disk space issues and stale session problems.
    """
    
    DEFAULT_PROFILE_DIR = "p"
    
    def __init__(self, profile_dir: Optional[str] = None):
        """
        Initialize ProfileManager.
        
        Args:
            profile_dir: Path to profile directory. Uses 'p' in cwd if None.
        """
        if profile_dir is None:
            profile_dir = os.path.join(os.getcwd(), self.DEFAULT_PROFILE_DIR)
        
        self.profile_dir = Path(profile_dir)
        self._cleanup_count = 0
    
    def cleanup(self) -> bool:
        """
        Delete profile folder.
        
        Returns:
            True if successful or directory didn't exist
        """
        if not self.profile_dir.exists():
            return True
        
        try:
            shutil.rmtree(self.profile_dir, ignore_errors=True)
            self._cleanup_count += 1
            print("🧹 Profile folder cleaned up")
            return True
        except Exception as e:
            print(f"⚠️ Profile cleanup failed: {e}")
            return False
    
    def ensure_fresh(self) -> str:
        """
        Ensure fresh profile folder exists.
        
        Removes existing profile if present, then creates new directory.
        
        Returns:
            Path to profile directory
        """
        self.cleanup()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        return str(self.profile_dir)
    
    def is_profile_present(self) -> bool:
        """
        Check if profile folder exists.
        
        Returns:
            True if profile directory exists
        """
        return self.profile_dir.exists() and self.profile_dir.is_dir()
    
    def get_profile_size(self) -> int:
        """
        Get profile folder size in bytes.
        
        Returns:
            Size in bytes
        """
        if not self.is_profile_present():
            return 0
        
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(self.profile_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
        except Exception as e:
            print(f"⚠️ Error calculating profile size: {e}")
        
        return total_size
    
    def get_profile_size_mb(self) -> float:
        """
        Get profile folder size in MB.
        
        Returns:
            Size in megabytes
        """
        return self.get_profile_size() / (1024 * 1024)
    
    @property
    def cleanup_count(self) -> int:
        """Number of times cleanup has been performed."""
        return self._cleanup_count
    
    @classmethod
    def cleanup_static(cls, profile_dir: Optional[str] = None) -> bool:
        """
        Static method to cleanup profile folder.
        
        Args:
            profile_dir: Path to profile directory
            
        Returns:
            True if successful
        """
        manager = cls(profile_dir)
        return manager.cleanup()
    
    @classmethod
    def ensure_fresh_static(cls, profile_dir: Optional[str] = None) -> str:
        """
        Static method to ensure fresh profile folder.
        
        Args:
            profile_dir: Path to profile directory
            
        Returns:
            Path to profile directory
        """
        manager = cls(profile_dir)
        return manager.ensure_fresh()
