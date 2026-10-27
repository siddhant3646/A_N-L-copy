"""Regression tests for the Hirist apply handler.

Covers the two reported Hirist defects:

1. The application cap must hold even when per-job verification is unreliable
   (previously ``applied`` only increased on a verified success, so a failed
   verification let the loop run through the whole feed).
2. Screening questionnaires must be handled BEFORE the generic confirm-modal
   helper, otherwise the modal helper clicks the questionnaire's own Submit and
   skips the questions.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class _FakePage:
    url = "https://www.hirist.tech/jobfeed"

    async def goto(self, *args, **kwargs):
        return None


class TestHiristApplyCap(unittest.TestCase):
    def setUp(self):
        self._old_cap = os.environ.get('HIRIST_MAX_APPLICATIONS')
        os.environ['HIRIST_MAX_APPLICATIONS'] = '3'
        self.agent = SentinelAgent()
        self.agent._page = _FakePage()

    def tearDown(self):
        if self._old_cap is None:
            os.environ.pop('HIRIST_MAX_APPLICATIONS', None)
        else:
            os.environ['HIRIST_MAX_APPLICATIONS'] = self._old_cap

    def _prime(self):
        self.agent._hirist_collect_jobs = AsyncMock(return_value=[
            {'id': str(i), 'url': f'https://www.hirist.tech/j/test-{i}', 'title': f'Job {i}'}
            for i in range(10)
        ])
        self.agent._hirist_dismiss_dialogs = AsyncMock()
        self.agent._hirist_read_meta = AsyncMock(
            return_value={'jobTitle': 'Backend Engineer', 'companyName': 'Acme'}
        )
        self.agent._hirist_click_apply = AsyncMock(return_value='applied')
        self.agent._hirist_handle_questionnaire = AsyncMock(return_value=False)
        self.agent._hirist_verify_applied = AsyncMock(return_value=False)
        self.agent._hirist_recheck_applied = AsyncMock(return_value=False)
        self.agent._hirist_confirm_modal = AsyncMock(return_value=False)

    def test_attempt_cap_holds_when_verification_fails(self):
        """Never click Apply more than the cap, even if nothing verifies."""
        self._prime()
        with patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            asyncio.run(self.agent._handle_hirist_apply_task())
        self.assertEqual(self.agent._hirist_click_apply.await_count, 3)
        self.assertEqual(self.agent.metrics['applications_submitted'], 0)

    def test_stops_after_confirmed_applications(self):
        """Stop at the cap once applications verify successfully."""
        self._prime()
        self.agent._hirist_verify_applied = AsyncMock(return_value=True)
        with patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            asyncio.run(self.agent._handle_hirist_apply_task())
        self.assertEqual(self.agent.metrics['applications_submitted'], 3)
        self.assertEqual(self.agent._hirist_click_apply.await_count, 3)

    def test_questionnaire_runs_before_confirm_modal(self):
        """The questionnaire handler must be invoked before the confirm helper."""
        self._prime()
        calls = []

        async def _questionnaire(page):
            calls.append('questionnaire')
            return False

        async def _confirm(page):
            calls.append('confirm')
            return True

        self.agent._hirist_handle_questionnaire = AsyncMock(side_effect=_questionnaire)
        self.agent._hirist_confirm_modal = AsyncMock(side_effect=_confirm)

        with patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            asyncio.run(self.agent._handle_hirist_apply_task())

        self.assertTrue(calls, "questionnaire/confirm should have been invoked")
        self.assertEqual(calls[0], 'questionnaire')
        self.assertIn('confirm', calls)

    def test_suitability_filter_skips_unsuitable_jobs(self):
        """Jobs with executive titles or excessive min experience must be skipped."""
        unsuitable_vp = {'title': 'Medi Assist - Vice President', 'exp': '9 - 16 yrs'}
        unsuitable_architect = {'title': 'Unisys - Technical Architect', 'exp': '12 - 20 yrs'}
        unsuitable_lead = {'title': 'Lead Software Engineer', 'exp': '8 - 12 yrs'}
        suitable_sde = {'title': 'Node.js Developer - Backend Architecture', 'exp': '4 - 8 yrs'}
        suitable_se = {'title': 'Symplr - Software Engineer - Java/AngularJS', 'exp': '4 - 6 yrs'}

        self.assertFalse(self.agent._is_hirist_job_suitable(unsuitable_vp)[0])
        self.assertFalse(self.agent._is_hirist_job_suitable(unsuitable_architect)[0])
        self.assertFalse(self.agent._is_hirist_job_suitable(unsuitable_lead)[0])
        self.assertTrue(self.agent._is_hirist_job_suitable(suitable_sde)[0])
        self.assertTrue(self.agent._is_hirist_job_suitable(suitable_se)[0])

    def test_script_error_count_resets_between_tasks(self):
        """_script_error_count must be reset in reset_per_task_state to prevent cascading task aborts."""
        self.agent._script_error_count = 10
        self.agent.reset_per_task_state()
        self.assertEqual(self.agent._script_error_count, 0)


if __name__ == '__main__':
    unittest.main()
