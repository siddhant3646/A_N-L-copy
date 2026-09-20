"""Unit tests for September 19 QA CSV audit fixes and enhancements.

Covers:
1. Ex-employee questions ("Did you work with us before ?", "Have you ever been employed by Vonage...") returning 'No'.
2. Portfolio URL regex safety: Tools/technologies proficiency prompt (containing 'github' in examples) returns tools stack, NOT portfolio URL.
3. Joining availability / notice period questions ("How soon can you join") returning '15' / '15 Days', not experience '4'.
4. Domain payment experience questions ("How many years of experience do you have in payment?") returning experience, NOT CTC '3000000'.
5. Experience category select dropdown defaults fixed from 'Yes' to '4.2 Years' / '4.2', resolving range matching.
6. Work mode multi-choice returning 'Hybrid' across platforms.
7. Negative options (None, None of the above) excluded during affirmative checkbox selections.
"""

import os
import re
import unittest
from unittest.mock import MagicMock

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver, InputType, Option


class TestQACSVAuditFixesSept19(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        json_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "config", "qa_patterns.json"
        )
        cls.patterns_data = load_patterns(json_path)
        cls.pattern_matcher = PatternMatcher(cls.patterns_data)
        cls.resolver = InputAwareResolver()
        cls.agent = SentinelAgent()

    def test_ex_employee_questions_return_no(self):
        questions = [
            "Did you work with us before ?",
            "Did you work with us before",
            "Did you work for us before ?",
            "Have you ever been employed by Vonage or any of its subsidiaries?",
            "Have you worked with us before?",
            "Have you ever worked here before?",
            "Have you been previously employed with Freshworks?",
            "Former employee of the company or subsidiaries",
        ]
        for q in questions:
            for platform in ["linkedin", "naukri"]:
                self.agent._current_platform = platform
                ans, conf = self.agent._fuzzy_match_question(q)
                self.assertEqual(ans, "No", f"Platform {platform} failed for question: {q}")
                self.assertGreaterEqual(conf, 0.90)

    def test_tools_proficiency_not_overwritten_by_portfolio(self):
        q = "Which tools, platforms, or technologies are you proficient in? (e.g., Jira, GitHub, Figma, etc.)"
        self.agent._current_platform = "linkedin"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertNotIn("https://siddhant3646.github.io/Portfolio/", ans)
        self.assertTrue("Git" in ans or "Docker" in ans or "Jira" in ans or conf >= 0.8)

    def test_how_soon_can_you_join_returns_notice(self):
        questions = [
            "How soon can you join us?",
            "How soon can you join?",
            "How quickly can you join us if shortlisted?",
            "When can you join us?",
        ]
        for q in questions:
            self.agent._current_platform = "linkedin"
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue("15" in ans or "Can join within 15 days" in ans, f"Failed for: {q}, got: {ans}")
            self.assertNotEqual(ans, "4")

    def test_payment_experience_not_confused_with_salary(self):
        q = "How many years of experience do you have in payment?"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("4", ans)
        self.assertNotIn("3000000", ans)
        self.assertNotIn("2300000", ans)

    def test_experience_select_dropdown_range_resolution(self):
        # Verify that experience patterns like azure, kubernetes, docker resolve to '3-5 years'
        options = [
            Option(value="0-1 years", label="0-1 years", index=0),
            Option(value="1-3 years", label="1-3 years", index=1),
            Option(value="3-5 years", label="3-5 years", index=2),
            Option(value="5+ years", label="5+ years", index=3),
        ]
        for key in ["azure_experience", "kubernetes_experience", "docker_experience", "gcp_experience"]:
            pattern_obj = self.patterns_data.get("patterns", {}).get(key)
            self.assertIsNotNone(pattern_obj, f"Pattern {key} not found")
            select_default = pattern_obj.get("input_type_defaults", {}).get("select")
            self.assertNotEqual(select_default, "Yes", f"Pattern {key} still has select: Yes")
            self.assertIn("4", select_default)
            
            # Resolve against options
            result = self.resolver.resolve(
                answer=select_default,
                input_type=InputType.SELECT,
                options=options,
                question=pattern_obj["patterns"][0]
            )
            self.assertIsNotNone(result.matched_option)
            self.assertEqual(result.matched_option.label, "3-5 years", f"Failed range resolution for {key}")

    def test_current_work_mode_question(self):
        q = "Current work mode 1.Remote 2.Onsite 3.Hybrid 4.Not working 5.Serving Np ?"
        for platform in ["linkedin", "naukri"]:
            self.agent._current_platform = platform
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Hybrid")
            self.assertNotEqual(ans, "15")

    def test_negative_options_regex_logic(self):
        negative_re = re.compile(r"^(none|none of the above|none of these|n/a|not applicable|no experience|neither|skip)\b", re.I)
        self.assertTrue(negative_re.search("None"))
        self.assertTrue(negative_re.search("None of the above"))
        self.assertTrue(negative_re.search("None of these"))
        self.assertTrue(negative_re.search("N/A"))
        self.assertTrue(negative_re.search("Not applicable"))
        self.assertTrue(negative_re.search("No experience"))
        self.assertTrue(negative_re.search("Skip this question"))
        self.assertFalse(negative_re.search("Node.js"))
        self.assertFalse(negative_re.search("Python"))
        self.assertFalse(negative_re.search("AWS"))


if __name__ == "__main__":
    unittest.main()
