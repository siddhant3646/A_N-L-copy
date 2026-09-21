"""Unit tests for September 21 QA engine hardening and disambiguation fixes.

Covers:
1. Current company vs Industry/Domain/Size/Product-type disambiguation:
   - "What is your current company name?" -> 'Everbridge'
   - "Which industry does your current organization belong to?" -> 'SaaS B2B' / not 'Everbridge'
   - "Size of your current organization" -> '1000+ employees' / not 'Everbridge'
   - "Is your current company product based?" -> 'Yes' / not 'Everbridge'
2. Compliance vs Tech experience disambiguation in QuestionClassifier & InputAwareResolver:
   - "Have you worked with React and Node.js?" -> 'Yes'
   - "Have you worked with Kafka and Redis?" -> 'Yes'
   - "Have you worked with Visa in the past?" -> 'No'
   - "Have you worked with Everbridge?" -> 'Yes'
   - "Have you worked with Navan / Google?" -> 'No'
3. Travel percentage and business travel flexibility:
   - Travel percentage with range options resolves to 'Up to 25%' or matching range.
4. Salary split and monthly salary precision.
"""

import os
import unittest

from src.sentinel.agent import SentinelAgent
from src.sentinel.question_classifier import QuestionClassifier, QuestionCategory
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver, InputType, Option


class TestQACSVAuditFixesSept21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        json_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "config", "qa_patterns.json"
        )
        cls.patterns_data = load_patterns(json_path)
        cls.pattern_matcher = PatternMatcher(cls.patterns_data)
        cls.resolver = InputAwareResolver()
        cls.agent = SentinelAgent()
        cls.classifier = QuestionClassifier()

    def test_current_company_vs_industry_size_domain(self):
        """Verify current company name questions return 'Everbridge' while industry/size questions do not."""
        company_name_questions = [
            "Company",
            "Current Company",
            "Current Employer",
            "Name of current company",
            "Name of current employer",
            "Your current company",
        ]
        for q in company_name_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Everbridge", f"Failed for company name query: {q}")
            self.assertGreaterEqual(conf, 0.90)

        # Questions about industry, size, product-service should NOT return 'Everbridge'
        domain_questions = [
            "Which industry does your current organization belong to?",
            "Industry of your current organization",
            "Size of your current organization",
            "Company size",
            "Is your current company product based or service based?",
        ]
        for q in domain_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertNotEqual(ans, "Everbridge", f"Domain/industry question wrongly returned Everbridge: {q}")

    def test_compliance_vs_tech_stack_experience(self):
        """Verify past employer compliance returns No while technical skills return Yes."""
        tech_questions = [
            "Have you worked with React and Node.js?",
            "Have you worked on Kafka and Redis?",
            "Do you have experience in Python?",
            "Have you worked with Docker and Kubernetes?",
            "Have you worked with Spring Boot microservices?",
        ]
        options = ["Yes", "No"]
        for q in tech_questions:
            ans, conf, reason = self.classifier.get_option_aware_answer(q, options)
            self.assertEqual(ans, "Yes", f"Technical experience wrongly answered '{ans}' for query: {q}")

        compliance_non_employers = [
            "Have you worked with Visa in the past?",
            "Have you worked with Navan?",
            "Have you worked with Reed?",
            "Have you worked with Nielsen?",
            "Have you worked with Google in the past?",
        ]
        for q in compliance_non_employers:
            ans, conf, reason = self.classifier.get_option_aware_answer(q, options)
            self.assertEqual(ans, "No", f"Non-employer question wrongly answered '{ans}' for query: {q}")

        # Current/past actual employers must answer Yes
        self_employer_questions = [
            "Have you worked with Everbridge?",
            "Have you worked with Fiserv?",
        ]
        for q in self_employer_questions:
            ans, conf, reason = self.classifier.get_option_aware_answer(q, options)
            self.assertEqual(ans, "Yes", f"Actual employer question wrongly answered '{ans}' for query: {q}")

    def test_input_aware_resolver_compliance_guard(self):
        """Verify InputAwareResolver boolean guards enforce compliance 'No' even on generic fallback inputs."""
        options = [
            Option(value="Yes", label="Yes", index=0),
            Option(value="No", label="No", index=1),
        ]
        # Even if base answer is "4 Years", compliance questions must resolve to "No"
        q_visa = "Have you worked with Visa in the past?"
        res = self.resolver.resolve("4 Years", InputType.RADIO, options, question=q_visa)
        self.assertEqual(res.matched_option.label, "No")

        q_conflict = "Do you have any conflict of interest with company employees?"
        res_conflict = self.resolver.resolve("Yes", InputType.RADIO, options, question=q_conflict)
        self.assertEqual(res_conflict.matched_option.label, "No")

    def test_travel_percentage_resolution(self):
        """Verify travel percentage questions resolve properly to percentage range options."""
        options = [
            Option(value="0-25%", label="0-25%", index=0),
            Option(value="25-50%", label="25-50%", index=1),
            Option(value="50-75%", label="50-75%", index=2),
            Option(value="75-100%", label="75-100%", index=3),
        ]
        ans, conf = self.pattern_matcher.fuzzy_match("What percentage of travel are you comfortable with?")
        self.assertTrue(ans is not None and ("25" in ans or "Yes" in ans or "Up to" in ans))

    def test_salary_breakup_and_monthly(self):
        """Verify fixed/variable salary breakup and monthly salary answers."""
        ans, conf = self.agent._fuzzy_match_question("Fixed vs variable salary breakup")
        self.assertEqual(ans, "Fixed CTC: 21 LPA, Variable: 2 LPA")
        self.assertGreaterEqual(conf, 0.95)

        ans_month, conf_month = self.agent._fuzzy_match_question("Current monthly salary")
        self.assertEqual(ans_month, "191667")
        self.assertGreaterEqual(conf_month, 0.95)

        ans_month_exp, conf_month_exp = self.agent._fuzzy_match_question("Expected monthly salary")
        self.assertEqual(ans_month_exp, "250000")
        self.assertGreaterEqual(conf_month_exp, 0.95)


if __name__ == "__main__":
    unittest.main()
