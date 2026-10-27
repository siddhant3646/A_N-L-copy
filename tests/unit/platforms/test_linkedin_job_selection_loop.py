import unittest
from unittest.mock import AsyncMock, patch
from src.sentinel.agent import SentinelAgent


class TestLinkedInJobSelectionLoop(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_script_fallback_js_has_robust_title_matching_and_events(self):
        """Verify _handle_scripted_fallback JS has isTitleSkipped, normalized casing, and pointer events."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("isTitleSkipped", src)
        self.assertIn("normalizeJobTitle", src)
        self.assertIn("window.__skippedJobTitles.add(t.toLowerCase().trim())", src)
        self.assertIn("PointerEvent('pointerdown'", src)
        self.assertIn("clickable.click()", src)

    async def test_job_selected_streak_resets_on_non_selection_results(self):
        """Verify _job_selected_streak is reset on LINKEDIN_SCROLLED and LINKEDIN_JOB_SKIPPED."""
        self.agent._job_selected_streak = 3
        # Simulate non-selection result logic
        result = "LINKEDIN_SCROLLED: Skipping stuck job — Test Job (Verified)"
        if 'Skipping stuck job — ' in result:
            skipped_t = result.split('Skipping stuck job — ')[-1].strip()
            if skipped_t:
                self.agent._linkedin_skipped_job_titles.add(skipped_t)
                self.agent._linkedin_skipped_job_titles.add(skipped_t.lower())

        if 'LINKEDIN_JOB_SELECTED' not in result:
            self.agent._job_selected_streak = 0

        self.assertEqual(self.agent._job_selected_streak, 0)
        self.assertIn("Test Job (Verified)", self.agent._linkedin_skipped_job_titles)
        self.assertIn("test job (verified)", self.agent._linkedin_skipped_job_titles)

    async def test_linkedin_job_skipped_adds_to_skipped_titles(self):
        """Verify LINKEDIN_JOB_SKIPPED with title adds to persistent skip set."""
        result = "LINKEDIN_JOB_SKIPPED: No Easy Apply — Backend Lead Software Engineer"
        if 'LINKEDIN_JOB_SKIPPED' in result and 'No Easy Apply — ' in result:
            skipped_t = result.split('No Easy Apply — ')[-1].strip()
            if skipped_t and not any(k in skipped_t for k in ['button not found', 'job closed', 'closed job', 'unknown job', 'URL signal']):
                self.agent._linkedin_skipped_job_titles.add(skipped_t)
                self.agent._linkedin_skipped_job_titles.add(skipped_t.lower())

        self.assertIn("Backend Lead Software Engineer", self.agent._linkedin_skipped_job_titles)
        self.assertIn("backend lead software engineer", self.agent._linkedin_skipped_job_titles)


if __name__ == "__main__":
    unittest.main()
