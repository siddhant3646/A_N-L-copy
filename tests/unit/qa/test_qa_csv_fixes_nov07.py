"""
Unit tests for Q&A pattern fixes and additions identified from qa_results.csv audit (Nov 07, 2026).
"""

import pytest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns


@pytest.fixture(scope="module")
def agent():
    return SentinelAgent()


@pytest.fixture(scope="module")
def pattern_matcher():
    patterns = load_patterns("config/qa_patterns.json")
    return PatternMatcher(patterns=patterns)


def test_programming_tool_hands_on(agent, pattern_matcher):
    """
    Question asks which development/programming tool candidate is hands-on with:
    'Which of these development/programming tool are you hands-on with - C++, Java or Golang'
    Must answer 'Java', not '4.2 Years'.
    """
    q = "Which of these development/programming tool are you hands-on with - C++, Java or Golang"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="text")
    assert ans_m == "Java"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Java"
    assert conf_a >= 0.90


def test_full_stack_technologies_working_with(agent, pattern_matcher):
    """
    Question asks which full-stack technologies candidate is working with.
    Must answer with technologies ('Java', 'Spring Boot', 'React'), not boolean 'Yes'.
    """
    questions = [
        "3.\tWhich full-stack technologies are you currently working with?",
        "Which full-stack technologies are you currently working with?",
        "What full-stack technologies are you currently working with?",
    ]
    for q in questions:
        ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="textarea")
        assert "Java" in ans_m and "Spring Boot" in ans_m
        assert ans_m != "Yes"
        assert conf_m >= 0.90

        ans_a, conf_a = agent._fuzzy_match_question(q)
        assert "Java" in ans_a and "Spring Boot" in ans_a
        assert ans_a != "Yes"
        assert conf_a >= 0.90


def test_us_hours_overlap_2_to_4_hours(agent, pattern_matcher):
    """
    Question asks about ability to overlap 2-4 hours with US working hours.
    Must answer 'Yes', not 'Full-time'.
    """
    questions = [
        "9.  Are you able to overlap at least 2-4 hours with U.S. working hours?",
        "Are you able to overlap at least 2-4 hours with U.S. working hours?",
        "Are you able to overlap at least 2-4 hours with US working hours?",
    ]
    for q in questions:
        ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="textarea")
        assert ans_m == "Yes"
        assert conf_m >= 0.90

        ans_a, conf_a = agent._fuzzy_match_question(q)
        assert ans_a == "Yes"
        assert conf_a >= 0.90


def test_relatives_employed_company(agent, pattern_matcher):
    """
    Question asks if any relatives are currently employed at company.
    Candidate has no relatives there, so must answer 'No' or 'N/A', NOT 'Yes'.
    """
    q = "Are any relatives currently employed here? If yes, give the full name of employee working in Inchcape"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="text")
    assert ans_m in ("No", "N/A", "None")
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a in ("No", "N/A", "None")
    assert conf_a >= 0.90


def test_confirm_state_residence(agent, pattern_matcher):
    """
    Question asks to confirm state of residence:
    'If the state you currently live in is not listed above, please confirm which state you reside in...'
    Must answer 'Karnataka', NOT 'Yes' from generic consent pattern.
    """
    q = "If the state you currently live in is not listed above, please confirm which state you reside in. Please complete this only if you selected \u2018State Not Listed\u2019 above."
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="text")
    assert ans_m == "Karnataka"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Karnataka"
    assert conf_a >= 0.90


def test_specific_azure_data_certifications(agent, pattern_matcher):
    """
    Question asks for specific certifications DP-700 / AZ-104 / AZ-400.
    Candidate does not have these, so must answer 'None' or 'No', NOT 'AWS Certified'.
    """
    q = "Have you done any of the certification below ( DP - 700 or AZ-104 or AZ-400)"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="text")
    assert ans_m in ("None", "No")
    assert "AWS" not in ans_m
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a in ("None", "No")
    assert "AWS" not in ans_a
    assert conf_a >= 0.90


def test_current_employment_status_serving(agent, pattern_matcher):
    """
    'Your Current Employment Status'
    Candidate is serving notice period with 15 days remaining.
    Must answer 'Serving Notice Period' / 'Currently In Notice or Serving Notice', NOT 'Not Serving'.
    """
    q = "Your Current Employment Status"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert "Serving Notice" in ans_m or "Serving" in ans_m
    assert "Not Serving" not in ans_m
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "Serving Notice" in ans_a or "Serving" in ans_a
    assert "Not Serving" not in ans_a
    assert conf_a >= 0.90


def test_independently_designed_architecture_web_applications(agent, pattern_matcher):
    """
    'Have you independently designed the architecture of web applications?'
    Must answer affirmatively with architecture details, not None.
    """
    q = "4.\tHave you independently designed the architecture of web applications?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="textarea")
    assert ans_m is not None
    assert "Yes" in ans_m or "architecture" in ans_m.lower()
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a is not None
    assert "Yes" in ans_a or "architecture" in ans_a.lower()
    assert conf_a >= 0.90


def test_immediate_basis_max_7_days(agent, pattern_matcher):
    """
    'Can you join on Immediate Basis ? Max 7 days ? Noida Location ?'
    Must answer 'Yes'.
    """
    q = "Can you join on Immediate Basis ? Max 7 days ? Noida Location ?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_education_verification_and_employment(agent, pattern_matcher):
    """
    Truncated label from LinkedIn DOM:
    'As part of the employment process, all candidates are subject to employment and education verificati'
    Must answer 'Yes'.
    """
    q = "As part of the employment process, all candidates are subject to employment and education verificati"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_english_communication_and_us_overlap(agent, pattern_matcher):
    """
    Truncated label:
    'Clear written and spoken English and availability for agreed overlap with US Eastern AM business ho'
    Must answer 'Yes'.
    """
    q = "Clear written and spoken English and availability for agreed overlap with US Eastern AM business ho"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_available_in_30_days_notice_period(agent, pattern_matcher):
    """
    'Are you available in 30 days notice period?' on a radio button must answer 'Yes', not '15'.
    """
    q = "Are you available in 30 days notice period?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_self_rating_splunk_dynatrace(pattern_matcher):
    """
    Self rating in technical tools (Splunk, Dynatrace) on 1-5 scale.
    Must return rating (e.g. '4/5_Advanced' or '4'), not '4.2 Years' or '9'.
    """
    for q in ("Self Rating in Splunk", "Self Rating in Dynatrace"):
        ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
        assert ans_m in ("4/5_Advanced", "4", "4/5")
        assert ans_m != "4.2 Years"
        assert ans_m != "9"
        assert conf_m >= 0.90


def test_position_applied_for(agent, pattern_matcher):
    """
    'Position Applied for' must return role title 'Software Engineer', not boolean 'Yes'.
    """
    q = "Position Applied for"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q, input_type="radio")
    assert ans_m == "Software Engineer"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "Software Engineer" in ans_a
    assert conf_a >= 0.90
