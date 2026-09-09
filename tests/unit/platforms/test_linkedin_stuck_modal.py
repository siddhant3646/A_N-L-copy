import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.agent import SentinelAgent


class TestLinkedInStuckModal(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    async def test_select_next_job_card_evaluates_and_cleans_modal(self):
        """Verify _select_next_job_card evaluates script to skip active job and remove modal."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="41029384")
        self.agent._page = mock_page

        result = await self.agent._select_next_job_card()

        self.assertEqual(result, "41029384")
        mock_page.evaluate.assert_called_once()
        eval_script = mock_page.evaluate.call_args[0][0]
        self.assertIn("__skippedJobIds", eval_script)
        self.assertIn(".artdeco-modal", eval_script)
        self.assertIn("remove()", eval_script)

    async def test_select_next_job_card_escalation_after_2_cleanups(self):
        """Verify that after 2 cleanup attempts, the 3rd escalates to navigating to search URL."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="CLEANED")
        self.agent._page = mock_page

        # 1st attempt: evaluates cleanup
        res1 = await self.agent._select_next_job_card()
        self.assertEqual(res1, "CLEANED")
        mock_page.goto.assert_not_called()

        # 2nd attempt: evaluates cleanup
        res2 = await self.agent._select_next_job_card()
        self.assertEqual(res2, "CLEANED")
        mock_page.goto.assert_not_called()

        # 3rd attempt (> 2 attempts): escalates to page.goto
        with patch("asyncio.sleep", AsyncMock()):
            res3 = await self.agent._select_next_job_card()

        self.assertEqual(res3, "NAVIGATED_SEARCH")
        mock_page.goto.assert_called_once_with('https://www.linkedin.com/jobs/search/', timeout=30000)
        self.assertEqual(self.agent._linkedin_stuck_cleanup_attempts, 0)

    def test_check_modals_prioritizes_form_over_success(self):
        """Verify checkModals checks for active form controls before success modal classification."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("hasActiveFormControls", src)
        self.assertIn("dialog.querySelector('input:not([type=\"hidden\"])", src)
        self.assertIn("return { type: 'form', element: dialog };", src)

    def test_safety_reminder_excludes_bare_continue_applying(self):
        """Verify isSafetyReminder and isSafetyModal don't use bare 'continue applying' without safety context."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        # Check that isSafetyModal and isSafetyReminder definitions require safety reminder or suspicious job text
        self.assertIn("titleText.includes('job search safety reminder')", src)
        self.assertNotIn("text.includes('continue applying')", src)
        self.assertNotIn("combinedText.includes('continue applying')", src)
        self.assertNotIn("dText.includes('continue applying')", src)


if __name__ == "__main__":
    unittest.main()
