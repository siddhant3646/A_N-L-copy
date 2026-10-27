import os
import sys
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType


class TestQACSVFixesOct20(unittest.TestCase):
    """Unit tests verifying all fixes from CSV audit (October 20)."""

    def setUp(self):
        self.agent = SentinelAgent()
        self.patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(self.patterns_data)
        self.resolver = InputAwareResolver()

    def test_ecommerce_platform_boolean_and_radio(self):
        """Have you built / scaled / managed a eCommerce platform should return Yes for radio/select/text."""
        q = "Have you built / scaled / managed a eCommerce platform?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertTrue(ans.startswith("Yes"), f"Expected answer starting with Yes, got: {ans}")
        self.assertGreaterEqual(conf, 0.90)

        # Check in pattern matcher directly
        res = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(res[0], "Yes")

    def test_current_ctc_fixed_variable_not_zero(self):
        """Current CTC with fixed + variable mention should never return 0."""
        questions = [
            "Current CTC ( Please mention Fixed + Variable )",
            "Current CTC (Please mention Fixed + Variable)",
            "Current CTC (fixed + variable)",
            "What is your current CTC (Fixed + Variable) in LPA (Lakhs Per Annum)?"
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertNotEqual(ans, "0", f"Failed for '{q}': answered 0")
            self.assertTrue("23" in ans or "2300000" in ans, f"Failed for '{q}': got {ans}")

    def test_expecting_ctc_and_current_ctc_compound(self):
        """Questions asking for Expecting CTC AND CTC should return both."""
        questions = [
            "What is Your Expecting CTC AND CTC ?",
            "What is your expecting ctc and ctc",
            "What is your expected ctc and current ctc"
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIn("23", ans, f"Current CTC missing in '{q}': got {ans}")
            self.assertIn("30", ans, f"Expected CTC missing in '{q}': got {ans}")
            self.assertGreaterEqual(conf, 0.95)

    def test_behavioral_complex_issue_codebase(self):
        """Describe a time you fixed a complex issue in codebase/tech stack should return behavioral answer."""
        q = "In 2-3 sentences, describe a time you fixed a complex issue in a codebase or tech stack you didn’t know well. How did you approach it, and did you use any AI-assisted tools?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("debugging", ans.lower())
        self.assertNotIn("Node.js, Python, AWS, Docker", ans)
        self.assertGreaterEqual(conf, 0.95)

    def test_medical_coding_zero(self):
        """Software engineer candidate has 0 experience and no certifications in medical coding."""
        q_exp = "How many years of experience you have working in Medical Coding Industry?"
        ans_exp, conf_exp = self.agent._fuzzy_match_question(q_exp)
        self.assertIn("0", ans_exp)

        q_cert = "Do you have certifications in Medical Coding?"
        ans_cert, conf_cert = self.agent._fuzzy_match_question(q_cert)
        self.assertIn(ans_cert.lower(), ["no", "0"])

    def test_province_state_karnataka(self):
        """Province / State should return Karnataka (not Uttar Pradesh)."""
        q = "Province / State (abbreviated)"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Karnataka")
        self.assertGreaterEqual(conf, 0.90)

    def test_english_rating_scale_5(self):
        """Rate English on scale of 1 to 5 should return 5."""
        q = "Rate your English communication skills on a scale of 1 to 5 (5 being the highest)"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "5")
        self.assertGreaterEqual(conf, 0.95)

    def test_backend_programming_language_java(self):
        """Primary backend language question should return Java."""
        q = "Which programming language do you use most extensively for backend/application development?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Java")
        self.assertGreaterEqual(conf, 0.95)

    def test_job_type_comfortable_with_full_time(self):
        """Job type comfortable with should return Full time."""
        q = "What kind of job are you comfortable with?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertTrue("full" in ans.lower())
        self.assertNotIn("part", ans.lower())

    def test_highest_qualification_bachelor_btech(self):
        """Highest qualification should include B.Tech and Bachelor's Degree."""
        q = "What is the highest level of education you have completed?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("Bachelor's Degree", ans)
        self.assertGreaterEqual(conf, 0.95)

        # In radio context it should return Bachelor's Degree
        res = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(res[0], "Bachelor's Degree")

    def test_frontend_architecture_years_exp(self):
        """Years of experience in frontend architecture should return 4.2 Years, not an essay."""
        q = "How many years of experience do you have in Solid understanding of frontend architecture, design patterns, and performance at scale?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("4.2", ans)
        self.assertNotIn("Architected an event-driven microservices", ans)

    def test_official_notice_period_serving_days_remaining(self):
        """Official notice period asking for days remaining if serving should return 15."""
        q = 'Kindly mention your official notice period. if serving, please mention number of days remaining and if you are immediate joiner please mention "0".'
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "15")

    def test_serving_notice_detailed_textarea(self):
        """Are you currently serving notice with LWD & negotiable NP should return detailed notice string."""
        q = "Are you currently serving notice? Is your notice period negotiable, reducible, or available for buyout? Mention Last Working Day & Negotiable NP."
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("serving notice", ans.lower())
        self.assertIn("15 days", ans.lower())


if __name__ == "__main__":
    unittest.main()
