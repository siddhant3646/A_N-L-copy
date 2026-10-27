"""Regression tests for pure-vs-compound company-history questions.

These guard the Infosys/NetApp collision fixes:

* Pure "have you worked here / are you a former employee" questions must
  resolve to a boolean ("No"), never to an ID placeholder ("NA").
* Compound questions that explicitly ask for an employee ID must resolve to
  "NA" (the candidate never worked at Infosys), never to "No".
* The generic ``company_association`` radio default must not leak the
  NetApp-specific label ("No - Never associated with NetApp") into unrelated
  companies.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import pytest

from src.patterns.pattern_matcher import create_matcher

# (question, input_type, expected_answer)
PURE_STATUS_CASES = [
    ("Ex-Infosys employee", "text", "No"),
    ("Ex-Infosys employee", "radio", "No"),
    ("Former Infosys employee", "text", "No"),
    ("Are you an ex-Infosys employee?", "text", "No"),
    ("Are you an ex-Infosys employee?", "radio", "No"),
    ("Are you a former Infosys employee?", "text", "No"),
    ("Have you previously worked in Infosys?", "text", "No"),
    ("Have you worked at Infosys before?", "text", "No"),
    ("Have you worked at Infosys before?", "radio", "No"),
    ("Were you previously employed at Infosys?", "text", "No"),
    ("Did you work at Infosys earlier?", "text", "No"),
]

COMPOUND_ID_CASES = [
    ("Ex-Infosys employee ID", "text", "NA"),
    ("Ex Infosys employee ID", "text", "NA"),
    ("Infosys Employee ID (if applicable)", "text", "NA"),
    ("Employee ID at Infosys", "text", "NA"),
    ("Your Infosys employee ID", "text", "NA"),
    ("Former Infosys employee ID", "text", "NA"),
    ("Have you previously worked in Infosys? If yes, provide ex-Infy ID", "text", "NA"),
    (
        "Are you an ex-Infosys employee? If yes, mention your employee ID, else write NA",
        "text",
        "NA",
    ),
    ("If you are an ex-Infosys employee, mention your employee ID", "text", "NA"),
]


@pytest.fixture(scope="module")
def matcher():
    return create_matcher()


@pytest.mark.unit
@pytest.mark.parametrize("question,input_type,expected", PURE_STATUS_CASES)
def test_pure_status_question_resolves_to_boolean(matcher, question, input_type, expected):
    answer, confidence = matcher.fuzzy_match(question, input_type=input_type)
    assert answer == expected, (
        f"{question!r} ({input_type}) resolved to {answer!r} at {confidence:.2f}; "
        f"expected {expected!r}"
    )
    assert confidence >= 0.6


@pytest.mark.unit
@pytest.mark.parametrize("question,input_type,expected", COMPOUND_ID_CASES)
def test_compound_id_question_resolves_to_na(matcher, question, input_type, expected):
    answer, confidence = matcher.fuzzy_match(question, input_type=input_type)
    assert answer == expected, (
        f"{question!r} ({input_type}) resolved to {answer!r} at {confidence:.2f}; "
        f"expected {expected!r}"
    )
    assert confidence >= 0.6


@pytest.mark.unit
def test_company_association_radio_has_no_netapp_leak():
    from src.patterns.pattern_loader import load_patterns

    config_path = os.path.join(
        os.path.dirname(__file__), "../../..", "config", "qa_patterns.json"
    )
    data = load_patterns(config_path)
    pattern = data["patterns"]["company_association"]
    radio = pattern.get("input_type_defaults", {}).get("radio", "")
    assert "netapp" not in str(radio).lower(), (
        "company_association.radio must not hardcode a NetApp-specific label; "
        f"found {radio!r}"
    )


@pytest.mark.unit
def test_netapp_association_stays_netapp_specific(matcher):
    answer, _ = matcher.fuzzy_match(
        "Have you been previously or are you currently associated with NetApp?",
        input_type="radio",
    )
    assert answer is not None and "netapp" in str(answer).lower(), (
        f"NetApp-specific question should keep the NetApp label, got {answer!r}"
    )

    answer, _ = matcher.fuzzy_match("Have you worked at Infosys before?", input_type="radio")
    assert "netapp" not in str(answer).lower(), (
        f"Infosys question must not return a NetApp label, got {answer!r}"
    )
