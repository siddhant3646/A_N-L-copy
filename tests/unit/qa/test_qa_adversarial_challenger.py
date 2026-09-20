"""
Adversarial Challenger Test Suite for Sentinel Milestone 4.

Empirically challenges:
1. Boundary conditions, casing, punctuation, and whitespace fuzzing around the 29 audit questions.
2. Platform overrides (LinkedIn whole number / raw INR, Naukri X Years / raw INR, Instahyre LPA).
3. Rule R4: Calypso, .NET/C#, and AEM backend queries never yielding 0 or empty answers under any fuzzing/phrasing variations.
4. Radio button numeric range bracket resolution for candidate 4.2 years experience.
5. Multi-language dropdown placeholder detection and elimination.
6. Empirical failure mode reproduction (LinkedIn fingerprint early-return bypass, radio range collapse on non-standard phrasings, and AEM full name omission).
"""

import json
import re
import unittest

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


class TestAdversarialBoundaryAndFuzzing(unittest.TestCase):
    """Stress tests boundary conditions, bizarre phrasings, casing, and whitespace perturbations."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()

    def _fuzz_variants(self, text: str):
        """Generate adversarial text variants: UPPER, lower, whitespace, punctuation."""
        return [
            text,
            text.upper(),
            text.lower(),
            f"   {text}   ",
            f"\n\t  {text}  \r\n",
            f"{text}???",
            f"{text}!!!",
            f"{text}:",
            re.sub(r"[?!.:,]", "", text),
        ]

    # --- Item 1 & 2: Textarea Yes/No Guards ---
    def test_fuzzed_textarea_bengaluru_location(self):
        base_q = "This role requires you to be in Bengaluru. Are you okay with that?"
        for fuzzed in self._fuzz_variants(base_q):
            ans, score = self.matcher.fuzzy_match(fuzzed, input_type="textarea")
            self.assertIsNotNone(ans, f"Failed on fuzzed: '{fuzzed}'")
            self.assertGreaterEqual(score, 0.90, f"Score < 0.90 for: '{fuzzed}'")
            self.assertFalse(
                "4+ years of professional full-stack software engineering" in ans,
                f"Textarea essay dumped for fuzzed: '{fuzzed}'"
            )
            self.assertTrue("Yes" in ans or "Bengaluru" in ans, f"Unexpected ans '{ans}' for '{fuzzed}'")

    def test_fuzzed_textarea_fast_paced_alignment(self):
        base_q = "We're incredibly fast-paced. We do whatever it takes to get things done. Would you be aligned with this aspect?"
        for fuzzed in self._fuzz_variants(base_q):
            ans, score = self.matcher.fuzzy_match(fuzzed, input_type="textarea")
            self.assertIsNotNone(ans, f"Failed on fuzzed: '{fuzzed}'")
            self.assertGreaterEqual(score, 0.90, f"Score < 0.90 for: '{fuzzed}'")
            self.assertFalse(
                "4+ years of professional full-stack software engineering" in ans,
                f"Textarea essay dumped for fuzzed: '{fuzzed}'"
            )
            self.assertTrue(ans.startswith("Yes"), f"Answer does not start with Yes: '{ans}'")

    # --- Item 3: Combined Compensation ---
    def test_fuzzed_textarea_compensation(self):
        base_q = "What is your current compensation? Would be great if you can highlight your expected compensation as well."
        for fuzzed in self._fuzz_variants(base_q):
            ans, score = self.matcher.fuzzy_match(fuzzed, input_type="textarea")
            self.assertIsNotNone(ans, f"Failed on fuzzed: '{fuzzed}'")
            self.assertGreaterEqual(score, 0.90, f"Score < 0.90 for: '{fuzzed}'")
            self.assertFalse(
                "4+ years of professional full-stack software engineering" in ans,
                f"Textarea essay dumped for compensation: '{fuzzed}'"
            )
            self.assertIn("23 LPA", ans)
            self.assertIn("30 LPA", ans)

    # --- Item 4: Joining Availability ---
    def test_fuzzed_textarea_joining_availability(self):
        base_q = "How quickly can you join us if shortlisted?"
        for fuzzed in self._fuzz_variants(base_q):
            ans, score = self.matcher.fuzzy_match(fuzzed, input_type="textarea")
            self.assertIsNotNone(ans, f"Failed on fuzzed: '{fuzzed}'")
            self.assertGreaterEqual(score, 0.90, f"Score < 0.90 for: '{fuzzed}'")
            self.assertFalse(
                "4+ years of professional full-stack software engineering" in ans,
                f"Textarea essay dumped for notice period: '{fuzzed}'"
            )
            self.assertIn("15", ans)

    # --- Items 5, 6, 7: Open-ended project experience in textarea ---
    def test_fuzzed_textarea_product_ownership(self):
        q = "   HAVE YOU BEEN THE MAIN OR ONLY DEVELOPER ON A PRODUCT THAT REAL USERS USED? IF YES, WHICH ONE AND WHAT WERE YOU RESPONSIBLE FOR KEEPING RUNNING AFTER LAUNCH?   "
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        self.assertIn("Everbridge", ans)

    def test_fuzzed_textarea_ui_fidelity(self):
        q = "Show a piece of UI you built from a design. How close did the final result come to the design, and how did you handle responsiveness???\n"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        self.assertIn("React.js", ans)

    def test_fuzzed_textarea_product_feature_owned(self):
        q = "\n\t  Describe one product or feature you owned end to end, from idea to production. What was your specific role, and what did you decide yourself?  \t"
        ans, score = self.matcher.fuzzy_match(q, input_type="textarea")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(score, 0.90)
        self.assertIn("Everbridge", ans)
        self.assertNotEqual(ans, "SDE-2 (Professional Software Developer)")

    # --- Items 8 & 9: Select Relevant Experience & Gender ---
    def test_fuzzed_select_relevant_years_experience(self):
        variants = [
            "Specify your relevant years of experience",
            "Specify your relevant years of experience ",
            "SPECIFY YOUR RELEVANT YEARS OF EXPERIENCE",
            "   specify your relevant years of experience   \n",
            "Specify your relevant years of experience:",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="select")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertIn(ans, ["4.2 Years", "4", "4.2"])
            self.assertNotEqual(ans, "Selecciona una opción")
            self.assertGreaterEqual(score, 0.90)

    def test_fuzzed_gender_selection(self):
        variants = [
            "Gender",
            "Gender ",
            "GENDER",
            "  Gender:  \n",
            "gender",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="select")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertEqual(ans, "Male")
            self.assertNotEqual(ans, "Selecciona una opción")
            self.assertGreaterEqual(score, 0.90)

    # --- Items 10, 11, 12: Tool Experience Select (must NOT answer 'Yes') ---
    def test_fuzzed_tool_experience_select(self):
        tool_queries = [
            "How many years of experience in Agentic AI?",
            "HOW MANY YEARS OF EXPERIENCE IN FULL STACK DEVELOPMENT?",
            "How many years of experience in Azure, Docker, Kubernetes, and GitHub???",
            "  years of experience in Agentic AI:  ",
            "Years of experience in full stack development",
        ]
        for q in tool_queries:
            ans, score = self.matcher.fuzzy_match(q, input_type="select")
            self.assertIsNotNone(ans, f"Failed on: '{q}'")
            self.assertNotEqual(ans, "Yes", f"Answered 'Yes' to experience question: '{q}'")
            self.assertNotEqual(ans, "No", f"Answered 'No' to experience question: '{q}'")
            self.assertIn(ans, ["4.2 Years", "4", "4.2"])
            self.assertGreaterEqual(score, 0.90)

    # --- Item 20: Capability Diagnostic Affirmative ---
    def test_fuzzed_diagnose_and_solve_problems(self):
        variants = [
            "Can you independently diagnose and solve technical problems?",
            "CAN YOU INDEPENDENTLY DIAGNOSE AND SOLVE TECHNICAL PROBLEMS?",
            "Can you independently diagnose and solve technical problems?:",
            "  can you independently diagnose and solve technical problems?  \n",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="select")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertEqual(ans, "Yes", f"Should be affirmative Yes for capability: '{v}'")
            self.assertGreaterEqual(score, 0.90)

    # --- Items 21, 23, 24: Exclusion & Negative Invariants ---
    def test_fuzzed_negative_compliance_and_degrees(self):
        neg_questions = [
            "Were you referred by an internal Xometry employee?",
            "WERE YOU REFERRED BY AN INTERNAL XOMETRY EMPLOYEE? REQUIRED",
            "Have you been previously employed with Freshworks?",
            "HAVE YOU BEEN PREVIOUSLY EMPLOYED WITH FRESHWORKS? REQUIRED",
            "Have you completed the following level of education: Master of Business Administration?",
            "HAVE YOU COMPLETED THE FOLLOWING LEVEL OF EDUCATION: MASTER OF BUSINESS ADMINISTRATION? REQUIRED",
        ]
        for q in neg_questions:
            for inp in ["radio", "select", "text"]:
                ans, score = self.matcher.fuzzy_match(q, input_type=inp)
                self.assertIsNotNone(ans, f"Failed on {inp} for: '{q}'")
                self.assertEqual(ans, "No", f"Expected 'No' for exclusion question: '{q}' (input: {inp}, got: '{ans}')")
                self.assertGreaterEqual(score, 0.90)

    # --- Item 22: Referee Name Cascade Invariant ---
    def test_fuzzed_internal_referral_employee_name(self):
        q = "If you answered yes to the last question, please provide the employee’s first and last name"
        for fuzzed in self._fuzz_variants(q):
            ans, score = self.matcher.fuzzy_match(fuzzed, input_type="text")
            self.assertIsNotNone(ans, f"Failed on: '{fuzzed}'")
            self.assertIn(ans, ["N/A", "None", "Not applicable"])
            self.assertNotEqual(ans, "Singh")
            self.assertGreaterEqual(score, 0.90)

    # --- Item 25: Confirm Notice Period 2-Digit ---
    def test_fuzzed_confirm_notice_period_digits(self):
        variants = [
            "Please confirm the notice period(7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)? 2 or 3 months candidates can ignore this role?",
            "PLEASE CONFIRM THE NOTICE PERIOD(7 DAYS, 15 DAYS, 30, 60 OR 90 DAYS JUST PUT 2 DIGIT NUMBER)?",
            "Please confirm the notice period (7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)?",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertEqual(ans, "15")
            self.assertNotEqual(ans, "4")
            self.assertGreaterEqual(score, 0.90)

    # --- Item 26: Rate Proficiency 1-5 Bounded ---
    def test_fuzzed_rate_proficiency_scale_5(self):
        variants = [
            "Rate your proficiency (1-5) in our core stack: React.js, Next.js, and React Native.",
            "RATE YOUR PROFICIENCY (1-5) IN OUR CORE STACK: REACT.JS, NEXT.JS, AND REACT NATIVE.",
            "Rate your proficiency (1-5) in our core stack: React.js, Next.js, and React Native",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertIn(ans, ["4", "5"])
            self.assertNotEqual(ans, "9")
            self.assertGreaterEqual(score, 0.90)

    # --- Item 27: SQL Hands-on or Familiar Affirmative ---
    def test_fuzzed_sql_hands_on_or_familiar(self):
        variants = [
            "Do you have hands-on experience with SQL, or are you familiar with SQL cpncepts?",
            "DO YOU HAVE HANDS-ON EXPERIENCE WITH SQL, OR ARE YOU FAMILIAR WITH SQL CPNCEPTS?",
            "Do you have hands-on experience with SQL, or are you familiar with SQL concepts?",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertIsNotNone(ans, f"Failed on: '{v}'")
            self.assertEqual(ans, "Yes")
            self.assertNotEqual(ans, "4")
            self.assertGreaterEqual(score, 0.90)

    # --- Items 28, 29, 30: GitHub, Title, Company ---
    def test_fuzzed_github_profile_link(self):
        variants = [
            "Github link",
            "GITHUB LINK",
            "  Github link:  \n",
            "Github Link",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertEqual(ans, "https://github.com/siddhant3646")
            self.assertFalse("Portfolio" in ans)
            self.assertGreaterEqual(score, 0.90)

    def test_fuzzed_job_title_and_company(self):
        title_variants = ["Your title", "YOUR TITLE", "  Your title:  \n", "Current title"]
        for v in title_variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertEqual(ans, "Software Engineer 2")
            self.assertNotEqual(ans, "Android Lead")
            self.assertGreaterEqual(score, 0.90)

        company_variants = ["Company", "COMPANY", "  Company:  \n"]
        for v in company_variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertEqual(ans, "Everbridge")
            self.assertNotEqual(ans, "DSC VIT Bhopal")
            self.assertGreaterEqual(score, 0.90)

    # --- Item 31: Compound CTC ---
    def test_fuzzed_compound_ctc(self):
        variants = [
            "CTC: Current & Expected?",
            "CTC: CURRENT & EXPECTED?",
            "  CTC: Current & Expected?  \n",
            "CTC: Current & Expected",
        ]
        for v in variants:
            ans, score = self.matcher.fuzzy_match(v, input_type="text")
            self.assertIsNotNone(ans)
            self.assertIn("23 LPA", ans)
            self.assertIn("30 LPA", ans)
            self.assertGreaterEqual(score, 0.90)


class TestPlatformOverridesAdversarial(unittest.TestCase):
    """Stress tests platform formatting rules across LinkedIn, Naukri, and Instahyre."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()
        with open("config/qa_patterns.json") as f:
            cls.patterns_db = json.load(f)["patterns"]

    def test_linkedin_explicit_whole_number_phrase(self):
        self.agent._current_platform = "linkedin"
        ans, score = self.agent._fuzzy_match_question("enter whole number years of experience")
        self.assertEqual(ans, "4")
        self.assertGreaterEqual(score, 0.90)

    def test_naukri_experience_x_years_enforcement(self):
        self.agent._current_platform = "naukri"
        test_phrasings = [
            "years of experience",
            "total experience",
            "how many years of experience do you have",
        ]
        for q in test_phrasings:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "4.2 Years", f"Naukri experience must be '4.2 Years', got '{ans}' for '{q}'")
            self.assertGreaterEqual(score, 0.90)

    def test_salary_raw_inr_versus_lpa(self):
        curr_p = self.patterns_db.get("current_salary")
        exp_p = self.patterns_db.get("expected_salary")

        # LinkedIn & raw INR input defaults
        self.assertEqual(curr_p["input_type_defaults"]["text_inr"], "2300000")
        self.assertEqual(exp_p["input_type_defaults"]["text_inr"], "3000000")

        # Standard text & LPA defaults
        self.assertEqual(curr_p["input_type_defaults"]["text"], "23 LPA")
        self.assertEqual(exp_p["input_type_defaults"]["text"], "30 LPA")
        self.assertEqual(curr_p["numeric_default"], "23")
        self.assertEqual(exp_p["numeric_default"], "30")

    def test_instahyre_ctc_lpa_suffix(self):
        p = self.patterns_db.get("instahyre_expected_ctc_lpa")
        self.assertIsNotNone(p)
        self.assertEqual(p["default"], "30 LPA")
        self.assertEqual(p["platform_overrides"]["instahyre"], "30 LPA")
        self.assertEqual(p["input_type_defaults"]["text"], "30 LPA")
        self.assertEqual(p["input_type_defaults"]["text_lpa"], "30 LPA")


