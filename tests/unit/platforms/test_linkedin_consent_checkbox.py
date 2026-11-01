import unittest
from unittest.mock import AsyncMock, MagicMock
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns


class TestLinkedInConsentCheckbox(unittest.TestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_eversana_privacy_notice_pattern_matching(self):
        """Verify EVERSANA privacy and SMS questions match 'Yes' for checkbox."""
        q1 = "You declare that you have read and agree to the job applications privacy notice of EVERSANA.*"
        q2 = "You declare that you have read and understand the privacy notice of EVERSANA and agree to receive text/SMS messages for job applications and/or future career opportunities."

        ans1, conf1 = self.agent._pattern_matcher.fuzzy_match(q1, input_type="checkbox")
        ans2, conf2 = self.agent._pattern_matcher.fuzzy_match(q2, input_type="checkbox")

        self.assertEqual(ans1, "Yes")
        self.assertGreaterEqual(conf1, 0.8)
        self.assertEqual(ans2, "Yes")
        self.assertGreaterEqual(conf2, 0.8)

    def test_handle_scripted_fallback_contains_required_checkbox_guard(self):
        """Verify JS form handler defines isCheckboxRequired and guards against unchecking required checkboxes."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        self.assertIn("isCheckboxRequired", src)
        self.assertIn("hasUncheckedCheckbox", src)
        self.assertIn("subQuestionBlocks", src)
        self.assertIn("isConsentGroup", src)
        self.assertIn("job applications privacy notice", src)

    def test_check_modals_prioritizes_form_over_success(self):
        """Verify checkModals checks hasActiveFormControls BEFORE isSuccessModal."""
        import inspect
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        form_idx = src.find("hasActiveFormControls")
        # In checkModals, the check for hasActiveFormControls should return type: 'form'
        # before isSuccessModal returns type: 'success'
        self.assertIn("if (hasActiveFormControls) {\n                                return { type: 'form', element: dialog };", src)
        self.assertIn("if (isSuccessModal) {\n                                return { type: 'success', element: dialog };", src)
        first_form = src.find("if (hasActiveFormControls) {\n                                return { type: 'form', element: dialog };")
        first_success = src.find("if (isSuccessModal) {\n                                return { type: 'success', element: dialog };")
        self.assertLess(first_form, first_success)
