"""
Rate Limiter Module - Rate limiting for platforms.

This module provides rate limiting functionality to prevent
excessive requests to job platforms.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict


class RateLimiter:
    """
    Manages rate limiting for job platforms.
    
    Tracks when platforms have rate limited the user and prevents
    further requests until the rate limit period has expired.
    """
    
    def __init__(self):
        """Initialize rate limiter."""
        self._limits: Dict[str, datetime] = {}
    
    def is_rate_limited(self, platform: str) -> bool:
        """
        Check if platform is currently rate limited.
        
        Args:
            platform: Platform identifier
            
        Returns:
            True if rate limited
        """
        if platform not in self._limits:
            return False
        
        limit_until = self._limits[platform]
        return datetime.now() < limit_until
    
    def set_rate_limit(self, platform: str, duration_hours: float) -> None:
        """
        Set rate limit for a platform.
        
        Args:
            platform: Platform identifier
            duration_hours: How long to rate limit (in hours)
        """
        until = datetime.now() + timedelta(hours=duration_hours)
        self._limits[platform] = until
        print(f"⏳ {platform} rate limited until {until.strftime('%Y-%m-%d %H:%M')}")
    
    def get_remaining_time(self, platform: str) -> Optional[timedelta]:
        """
        Get remaining rate limit time.
        
        Args:
            platform: Platform identifier
            
        Returns:
            Timedelta until limit expires, or None if not rate limited
        """
        if not self.is_rate_limited(platform):
            return None
        
        return self._limits[platform] - datetime.now()
    
    def get_remaining_hours(self, platform: str) -> float:
        """
        Get remaining rate limit hours.
        
        Args:
            platform: Platform identifier
            
        Returns:
            Hours until limit expires, 0 if not rate limited
        """
        remaining = self.get_remaining_time(platform)
        if remaining is None:
            return 0.0
        
        return remaining.total_seconds() / 3600
    
    def clear_rate_limit(self, platform: str) -> bool:
        """
        Manually clear rate limit for a platform.
        
        Args:
            platform: Platform identifier
            
        Returns:
            True if limit was cleared
        """
        if platform in self._limits:
            del self._limits[platform]
            return True
        return False
    
    def get_all_rate_limits(self) -> Dict[str, datetime]:
        """
        Get all active rate limits.
        
        Returns:
            Dictionary of platform -> limit expiry datetime
        """
        # Filter out expired limits
        now = datetime.now()
        active = {
            platform: expiry
            for platform, expiry in self._limits.items()
            if expiry > now
        }
        
        # Update internal dict
        self._limits = active
        
        return active.copy()
    
    def clear_all(self) -> None:
        """Clear all rate limits."""
        self._limits.clear()
    
    @property
    def has_active_limits(self) -> bool:
        """Check if any rate limits are active."""
        return len(self.get_all_rate_limits()) > 0
    
    def __str__(self) -> str:
        """String representation of rate limits."""
        limits = self.get_all_rate_limits()
        if not limits:
            return "No active rate limits"
        
        lines = ["Active rate limits:"]
        for platform, expiry in limits.items():
            hours = (expiry - datetime.now()).total_seconds() / 3600
            lines.append(f"  {platform}: {hours:.1f} hours remaining")
        
        return "\n".join(lines)
