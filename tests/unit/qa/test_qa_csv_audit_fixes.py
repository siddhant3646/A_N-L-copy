"""
Unit tests covering all 29 question discrepancies identified during the qa_results.csv audit,
verifying accurate answers, proper input-type handling, and tool rule preservation (.NET/Calypso/AEM).
"""

import unittest
from src.patterns.pattern_matcher import create_matcher
from src.sentinel.agent import SentinelAgent


class TestQACSVAuditFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()

    def test_textarea_location_affirmative(self):
        q = "This role requires you to be in Bengaluru. Are you okay with that?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("Yes", ans)
        self.assertIn("Bengaluru", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_fast_paced_alignment(self):
        q = "We're incredibly fast-paced. We do whatever it takes to get things done. Would you be aligned with this aspect?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.startswith("Yes"))
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_combined_compensation(self):
        q = "What is your current compensation? Would be great if you can highlight your expected compensation as well."
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("23 LPA", ans)
        self.assertIn("30 LPA", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_joining_availability(self):
        q = "How quickly can you join us if shortlisted?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("15", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_lead_developer_product_ownership(self):
        q = "Have you been the main or only developer on a product that real users used? If yes, which one and what were you responsible for keeping running after launch?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("Everbridge", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_ui_design_fidelity_responsiveness(self):
        q = "Show a piece of UI you built from a design. How close did the final result come to the design, and how did you handle responsiveness?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("React.js", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_textarea_product_feature_owned_end_to_end(self):
        q = "Describe one product or feature you owned end to end, from idea to production. What was your specific role, and what did you decide yourself?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertIn("Everbridge", ans)
        self.assertIn("microservices", ans)
        self.assertGreaterEqual(score, 0.90)

    def test_select_relevant_years_experience(self):
        q = "Specify your relevant years of experience"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_gender_selection(self):
        q = "Gender"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "Male")
        self.assertGreaterEqual(score, 0.90)

    def test_experience_agentic_ai(self):
        q = "How many years of experience in Agentic AI?"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_experience_full_stack_select(self):
        q = "How many years of experience in Full Stack Development?"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_experience_cloud_devops_select(self):
        q = "How many years of experience in Azure, Docker, Kubernetes, and GitHub?"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_preserved_tool_rule_dotnet_core(self):
        q = "How many years of experience do you have in .Net Core?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertNotEqual(ans, "0")
        self.assertGreaterEqual(score, 0.90)

    def test_preserved_tool_rule_rel_exp_dotnetcore(self):
        q = "Rel Exp in .Netcore:"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertNotEqual(ans, "0")
        self.assertGreaterEqual(score, 0.90)

    def test_preserved_tool_rule_calypso(self):
        q = "How many years of experience do you have in Calypso?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_preserved_tool_rule_aem_backend(self):
        q = "How many years of experience do you have in AEM backend?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_diagnose_and_solve_problems_affirmative(self):
        q = "Can you independently diagnose and solve technical problems?"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "Yes")
        self.assertGreaterEqual(score, 0.90)

    def test_internal_employee_referral_negative(self):
        q = "Were you referred by an internal Xometry employee?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "No")
        self.assertGreaterEqual(score, 0.90)

    def test_internal_referral_name_na(self):
        q = "If you answered yes to the last question, please provide the employee’s first and last name"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "N/A")
        self.assertGreaterEqual(score, 0.90)

    def test_ex_employee_freshworks_negative(self):
        q = "Have you been previously employed with Freshworks?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "No")
        self.assertGreaterEqual(score, 0.90)

    def test_education_mba_negative(self):
        q = "Have you completed the following level of education: Master of Business Administration?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "No")
        self.assertGreaterEqual(score, 0.90)

    def test_confirm_notice_period_2_digit(self):
        q = "Please confirm the notice period(7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)? 2 or 3 months candidates can ignore this role?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "15")
        self.assertGreaterEqual(score, 0.90)

    def test_rate_proficiency_scale_5(self):
        q = "Rate your proficiency (1-5) in our core stack: React.js, Next.js, and React Native."
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertIn(ans, ["4", "5"])
        self.assertGreaterEqual(score, 0.90)

    def test_sql_hands_on_or_familiar(self):
        q = "Do you have hands-on experience with SQL, or are you familiar with SQL cpncepts?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "Yes")
        self.assertGreaterEqual(score, 0.90)

    def test_github_link_exact(self):
        q = "Github link"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "https://github.com/siddhant3646")
        self.assertGreaterEqual(score, 0.90)

    def test_current_job_title(self):
        q = "Your title"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "Software Engineer 2")
        self.assertGreaterEqual(score, 0.90)

    def test_current_company(self):
        q = "Company"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertEqual(ans, "Everbridge")
        self.assertGreaterEqual(score, 0.90)

    def test_compound_ctc_current_and_expected(self):
        q = "CTC: Current & Expected?"
        ans, score = self.matcher.fuzzy_match(q, input_type="text")
        self.assertIsNotNone(ans)
        self.assertIn("23 LPA", ans)
        self.assertIn("30 LPA", ans)
        self.assertGreaterEqual(score, 0.90)


if __name__ == "__main__":
    unittest.main()
