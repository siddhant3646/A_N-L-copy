"""
Unit tests covering all 29 question discrepancies identified during the qa_results.csv audit,
verifying accurate answers, proper input-type handling, and tool rule preservation (.NET/Calypso/AEM).
"""

import unittest
import json
import re
from src.patterns.pattern_matcher import create_matcher
from src.patterns.pattern_loader import load_patterns, validate_patterns
from src.patterns.input_aware_resolver import (
    InputAwareResolver,
    InputType,
    Option,
    OptionExtractor,
    NumericRangeMatcher,
)
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
    def test_experience_microservices_radio_range(self):
        q = "How many years of experience do you have in Microservices?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        resolver = InputAwareResolver()
        options = [
            Option(value="0", label="0 - 6 months"),
            Option(value="1", label="1 - 3 yrs"),
            Option(value="2", label="3 - 5 yrs"),
            Option(value="3", label="5+ yrs")
        ]
        res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3 - 5 yrs")
        self.assertNotEqual(res.matched_option.label, "0 - 6 months")

    def test_experience_cloud_radio_range(self):
        q = "How much experience you hold in Cloud?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        resolver = InputAwareResolver()
        options = [
            Option(value="0", label="0 - 6 months"),
            Option(value="1", label="1 - 3 yrs"),
            Option(value="2", label="3 - 5 yrs"),
            Option(value="3", label="5+ yrs")
        ]
        res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3 - 5 yrs")
        self.assertNotEqual(res.matched_option.label, "0 - 6 months")

    def test_experience_python_iam_radio_range(self):
        q = "How much experience you hold in IAM Roles and Python (Fast API)?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        resolver = InputAwareResolver()
        options = [
            Option(value="0", label="0 - 6 months"),
            Option(value="1", label="1 - 3 yrs"),
            Option(value="2", label="3 - 5 yrs")
        ]
        res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3 - 5 yrs")
        self.assertNotEqual(res.matched_option.label, "0 - 6 months")

    def test_experience_java_radio_range(self):
        q = "How much experience you hold in Java"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        resolver = InputAwareResolver()
        options = [
            Option(value="0", label="0 - 2 yrs"),
            Option(value="1", label="2 - 4 yrs"),
            Option(value="2", label="4 - 6 yrs"),
            Option(value="3", label="6+ yrs")
        ]
        res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "4 - 6 yrs")
        self.assertNotEqual(res.matched_option.label, "0 - 2 yrs")

    def test_experience_react_radio_range(self):
        q = "How much experience you hold in React.Js?"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        resolver = InputAwareResolver()
        options = [
            Option(value="0", label="0 - 0.6 months"),
            Option(value="1", label="1 - 3 yrs"),
            Option(value="2", label="3 - 5 yrs"),
            Option(value="3", label="5+ yrs")
        ]
        res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3 - 5 yrs")
        self.assertNotEqual(res.matched_option.label, "0 - 0.6 months")

    def test_instahyre_expected_ctc_lpa(self):
        p = self.matcher.patterns['patterns'].get('instahyre_expected_ctc_lpa')
        self.assertIsNotNone(p)
        self.assertEqual(p.get('default'), "30 LPA")
        self.assertEqual(p.get('platform_overrides', {}).get('instahyre'), "30 LPA")
        self.assertEqual(p.get('input_type_defaults', {}).get('text'), "30 LPA")
        self.assertEqual(p.get('input_type_defaults', {}).get('text_lpa'), "30 LPA")


