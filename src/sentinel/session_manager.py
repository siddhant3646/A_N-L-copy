"""
Session Manager Module - Detects and recovers from broken browser sessions.

Tracks session health (page crashes, navigation drift, timeouts) and provides
recovery strategies such as reload, re-navigation, and graceful shutdown.
"""

import time
from typing import Optional
from playwright.async_api import Page


class SessionManager:
    def __init__(self, max_inactive_seconds: float = 300.0):
        self.start_time = time.monotonic()
        self.last_url: Optional[str] = None
        self.last_title: Optional[str] = None
        self.last_activity = time.monotonic()
        self.max_inactive = max_inactive_seconds
        self.crashes = 0
        self.max_crashes = 3

    def record_activity(self, url: Optional[str] = None, title: Optional[str] = None) -> None:
        self.last_activity = time.monotonic()
        if url:
            self.last_url = url
        if title:
            self.last_title = title

    async def check_health(self, page: Optional[Page]) -> dict:
        """
        Check session health of the given page.

        Returns: { "healthy": bool, "reason": str, "crashes": int }
        """
        if page is None:
            return {"healthy": False, "reason": "Page is None", "crashes": self.crashes}

        try:
            closed = page.is_closed()
        except Exception:
            closed = True

        if closed:
            self.crashes += 1
            return {"healthy": False, "reason": "Page closed / crashed", "crashes": self.crashes}

        now = time.monotonic()
        inactive = now - self.last_activity
        if inactive > self.max_inactive:
            return {
                "healthy": False,
                "reason": f"Inactive for {inactive:.0f}s (max {self.max_inactive}s)",
                "crashes": self.crashes,
            }

        try:
            current_url = page.url
            current_title = await page.title()
        except Exception as e:
            return {"healthy": False, "reason": f"Page interaction error: {e}", "crashes": self.crashes}

        self.last_url = current_url
        self.last_title = current_title
        return {"healthy": True, "reason": "OK", "crashes": self.crashes}

    async def recover(self, page: Optional[Page], expected_url: Optional[str] = None) -> bool:
        """
        Attempt to revive the session by reloading or re-navigating.

        Returns True if recovery succeeded.
        """
        if page is None or page.is_closed():
            return False

        url_to_use = expected_url or self.last_url
        try:
            await page.reload(timeout=10000)
            if url_to_use and page.url != url_to_use:
                await page.goto(url_to_use, timeout=15000, wait_until="domcontentloaded")
            self.record_activity(url=page.url)
            return True
        except Exception as e:
            return False

    def should_stop(self) -> bool:
        """Return True if session has crashed too many times to continue."""
        return self.crashes >= self.max_crashes
