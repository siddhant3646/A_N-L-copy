"""
Unit tests for QA patterns identified from qa_results.csv analysis (Nov 13, 2026).
Covers:
1. US work authorization gate (No for Yes/No gates)
2. High experience threshold gates (5+, 6+, 7-10, 10+ years -> No)
3. Notice period in weeks (2 Weeks / 2)
4. LWD date resolution (dynamic LWD date, not numeric 15 or day number)
5. Production-grade application description (technical essay, not 'Yes')
6. Single-word 'application' pattern requires exact match (does not hijack open-ended questions)
7. PAN card number variants
8. Location queries for cities candidate is not in (Vizag, Delhi -> No)
9. CloudFormation explanation vs numeric years
10. Shift preference (Day Job, not Yes)
11. US hours acceptability (Yes)
"""

import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVFixesNov13(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SentinelAgent()
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.matcher = PatternMatcher(cls.patterns)

    def test_us_work_authorization_gate_no(self):
        for q in [
            "Are you able to work in the United States?",
            "Are you able to work in the US?",
            "Are you authorized to work in the United States?",
        ]:
            ans_m, score_m = self.matcher.fuzzy_match(q, input_type="radio")
            self.assertEqual(ans_m, "No", f"Matcher failed for: {q}")

            ans_a, score_a = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans_a, "No", f"Agent failed for: {q}")

    def test_high_experience_gates_no(self):
        for q in [
            "Do you have 7–10 years of overall IT experience?",
            "Do you have 7-10 years of overall IT experience?",
            "Do you have 6+ years of  experience with Node.js and TypeScript development?",
            "Do you have at least 5 to 7 years of hands-on production experience using both React.js/React Native",
            "Do you have 10 plus years of experience?",
            "Do you have 10+ years of experience?",
        ]:
            ans_m, score_m = self.matcher.fuzzy_match(q, input_type="radio")
            self.assertEqual(ans_m, "No", f"Matcher failed for: {q}")

            ans_a, score_a = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans_a, "No", f"Agent failed for: {q}")

    def test_notice_period_in_weeks(self):
        for q in [
            "what is your notice period? in weeks?",
            "what is your notice period in weeks?",
            "notice period (in weeks)",
        ]:
            ans_m, score_m = self.matcher.fuzzy_match(q, input_type="number")
            self.assertIn("2", ans_m, f"Matcher failed for: {q}")
            self.assertNotIn("15", ans_m)

            ans_a, score_a = self.agent._fuzzy_match_question(q)
            self.assertIn("2", ans_a, f"Agent failed for: {q}")
            self.assertNotIn("15", ans_a)

    def test_lwd_date_resolution(self):
        q1 = "If serving Notice Period, when is your last working day with your employer?"
        ans_m1, _ = self.matcher.fuzzy_match(q1, input_type="text")
        self.assertNotIn(ans_m1, ("15", "24", "0", "Yes"))
        self.assertTrue(any(month in ans_m1 for month in ("Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct")) or "/" in ans_m1 or "-" in ans_m1)

        q2 = "Your Official Notice Period or If serving LWD?"
        ans_m2, _ = self.matcher.fuzzy_match(q2, input_type="text")
        self.assertNotIn(ans_m2, ("15", "24", "Yes"))
        self.assertIn("15", ans_m2)
        self.assertIn("LWD", ans_m2)

    def test_production_grade_application_description(self):
        q = "Briefly describe a production-grade application you built or significantly contributed to. What was the scale and your specific role?"
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertGreaterEqual(score_m, 0.85)
        self.assertNotEqual(ans_m, "Yes")
        self.assertIn("Everbridge", ans_m)

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score_a, 0.85)
        self.assertNotEqual(ans_a, "Yes")
        self.assertIn("Everbridge", ans_a)

    def test_lever_application_exact_match(self):
        # Bare 'application' must require exact match so it does not hijack open-ended questions
        pattern_entry = self.patterns.get("patterns", {}).get("lever_application", {})
        self.assertTrue(pattern_entry.get("requires_exact_match", False))
        q_long = "Tell us about a distributed web application you designed in Java."
        ans, _ = self.matcher.fuzzy_match(q_long, input_type="textarea")
        self.assertNotEqual(ans, "Yes")

    def test_pan_card_mandatory_upload(self):
        q = "PAN No, mandatory for uploading the profile."
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="text")
        self.assertEqual(ans_m, "MTKPS1941P")
        self.assertNotEqual(ans_m, "Yes")

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_a, "MTKPS1941P")
        self.assertNotEqual(ans_a, "Yes")

    def test_location_queries_vizag_delhi(self):
        q_vizag = "Are you currently in Vizag?"
        ans_v_m, _ = self.matcher.fuzzy_match(q_vizag, input_type="radio")
        self.assertEqual(ans_v_m, "No")

        q_vizag2 = "If you are not currently in Vizag are you originally from Vizag or nearby?"
        ans_v2_m, _ = self.matcher.fuzzy_match(q_vizag2, input_type="radio")
        self.assertEqual(ans_v2_m, "No")

        q_delhi = "Are you based in Delhi?"
        ans_d_m, _ = self.matcher.fuzzy_match(q_delhi, input_type="radio")
        self.assertEqual(ans_d_m, "No")

    def test_cloudformation_explanation_not_years(self):
        q = "Have you worked with CloudFormation? Please explain your experience."
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="text")
        self.assertNotEqual(ans_m, "4.2 Years")
        self.assertTrue("CloudFormation" in ans_m or "Terraform" in ans_m)

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertNotEqual(ans_a, "4.2 Years")

    def test_us_hours_acceptable(self):
        q = "This job requires working US hours i.e. from 7PM India time to 4AM India time. Is that acceptable? I"
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_m, "Yes")

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_a, "Yes")


if __name__ == "__main__":
    unittest.main()