class TestInputTypeAwareResolving(unittest.TestCase):
    """Verifies that pattern groups support all HTML form input types."""

    @classmethod
    def setUpClass(cls):
        with open("config/qa_patterns.json") as f:
            cls.patterns_db = json.load(f)["patterns"]

    def test_experience_patterns_input_types(self):
        keys = ["dotnet_core_exp", "rel_exp_dotnetcore", "calypso_experience", "aem_backend_experience"]
        for k in keys:
            p = self.patterns_db.get(k)
            self.assertIsNotNone(p, f"Pattern {k} must exist")
            defaults = p.get("input_type_defaults", {})
            self.assertEqual(defaults.get("text"), "4.2 Years")
            self.assertEqual(defaults.get("select"), "4.2 Years")
            self.assertEqual(defaults.get("radio"), "4.2")
            self.assertEqual(defaults.get("number"), "4.2")
            self.assertIn("textarea", defaults)
            self.assertTrue(len(defaults["textarea"]) > 0)

    def test_salary_patterns_input_types(self):
        p = self.patterns_db.get("current_salary")
        self.assertIsNotNone(p)
        defaults = p.get("input_type_defaults", {})
        self.assertEqual(defaults.get("text"), "23 LPA")
        self.assertEqual(defaults.get("select"), "23 LPA")
        self.assertEqual(defaults.get("radio"), "23")
        self.assertEqual(defaults.get("number"), "23")
        self.assertEqual(defaults.get("text_inr"), "2300000")

        p_exp = self.patterns_db.get("expected_salary")
        self.assertIsNotNone(p_exp)
        exp_defaults = p_exp.get("input_type_defaults", {})
        self.assertEqual(exp_defaults.get("text"), "30 LPA")
        self.assertEqual(exp_defaults.get("select"), "30 LPA")
        self.assertEqual(exp_defaults.get("radio"), "30")
        self.assertEqual(exp_defaults.get("number"), "30")
        self.assertEqual(exp_defaults.get("text_inr"), "3000000")

    def test_notice_period_input_types(self):
        p = self.patterns_db.get("notice_period")
        self.assertIsNotNone(p)
        defaults = p.get("input_type_defaults", {})
        self.assertEqual(defaults.get("text"), "15")
        self.assertEqual(defaults.get("select"), "15 days")
        self.assertEqual(defaults.get("radio"), "15")
        self.assertEqual(defaults.get("number"), "15")

    def test_yes_no_compliance_input_types(self):
        keys = ["referred_by_internal_employee", "ex_employee_freshworks", "education_mba_degree"]
        for k in keys:
            p = self.patterns_db.get(k)
            self.assertIsNotNone(p, f"Pattern {k} must exist")
            self.assertEqual(p.get("default"), "No")
            defaults = p.get("input_type_defaults", {})
            self.assertEqual(defaults.get("radio"), "No")
            self.assertEqual(defaults.get("select"), "No")
            self.assertEqual(defaults.get("text"), "No")


