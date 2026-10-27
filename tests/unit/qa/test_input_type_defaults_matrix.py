"""Regression tests for input-type applicability across the QA corpus.

These tests exercise the sanitizer directly and audit the real
``config/qa_patterns.json`` so a new pattern cannot silently ship a value that
is unusable for one of the supported controls.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_qa_input_types as audit  # noqa: E402
from patterns.input_type_sanitizer import (  # noqa: E402
    LWD_ISO_MARKER,
    LWD_NUMERIC_MARKER,
    TODAY_ISO_MARKER,
    build_input_type_defaults,
    correct_stale_date_default,
    detect_intent,
    detect_pii_kind,
    is_static_date_value,
)
from patterns.pattern_matcher import PatternMatcher  # noqa: E402

CORE_INPUT_TYPES = ("text", "textarea", "radio", "select", "checkbox", "number")


def _pattern(question: str, default: str, category: str) -> dict:
    return {"patterns": [question], "category": category, "default": default}


@pytest.fixture(scope="module")
def qa_config() -> dict:
    return audit.load_patterns(ROOT / "config" / "qa_patterns.json")


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,default,category",
    [
        ("what is your current ctc", "23 LPA", "salary"),
        ("how many years of java experience", "4.2 Years", "experience"),
        ("what is your notice period", "15 days", "notice_period"),
        ("what is your current location", "Bengaluru", "location"),
        ("are you willing to relocate", "Yes", "yes_no"),
        ("describe your experience", "I built payment microservices.", "skills"),
        ("date of birth", "17/12/2000", "personal_info"),
        ("contact number", "7905828880", "personal_info"),
    ],
)
def test_every_core_input_type_is_populated(question, default, category):
    defaults = build_input_type_defaults(_pattern(question, default, category))
    for input_type in CORE_INPUT_TYPES:
        value = defaults.get(input_type)
        if input_type == "number" and value is not None and not str(value).strip():
            # A blank number control is the sanctioned answer for questions
            # with no measurable value ("Bengaluru" has no number); matchers
            # fall through to the next tier instead of typing an invented digit.
            continue
        assert value is not None and str(value).strip(), (
            f"{input_type} missing for {question!r}: {defaults}"
        )


@pytest.mark.unit
def test_salary_units_match_the_requested_control():
    defaults = build_input_type_defaults(_pattern("what is your current ctc", "23 LPA", "salary"))
    assert defaults["number"] == "23"
    assert defaults["text_inr"] == "2300000"
    assert defaults["text_lpa"] == "23"
    assert "LPA" in defaults["text"]


@pytest.mark.unit
def test_compound_salary_keeps_both_values_without_scientific_notation():
    defaults = build_input_type_defaults(
        _pattern("current and expected ctc", "2300000 / 3000000", "salary")
    )
    assert defaults["text_inr"] == "2300000 / 3000000"
    assert defaults["text_lpa"] == "23 / 30"
    assert re.search(r"\d[eE][+-]\d", json.dumps(defaults)) is None


@pytest.mark.unit
def test_experience_is_numeric_for_number_and_short_for_choices():
    defaults = build_input_type_defaults(
        _pattern("how many years of java experience", "4.2 Years", "experience")
    )
    assert defaults["number"] == "4.2"
    assert "year" not in defaults["number"].lower()
    assert len(defaults["radio"]) <= audit.MAX_CHOICE_LENGTH["radio"]
    assert len(defaults["select"]) <= audit.MAX_CHOICE_LENGTH["select"]


@pytest.mark.unit
def test_lwd_and_notice_dates_are_dynamic_and_type_specific():
    lwd = build_input_type_defaults(
        _pattern("what is your lwd", "__DYNAMIC_LWD_DDMMYYYY__", "notice_period")
    )
    assert lwd["number"] == LWD_NUMERIC_MARKER
    assert lwd["date"] == LWD_ISO_MARKER
    assert lwd["text"] == LWD_NUMERIC_MARKER

    no_notice = build_input_type_defaults(
        _pattern("what is your last working day if not serving notice", "No", "notice_period")
    )
    assert no_notice["number"] == "0"
    assert no_notice["date"] == TODAY_ISO_MARKER
    assert no_notice["checkbox"] == "No"


@pytest.mark.unit
def test_stale_lwd_literal_is_replaced_but_dob_is_preserved():
    assert is_static_date_value("23102026")
    stale = build_input_type_defaults(
        _pattern("what is your last working day", "23102026", "notice_period")
    )
    assert stale["text"] == LWD_NUMERIC_MARKER
    assert stale["date"] == LWD_ISO_MARKER

    assert correct_stale_date_default("date of birth", "personal_info", "17/12/2000") == "17/12/2000"


@pytest.mark.unit
def test_dob_uses_date_and_numeric_but_not_lwd_markers():
    defaults = build_input_type_defaults(_pattern("date of birth", "17/12/2000", "personal_info"))
    assert defaults["date"] == "2000-12-17"
    assert defaults["number"] == "17122000"
    assert LWD_NUMERIC_MARKER not in defaults["text"]


@pytest.mark.unit
def test_numeric_zero_is_not_treated_as_yes():
    defaults = build_input_type_defaults(
        _pattern("please specify your disability percentage", "0", "compliance")
    )
    assert defaults["number"] == "0"
    assert defaults["checkbox"] == "No"


@pytest.mark.unit
def test_checkbox_lists_keep_items_and_na_stays_unchecked():
    tech = build_input_type_defaults(_pattern("tech stack", "Java, Spring Boot, React, AWS", "skills"))
    assert tech["checkbox"] == "Java, Spring Boot, React, AWS"
    assert tech["checkbox"] != "Yes"

    na = build_input_type_defaults(
        _pattern("if referred, mention employee name", "N/A", "compliance")
    )
    assert na["checkbox"] == "No"


@pytest.mark.unit
@pytest.mark.parametrize(
    "question,default,expected",
    [
        ("email address", "x@example.com", "email"),
        ("contact number", "7905828880", "phone"),
        ("pan number", "MTKPS1941P", "pan"),
        ("passport number", "M1234567", "passport"),
        ("date of birth", "17/12/2000", "dob"),
        ("pin code", "560001", "pincode"),
        ("current address", "Bengaluru, Karnataka", "address"),
        ("full name", "Siddhant Singh", "name"),
        ("passport valid", "Yes", None),
    ],
)
def test_pii_classification(question, default, expected):
    assert detect_pii_kind(question, default) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "pattern_id",
    [
        "contact_email",
        "contact_phone",
        "email_and_phone",
        "pan_card",
        "personal_dob",
        "personal_pan",
        "dob_and_pan",
        "zip_code",
        "current_address",
        "self_id_name",
    ],
)
def test_real_pii_patterns_require_exact_match(qa_config, pattern_id):
    data = qa_config["patterns"][pattern_id]
    assert data.get("sensitive") is True
    assert data.get("requires_exact_match") is True


@pytest.mark.unit
def test_requires_exact_match_blocks_fuzzy_tiers():
    matcher = PatternMatcher(
        {
            "patterns": {
                "contact_email": {
                    "patterns": ["email address"],
                    "category": "personal_info",
                    "default": "secret@example.com",
                    "requires_exact_match": True,
                    "priority": 20,
                },
                "notice": {
                    "patterns": ["notice period"],
                    "category": "notice_period",
                    "default": "15 days",
                    "priority": 5,
                },
            }
        }
    )

    assert matcher.fuzzy_match("email address")[0] == "secret@example.com"
    assert matcher.fuzzy_match("please enter your email address")[0] != "secret@example.com"
    assert matcher.fuzzy_match("email adress")[0] != "secret@example.com"


@pytest.mark.unit
def test_no_template_or_placeholder_leaks_in_real_config(qa_config):
    leaks = []
    junk = []
    for pattern_id, data in qa_config["patterns"].items():
        values = [data.get("default")]
        values.extend((data.get("input_type_defaults") or {}).values())
        for value in values:
            text = str(value)
            if "{{" in text or "}}" in text:
                leaks.append((pattern_id, text[:80]))
            if text.strip().lower() in audit.PLACEHOLDER_JUNK:
                junk.append((pattern_id, text))
    assert not leaks, leaks[:10]
    assert not junk, junk[:10]


@pytest.mark.unit
def test_intent_detection_does_not_collapse_open_questions_to_yes_no():
    intent = detect_intent(
        "what are the key architectural trade-offs of database sharding",
        "skills",
        "The main trade-off is operational complexity.",
    )
    assert intent.is_yes_no is False
    assert not intent.negative and not intent.affirmative


@pytest.mark.slow
def test_full_corpus_input_type_audit_is_clean(qa_config):
    result = audit.audit_patterns(qa_config, max_examples=5)
    assert result["violation_count"] == 0, result["examples"]
