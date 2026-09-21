import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestNaukriRateLimitDetection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        self.agent._task_description = "Apply to Naukri jobs"
        self.mock_page = AsyncMock()
        self.mock_page.url = "https://www.naukri.com/mnjuser/recommendedjobs"
        self.agent._page = self.mock_page

    async def test_poll_returns_signal_when_toast_visible(self):
        self.mock_page.evaluate = AsyncMock(
            return_value="NAUKRI_RATE_LIMITED: Error snackbar detected (some error)"
        )
        with patch.object(self.agent, '_inject_patterns_once', new=AsyncMock()):
            result = await self.agent._poll_naukri_error_snackbar(attempts=1, interval=0.01)
        self.assertIn('NAUKRI_RATE_LIMITED', result)

    async def test_poll_returns_empty_when_no_toast(self):
        self.mock_page.evaluate = AsyncMock(return_value=None)
        with patch.object(self.agent, '_inject_patterns_once', new=AsyncMock()):
            result = await self.agent._poll_naukri_error_snackbar(attempts=2, interval=0.01)
        self.assertEqual(result, '')
        self.assertEqual(self.mock_page.evaluate.await_count, 2)

    async def test_poll_js_handles_fixed_toast_visibility(self):
        self.mock_page.evaluate = AsyncMock(return_value=None)
        with patch.object(self.agent, '_inject_patterns_once', new=AsyncMock()):
            await self.agent._poll_naukri_error_snackbar(attempts=1, interval=0.01)
        check_js = self.mock_page.evaluate.await_args_list[0].args[0]
        self.assertIn('__SENTINEL_ISVISIBLE__', check_js)
        self.assertIn('getBoundingClientRect', check_js)
        self.assertNotIn('snack.offsetParent === null', check_js)

    async def test_inject_patterns_defines_visibility_helper(self):
        self.agent._profile_store = None
        self.mock_page.evaluate = AsyncMock(side_effect=[False, True])
        await self.agent._inject_patterns_once()
        init_script = self.mock_page.evaluate.await_args_list[1].args[0]
        self.assertIn('__SENTINEL_ISVISIBLE__', init_script)
        self.assertIn('getBoundingClientRect', init_script)


if __name__ == '__main__':
    unittest.main()
