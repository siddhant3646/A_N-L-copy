"""
Unit tests for the CSV audit fixes from October 22.

Covers:
- Blanket tech-skill rule: every tech experience question answers the
  candidate's total experience (4.2 Years / 4 on LinkedIn/Indeed/Hirist)
- Role/domain overrides (product manager, price elasticity) still answer 0
- Year-threshold eligibility gates ("5+ years", "8+ years", "10-15 years")
- 0-5 self-rating scales
- City / state / employment-year form fields
- Skill-aware Yes/No answers (OR lists, AND lists, zero-experience overrides)
- "go" as an English verb vs the Go language
- New JSON patterns added during the audit
"""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVFixesOct22(unittest.TestCase):
    """Unit tests verifying the October 22 CSV audit fixes."""

    def setUp(self):
        self.agent = SentinelAgent()
        self.patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(self.patterns_data)

    # ------------------------------------------------------------------
    # Skill-specific experience years (blanket tech rule)
    # ------------------------------------------------------------------

    def test_tech_skills_answer_total_experience(self):
        cases = [
            "how many years of work experience do you have with angular?",
            "how many years of work experience do you have with coveo search?",
            "how many years of experience you have in django developing rest api?",
            "how many years of hands-on experience do you have in mlops?",
            "how many years of hands-on experience do you have with go, rust, or java?",
        ]
        for q in cases:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue(
                ans.startswith("4.2"),
                f"Expected total experience (4.2) for {q!r}, got {ans!r} (conf {conf})",
            )

    def test_role_domain_skills_still_answer_zero(self):
        cases = [
            "what is your experience in price elasticity?",
            "how many years of product management experience do you have?",
        ]
        for q in cases:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertTrue(
                ans.startswith("0"),
                f"Expected 0 for role/domain question {q!r}, got {ans!r}",
            )

    def test_real_skills_use_their_own_years(self):
        cases = {
            "how many years of work experience do you have with python (programming language)?": "4.2",
            "how many years of work experience do you have with jquery?": "4.2",
            "how many years of work experience do you have with react?": "4.2",
            "how many years of work experience do you have with aws?": "4.2",
            "how many years of work experience do you have with azure": "4.2",
        }
        for q, expected in cases.items():
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertTrue(
                ans.startswith(expected),
                f"Expected {expected!r} for {q!r}, got {ans!r}",
            )

    def test_or_list_takes_highest_skill_years(self):
        q = "how many years of hands-on experience do you have with go, rust, or java?"
        ans, _ = self.agent._fuzzy_match_question(q)
        # Blanket rule: every tech skill answers the total experience.
        self.assertTrue(ans.startswith("4.2"), f"Expected total experience, got {ans!r}")

    def test_and_list_takes_lowest_skill_years(self):
        q = "how many years of experience do you have with django and rest apis?"
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertTrue(ans.startswith("4.2"), f"Expected total experience, got {ans!r}")

    # ------------------------------------------------------------------
    # Experience threshold gates
    # ------------------------------------------------------------------

    def test_experience_threshold_gates(self):
        should_reject = [
            "do you have 5+ years of experience in java, spring boot, and microservices?",
            "pl confirm if you have overall 8 + yrs and above experience . incase if you have less than 8 yrs",
            "we are looking for candidates with 10\u201315 years of total experience only.",
        ]
        for q in should_reject:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Expected No for {q!r}, got {ans!r}")

        should_accept = [
            "\u2022 4-9 years of experience in full stack, frontend, or backend software development.",
            "do you have 3+ years of experience in react?",
            "do you have 4+ years of experience in java?",
        ]
        for q in should_accept:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Expected Yes for {q!r}, got {ans!r}")

    # ------------------------------------------------------------------
    # 0-5 self rating scales
    # ------------------------------------------------------------------

    def test_zero_to_five_rating_scale(self):
        ans, _ = self.agent._fuzzy_match_question("rate yourself on a scale of 0-5 for java")
        self.assertEqual(ans, "4")

        ai_ans, _ = self.agent._fuzzy_match_question("rate yourself on a scale of 0-5 for llm evals")
        self.assertEqual(ai_ans, "3")

    # ------------------------------------------------------------------
    # Location / employment year fields
    # ------------------------------------------------------------------

    def test_city_and_state_fields(self):
        for q in ("location (city)", "city", "current city", "which city do you currently live in"):
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertIn("Bengaluru", ans, f"Expected Bengaluru for {q!r}, got {ans!r}")

        state_ans, _ = self.agent._fuzzy_match_question("what state are you currently located in?")
        self.assertEqual(state_ans, "Karnataka")

    def test_employment_year_fields(self):
        from_ans, _ = self.agent._fuzzy_match_question("from year")
        self.assertEqual(from_ans, "2022")

        to_ans, _ = self.agent._fuzzy_match_question("to year")
        self.assertEqual(to_ans, "2026")

    # ------------------------------------------------------------------
    # Skill-aware Yes/No answers
    # ------------------------------------------------------------------

    def test_skill_yes_no_or_list_uses_any_positive_skill(self):
        q = "do you have experience working with ipaas, saas, or other cloud-based platforms?"
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes", f"Expected Yes (SaaS/cloud experience), got {ans!r}")

    def test_skill_yes_no_and_list_requires_all_skills(self):
        # Blanket rule: any concrete tech skill => Yes (even in AND lists).
        ans, _ = self.agent._fuzzy_match_question("do you have experience with java and angular?")
        self.assertEqual(ans, "Yes")

        ans, _ = self.agent._fuzzy_match_question("do you have experience with java or angular?")
        self.assertEqual(ans, "Yes")

    def test_zero_experience_override_beats_generic_ai_token(self):
        ans, _ = self.agent._fuzzy_match_question("do you have experience as an AI Product Manager?")
        self.assertEqual(ans, "No")

    def test_go_verb_is_not_treated_as_golang(self):
        ans, _ = self.agent._fuzzy_match_question(
            "only apply if you can go to the office for the interview, bangalore"
        )
        self.assertEqual(ans, "Yes")

        ans, _ = self.agent._fuzzy_match_question("how many years of experience do you have with go?")
        self.assertTrue(ans.startswith("4.2"), f"Expected total experience for Go, got {ans!r}")

    def test_integration_migration_question_including_typo(self):
        cases = [
            "Have you done intigretion or Migration with other products?",
            "Have you done integration or migration with other products?",
        ]
        for q in cases:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Expected Yes for {q!r}, got {ans!r}")

    def test_requirement_statements_are_yes_no_not_years(self):
        questions = [
            "Experience developing and consuming RESTful APIs.*",
            "Developing and consuming RESTful APIs",
            "Do you have experience developing and consuming RESTful APIs?",
        ]
        for q in questions:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Expected Yes for {q!r}, got {ans!r}")

    def test_relevant_full_time_experience_excludes_platform_rounding(self):
        q = "How many years of relevant full-time experience do you have? (Excluding internship)*"
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "4.2 Years")

    # ------------------------------------------------------------------
    # Notice status and salary component questions
    # ------------------------------------------------------------------

    def test_servicing_notice_yes_no_is_not_days(self):
        cases = [
            "are you currently servicing notice period?",
            "are you serving notice?",
            "are you on notice period?",
        ]
        for q in cases:
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Expected Yes for {q!r}, got {ans!r}")

        # Numeric notice questions must keep returning days.
        ans, _ = self.agent._fuzzy_match_question("what is your notice period?")
        self.assertEqual(ans, "15")

    def test_salary_breakdown_is_not_flattened_to_ctc(self):
        q = (
            "can you please provide the details of your current ctc, including "
            "the fixed, variable, and rsu/esop components?"
        )
        ans, _ = self.agent._fuzzy_match_question(q)
        self.assertIn("Fixed CTC: 23 LPA", ans)
        self.assertIn("Variable: 0", ans)

        # Plain CTC questions must still return the single numeric value.
        ans, _ = self.agent._fuzzy_match_question("what is your current ctc?")
        self.assertEqual(ans, "23")

    # ------------------------------------------------------------------
    # New JSON patterns
    # ------------------------------------------------------------------

    def test_new_json_patterns_exist_and_resolve(self):
        expected = {
            "current_city_field": "Bengaluru",
            "employment_from_year": "2022",
            "employment_to_year": "2026",
            "mentioned_skills_yes_no": "Yes",
            "experience_leading_backend_systems": "4.2 Years",
        }
        patterns = self.patterns_data["patterns"]
        for key, default in expected.items():
            self.assertIn(key, patterns, f"Missing pattern {key}")
            self.assertEqual(patterns[key]["default"], default)

        ans, _ = self.matcher.fuzzy_match("do you have mentioned skills (python, react, fastapi) as per jd ?")
        self.assertEqual(ans, "Yes")

        ans, _ = self.matcher.fuzzy_match("location (city)")
        self.assertEqual(ans, "Bengaluru")

    # ------------------------------------------------------------------
    # Oct 23-24 replay fixes: relocate, availability, privacy, data science
    # ------------------------------------------------------------------

    def test_living_in_question_with_relocation_answers_yes(self):
        for q in (
            "Are you currently living in or ready to relocate to Gurugram ?",
            "Are you currently living in or ready to relocate to Noida ?",
        ):
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes")
            self.assertGreaterEqual(conf, 0.9)

    def test_living_in_confirmation_without_relocation_still_no(self):
        ans, _ = self.agent._fuzzy_match_question("Are you currently located in Chennai?")
        self.assertEqual(ans, "No")

    def test_interview_availability_not_answered_as_location(self):
        for q in (
            "Are you available on 24th October for face-to-face interview in Indore location?",
            "Are you 100% sure you can attend the face-to-face interview in Hyderabad on Saturday, 24 October 2026?",
            "Are you available on this Saturday (23rd Oct) for F2F drive?",
        ):
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes")

    def test_privacy_statement_is_consent_not_profile_summary(self):
        ans, _ = self.agent._fuzzy_match_question("Privacy Statement")
        self.assertEqual(ans, "Yes")
        ans, _ = self.matcher.fuzzy_match("privacy policy")
        self.assertEqual(ans, "Yes")

    def test_privacy_json_pattern_registered(self):
        patterns = self.patterns_data["patterns"]
        self.assertIn("privacy_statement_agreement", patterns)
        self.assertEqual(patterns["privacy_statement_agreement"]["default"], "Yes")
        self.assertEqual(patterns["privacy_statement_agreement"]["input_type_defaults"]["select"], "I Agree")

    def test_data_science_is_tech_and_answers_total_experience(self):
        for q in (
            "how many years of experience as a data scientist?",
            "How many years of experience do you have in Data Science?",
            'How many years of experience do you have in "data science, classical ML and model building" ?',
        ):
            ans, _ = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "4.2 Years")
        ans, _ = self.agent._fuzzy_match_question(
            "Do you have hands-on experience in both Machine Learning and Data Science?"
        )
        self.assertEqual(ans, "Yes")


if __name__ == "__main__":
    unittest.main()
