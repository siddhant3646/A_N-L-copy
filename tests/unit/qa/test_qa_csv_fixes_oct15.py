import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver


class TestQACSVFixesOct15(unittest.TestCase):
    """Unit tests for QA pattern fixes identified in Naukri chatbot logs (Oct 15)."""

    def setUp(self):
        self.agent = SentinelAgent()
        patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(patterns_data)
        self.resolver = InputAwareResolver()

    def test_team_management_experience(self):
        questions = [
            "How many years of experience do you have in team management?",
            "how many years of experience do you have in team management",
            "Years of experience in team management",
            "How many years of experience do you have in leading a team",
            "experience in team management",
        ]
        self.agent._current_platform = "naukri"
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "3 Years", f"Question '{q}' returned '{ans}' instead of '3 Years'")
            self.assertGreaterEqual(conf, 0.90)

        # Check LinkedIn whole number format
        self.agent._current_platform = "linkedin"
        ans_li, conf_li = self.agent._fuzzy_match_question("How many years of experience do you have in team management?")
        self.assertEqual(ans_li, "3", f"LinkedIn team management returned '{ans_li}' instead of '3'")
        self.assertGreaterEqual(conf_li, 0.90)

    def test_rating_scale_out_of_10_and_5(self):
        questions_10 = [
            "Rate Your understanding of MLOps (machine learning operation) flow out of 10",
            "Rate Your ability to write Python code (e.g.: API, application code from scratch) out of 10",
            "Rate Your ability to write advance SQL queries (e.g.: window, quality) out of 10",
            "Rate your understanding of MLOps flow out of 10",
            "Rate your ability to write advanced SQL queries out of 10",
        ]
        self.agent._current_platform = "naukri"
        for q in questions_10:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "9", f"Rating question '{q}' answered with '{ans}' instead of '9'")
            self.assertGreaterEqual(conf, 0.90)

        # Check 5-scale rating
        ans_5, conf_5 = self.agent._fuzzy_match_question("Rate yourself on a scale of 1 to 5")
        self.assertEqual(ans_5, "5")
        self.assertGreaterEqual(conf_5, 0.90)

    def test_which_locations_willing_to_relocate(self):
        questions = [
            "Which of these locations are you willing to relocate to?",
            "Which of these locations are you willing to relocate to",
            "which locations are you willing to relocate to",
        ]
        self.agent._current_platform = "naukri"
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue(
                "Bengaluru" in ans or "Bangalore" in ans,
                f"Relocation location '{q}' returned '{ans}' which does not mention Bangalore/Bengaluru"
            )
            self.assertGreaterEqual(conf, 0.90)

    def test_lwd_and_notice_period_number_input(self):
        question = "Notice Period/ LWD (Last Working Day) - Mention in Days / Mention the Date"
        ans, conf = self.matcher.fuzzy_match(question, input_type="number")
        self.assertEqual(ans, "15", f"LWD numeric input returned '{ans}' instead of '15'")
        self.assertGreaterEqual(conf, 0.65)

    def test_supporting_documents(self):
        question = "Do you have all the companies supporting documents like(pf deduction, expereince letter, reliving letter, pay slips etc) yes/no?"
        ans, conf = self.agent._fuzzy_match_question(question)
        self.assertEqual(ans, "Yes", f"Supporting documents question returned '{ans}' instead of 'Yes'")
        self.assertGreaterEqual(conf, 0.90)

    def test_empty_or_whitespace_question(self):
        empty_questions = ["", "   ", "\t\n  "]
        for eq in empty_questions:
            ans, conf = self.agent._fuzzy_match_question(eq)
            self.assertIn(ans, [None, ""], f"Empty question '{eq!r}' returned '{ans}' instead of None")


if __name__ == "__main__":
    unittest.main()
