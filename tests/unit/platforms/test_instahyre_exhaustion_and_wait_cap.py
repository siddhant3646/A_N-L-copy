import unittest
import os
import sys
import inspect
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts


class TestInstahyreExhaustionAndWaitCap(unittest.IsolatedAsyncioTestCase):
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

    async def test_waiting_for_results_capped_at_five_breaks_task(self):
        """Verify that 5 consecutive INSTAHYRE_WAITING_FOR_RESULTS terminate the task cleanly without reaching max steps."""
        self.agent._instahyre_apply_count = 2

        with patch.object(self.agent, '_handle_scripted_fallback', new=AsyncMock(side_effect=[
            'INSTAHYRE_WAITING_FOR_RESULTS',
            'INSTAHYRE_WAITING_FOR_RESULTS',
            'INSTAHYRE_WAITING_FOR_RESULTS',
            'INSTAHYRE_WAITING_FOR_RESULTS',
            'INSTAHYRE_WAITING_FOR_RESULTS',
            'INSTAHYRE_WAITING_FOR_RESULTS',
        ])), patch.object(self.agent, '_check_page_health', new=AsyncMock(return_value=True)), \
           patch.object(self.agent, '_check_login_state', new=AsyncMock(return_value=True)), \
           patch.object(self.agent._session_manager, 'check_health', new=AsyncMock(return_value={"healthy": True})), \
           patch.object(self.agent, '_get_max_steps', return_value=120), \
           patch('asyncio.sleep', new=AsyncMock()):

            await self.agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

            self.assertTrue(self.agent.state.task_complete)
            self.assertTrue(self.agent._last_instahyre_no_more_jobs)
            self.assertEqual(self.agent._instahyre_wait_count, 0)
            self.assertEqual(self.agent._instahyre_apply_count, 0)
            # Must finish well before 120 steps (after 5 wait attempts)
            self.assertLessEqual(self.agent.state.step_count, 6)

    async def test_no_more_jobs_stops_immediately_and_sets_exhaustion(self):
        """Verify INSTAHYRE_NO_MORE_JOBS sets task_complete and _last_instahyre_no_more_jobs immediately."""
        self.agent._instahyre_apply_count = 3

        with patch.object(self.agent, '_handle_scripted_fallback', new=AsyncMock(side_effect=[
            'INSTAHYRE_NO_MORE_JOBS',
        ])), patch.object(self.agent, '_check_page_health', new=AsyncMock(return_value=True)), \
           patch.object(self.agent, '_check_login_state', new=AsyncMock(return_value=True)), \
           patch.object(self.agent._session_manager, 'check_health', new=AsyncMock(return_value={"healthy": True})), \
           patch.object(self.agent, '_get_max_steps', return_value=120), \
           patch('asyncio.sleep', new=AsyncMock()):

            await self.agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

            self.assertTrue(self.agent.state.task_complete)
            self.assertTrue(self.agent._last_instahyre_no_more_jobs)
            self.assertEqual(self.agent._instahyre_wait_count, 0)
            self.assertEqual(self.agent._instahyre_apply_count, 0)
            self.assertEqual(self.agent.state.step_count, 1)

    async def test_no_action_loop_marks_last_instahyre_no_more_jobs(self):
        """Verify that 8 consecutive NO_ACTION events set _last_instahyre_no_more_jobs and terminate."""
        with patch.object(self.agent, '_handle_scripted_fallback', new=AsyncMock(return_value='NO_ACTION')), \
           patch.object(self.agent, '_check_page_health', new=AsyncMock(return_value=True)), \
           patch.object(self.agent, '_check_login_state', new=AsyncMock(return_value=True)), \
           patch.object(self.agent._session_manager, 'check_health', new=AsyncMock(return_value={"healthy": True})), \
           patch.object(self.agent, '_get_max_steps', return_value=120), \
           patch('asyncio.sleep', new=AsyncMock()):

            await self.agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

            self.assertTrue(self.agent.state.task_complete)
            self.assertTrue(self.agent._last_instahyre_no_more_jobs)
            self.assertEqual(self.agent._instahyre_wait_count, 0)
            self.assertLessEqual(self.agent.state.step_count, 9)

    def test_reset_clears_instahyre_wait_count(self):
        """Verify agent.reset() clears _instahyre_wait_count and _last_instahyre_no_more_jobs."""
        self.agent._instahyre_wait_count = 4
        self.agent._last_instahyre_no_more_jobs = True
        self.agent.reset_per_task_state()
        self.assertEqual(self.agent._instahyre_wait_count, 0)
        self.assertFalse(self.agent._last_instahyre_no_more_jobs)

    def test_js_fallback_contains_spinner_visibility_and_empty_state_checks(self):
        """Verify JS code in _handle_scripted_fallback contains visible spinner checking and empty state checking."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("isSpinnerVisible", src)
        self.assertIn("noJobsIndicators", src)
        self.assertIn("isNoJobsConfirmed", src)
        self.assertIn("instahyre_wait_results_count", src)
        self.assertIn("INSTAHYRE_NO_MORE_JOBS", src)

    def test_js_fallback_wait_attempts_cap_and_no_jobs_return(self):
        """Verify JS code caps wait attempts at 5 and returns INSTAHYRE_NO_MORE_JOBS when wait is exceeded."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("waitAttempts < 5", src)
        self.assertIn("timeSinceClick < 12000", src)
        self.assertIn("INSTAHYRE_WAITING_FOR_RESULTS", src)


if __name__ == '__main__':
    unittest.main()
