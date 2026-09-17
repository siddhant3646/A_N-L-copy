"""Unit tests for September 14 QA fixes."""

import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestQASept14Fixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.pattern_matcher = PatternMatcher(cls.patterns)
        cls.agent = SentinelAgent()

    def test_visa_sponsorship_answers_no(self):
        questions = [
            "Will you now or in the future require Visa Sponsorship?",
            "Do you now, or will you in the future, require employment visa sponsorship or support (e.g., H-1B, O-1, TN...)?",
            "Will you require visa sponsorship now or in the future?",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
            self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_family_relatives_personal_relationships_answers_no(self):
        q = (
            "To the best of your knowledge, do you have any family members / relatives "
            "or personal relationships at Okta or at any suppliers, partners, or vendors "
            "that have a business relationship with Okta?"
        )
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
        self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_outside_business_activities_answers_no(self):
        q = (
            "Do you have any outside business activity(ies) (advisory, consulting, "
            "or board roles, or side businesses) that you would continue engaging in "
            "or plan to engage in if you joined Okta in this role?"
        )
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
        self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_ex_employee_okta_subsidiaries_answers_no(self):
        q = "Have you been employed by Okta, Inc. or any of its subsidiaries in the past?"
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
        self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_internal_referral_answers_no(self):
        questions = [
            "Were you referred by an internal Xometry employee?",
            "Were you referred by an internal employee?",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
            self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_country_of_residence_answers_india(self):
        questions = [
            "Please confirm the Country in which you currently reside?",
            "If the country you currently live in is NOT listed in the question above, please confirm in which country you live?",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertEqual(agent_ans, "India", f"Agent failed for: {q}")
            self.assertEqual(pm_ans, "India", f"PatternMatcher failed for: {q}")

    def test_salary_expectations(self):
        q = "What are your salary expectations for this role?"
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertIn("30", agent_ans)
        self.assertIn("30", pm_ans)

    def test_employment_documents_and_payslips(self):
        q = "PF, Payslips & Employment Documents Available for All Previous Employers?"
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertTrue(agent_ans.startswith("Yes"))
        self.assertTrue(pm_ans.startswith("Yes"))

    def test_notice_period_negotiable(self):
        questions = [
            "Is Notice Period negotiable?",
            "Is your notice period negotiable?",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertEqual(agent_ans, "Yes", f"Agent failed for: {q}")
            self.assertEqual(pm_ans, "Yes", f"PatternMatcher failed for: {q}")

    def test_if_yes_please_describe(self):
        q = "If yes, please describe:"
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertIn(agent_ans, ["N/A", "None", "No"])
        self.assertIn(pm_ans, ["N/A", "None", "No"])

    def test_counter_offers_answers_no(self):
        questions = [
            "Are you holding any counter offer ?",
            "Any offer? (If Yes, please mention the value and DOJ)",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertEqual(agent_ans, "No", f"Agent failed for: {q}")
            self.assertEqual(pm_ans, "No", f"PatternMatcher failed for: {q}")

    def test_contract_type_answers_full_time(self):
        q = "What type of contract are you looking for ?"
        agent_ans, _ = self.agent._fuzzy_match_question(q)
        pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
        self.assertEqual(agent_ans, "Full-time")
        self.assertEqual(pm_ans, "Full-time")

    def test_excluded_questions_maintain_total_experience(self):
        # 13, 14, 15 must NOT be 0 (retains candidate total experience)
        questions = [
            "How many years of experience do you have in Calypso?",
            "How much hands-on experience do you have with .NET and C# development?",
            "How many years of hands-on AEM backend experience you have?",
        ]
        for q in questions:
            agent_ans, _ = self.agent._fuzzy_match_question(q)
            pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
            self.assertNotEqual(agent_ans, "0", f"Should not be 0 for: {q}")
            self.assertNotEqual(pm_ans, "0", f"Should not be 0 for: {q}")
            self.assertTrue("4" in agent_ans, f"Expected 4+ years for: {q}")


if __name__ == "__main__":
    unittest.main()
