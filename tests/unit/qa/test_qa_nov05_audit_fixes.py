"""
Unit tests for Q&A pattern fixes and intercepts identified in the November 2026 qa_results.csv audit.
"""

import pytest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns


@pytest.fixture(scope="module")
def agent():
    a = SentinelAgent()
    return a


@pytest.fixture(scope="module")
def pattern_matcher():
    patterns = load_patterns("config/qa_patterns.json")
    return PatternMatcher(patterns=patterns)


def test_experience_gate_not_triggered_for_value_inquiries(agent):
    """
    Questions asking for years of experience (even with parenthetical constraints
    like '(Minimum 6 years required)' or '(7yrs + only apply)') must return the
    candidate's actual experience, not a Yes/No gate answer of 'No'.
    """
    q1 = "How many years of hands-on experience do you have with Java and Spring Boot? (Minimum 6 years required)"
    ans1, conf1 = agent._fuzzy_match_question(q1)
    assert ans1 is not None
    assert ans1 != "No"
    assert "4" in ans1

    q2 = "How many years do you have experience in Java? (7yrs + only apply)"
    ans2, conf2 = agent._fuzzy_match_question(q2)
    assert ans2 is not None
    assert ans2 != "No"
    assert "4" in ans2


def test_naukri_registered_mobile_number(agent, pattern_matcher):
    """
    Naukri registered mobile number question must return candidate's phone number
    7905828880 instead of defaulting to 'Yes'.
    """
    q = "What is your Naukri Registered Mobile Number?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans == "7905828880"
    assert conf >= 0.90

    # Pattern matcher direct match
    p_ans, p_conf = pattern_matcher.fuzzy_match(q)
    assert p_ans == "7905828880"
    assert p_conf >= 0.80


def test_expected_total_compensation_etc(agent, pattern_matcher):
    """
    Standalone 'ETC ?' or 'Expected Total Compensation' questions must return
    3000000 or 30 LPA, not Yes.
    """
    q = "ETC ?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans in ("3000000", "30 LPA")
    assert conf >= 0.90

    q_full = "What is your ETC?"
    ans_full, conf_full = agent._fuzzy_match_question(q_full)
    assert ans_full in ("3000000", "30 LPA")
    assert conf_full >= 0.90


def test_full_name_with_punctuation(agent):
    """
    'Please enter your full name.' must return 'Siddhant Singh' and not overlap
    with referral patterns returning 'N/A'.
    """
    q = "Please enter your full name."
    ans, conf = agent._fuzzy_match_question(q)
    assert ans == "Siddhant Singh"
    assert conf >= 0.95


def test_onsite_hyderabad_vs_relocation(agent, pattern_matcher):
    """
    'Are you working onsite in Hyderabad?' must clarify that candidate is in Bangalore
    and can relocate to Hyderabad, not claim to currently be in Hyderabad.
    """
    q = "Are you working onsite in Hyderabad? You may also have to travel to client locations whenever required"
    ans, conf = agent._fuzzy_match_question(q)
    assert "relocate to Hyderabad" in ans
    assert conf >= 0.90


def test_women_networking_session_male_candidate(agent, pattern_matcher):
    """
    Candidate is male, so Women networking session must answer No.
    """
    q = "Are you available for the Offline Women Networking Session on 20th Nov from 2:30PM?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans.upper() in ("NO", "N")
    assert conf >= 0.90


def test_compound_notice_period_and_lwd(agent):
    """
    Questions asking for both notice period and last working day must answer with
    15 days notice and include LWD (or 15 on LinkedIn numeric).
    """
    q = "What is your notice period? If you are currently serving it, please share your last working day."
    ans, conf = agent._fuzzy_match_question(q)
    assert ans != "Yes"
    assert "15" in ans


def test_days_left_in_last_working_day(agent, pattern_matcher):
    """
    'How many days are left in your last working day?' asks for count of days,
    so it must answer '15', NOT a date like '13 Nov 2026'.
    """
    q = "How many days are left in your last working day?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans == "15"
    assert conf >= 0.90

    p_ans, p_conf = pattern_matcher.fuzzy_match(q)
    assert p_ans == "15"
    assert p_conf >= 0.80


def test_can_join_in_15_to_20_days_yes_no(agent):
    """
    'Can you join in 15-20 days ?' is a Yes/No question and candidate's notice period
    is 15 days, so answer must be 'Yes', not '15'.
    """
    q = "Can you join in 15-20 days ?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans == "Yes"
    assert conf >= 0.95


def test_open_ended_technical_questions(pattern_matcher):
    """
    Technical questions that previously had no pattern and defaulted to 'Yes'
    must now have detailed answers in pattern matcher.
    """
    # 1. DevTools load time slow
    q1 = "App's initial load time is slow. How will you diagnose and improve it ?"
    ans1, conf1 = pattern_matcher.fuzzy_match(q1)
    assert conf1 >= 0.70
    assert "DevTools" in ans1 or "Lighthouse" in ans1 or "code split" in ans1

    # 2. Built from zero
    q2 = "Tell me about something you built from zero. What decisions did you make and what would you change?"
    ans2, conf2 = pattern_matcher.fuzzy_match(q2)
    assert conf2 >= 0.70
    assert "Everbridge" in ans2 or "Kafka" in ans2

    # 3. Recent AI development
    q3 = "What s one AI development you recently learned about, and what did you do with it?"
    ans3, conf3 = pattern_matcher.fuzzy_match(q3)
    assert conf3 >= 0.70
    assert "Agent" in ans3 or "LLM" in ans3 or "LangChain" in ans3

    # 4. Drupal upgrades
    q4 = "What kind of Drupal upgrades have you done?"
    ans4, conf4 = pattern_matcher.fuzzy_match(q4)
    assert conf4 >= 0.70
    assert "None" in ans4 or "Java" in ans4

    # 5. Software development practices
    q5 = "Software development practices/lifecycle that you are familiar with?"
    ans5, conf5 = pattern_matcher.fuzzy_match(q5)
    assert conf5 >= 0.70
    assert "Agile" in ans5 or "TDD" in ans5 or "CI/CD" in ans5
