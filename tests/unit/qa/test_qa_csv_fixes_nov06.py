"""
Unit tests for Q&A pattern fixes and additions identified from qa_results.csv audit (Nov 06, 2026).
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


def test_work_authorization_without_sponsorship(agent, pattern_matcher):
    """
    Candidate is an Indian citizen in India and can provide proof of eligibility without sponsorship.
    Questions must answer 'Yes', not 'No'.
    """
    q = "If hired, can you provide proof of identity and eligibility to work in India without sponsorship?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_gdpr_notice_consent(agent, pattern_matcher):
    """
    'GDPR Notice' is a data consent question and must answer 'Yes', NOT '15' (notice period days).
    """
    q = "GDPR Notice"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_which_database_experience(agent, pattern_matcher):
    """
    Questions asking which database experience candidate has (SQL/MySQL/Drupal/MSSQL/others)
    must return database names, not '4.2 Years'.
    """
    q = "Which database experience do you have, mention if it's SQL/ MySQL/ Drupal DB/ MSSQL/ others?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert "PostgreSQL" in ans_m or "MySQL" in ans_m
    assert "Years" not in ans_m
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "PostgreSQL" in ans_a or "MySQL" in ans_a
    assert "Years" not in ans_a
    assert conf_a >= 0.90


def test_backend_engineering_experience_and_technologies_production(agent, pattern_matcher):
    """
    Descriptive prompt asking for hands-on backend experience and technologies used in production
    must return a technical description, not '4.2 Years'.
    """
    q = "What is your hands-on backend engineering experience and which technologies have you used in production?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert "Java" in ans_m or "Spring Boot" in ans_m
    assert ans_m != "4.2 Years"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "Java" in ans_a or "Spring Boot" in ans_a
    assert ans_a != "4.2 Years"
    assert conf_a >= 0.90


def test_mention_strong_experience_skills(agent, pattern_matcher):
    """
    'Please mention Strong experience skills(like React, Angular Typescript...)'
    asks to list skills, not a number of years '4'.
    """
    q = "Please mention Strong experience skills(like React, Angular Typescript, Java Script, ES6, Express..js, node.js ect...,)"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert "Java" in ans_m or "React" in ans_m or "TypeScript" in ans_m
    assert ans_m not in ("4", "4.2", "4.2 Years")
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "Java" in ans_a or "React" in ans_a or "TypeScript" in ans_a
    assert ans_a not in ("4", "4.2", "4.2 Years")
    assert conf_a >= 0.90


def test_which_location_preferred_and_noida_kolkata(agent, pattern_matcher):
    """
    'Which location do you prefer ? Noida, Pune, chennai, bangalore, hyderabad, Mumbai ?'
    and 'Preferred Location- Noida/Kolkata' must return specific cities, not 'Yes' or 'No'.
    """
    q1 = "Which location do you prefer ? Noida, Pune, chennai, bangalore, hyderabad, Mumbai ?"
    ans_m1, conf_m1 = pattern_matcher.fuzzy_match(q1)
    assert "Bangalore" in ans_m1 or "Bengaluru" in ans_m1
    assert ans_m1 not in ("Yes", "No")
    assert conf_m1 >= 0.90

    ans_a1, conf_a1 = agent._fuzzy_match_question(q1)
    assert "Bangalore" in ans_a1 or "Bengaluru" in ans_a1
    assert ans_a1 not in ("Yes", "No")
    assert conf_a1 >= 0.90

    q2 = "Preferred Location- Noida/Kolkata"
    ans_m2, conf_m2 = pattern_matcher.fuzzy_match(q2)
    assert "Noida" in ans_m2
    assert ans_m2 not in ("Yes", "No")
    assert conf_m2 >= 0.90

    ans_a2, conf_a2 = agent._fuzzy_match_question(q2)
    assert "Noida" in ans_a2
    assert ans_a2 not in ("Yes", "No")
    assert conf_a2 >= 0.90


def test_working_mode_hybrid_comfortable(agent, pattern_matcher):
    """
    'Work Location : Pune, working Mode: Hybrid, Are you Comfortable with that?'
    must answer 'Yes', not the 10-city preferred locations list.
    """
    q = "Work Location : Pune, working Mode: Hybrid, Are you Comfortable with that?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_years_of_notice_period(agent, pattern_matcher):
    """
    'How many years of notice period do you have?' asks for notice period,
    so it must return '15 Days', not experience years '4'.
    """
    q = "How many years of notice period do you have?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert "15" in ans_m
    assert ans_m != "4"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert "15" in ans_a
    assert ans_a != "4"
    assert conf_a >= 0.90


def test_shift_preference_options(agent, pattern_matcher):
    """
    'Please share your shift preference' with options ['Night Job', 'Day Job', 'Flex Job']
    must answer 'Day Job', not 'Yes' or '<AsyncMock...>'.
    """
    q = "Please share your shift preference"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert ans_m == "Day Job"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Day Job"
    assert conf_a >= 0.90


def test_dou_you_have_agentic_ai_fullstack(agent, pattern_matcher):
    """
    'Dou you have Agentic AI and Python Full stack Experience?' has typo 'Dou'
    and must answer 'Yes', not '4.2'.
    """
    q = "Dou you have Agentic AI and Python Full stack Experience?"
    ans_m, conf_m = pattern_matcher.fuzzy_match(q)
    assert ans_m == "Yes"
    assert conf_m >= 0.90

    ans_a, conf_a = agent._fuzzy_match_question(q)
    assert ans_a == "Yes"
    assert conf_a >= 0.90


def test_how_much_annual_salary_expecting_radio(pattern_matcher):
    """
    For radio/select options, 'How much annual salary are you expecting?'
    must provide '30' or '30 LPA' so numeric range matcher matches options like
    '25 to 30 lakhs' or '30-35 lakhs' instead of failing on '3000000'.
    """
    p = pattern_matcher.patterns["patterns"].get("how_much_annual_salary_expecting", {})
    inputs = p.get("input_type_defaults", {})
    assert inputs.get("radio") == "30"
    assert inputs.get("select") == "30 LPA"
    assert inputs.get("textarea") == "30 LPA"
