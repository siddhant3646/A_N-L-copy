import unittest
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sentinel.agent import SentinelAgent


class TestNaukriNoChatbotLimit(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_naukri_no_chatbot_counter_initialization(self):
        """Verify _naukri_no_chatbot_count starts at 0 and max is 3."""
        self.assertEqual(self.agent._naukri_no_chatbot_count, 0)
        self.assertEqual(self.agent._naukri_no_chatbot_max, 3)

    def test_naukri_reset_per_task_state(self):
        """Verify _naukri_no_chatbot_count resets on new task."""
        self.agent._naukri_no_chatbot_count = 2
        self.agent.reset_per_task_state()
        self.assertEqual(self.agent._naukri_no_chatbot_count, 0)

    async def _async_test_no_chatbot_closes_after_3_turns(self):
        mock_page = AsyncMock()
        mock_page.url = "https://www.naukri.com/mnjuser/recommendedjobs"
        mock_page.is_visible.return_value = False
        mock_page.query_selector.return_value = None

        self.agent._page = mock_page

        # Mock _handle_chatbot_loop to always return False (no chatbot)
        with patch.object(self.agent, '_handle_chatbot_loop', new_callable=AsyncMock) as mock_chatbot:
            mock_chatbot.return_value = False

            # Simulate 3 turns of APPLY_CLICKED
            for step in range(3):
                result = 'NAUKRI_APPLY_CLICKED: 5 jobs selected'
                current_url = 'https://www.naukri.com/mnjuser/recommendedjobs'

                # Execute outer logic for direct apply
                if 'APPLY_CLICKED' in result and 'LINKEDIN' not in result and 'naukri.com' in current_url:
                    chatbot_done = await self.agent._handle_chatbot_loop()
                    if not chatbot_done:
                        resolved_res = None
                        if '/myapply/saveApply' in self.agent._page.url:
                            resolved_res = await self.agent._resolve_naukri_completion()
                        if not (resolved_res and 'CHATBOT_COMPLETE' in str(resolved_res) and not '0/' in str(resolved_res)):
                            self.agent._naukri_no_chatbot_count += 1
                            if self.agent._naukri_no_chatbot_count >= self.agent._naukri_no_chatbot_max:
                                self.agent.state.task_complete = True
                                break

            self.assertEqual(self.agent._naukri_no_chatbot_count, 3)
            self.assertTrue(self.agent.state.task_complete)

    def test_no_chatbot_closes_after_3_turns(self):
        import asyncio
        asyncio.run(self._async_test_no_chatbot_closes_after_3_turns())


if __name__ == '__main__':
    unittest.main()
