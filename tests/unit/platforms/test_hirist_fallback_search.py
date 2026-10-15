"""Unit tests for Hirist random fallback search URLs when job feed is empty."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestHiristFallbackSearch(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()

    def test_default_fallback_urls_contains_required_urls(self):
        """HIRIST_DEFAULT_FALLBACK_URLS contains the required 4 search URLs."""
        expected_urls = [
            "https://www.hirist.tech/k/full-stack-jobs?ref=topnavigation",
            "https://www.hirist.tech/k/java-jobs?ref=popular_tag",
            "https://www.hirist.tech/k/spring-jobs?ref=topnavigation",
            "https://www.hirist.tech/k/reactjs-jobs?ref=topnavigation",
        ]
        self.assertTrue(hasattr(self.agent, "HIRIST_DEFAULT_FALLBACK_URLS"))
        for url in expected_urls:
            self.assertIn(url, self.agent.HIRIST_DEFAULT_FALLBACK_URLS)

    async def test_hirist_has_no_jobs_detection(self):
        """_hirist_has_no_jobs detects 'No result found' and variations."""
        mock_page = MagicMock()

        # Case 1: 'Sorry, No result found :('
        async def evaluate_empty(script):
            return True

        mock_page.evaluate = AsyncMock(side_effect=evaluate_empty)
        is_empty = await self.agent._hirist_has_no_jobs(mock_page)
        self.assertTrue(is_empty)

        # Case 2: Page with jobs
        async def evaluate_with_jobs(script):
            return False

        mock_page.evaluate = AsyncMock(side_effect=evaluate_with_jobs)
        has_jobs = await self.agent._hirist_has_no_jobs(mock_page)
        self.assertFalse(has_jobs)

    async def test_handle_hirist_apply_task_falls_back_when_feed_empty(self):
        """When the feed has no jobs, agent navigates to a random fallback URL and applies."""
        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/jobfeed"
        visited_urls = []

        async def fake_goto(url, **kwargs):
            visited_urls.append(url)
            mock_page.url = url

        mock_page.goto = AsyncMock(side_effect=fake_goto)
        self.agent._page = mock_page
        self.agent._hirist_dismiss_dialogs = AsyncMock()
        self.agent._hirist_read_meta = AsyncMock(return_value={"isLoggedIn": True})

        # Feed returns 0 jobs & shows no result; fallback returns 1 job
        async def fake_collect(page):
            if "jobfeed" in (page.url or ""):
                return []
            return [{"id": "12345", "url": "https://www.hirist.tech/j/java-lead-12345", "title": "Java Lead"}]

        self.agent._hirist_collect_jobs = AsyncMock(side_effect=fake_collect)

        async def fake_has_no_jobs(page):
            return "jobfeed" in (page.url or "")

        self.agent._hirist_has_no_jobs = AsyncMock(side_effect=fake_has_no_jobs)
        self.agent._hirist_click_apply = AsyncMock(return_value="applied")
        self.agent._hirist_handle_questionnaire = AsyncMock(return_value=False)
        self.agent._hirist_verify_applied = AsyncMock(return_value=True)
        self.agent._hirist_confirm_modal = AsyncMock()

        with patch.dict(os.environ, {"HIRIST_MAX_APPLICATIONS": "1"}):
            success = await self.agent._handle_hirist_apply_task()

        self.assertTrue(success)
        # Check that visited_urls visited at least one of the fallback URLs
        fallback_visited = [u for u in visited_urls if "/k/" in u]
        self.assertGreaterEqual(len(fallback_visited), 1)
        self.assertIn(fallback_visited[0], self.agent.HIRIST_DEFAULT_FALLBACK_URLS)
        self.assertEqual(self.agent.metrics.get("applications_submitted"), 1)

    async def test_handle_hirist_apply_task_exhausts_multiple_fallbacks(self):
        """If one fallback URL has fewer jobs than max_applications, agent tries next fallback."""
        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/jobfeed"
        visited_urls = []

        async def fake_goto(url, **kwargs):
            visited_urls.append(url)
            mock_page.url = url

        mock_page.goto = AsyncMock(side_effect=fake_goto)
        self.agent._page = mock_page
        self.agent._hirist_dismiss_dialogs = AsyncMock()
        self.agent._hirist_read_meta = AsyncMock(return_value={"isLoggedIn": True})

        # Each URL returns 1 job; max_applications = 2
        call_count = {"k_calls": 0}

        async def fake_collect(page):
            if "jobfeed" in (page.url or ""):
                return []
            call_count["k_calls"] += 1
            return [{"id": f"job_{call_count['k_calls']}", "url": f"https://www.hirist.tech/j/job_{call_count['k_calls']}", "title": "Dev"}]

        self.agent._hirist_collect_jobs = AsyncMock(side_effect=fake_collect)
        self.agent._hirist_has_no_jobs = AsyncMock(side_effect=lambda p: "jobfeed" in (p.url or ""))
        self.agent._hirist_click_apply = AsyncMock(return_value="applied")
        self.agent._hirist_handle_questionnaire = AsyncMock(return_value=False)
        self.agent._hirist_verify_applied = AsyncMock(return_value=True)
        self.agent._hirist_confirm_modal = AsyncMock()

        with patch.dict(os.environ, {"HIRIST_MAX_APPLICATIONS": "2"}):
            success = await self.agent._handle_hirist_apply_task()

        self.assertTrue(success)
        fallback_visited = [u for u in visited_urls if "/k/" in u]
        self.assertGreaterEqual(len(fallback_visited), 2)
        self.assertEqual(self.agent.metrics.get("applications_submitted"), 2)


if __name__ == "__main__":
    unittest.main()