class TestRuleR4DeepAdversarial(unittest.TestCase):
    """Exhaustive stress tests verifying Calypso, .NET/C#, and AEM backend queries NEVER return 0 or empty answers."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()

    def test_rule_r4_never_zero_or_empty_dotnet(self):
        queries = [
            "How many years of experience do you have in .Net Core?",
            "HOW MANY YEARS OF EXPERIENCE DO YOU HAVE IN .NET CORE?",
            "how many years of experience do you have in .net core",
            "Rel Exp in .Netcore:",
            "REL EXP IN .NETCORE:",
            "Rel Exp in .Netcore",
            "how many years of experience do you have in dotnet core",
            ".Net Core experience",
            ".NET CORE EXPERIENCE",
            "Years of experience in C# / .NET",
            "how many years of experience in C#?",
            "c# experience",
            "  .net core experience (in years):  \n",
            "Total years of experience in .NET framework",
        ]
        for q in queries:
            for inp in ["text", "number", "select", "radio", "textarea"]:
                ans, score = self.matcher.fuzzy_match(q, input_type=inp)
                self.assertIsNotNone(ans, f"Returned None for .NET query: '{q}' ({inp})")
                self.assertNotIn(ans, ["0", 0, 0.0, "", "N/A"], f"Violation of Rule R4 (zero/empty) for: '{q}' ({inp}) -> '{ans}'")

    def test_rule_r4_never_zero_or_empty_calypso(self):
        queries = [
            "How many years of experience do you have in Calypso?",
            "HOW MANY YEARS OF EXPERIENCE DO YOU HAVE IN CALYPSO?",
            "How many years of experience do you have in Calypso",
            "Calypso experience",
            "CALYPSO EXPERIENCE",
            "  calypso experience (years):  \n",
            "Years of experience in Calypso",
            "Total Calypso platform experience",
        ]
        for q in queries:
            for inp in ["text", "number", "select", "radio", "textarea"]:
                ans, score = self.matcher.fuzzy_match(q, input_type=inp)
                self.assertIsNotNone(ans, f"Returned None for Calypso query: '{q}' ({inp})")
                self.assertNotIn(ans, ["0", 0, 0.0, "", "N/A"], f"Violation of Rule R4 (zero/empty) for: '{q}' ({inp}) -> '{ans}'")

    def test_rule_r4_never_zero_or_empty_aem_backend(self):
        queries = [
            "How many years of experience do you have in AEM backend?",
            "HOW MANY YEARS OF EXPERIENCE DO YOU HAVE IN AEM BACKEND?",
            "How many years of experience do you have in AEM backend",
            "AEM backend experience",
            "AEM BACKEND EXPERIENCE",
            "  aem backend experience:  \n",
            "Years of experience in Adobe Experience Manager (AEM)",
        ]
        for q in queries:
            for inp in ["text", "number", "select", "radio", "textarea"]:
                ans, score = self.matcher.fuzzy_match(q, input_type=inp)
                self.assertIsNotNone(ans, f"Returned None for AEM query: '{q}' ({inp})")
                self.assertNotIn(ans, ["0", 0, 0.0, "", "N/A"], f"Violation of Rule R4 (zero/empty) for: '{q}' ({inp}) -> '{ans}'")


class TestAdversarialRadioRangeBrackets(unittest.TestCase):
    """Stress tests candidate 4.2 years matching into diverse radio button option ranges."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.resolver = InputAwareResolver()

    def test_range_options_collapse_prevention(self):
        test_cases = [
            (
                "How much experience you hold in Java",
                [Option(value="0", label="0 - 2 yrs"), Option(value="1", label="2 - 4 yrs"), Option(value="2", label="4 - 6 yrs"), Option(value="3", label="6+ yrs")],
                "4 - 6 yrs",
                "0 - 2 yrs"
            ),
            (
                "How much experience you hold in Cloud?",
                [Option(value="0", label="0 - 6 months"), Option(value="1", label="1 - 3 yrs"), Option(value="2", label="3 - 5 yrs"), Option(value="3", label="5+ yrs")],
                "3 - 5 yrs",
                "0 - 6 months"
            ),
            (
                "How much experience you hold in React.Js?",
                [Option(value="0", label="0 - 0.6 months"), Option(value="1", label="1 - 3 yrs"), Option(value="2", label="3 - 5 yrs"), Option(value="3", label="5+ yrs")],
                "3 - 5 yrs",
                "0 - 0.6 months"
            ),
            (
                "How many years of experience do you have in Microservices?",
                [Option(value="0", label="Less than 1 year"), Option(value="1", label="1 - 3 years"), Option(value="2", label="3 - 5 years"), Option(value="3", label="More than 5 years")],
                "3 - 5 years",
                "Less than 1 year"
            ),
            (
                "How much experience you hold in IAM Roles and Python (Fast API)?",
                [Option(value="0", label="Fresher (0 yrs)"), Option(value="1", label="1 to 3 yrs"), Option(value="2", label="3 to 5 yrs"), Option(value="3", label="5 to 8 yrs")],
                "3 to 5 yrs",
                "Fresher (0 yrs)"
            ),
        ]

        for question, options, expected_label, forbidden_label in test_cases:
            ans, score = self.matcher.fuzzy_match(question, input_type="radio")
            self.assertIsNotNone(ans)
            res = self.resolver.resolve(ans, InputType.RADIO, options=options, question=question)
            self.assertIsNotNone(res.matched_option, f"No option matched for '{question}' with ans '{ans}'")
            self.assertEqual(res.matched_option.label, expected_label, f"Wrong range matched for '{question}': got '{res.matched_option.label}', expected '{expected_label}'")
            self.assertNotEqual(res.matched_option.label, forbidden_label, f"Collapsed to entry-level option for '{question}'!")


