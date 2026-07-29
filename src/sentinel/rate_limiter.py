"""
Rate Limiter Module - Prevents bot detection via adaptive delays.

Provides per-platform rate limiting with exponential backoff on errors,
enforced minimum delays between actions, and jitter to mimic human pacing.
"""

import asyncio
import random
import time
from typing import Dict, Optional


class RateLimiter:
    DEFAULT_DELAYS = {
        "naukri": 1.5,
        "linkedin": 2.0,
        "instahyre": 1.5,
        "default": 1.0,
    }

    MAX_BACKOFF = 60.0  # Cap backoff at 60 seconds

    def __init__(self, custom_delays: Optional[Dict[str, float]] = None):
        self._last_action: Dict[str, float] = {}
        self._backoff_until: Dict[str, float] = {}
        self._error_counts: Dict[str, int] = {}
        self._delays = dict(self.DEFAULT_DELAYS)
        if custom_delays:
            self._delays.update(custom_delays)

    def record_action(self, platform: str) -> None:
        """Record a successful action timestamp for the given platform."""
        self._last_action[platform.lower()] = time.monotonic()

    def record_error(self, platform: str, multiplier: float = 2.0) -> None:
        """Increase backoff after an error on a platform."""
        pl = platform.lower()
        self._error_counts[pl] = self._error_counts.get(pl, 0) + 1
        delay = self._delays.get(pl, self._delays["default"])
        backoff = min(delay * (multiplier ** self._error_counts[pl]), self.MAX_BACKOFF)
        self._backoff_until[pl] = time.monotonic() + backoff

    def reset_errors(self, platform: str) -> None:
        """Reset error backoff for a platform (e.g., after a successful action)."""
        pl = platform.lower()
        self._error_counts[pl] = 0
        if pl in self._backoff_until:
            del self._backoff_until[pl]

    async def wait_if_needed(self, platform: str) -> None:
        """Async sleep if we are within the rate limit window for the platform."""
        pl = platform.lower()
        now = time.monotonic()

        # Apply any active backoff from prior errors
        backoff_until = self._backoff_until.get(pl, 0)
        if now < backoff_until:
            sleep = backoff_until - now
            await asyncio.sleep(sleep)
            now = time.monotonic()

        # Enforce minimum delay between actions
        last = self._last_action.get(pl, 0)
        min_delay = self._delays.get(pl, self._delays["default"])
        jitter = random.uniform(0.0, 0.3)
        elapsed = now - last
        if elapsed < min_delay + jitter:
            await asyncio.sleep(min_delay + jitter - elapsed)

        self.record_action(pl)

    def peek_backoff(self, platform: str) -> float:
        """Return seconds remaining in current backoff (0 if none)."""
        pl = platform.lower()
        now = time.monotonic()
        until = self._backoff_until.get(pl, 0)
        return max(0.0, until - now)