class TestPlatformOverrides(unittest.TestCase):
    """Verifies platform-specific formatting rules (LinkedIn whole number vs Naukri 'X Years', raw INR vs LPA)."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()
        with open("config/qa_patterns.json") as f:
            cls.patterns_db = json.load(f)["patterns"]

    def test_linkedin_experience_whole_number(self):
        self.agent._current_platform = "linkedin"
        ans, score = self.agent._fuzzy_match_question("enter whole number years of experience")
        self.assertEqual(ans, "4")
        self.assertGreaterEqual(score, 0.90)
        p = self.patterns_db.get("select_relevant_years_experience")
        self.assertEqual(p["platform_overrides"]["linkedin"], "4")

    def test_naukri_experience_x_years(self):
        self.agent._current_platform = "naukri"
        ans, score = self.agent._fuzzy_match_question("years of experience")
        self.assertEqual(ans, "4.2 Years")
        self.assertGreaterEqual(score, 0.90)

    def test_calypso_platform_overrides(self):
        p = self.patterns_db.get("calypso_experience")
        self.assertEqual(p["default"], "4.2 Years")
        self.assertEqual(p["platform_overrides"]["linkedin"], "4")

    def test_dotnet_platform_overrides(self):
        p = self.patterns_db.get("dotnet_core_exp")
        self.assertEqual(p["default"], "4.2 Years")
        self.assertEqual(p["platform_overrides"]["linkedin"], "4")

        p_rel = self.patterns_db.get("rel_exp_dotnetcore")
        self.assertEqual(p_rel["default"], "4.2 Years")
        self.assertEqual(p_rel["platform_overrides"]["linkedin"], "4")

    def test_aem_platform_overrides(self):
        p = self.patterns_db.get("aem_backend_experience")
        self.assertEqual(p["default"], "4.2 Years")
        self.assertEqual(p["platform_overrides"]["linkedin"], "4")

    def test_salary_platform_overrides(self):
        p_curr = self.patterns_db.get("current_salary")
        self.assertEqual(p_curr["input_type_defaults"]["text_inr"], "2300000")
        self.assertEqual(p_curr["input_type_defaults"]["text"], "23 LPA")

        p_exp = self.patterns_db.get("expected_salary")
        self.assertEqual(p_exp["input_type_defaults"]["text_inr"], "3000000")
        self.assertEqual(p_exp["input_type_defaults"]["text"], "30 LPA")


class TestRuleR4ExperiencePreservation(unittest.TestCase):
    """Rule R4: Candidate total experience preservation for Calypso, .NET/C#, and AEM backend questions."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()
        with open("config/qa_patterns.json") as f:
            cls.patterns_db = json.load(f)["patterns"]

    def test_r4_dotnet_core_not_zero(self):
        q = "How many years of experience do you have in .Net Core?"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertNotEqual(ans, "0")
        self.assertIn(ans, ["4.2 Years", "4", "4.2"])
        self.assertGreaterEqual(score, 0.90)

    def test_r4_rel_exp_dotnetcore_not_zero(self):
        q = "Rel Exp in .Netcore:"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertNotEqual(ans, "0")
        self.assertIn(ans, ["4.2 Years", "4", "4.2"])
        self.assertGreaterEqual(score, 0.90)

    def test_r4_calypso_not_zero(self):
        q = "How many years of experience do you have in Calypso?"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertNotEqual(ans, "0")
        self.assertIn(ans, ["4.2 Years", "4", "4.2"])
        self.assertGreaterEqual(score, 0.90)

    def test_r4_aem_backend_not_zero(self):
        q = "How many years of experience do you have in AEM backend?"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertNotEqual(ans, "0")
        self.assertIn(ans, ["4.2 Years", "4", "4.2"])
        self.assertGreaterEqual(score, 0.90)

    def test_r4_json_pattern_defaults(self):
        for key in ["dotnet_core_exp", "rel_exp_dotnetcore", "calypso_experience", "aem_backend_experience"]:
            p = self.patterns_db.get(key)
            self.assertIsNotNone(p, f"Missing pattern {key}")
            self.assertEqual(p.get("default"), "4.2 Years")
            self.assertEqual(p.get("numeric_default"), "4.2")
            self.assertEqual(p.get("platform_overrides", {}).get("linkedin"), "4")


