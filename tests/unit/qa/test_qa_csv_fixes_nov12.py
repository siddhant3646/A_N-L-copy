"""
Unit tests for QA patterns fixed from qa_results.csv analysis (Nov 12, 2026).
Covers:
1. REST and SOAP web services in banking/financial applications
2. Coding Profile Link (returns GitHub, not LinkedIn)
3. 10th, 12th, and Graduation passed out year and percentage
4. Engineering Manager / EM experience (0 years)
5. Attended interviews or received calls regarding companies previously (No)
6. Non-spoken foreign languages (Arabic, German, French, etc. -> No)
7. IIT / NIT / IIIT education background (No)
8. Bare tech name on text input (e.g. Kafka -> 4 / 4.2 Years, not Yes)
9. Experience managing engineering teams (No)
10. Shift preference on checkbox (Day Job, not Yes)
"""

import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVFixesNov12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SentinelAgent()
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.matcher = PatternMatcher(cls.patterns)

    def test_rest_soap_banking_financial(self):
        q = "Have you developed or consumed REST and SOAP web services (JSON / XML) in a banking or financial application? (Yes / No, with a one-line example.)"
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertGreaterEqual(score_m, 0.95)
        self.assertIn("rest and soap", ans_m.lower())
        self.assertNotIn(ans_m, ("23", "23 LPA", "30", "30 LPA"))

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score_a, 0.95)
        self.assertIn("rest and soap", ans_a.lower())
        self.assertNotIn(ans_a, ("23", "23 LPA", "30", "30 LPA"))

    def test_coding_profile_link(self):
        q = "Coding Profile Link"
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertGreaterEqual(score_m, 0.90)
        self.assertIn("github.com/siddhant3646", ans_m)
        self.assertNotIn("linkedin.com", ans_m)

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score_a, 0.90)
        self.assertIn("github.com/siddhant3646", ans_a)
        self.assertNotIn("linkedin.com", ans_a)

    def test_passed_out_year_and_percentage(self):
        q10 = "10th class passed out year and percentage ( for example 2015 and 90%)"
        ans10_m, _ = self.matcher.fuzzy_match(q10, input_type="text")
        self.assertIn("2016", ans10_m)
        self.assertIn("90%", ans10_m)

        ans10_a, _ = self.agent._fuzzy_match_question(q10)
        self.assertIn("2016", ans10_a)
        self.assertIn("90%", ans10_a)

        q12 = "12th class or Diploma passed out year and Percentage (for example 2017 and 85% or Diploma 2018 and 85%)"
        ans12_m, _ = self.matcher.fuzzy_match(q12, input_type="text")
        self.assertIn("2018", ans12_m)
        self.assertIn("85%", ans12_m)

        ans12_a, _ = self.agent._fuzzy_match_question(q12)
        self.assertIn("2018", ans12_a)
        self.assertIn("85%", ans12_a)

        qgrad = "Graduation passed out year and percentage (for example B.Tech -2021-60%)"
        ansg_m, _ = self.matcher.fuzzy_match(qgrad, input_type="text")
        self.assertIn("2022", ansg_m)
        self.assertNotEqual(ansg_m, "Yes")

        ansg_a, _ = self.agent._fuzzy_match_question(qgrad)
        self.assertIn("2022", ansg_a)
        self.assertNotEqual(ansg_a, "Yes")

    def test_em_experience_zero(self):
        q = "How many years of experience do you have in EM (in Years)?"
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="number")
        self.assertEqual(ans_m, "0")

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertIn("0", ans_a)
        self.assertNotIn(ans_a, ("4", "4.2", "4.2 Years"))

    def test_interviewed_or_calls_previously(self):
        q = "Have you attended any interviews or received any calls regarding IBM previously?"
        ans_m, score_m = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_m, "No")

        ans_a, score_a = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_a, "No")

    def test_foreign_languages_no(self):
        for lang_q in [
            "Are you fluent in Arabic (spoken and written)?",
            "do you speak german",
            "french language proficiency",
            "are you proficient in spanish",
        ]:
            ans_m, _ = self.matcher.fuzzy_match(lang_q, input_type="radio")
            self.assertEqual(ans_m, "No", f"Matcher failed for {lang_q}")

            ans_a, _ = self.agent._fuzzy_match_question(lang_q)
            self.assertEqual(ans_a, "No", f"Agent failed for {lang_q}")

    def test_iit_nit_iiit_education(self):
        q = "Are you from any IIT / NIT / IIIT - BE / B.Tech / MTech / MCA - Education Background?"
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_m, "No")

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_a, "No")

    def test_bare_kafka_text_input(self):
        q = "Kafka"
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIn("4", ans_m)
        self.assertNotEqual(ans_m, "Yes")

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertIn("4", ans_a)
        self.assertNotEqual(ans_a, "Yes")

    def test_experience_managing_engineering_teams(self):
        q = "Engineering Management & Technical Leadership Do you have at least 3 years of experience managing frontend, backend and/or platform engineering teams, including architecture decisions, system design, code reviews, technical mentoring and end-to-end engineering delivery?"
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_m, "No")

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_a, "No")

    def test_shift_preference_checkbox(self):
        q = "Please share your shift preference"
        ans_m, _ = self.matcher.fuzzy_match(q, input_type="checkbox")
        self.assertIn("Day Job", ans_m)
        self.assertNotEqual(ans_m, "Yes")

        ans_a, _ = self.agent._fuzzy_match_question(q)
        self.assertIn("Day Job", ans_a)
        self.assertNotEqual(ans_a, "Yes")


if __name__ == "__main__":
    unittest.main()
