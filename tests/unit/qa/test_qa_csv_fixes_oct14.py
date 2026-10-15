import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver


class TestQACSVFixesOct14(unittest.TestCase):
    """Unit tests for QA pattern fixes identified in qa_results.csv audit."""

    def setUp(self):
        self.agent = SentinelAgent()
        patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(patterns_data)
        self.resolver = InputAwareResolver()

    def test_scale_of_5_rating(self):
        questions_scale_5 = [
            "Rate yourself in coding (on scale of 5) - backend & frontend",
            "Rate yourself in coding (on scale of 5)",
            "Rate yourself (on scale of 5)",
            "Rate your proficiency (1-5)",
        ]
        for q in questions_scale_5:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIn(ans, ["5", "4"], f"Scale of 5 question '{q}' answered with '{ans}' instead of 5 or 4")
            self.assertGreaterEqual(conf, 0.90)

        # Ensure standard 1-10 rating questions still return 9
        q_10 = "Rate your coding skills on a scale of 1-10"
        ans_10, _ = self.agent._fuzzy_match_question(q_10)
        self.assertEqual(ans_10, "9")

    def test_fixed_expected_annual_ctc(self):
        q = "What is your fixed expected annual CTC in INR ?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "3000000", f"Annual CTC question answered with '{ans}' instead of 3000000")
        self.assertGreaterEqual(conf, 0.90)

        # Ensure monthly compensation question still maps to monthly figure
        q_monthly = "What are your expected fixed monthly compensation expectations (in inr)"
        ans_m, _ = self.agent._fuzzy_match_question(q_monthly)
        self.assertEqual(ans_m, "250000")

    def test_degree_completion_yes_no(self):
        questions = [
            "Have you completed [Degree]?",
            "Have you completed your degree?",
            "Have you completed a degree?",
            "Do you hold a degree?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Degree question '{q}' answered with '{ans}' instead of Yes")
            self.assertGreaterEqual(conf, 0.90)

    def test_relocation_includes_bengaluru(self):
        q = "Which of these locations are you willing to relocate to?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("Bengaluru", ans, f"Relocation answer '{ans}' missing 'Bengaluru'")
        self.assertIn("Bangalore", ans, f"Relocation answer '{ans}' missing 'Bangalore'")

    def test_sponsorship_answers_no(self):
        sponsorship_questions = [
            "Do you now or will you at any time in the future require sponsorship?",
            "Do you require sponsorship now or in the future?",
            "Will you at any time in the future require sponsorship?",
            "Will you now or in the future require visa sponsorship for employment at Anaplan?",
        ]
        for q in sponsorship_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Sponsorship question '{q}' answered with '{ans}' instead of No")
            self.assertGreaterEqual(conf, 0.90)

        # Work authorization in India must answer Yes
        q_auth = "Are you legally authorized to work in India without requiring visa sponsorship?"
        ans_auth, _ = self.agent._fuzzy_match_question(q_auth)
        self.assertTrue("Yes" in ans_auth or ans_auth.startswith("Yes"))

    def test_living_in_non_bangalore_cities_answers_no(self):
        non_bangalore = [
            "Do you currently live in Pune?",
            "Are you currently based in Mumbai ?",
            "Are you currently living in Hyderabad?",
            "Do you currently live in Gurgaon?",
            "Are you currently based in Delhi?",
        ]
        for q in non_bangalore:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue(ans.startswith("No"), f"Living in non-Bangalore question '{q}' answered with '{ans}' instead of No")

        bangalore = [
            "Do you currently live in Bangalore?",
            "Are you currently based in Bengaluru?",
        ]
        for q in bangalore:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Living in Bangalore question '{q}' answered with '{ans}' instead of Yes")

    def test_notice_period_options_matching(self):
        """Verify notice period resolves to immediate / 15 days, never 1 month or >3 months."""
        options_hirist = ["Immediately Available", "15 days or less", "1 month", "2 months", "More than 3 Months"]
        res = self.resolver.resolve_answer(
            "15",
            "radio",
            options=options_hirist,
            question="What is your current notice period?"
        )
        self.assertIn(res.selected_option, ["Immediately Available", "15 days or less"])

        options_hirist_pills = ["15 Days", "1 Month", "2 Months", "3 Months", "More than 3 Months"]
        res2 = self.resolver.resolve_answer(
            "15",
            "radio",
            options=options_hirist_pills,
            question="Notice Period"
        )
        self.assertEqual(res2.selected_option, "15 Days")

    def test_experience_closest_range_matching(self):
        """Verify experience answers find the closest range rather than string similarity mismatches."""
        options = ["4 -5 years", "7 - 10 years", "10+ years"]
        res = self.resolver.resolve_answer(
            "3.0 Years",
            "select",
            options=options,
            question="How many years of experience do you have in Python?"
        )
        self.assertEqual(res.selected_option, "4 -5 years")

        res_4_2 = self.resolver.resolve_answer(
            "4.2 Years",
            "select",
            options=options,
            question="Experience in Python"
        )
        self.assertEqual(res_4_2.selected_option, "4 -5 years")

    def test_total_ctc_fixed_plus_variable(self):
        """Verify Total CTC with Fixed+Variable mentioned returns salary, not 0."""
        q = "Total CTC - Fixed+Variable"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn(ans, ["2300000", "23 LPA", "23"])
        self.assertNotEqual(ans, "0")

        q2 = "Total Annual CTC (Fixed + Variable)"
        ans2, _ = self.agent._fuzzy_match_question(q2)
        self.assertIn(ans2, ["2300000", "23 LPA", "23"])
        self.assertNotEqual(ans2, "0")

    def test_exp_ctc_abbreviation(self):
        """Verify 'exp ctc' returns expected salary 30 LPA / 3000000, not current CTC."""
        q = "What is your exp ctc in INR?"
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "3000000")

        q2 = "exp ctc"
        ans2, _ = self.agent._fuzzy_match_question(q2)
        self.assertIn(ans2, ["30", "3000000", "30 LPA"])

    def test_work_link_and_project_description(self):
        """Verify open-ended link and project descriptions do not answer 'Yes'."""
        q_link = "Paste a link to some of your work."
        ans_link, _ = self.agent._fuzzy_match_question(q_link)
        self.assertEqual(ans_link, "https://siddhant3646.github.io/Portfolio/")

        q_proj = "Briefly describe the product/project you last worked on and your role in its development."
        ans_proj, _ = self.agent._fuzzy_match_question(q_proj)
        self.assertIn("Everbridge", ans_proj)
        self.assertNotEqual(ans_proj, "Yes")

    def test_area_of_experience(self):
        """Verify 'what area have you most  experience in' (two spaces) and 'what other areas'."""
        q_area = "what area have you most  experience in"
        ans_area, _ = self.agent._fuzzy_match_question(q_area)
        self.assertEqual(ans_area, "Full-stack")

        q_other = "what other areas have you previous employment experience in"
        ans_other, _ = self.agent._fuzzy_match_question(q_other)
        self.assertEqual(ans_other, "Full-stack, AI/ML")

    def test_contractual_role_preference(self):
        """Verify contractual arrangement returns 'Contract Full-time'."""
        q = "This is a 6-month contractual role. Which employment arrangement would you be interested in?"
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Contract Full-time")

    def test_compliance_and_conflict_questions(self):
        """Verify compliance, conflict of interest, non-compete, and ex-employee questions answer 'No'."""
        compliance_questions = [
            "Are you bound by any non-compete or non-solicitation agreements?",
            "Do you have any conflict of interest with company employees or suppliers?",
            "Do you have any relatives or family members currently employed at our company?",
            "Have you ever been employed by this company or its subsidiaries?",
            "Have you applied with us in the past 6 months?",
            "Are you subject to any restrictive covenants from previous employers?",
            "Do you have any disciplinary proceedings or felony convictions?",
        ]
        for q in compliance_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Compliance question '{q}' answered with '{ans}' instead of No")
            self.assertGreaterEqual(conf, 0.90)

            # Test resolver for radio option selection
            res = self.resolver.resolve_answer(
                ans,
                "radio",
                options=["Yes", "No"],
                question=q
            )
            self.assertEqual(res.selected_option, "No")


if __name__ == '__main__':
    unittest.main()

