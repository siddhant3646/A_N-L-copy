import sys
import os
import unittest
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVFixesOct12(unittest.TestCase):
    """Unit tests for Q&A pattern fixes from October 12 failure log audit."""

    def setUp(self):
        self.agent = SentinelAgent()

    # 1. Disability Questions
    def test_disability_status(self):
        questions = [
            "Do you consider yourself to have a disability, impairment or long-term health condition?",
            "Do you have any disability?",
            "Disability status",
            "Person with disability"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn(ans, ["I don’t have a disability", "No"], f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for: {q}")

    def test_disability_type(self):
        questions = [
            "What kind of disability do you have?",
            "Disability type",
            "Type of disability"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "None", f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for: {q}")

    def test_disability_percentage(self):
        questions = [
            "Disability percentage",
            "Percentage of disability",
            "What is your disability percentage?"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "0", f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for: {q}")

    # 2. Variable Compensation & Stock / Equity
    def test_variable_compensation(self):
        questions = [
            "Current Variable Compensation",
            "Variable component in current CTC",
            "Annual variable pay",
            "Current bonus / variable"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "0", f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for: {q}")

    def test_unvested_rsu_stock_options(self):
        questions = [
            "Current Unvested Options/RSU value",
            "Unvested stock options value",
            "Current unvested RSU value"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "0", f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for: {q}")

    def test_variable_pay_details(self):
        q = "Please provide details on your variable pay component."
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertIn("100% fixed salary", ans)
        self.assertGreater(score, 0.7)

    # 3. Base Salary Questions (Must NOT be hijacked by variable pay = 0)
    def test_base_salary(self):
        ans_curr, score_curr = self.agent._fuzzy_match_question("Current CTC")
        self.assertIn("23", ans_curr)
        self.assertGreater(score_curr, 0.8)

        ans_exp, score_exp = self.agent._fuzzy_match_question("Expected CTC")
        self.assertIn("30", ans_exp)
        self.assertGreater(score_exp, 0.8)

    # 4. Consumer Tech Experience (Yes/No prompt, NOT numeric years)
    def test_consumer_tech_experience(self):
        q = "Do you have experience of working in consumer tech?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes", f"Expected 'Yes' but got '{ans}'")
        self.assertGreater(score, 0.8)

    # 5. Location Questions
    def test_living_in_gurgaon_no(self):
        questions = [
            "Are you currently living in Gurgaon?",
            "Are you staying in Gurgaon?"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Expected 'No' for: {q}")
            self.assertGreater(score, 0.8)

    def test_living_in_hyderabad_no(self):
        questions = [
            "Are you currently living in Hyderabad?",
            "Are you currently residing in Hyderabad?"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Expected 'No' for: {q}")
            self.assertGreater(score, 0.8)

    def test_job_location_interest(self):
        q = "If you do not stay in Gurgaon, are you interested in relocating or working from office in Gurgaon?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes", f"Expected 'Yes' for: {q}")
        self.assertGreater(score, 0.8)

    # 6. Company Excitement (Generic vs Wissen vs Supersourcing)
    def test_generic_company_excitement(self):
        q = "What excites you about working with our company?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertNotIn("Wissen", ans, "Generic company question must not mention Wissen Technology")
        self.assertGreater(score, 0.6)

    def test_wissen_excitement(self):
        q = "Why do you want to work at Wissen Technology?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertIn("Wissen", ans)
        self.assertGreater(score, 0.8)

    def test_supersourcing_excitement(self):
        q = "Why are you interested in joining Supersourcing?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertIn("Supersourcing", ans)
        self.assertGreater(score, 0.8)

    # 7. AWS Experience & Services
    def test_aws_years_and_services(self):
        questions = [
            "AWS (years of experience and services used)",
            "AWS years of experience and services used"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn("4.2 years", ans)
            self.assertIn("S3", ans)
            self.assertGreater(score, 0.8)

    # 8. Notice Period & Numeric LWD
    def test_serving_notice_lwd_numeric_format(self):
        q = "Please confirm your Last Working Day (LWD) if you are currently serving notice period. (Please enter as DDMMYYYY e.g., if LWD is 19th Oct 2026, enter as 19102026). If not serving notice, please enter NA"
        ans, score = self.agent._fuzzy_match_question(q)
        expected = (datetime.now() + timedelta(days=15)).strftime("%d%m%Y")
        self.assertEqual(ans, expected)
        self.assertGreater(score, 0.8)

    def test_notice_period_option_6(self):
        q = "Please select Option (6) if you are serving notice period"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertIn("(6)", ans)
        self.assertGreater(score, 0.8)

    # 9. Military Service
    def test_military_service(self):
        questions = [
            "Military Service",
            "Are you a veteran or have military service?",
            "Military service status"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn(ans, ["Never served", "No"])
            self.assertGreater(score, 0.7)

    # 10. Career Break
    def test_career_break(self):
        questions = [
            "Do you have any career breaks?",
            "Career break status",
            "Have you taken a career break?"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No")
            self.assertGreater(score, 0.8)

    def test_career_break_reason(self):
        q = "Reason for career break"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertIn(ans, ["Personal", "Not applicable - No career break"])
        self.assertGreater(score, 0.7)


if __name__ == '__main__':
    unittest.main()
