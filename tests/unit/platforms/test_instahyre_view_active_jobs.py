import unittest
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts


class TestInstahyreViewActiveJobs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        self.mock_page = AsyncMock()
        self.mock_page.url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
        self.mock_page.is_closed = MagicMock(return_value=False)
        self.mock_page.keyboard = AsyncMock()
        self.mock_page.evaluate = AsyncMock(return_value=True)
        self.mock_page.context = MagicMock()
        self.mock_page.context.pages = [self.mock_page]
        self.agent._page = self.mock_page

    def test_prompts_include_view_active_jobs_instruction(self):
        """Verify prompt contains explicit instruction to skip View active jobs."""
        for prompt_name, prompt in [
            ("INSTAHYRE_SEARCH_TASK", prompts.INSTAHYRE_SEARCH_TASK),
            ("INSTAHYRE_INTERSESSION_TASK", prompts.INSTAHYRE_INTERSESSION_TASK),
        ]:
            self.assertIn("View active jobs", prompt, f"Missing 'View active jobs' in {prompt_name}")
            self.assertIn("proceed to next job", prompt, f"Missing 'proceed to next job' in {prompt_name}")

    async def test_view_active_jobs_skipped_handling(self):
        """Verify INSTAHYRE_VIEW_ACTIVE_JOBS_SKIPPED resets view count, presses Escape, and does not increment apply count."""
        self.agent._instahyre_consecutive_views = 2
        self.agent._instahyre_apply_count = 0

        # Simulate script fallback returning INSTAHYRE_VIEW_ACTIVE_JOBS_SKIPPED then view then apply
        with patch.object(self.agent, '_handle_scripted_fallback', new=AsyncMock(side_effect=[
            'INSTAHYRE_VIEW_ACTIVE_JOBS_SKIPPED',
            'INSTAHYRE_VIEW_CLICKED',
            'INSTAHYRE_APPLY_CLICKED',
        ])), patch.object(self.agent, '_check_page_health', new=AsyncMock(return_value=True)), \
           patch.object(self.agent, '_check_login_state', new=AsyncMock(return_value=True)), \
           patch.object(self.agent._session_manager, 'check_health', new=AsyncMock(return_value={"healthy": True})), \
           patch.object(self.agent, '_get_max_steps', return_value=3), \
           patch('asyncio.sleep', new=AsyncMock()):

            # Execute run for 3 steps
            await self.agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

            # Check that Escape was pressed to dismiss modal
            self.mock_page.keyboard.press.assert_any_call('Escape')

            # Check that apply count only incremented once (for INSTAHYRE_APPLY_CLICKED, not for SKIPPED)
            self.assertEqual(self.agent._instahyre_apply_count, 1)

    async def test_consecutive_scrolls_capped_at_three_breaks_task(self):
        """Verify that 3 consecutive scrolling events terminate the task gracefully without infinite loop."""
        with patch.object(self.agent, '_handle_scripted_fallback', new=AsyncMock(side_effect=[
            'INSTAHYRE_ALL_APPLIED_SCROLLING',
            'INSTAHYRE_ALL_APPLIED_SCROLLING',
            'INSTAHYRE_ALL_APPLIED_SCROLLING',
        ])), patch.object(self.agent, '_check_page_health', new=AsyncMock(return_value=True)), \
           patch.object(self.agent, '_check_login_state', new=AsyncMock(return_value=True)), \
           patch.object(self.agent._session_manager, 'check_health', new=AsyncMock(return_value={"healthy": True})), \
           patch.object(self.agent, '_get_max_steps', return_value=10), \
           patch('asyncio.sleep', new=AsyncMock()):

            await self.agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

            self.assertTrue(self.agent.state.task_complete)
            self.assertTrue(self.agent._last_instahyre_no_more_jobs)
            self.assertEqual(self.agent._instahyre_consecutive_scrolls, 0)

    def test_js_fallback_contains_view_active_jobs_detection(self):
        """Verify JS code in _handle_scripted_fallback contains View active jobs handling."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("view active jobs", src)
        self.assertIn("INSTAHYRE_VIEW_ACTIVE_JOBS_SKIPPED", src)
        self.assertIn("data-sentinel-skipped", src)

    def test_js_fallback_contains_exhaustion_detection(self):
        """Verify JS code contains showingMatch, searchResultsMatch and scroll limit detection."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("showingMatch", src)
        self.assertIn("searchResultsMatch", src)
        self.assertIn("instahyre_all_applied_scrolls", src)
        self.assertIn("INSTAHYRE_NO_MORE_JOBS", src)


if __name__ == '__main__':
    unittest.main()

