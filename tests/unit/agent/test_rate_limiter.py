"""
Tests for Rate Limiter module.
"""

import pytest
import time
from datetime import datetime, timedelta
from src.agent.rate_limiter import RateLimiter


class TestRateLimiterInit:
    """Test RateLimiter initialization."""
    
    def test_init_empty(self):
        """Test initialization with no limits."""
        limiter = RateLimiter()
        assert limiter._limits == {}
        assert limiter.has_active_limits is False


class TestRateLimiterIsRateLimited:
    """Test rate limit checking."""
    
    def test_not_limited_initially(self):
        """Test that platform is not limited initially."""
        limiter = RateLimiter()
        assert limiter.is_rate_limited("linkedin") is False
    
    def test_is_limited_after_set(self):
        """Test that platform is limited after setting."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 1)  # 1 hour
        
        assert limiter.is_rate_limited("linkedin") is True
    
    def test_not_limited_after_expiry(self):
        """Test that limit expires correctly."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 0.0001)  # ~0.36 seconds
        
        assert limiter.is_rate_limited("linkedin") is True
        
        time.sleep(0.5)  # Wait for expiry
        
        assert limiter.is_rate_limited("linkedin") is False


class TestRateLimiterSetRateLimit:
    """Test setting rate limits."""
    
    def test_set_rate_limit(self):
        """Test setting a rate limit."""
        limiter = RateLimiter()
        limiter.set_rate_limit("naukri", 12)
        
        assert "naukri" in limiter._limits
        assert limiter.is_rate_limited("naukri") is True
    
    def test_set_multiple_limits(self):
        """Test setting limits for multiple platforms."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        limiter.set_rate_limit("naukri", 12)
        
        assert limiter.is_rate_limited("linkedin") is True
        assert limiter.is_rate_limited("naukri") is True


class TestRateLimiterGetRemainingTime:
    """Test getting remaining time."""
    
    def test_get_remaining_time_limited(self):
        """Test getting remaining time when limited."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 1)  # 1 hour
        
        remaining = limiter.get_remaining_time("linkedin")
        
        assert remaining is not None
        assert isinstance(remaining, timedelta)
        assert remaining.total_seconds() > 0
    
    def test_get_remaining_time_not_limited(self):
        """Test getting remaining time when not limited."""
        limiter = RateLimiter()
        
        remaining = limiter.get_remaining_time("linkedin")
        
        assert remaining is None


class TestRateLimiterGetRemainingHours:
    """Test getting remaining hours."""
    
    def test_get_remaining_hours_limited(self):
        """Test getting remaining hours when limited."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 2)  # 2 hours
        
        hours = limiter.get_remaining_hours("linkedin")
        
        assert hours > 1.9  # Should be approximately 2 hours
        assert hours <= 2.0
    
    def test_get_remaining_hours_not_limited(self):
        """Test getting remaining hours when not limited."""
        limiter = RateLimiter()
        
        hours = limiter.get_remaining_hours("linkedin")
        
        assert hours == 0.0


class TestRateLimiterClearRateLimit:
    """Test clearing rate limits."""
    
    def test_clear_existing_limit(self):
        """Test clearing an existing rate limit."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        
        result = limiter.clear_rate_limit("linkedin")
        
        assert result is True
        assert limiter.is_rate_limited("linkedin") is False
    
    def test_clear_nonexistent_limit(self):
        """Test clearing a non-existent rate limit."""
        limiter = RateLimiter()
        
        result = limiter.clear_rate_limit("linkedin")
        
        assert result is False


class TestRateLimiterGetAllRateLimits:
    """Test getting all rate limits."""
    
    def test_get_all_limits(self):
        """Test getting all active limits."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        limiter.set_rate_limit("naukri", 12)
        
        limits = limiter.get_all_rate_limits()
        
        assert len(limits) == 2
        assert "linkedin" in limits
        assert "naukri" in limits
    
    def test_get_all_limits_excludes_expired(self):
        """Test that expired limits are excluded."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        limiter.set_rate_limit("expired", 0.0001)  # ~0.36 seconds
        
        time.sleep(0.5)  # Wait for expiry
        
        limits = limiter.get_all_rate_limits()
        
        assert "linkedin" in limits
        assert "expired" not in limits


class TestRateLimiterClearAll:
    """Test clearing all limits."""
    
    def test_clear_all(self):
        """Test clearing all rate limits."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        limiter.set_rate_limit("naukri", 12)
        limiter.set_rate_limit("instahyre", 6)
        
        limiter.clear_all()
        
        assert limiter.is_rate_limited("linkedin") is False
        assert limiter.is_rate_limited("naukri") is False
        assert limiter.is_rate_limited("instahyre") is False
        assert limiter.has_active_limits is False


class TestRateLimiterHasActiveLimits:
    """Test checking for active limits."""
    
    def test_has_active_limits_true(self):
        """Test when limits are active."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        
        assert limiter.has_active_limits is True
    
    def test_has_active_limits_false(self):
        """Test when no limits are active."""
        limiter = RateLimiter()
        
        assert limiter.has_active_limits is False


class TestRateLimiterStringRepresentation:
    """Test string representation."""
    
    def test_str_no_limits(self):
        """Test string when no limits."""
        limiter = RateLimiter()
        
        result = str(limiter)
        
        assert "No active rate limits" in result
    
    def test_str_with_limits(self):
        """Test string when limits exist."""
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        
        result = str(limiter)
        
        assert "Active rate limits" in result
        assert "linkedin" in result