class TestTextareaInputAwareGuards(unittest.TestCase):
    """Verifies that textarea fields receive concise answers for Yes/No, location, salary, and notice period,

    while descriptive open-ended technical prompts receive comprehensive technical essays.
    """

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")

    def test_textarea_yes_no_guards_concise(self):
        questions = [
            "This role requires you to be in Bengaluru. Are you okay with that?",
            "We're incredibly fast-paced. We do whatever it takes to get things done. Would you be aligned with this aspect?",
            "Are you willing to work in rotational shifts?",
            "Do you have any conflict of interest with our current clients?",
            "Have you been bound by any non-compete agreement?",
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
            self.assertIsNotNone(ans)
            self.assertFalse(
                "4+ years of professional full-stack software engineering experience specializing in distributed systems" in ans,
                f"Question received technical essay instead of concise answer: {q}"
            )
            self.assertTrue(any(ans.startswith(w) for w in ["Yes", "No", "Bengaluru"]), f"Unexpected answer for {q}: {ans}")

    def test_textarea_location_guard_concise(self):
        q = "Where are you currently located or based?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertFalse("4+ years of professional full-stack" in ans)
        self.assertTrue("Bengaluru" in ans or "Bangalore" in ans)

    def test_textarea_salary_guard_concise(self):
        q = "What is your current compensation? Would be great if you can highlight your expected compensation as well."
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertFalse("4+ years of professional full-stack" in ans)
        self.assertIn("23 LPA", ans)
        self.assertIn("30 LPA", ans)

    def test_textarea_notice_guard_concise(self):
        q = "How quickly can you join us if shortlisted?"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertFalse("4+ years of professional full-stack" in ans)
        self.assertIn("15", ans)

    def test_textarea_conditional_guard_concise(self):
        q = "If you answered yes to the last question, please provide the employee’s first and last name"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertFalse("4+ years of professional full-stack" in ans)
        self.assertIn(ans, ["N/A", "None", "Not applicable"])

    def test_textarea_open_ended_technical_essay(self):
        q = "Describe a scalable backend microservice architecture you designed and deployed:"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertTrue(
            "4+ years of professional full-stack software engineering experience" in ans or
            "microservices" in ans.lower()
        )
        self.assertTrue(len(ans) > 100)


class TestDropdownPlaceholderGuards(unittest.TestCase):
    """Verifies that dropdown placeholder options across languages are rejected and legitimate options are selected."""

    def test_placeholder_filtering_multilingual(self):
        html = """
        <select id="lang_test">
            <option value="">Selecciona una opción</option>
            <option value="">Selecione uma opção</option>
            <option value="">Seleziona un'opzione</option>
            <option value="">Bitte auswählen</option>
            <option value="">Sélectionnez une option</option>
            <option value="">Select an option</option>
            <option value="">Choose an option</option>
            <option value="">---</option>
            <option value="3-6">3-6 years</option>
            <option value="6+">6+ years</option>
        </select>
        """
        extracted = OptionExtractor.extract_select_options(html)
        labels = [opt.label for opt in extracted]
        self.assertNotIn("Selecciona una opción", labels)
        self.assertNotIn("Selecione uma opção", labels)
        self.assertNotIn("Seleziona un'opzione", labels)
        self.assertNotIn("Bitte auswählen", labels)
        self.assertNotIn("Sélectionnez une option", labels)
        self.assertNotIn("Select an option", labels)
        self.assertNotIn("Choose an option", labels)
        self.assertNotIn("---", labels)
        self.assertIn("3-6 years", labels)
        self.assertIn("6+ years", labels)

    def test_placeholder_rejection_in_resolver(self):
        resolver = InputAwareResolver()
        raw_options = [
            Option(value="", label="Selecciona una opción"),
            Option(value="Male", label="Male"),
            Option(value="Female", label="Female"),
        ]
        res = resolver.resolve("Male", InputType.SELECT, options=raw_options)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "Male")
        self.assertNotEqual(res.matched_option.label, "Selecciona una opción")

    def test_spanish_placeholder_freshworks_scenario(self):
        html = """
        <select id="freshworks_exp">
            <option value="">Selecciona una opción</option>
            <option value="0-2">0-2 years</option>
            <option value="3-6">3-6 years</option>
            <option value="7+">7+ years</option>
        </select>
        """
        extracted = OptionExtractor.extract_select_options(html)
        resolver = InputAwareResolver()
        res = resolver.resolve("4.2 Years", InputType.SELECT, options=extracted)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3-6 years")
        self.assertNotEqual(res.matched_option.label, "Selecciona una opción")


class TestQAPatternsSchemaValidation(unittest.TestCase):
    """Schema validation confirming config/qa_patterns.json passes validate_patterns with 0 errors."""

    def test_validate_patterns_zero_errors(self):
        patterns = load_patterns("config/qa_patterns.json")
        errors = validate_patterns(patterns)
        self.assertEqual(
            len(errors), 0,
            f"Pattern validation failed with {len(errors)} error(s): {errors[:5]}"
        )

    def test_required_categories_valid(self):
        with open("config/qa_patterns.json") as f:
            data = json.load(f)
        used_cats = set(p.get("category") for p in data["patterns"].values())
        self.assertEqual(len(used_cats), 27, f"Expected exactly 27 categories across patterns, found {len(used_cats)}")
        for pattern_id, pdata in data["patterns"].items():
            cat = pdata.get("category")
            self.assertIn(
                cat, used_cats,
                f"Pattern '{pattern_id}' has invalid category '{cat}'"
            )

    def test_rule_r4_patterns_exist_and_valid(self):
        with open("config/qa_patterns.json") as f:
            patterns = json.load(f)["patterns"]
        for key in ["dotnet_core_exp", "rel_exp_dotnetcore", "calypso_experience", "aem_backend_experience"]:
            self.assertIn(key, patterns)
            p = patterns[key]
            self.assertEqual(p.get("default"), "4.2 Years")
            self.assertEqual(p.get("platform_overrides", {}).get("linkedin"), "4")


if __name__ == "__main__":
    unittest.main()
