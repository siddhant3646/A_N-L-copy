import unittest
import os
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.agent import SentinelAgent


class TestLinkedInResumeAttach(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_startup_path_validation(self):
        """Resume file path is set on SentinelAgent and points to an existing file."""
        self.assertTrue(hasattr(self.agent, "resume_file_path"))
        self.assertTrue(os.path.exists(self.agent.resume_file_path), f"Resume not found at {self.agent.resume_file_path}")
        self.assertTrue(self.agent.resume_file_path.endswith(".pdf"))

    async def test_resume_upload_success_flow(self):
        """When Easy Apply modal has unattached file input, executes 4-stage upload flow."""
        mock_page = AsyncMock()
        mock_file_input = AsyncMock()
        mock_file_input.count = AsyncMock(return_value=1)
        mock_locator = MagicMock()
        mock_locator.first = mock_file_input
        mock_page.locator = MagicMock(return_value=mock_locator)

        # evaluate calls:
        # 1. has_file_input -> True
        # 2. dispatchEvent -> None
        # 3. verified in UI -> True
        mock_page.evaluate = AsyncMock(side_effect=[True, None, True])

        with patch("asyncio.sleep", AsyncMock()):
            res = await self.agent._handle_linkedin_resume_upload(mock_page)

        self.assertTrue(res)
        mock_file_input.set_input_files.assert_called_once_with(self.agent.resume_file_path)

    async def test_resume_upload_skipped_when_already_attached(self):
        """When modal already has attached resume document, skips upload."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=False)

        res = await self.agent._handle_linkedin_resume_upload(mock_page)
        self.assertFalse(res)

    async def test_resume_upload_fails_open_missing_file(self):
        """When resume file path does not exist, returns False safely."""
        mock_page = AsyncMock()
        with patch.object(self.agent, "resume_file_path", "/nonexistent/resume.pdf"):
            res = await self.agent._handle_linkedin_resume_upload(mock_page)
            self.assertFalse(res)

    def test_force_click_next_guard_present(self):
        """Verify the JS fallback contains the required file guard blocking force-click Next."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("hasEmptyRequiredFile", src)
        self.assertIn("Resume not attached", src)
        self.assertIn("LINKEDIN_FORM_STUCK: Resume not attached", src)


if __name__ == "__main__":
    unittest.main()
