import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sentinel.agent import SentinelAgent

class TestQAUpdates(unittest.TestCase):
    """QA pattern matching tests.

    Note: Tests use assertGreater(score, 0.8) which exceeds
    PatternMatcher.DEFAULT_THRESHOLD (0.65). They pass because PHASE 1
    hardcoded interceptions in agent.py return 0.90-0.98 confidence.
    See IMPLEMENTATION_SUMMARY.md 'Two-Tier Matching Architecture' for details.
    """
    def setUp(self):
        self.agent = SentinelAgent()

    def test_onsite_availability(self):
        questions = [
            "Are you available to work Full-Time on-site*",
            "Are you available to work Full-Time on-site",
            "available for full-time on-site work"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn('Yes', ans, f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_experience_years(self):
        questions = [
            "How Many Years of work experience do you have in your chosen engineering field*",
            "years of work experience in chosen engineering field"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn(ans, ['4', '4'], f"Failed for question: {q}") 
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_area_of_experience(self):
        questions = [
            "What area have you most experience in?*",
            "What area have you most experience in"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Full-stack', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_leetcode_questions(self):
        questions = [
            "How many questions you have solved in Leetcode?*",
            "Number of Leetcode problems solved"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, '500+', f"Failed for question: {q}")
    def test_commuting_availability(self):
        questions = [
            "Are you comfortable commuting to this job's location?*",
            "Are you comfortable commuting to this job's location",
            "comfortable commuting to this job"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Yes', f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for question: {q}")

    def test_ex_amazon_candidate(self):
        questions = [
            "Are you an Ex- Amazon candidate?*",
            "Are you an Ex-Amazon candidate?",
            "ex-amazon candidate"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'No', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_join_immediately_serving_np(self):
        questions = [
            "Can you Join Immediately or Currently Serving NP?*",
            "Can you Join Immediately or Currently Serving NP?",
            "can you join immediately or currently serving np"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Yes', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_based_in_mumbai_or_pune(self):
        questions = [
            "Are you Currently based in Mumbai or Pune*",
            "Are you Currently based in Mumbai or Pune",
            "currently based in mumbai or pune"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn('Bangalore', ans, f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

class TestNewPatternsReliability(unittest.TestCase):
    """Tests for the 2026-08-04 pattern additions.

    Uses PatternMatcher directly (like test_known_qa_reliability.py) since
    these patterns are verified at the JSON pattern layer (0.98 confidence).
    """
    def setUp(self):
        from src.patterns.pattern_matcher import create_matcher
        self.matcher = create_matcher()

    def check(self, question, expected, hint=None):
        ans, score = self.matcher.fuzzy_match(question)
        print(f"Q: '{question}' -> A: '{ans}' (Score: {score})")
        self.assertIsNotNone(ans, f"No match for question: {question}")
        self.assertIn(expected.lower(), str(ans).lower(), f"Failed for question: {question}" + (f" ({hint})" if hint else ""))
        self.assertGreater(score, 0.8, f"Low confidence for question: {question}")

    def test_bare_email(self):
        for q in ["Email", "Email*", "Your Email Address"]:
            self.check(q, "siddhant3646@gmail.com")

    def test_pf_history(self):
        for q in [
            "Do you have PF for all companies which you have worked?",
            "Do you have PF for all companies which you have worked?*",
            "Do you have provident fund for all companies?",
        ]:
            self.check(q, "Yes")

    def test_policy_opcodes(self):
        for q in ["Have you developed Policy Opcodes? (Yes/No)", "Have you developed Policy Opcodes?"]:
            self.check(q, "Yes")

    def test_fresher_check(self):
        for q in ["Are you a fresher?", "Are you a fresher or experienced professional?", "Fresher"]:
            self.check(q, "No")

    def test_has_work_experience(self):
        for q in ["Do you have any work experience?", "Do you have any prior work experience?"]:
            self.check(q, "Yes")

    def test_relatives_at_company(self):
        for q in ["Do you have any relatives working in our company?", "Do you have any family member working with us?"]:
            self.check(q, "No")

    def test_ex_employee_check(self):
        for q in ["Have you ever worked for our company?", "Have you previously worked for our company?"]:
            self.check(q, "No")

    def test_azure_experience(self):
        for q in [
            "Do you have azure cloud experience? if yes how many years?",
            "azure cloud experience",
            "years of experience in azure",
        ]:
            self.check(q, "4")

    def test_gcp_experience(self):
        for q in [
            "how many years of experience do you have in gcp",
            "google cloud experience",
            "gcp experience",
        ]:
            self.check(q, "4")

    def test_laid_off_check(self):
        for q in ["Have you ever been laid off?", "Have you ever been terminated from a job?"]:
            self.check(q, "No")

    def test_noc_relieving_letter(self):
        for q in ["Can you provide NOC from current employer?", "Can you provide a relieving letter?", "experience letter available"]:
            self.check(q, "Yes")

    def test_laptop_availability(self):
        for q in ["Do you have your own laptop?", "Do you have a laptop and internet connection?"]:
            self.check(q, "Yes")

    def test_expected_hike_percent(self):
        for q in ["What is your expected hike percentage?", "Expected hike %", "What salary hike are you expecting?"]:
            self.check(q, "30")

    def test_salary_slips(self):
        for q in ["Can you provide salary slips?", "Please provide your payslip", "Can you provide form 16?"]:
            self.check(q, "Yes")

    def test_db_experience(self):
        for q in [
            "How many years of experience do you have with PostgreSQL?",
            "years of experience with mongodb",
            "years of experience with mysql",
            "sonarqube experience",
            "memcached experience",
        ]:
            self.check(q, "4")

    def test_distributed_system_concepts(self):
        for q in [
            "Do you have experience with circuit breaker patterns?",
            "Have you implemented idempotency in your APIs?",
            "Do you have load testing experience?",
            "Have you implemented rate limiting?",
        ]:
            self.check(q, "Yes")

    def test_redux_state_management(self):
        for q in ["Do you use Redux for state management?", "Do you use Redux Toolkit?", "Which state management library do you use?"]:
            self.check(q, "Yes")

    def test_oauth_jwt_sso(self):
        for q in ["Have you implemented OAuth 2.0 or JWT based auth?", "Do you have single sign on experience?", "Have you implemented token based authentication?"]:
            self.check(q, "Yes")

    def test_feature_flags_ab_testing(self):
        for q in ["Do you have experience with feature flags?", "Do you use feature toggles?", "Do you have A/B testing experience?"]:
            self.check(q, "Yes")

    def test_oncall_availability(self):
        for q in ["Are you available for on-call support?", "Are you available for on-call?", "Are you available for production support?"]:
            self.check(q, "Yes")

    def test_startup_comfort(self):
        for q in ["Are you comfortable working in a startup environment?", "Are you comfortable with a fast paced environment?"]:
            self.check(q, "Yes")

    def test_industry_domain(self):
        for q in [
            "Do you have experience in the insurance domain?",
            "Do you have experience in the healthcare domain?",
            "Do you have experience in the telecom domain?",
            "Do you have experience in the retail domain?",
        ]:
            self.check(q, "Yes")

    def test_monolith_migration(self):
        for q in [
            "Have you worked on monolith to microservices migration?",
            "Have you done monolithic to microservices migration?",
            "Do you have microservices migration experience?",
        ]:
            self.check(q, "Yes")

    def test_site_visit_availability(self):
        for q in ["Are you available for site visits?", "Can you visit client site?", "Are you available for onsite visits?"]:
            self.check(q, "Yes")

    def test_terms_consent(self):
        for q in ["Do you agree to the terms and conditions?", "Do you accept the terms and conditions?", "Do you consent to data processing?"]:
            self.check(q, "Yes")


if __name__ == '__main__':
    unittest.main()
