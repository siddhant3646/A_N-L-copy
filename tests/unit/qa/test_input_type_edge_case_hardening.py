"""Regression tests for input-type applicability and wrong-answer edge cases.

Covers the fixes that stopped ``input_type_defaults`` fall-throughs from
inventing values: bogus ``0`` on non-numeric questions, PII leaks through
``tel``/``text_inr`` coercion, and blank-number fall-through in the matcher.
"""

import re

import pytest

from src.patterns.input_type_sanitizer import (
    build_input_type_defaults,
    detect_intent,
    derive_value,
    is_valid_value,
    number_value_is_honest,
    sanitize_answer,
)

pytestmark = pytest.mark.unit


class TestNumberControlBlanks:
    def test_open_ended_question_gets_blank_number(self):
        q = "Which AWS services do you have experience with?"
        assert sanitize_answer("EC2, S3, Lambda", "number", question=q, category="skills") == ""

    def test_location_question_gets_blank_number(self):
        assert sanitize_answer("Bangalore", "number", question="Current location?", category="location") == ""

    def test_experience_years_still_numeric(self):
        got = sanitize_answer("4.2 Years", "number", question="How many years of experience?", category="experience")
        assert got == "4.2"

    def test_notice_period_still_numeric(self):
        assert sanitize_answer("15 days", "number", question="What is your notice period?", category="notice_period") == "15"

    def test_boolean_yes_no_keeps_zero_one(self):
        assert sanitize_answer("No", "number", question="Have you applied before?", category="compliance") == "0"
        assert sanitize_answer("Yes", "number", question="Have you applied before?", category="compliance") == "1"

    def test_derive_number_returns_empty_for_non_quantity(self):
        q = "Explain your system design approach"
        assert sanitize_answer("I design for scale first", "number", question=q, category="skills") == ""


class TestTelAndInrFallthrough:
    def test_salary_answer_never_becomes_candidate_phone(self):
        got = sanitize_answer("23 LPA", "tel", question="Current CTC?", category="salary", default="23 LPA")
        assert got == "23 LPA"

    def test_date_answer_never_becomes_candidate_phone(self):
        got = sanitize_answer("17/12/2000", "tel", question="What is your date of birth?", category="personal_info")
        assert got == "17/12/2000"

    def test_real_phone_still_normalized(self):
        got = sanitize_answer("+91-7905828880", "tel", question="Your phone number?", category="personal_info")
        assert got == "7905828880"

    def test_experience_answer_never_becomes_inr(self):
        got = sanitize_answer("4.2 Years", "text_inr", question="How many years of experience?", category="experience")
        assert got == "4.2 Years"

    def test_salary_still_coerced_to_inr(self):
        got = sanitize_answer("23 LPA", "text_inr", question="Current CTC?", category="salary")
        assert got == "2300000"

    def test_derive_value_rejects_tel_for_non_phone(self):
        assert derive_value("23 LPA", "tel", "Current CTC?", "salary") is None


class TestHonestyRule:
    def test_invented_rating_number_is_dishonest(self):
        intent = detect_intent("Provide examples of projects", "experience", "Yes, I led an AI document tool")
        assert number_value_is_honest("4.2", "Yes, I led an AI document tool", intent) is False

    def test_number_grounded_in_default_is_honest(self):
        intent = detect_intent("experience in kafka", "skills", "4.2 Years")
        assert number_value_is_honest("4.2", "4.2 Years", intent) is True

    def test_dob_digits_are_honest(self):
        intent = detect_intent("What is your date of birth?", "personal_info", "17/12/2000")
        assert number_value_is_honest("17122000", "17/12/2000", intent) is True

    def test_blank_is_valid_only_for_non_quantity(self):
        qty = detect_intent("What is your notice period?", "notice_period", "15 days")
        assert is_valid_value("", "number", qty) is False
        prose = detect_intent("Explain your architecture approach", "skills", "Microservices with event-driven")
        assert is_valid_value("", "number", prose) is True


class TestBuildInputTypeDefaults:
    def test_repair_blanks_invented_number(self):
        data = {
            "patterns": ["how good are you in dsa"],
            "category": "skills",
            "default": "Strong in arrays, trees, graphs and dynamic programming",
            "input_type_defaults": {"number": "9"},
        }
        repaired = build_input_type_defaults(data, data["input_type_defaults"])
        assert repaired["number"] == ""

    def test_repair_keeps_grounded_number(self):
        data = {
            "patterns": ["latest version of java"],
            "category": "skills",
            "default": "24",
            "input_type_defaults": {"number": "24"},
        }
        repaired = build_input_type_defaults(data, data["input_type_defaults"])
        assert repaired["number"] == "24"

    def test_repair_purges_tel_from_non_phone_questions(self):
        data = {
            "patterns": ["current ctc"],
            "category": "salary",
            "default": "23 LPA",
            "input_type_defaults": {"tel": "7905828880"},
        }
        repaired = build_input_type_defaults(data, data["input_type_defaults"])
        assert "tel" not in repaired


class TestMatcherBlankFallthrough:
    def test_blank_typed_answer_falls_through_to_none(self, real_patterns_data):
        from src.patterns.pattern_matcher import PatternMatcher

        matcher = PatternMatcher(real_patterns_data)
        # A skills question asked into a number control has no numeric answer;
        # the matcher must not type "0" and must not return an empty string.
        answer, _ = matcher.fuzzy_match("which_aws_services_placeholder_missing_question_zz", input_type="number")
        assert answer is None or str(answer).strip() != ""

    def test_corpus_has_no_bogus_zero_numbers(self, real_patterns_data):
        bad = []
        for pid, data in real_patterns_data["patterns"].items():
            itd = data.get("input_type_defaults") or {}
            value = itd.get("number")
            if value in (None, "", "0", "1"):
                continue
            question = str((data.get("patterns") or [""])[0])
            intent = detect_intent(question, str(data.get("category", "")), str(data.get("default", "")))
            if not number_value_is_honest(str(value), str(data.get("default", "")), intent):
                bad.append(pid)
        assert bad == []

    def test_corpus_tel_keys_are_phone_questions(self, real_patterns_data):
        leaks = []
        for pid, data in real_patterns_data["patterns"].items():
            itd = data.get("input_type_defaults") or {}
            if "tel" not in itd:
                continue
            question = str((data.get("patterns") or [""])[0])
            intent = detect_intent(question, str(data.get("category", "")), str(data.get("default", "")))
            if not intent.is_phone and not re.search(r"\d{10}", str(itd["tel"]).replace("-", "").replace(" ", "")):
                leaks.append(pid)
        assert leaks == []