class TestDropdownPlaceholderStress(unittest.TestCase):
    """Stress tests multi-language placeholder rejection."""

    def test_adversarial_placeholder_rejections(self):
        bizarre_placeholders = [
            "Selecciona una opción",
            "SELECCIONA UNA OPCIÓN",
            "   Selecciona una opción   ",
            "Elija una opción",
            "Selecione uma opção",
            "Seleziona un'opzione",
            "Bitte auswählen",
            "Sélectionnez une option",
            "Select an option",
            "Choose an option",
            "-- Select --",
            "---",
            "[Select Option]",
            "<Choose>",
            "Select...",
            "None",
            "Placeholder",
        ]

        raw_options = [Option(value=str(i), label=ph) for i, ph in enumerate(bizarre_placeholders)]
        raw_options.append(Option(value="valid_male", label="Male"))
        raw_options.append(Option(value="valid_female", label="Female"))

        resolver = InputAwareResolver()
        res = resolver.resolve("Male", InputType.SELECT, options=raw_options)
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "Male")
        self.assertNotIn(res.matched_option.label, bizarre_placeholders)


class TestEmpiricalChallengerBugDemonstration(unittest.TestCase):
    """Empirically reproduces and documents the failure modes found by Challenger 1."""

    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher("config/qa_patterns.json")
        cls.agent = SentinelAgent()
        cls.resolver = InputAwareResolver()

    def test_bug_1_linkedin_fingerprint_bypass(self):
        """BUG 1: On LinkedIn, fingerprint match at Phase 0.5 bypasses platform formatting.

        Expected: LinkedIn requires whole number ('4').
        Observed: Phase 0.5 returns early with '4.2 Years' before line 1315 is reached.
        """
        self.agent._current_platform = "linkedin"
        # Standard question matched in fingerprint store
        ans, score = self.agent._fuzzy_match_question("years of experience")
        # Demonstrating empirical behavior: ans is "4.2 Years" instead of "4"
        self.assertEqual(ans, "4.2 Years", "Fingerprint bypass confirmed: returns 4.2 Years instead of 4")

    def test_bug_2_radio_range_collapse_on_rel_exp(self):
        """BUG 2: For questions lacking 'how many years' / 'how much experience',

        pattern_matcher.py coerces numeric experience into 'Yes' when input_type='radio',
        breaking range resolution in InputAwareResolver.
        """
        q = "Rel Exp in .Netcore:"
        ans, score = self.matcher.fuzzy_match(q, input_type="radio")
        # Coerced into 'Yes' instead of numeric '4.2'
        self.assertEqual(ans, "Yes")

        # Now test what happens when range options are presented:
        options = [
            Option(value="0", label="0 - 2 yrs"),
            Option(value="1", label="2 - 4 yrs"),
            Option(value="2", label="4 - 6 yrs"),
            Option(value="3", label="6+ yrs"),
        ]
        res = self.resolver.resolve(ans, InputType.RADIO, options=options, question=q)
        # It fails to match any option!
        self.assertIsNone(res.matched_option, "Radio range resolution failed due to 'Yes' answer")

    def test_bug_3_aem_full_name_omission(self):
        """BUG 3: Pattern 'aem_backend_experience' only defines patterns with acronym 'aem'.

        When asked 'Adobe Experience Manager backend experience', it drops below 0.90 confidence (0.85)
        and returns 'Yes' for select dropdowns instead of candidate experience.
        """
        q = "Adobe Experience Manager backend experience"
        ans, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertEqual(ans, "4.2", "Fell back to tech_specific_experience instead of AEM pattern")
        self.assertGreaterEqual(score, 0.90, "Score resolved with high confidence")


if __name__ == "__main__":
    unittest.main()
