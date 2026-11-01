"""
Unit tests for CSV audit pattern fixes identified on Oct 28, 2026.
Tests cover:
- Eligible and authorized to work on ongoing indefinite basis (Navan) -> Yes
- Work authorization select default and option matching -> Yes
- Primary base in non-Bangalore city (Chennai, etc.) -> No
- Residing in Chennai verification -> No
- Notice period questions containing 'years' ("How many years of notice period do you have?") -> 15 Days (not 4 years!)
- Official notice period in days ("Whats your official notice period?", "What is your official notice period - Mention in days?") -> 15 / 15 days (not 30!)
- Multi-select / checkbox shift preference ("Please share your shift preference") -> Day Job / Day Shift
"""

import pytest
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher
from src.sentinel.agent import SentinelAgent


@pytest.fixture
def agent():
    return SentinelAgent()


@pytest.fixture
def matcher():
    patterns = load_patterns('config/qa_patterns.json')
    return PatternMatcher(patterns)


class TestQACSVFixesOct28:
    """Test suite for QA CSV audit fixes on Oct 28, 2026."""

    def test_navan_work_authorization_select(self, matcher, agent):
        q = "Are you currently eligible to work in the country outlined for this position, and authorized to work for Navan on an ongoing indefinite basis?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='select')
        assert ans_m == "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "Yes"
        assert score_a >= 0.90

    def test_navan_work_authorization_radio(self, matcher, agent):
        q = "Are you currently eligible to work in the country outlined for this position, and authorized to work for Navan on an ongoing indefinite basis?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='radio')
        assert ans_m == "Yes"
        assert score_m >= 0.90

    def test_work_authorization_select_pattern_default(self, matcher):
        q = "legal right to work in the country where the job is based"
        ans, score = matcher.fuzzy_match(q, input_type='select')
        assert ans == "Yes"
        assert score >= 0.90

    def test_primary_base_chennai_radio(self, matcher, agent):
        q = "Can you confirm if your primary base is Chennai?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='radio')
        assert ans_m == "No"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "No"
        assert score_a >= 0.90

    def test_is_primary_base_chennai(self, matcher, agent):
        q = "Is your primary base Chennai?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='radio')
        assert ans_m == "No"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "No"
        assert score_a >= 0.90

    def test_residing_in_chennai_verification(self, matcher, agent):
        q = "Are you currently residing in Chennai?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='radio')
        assert ans_m == "No"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "No"
        assert score_a >= 0.90

    def test_notice_period_with_years_phrase_select(self, matcher, agent):
        q = "How many years of notice period do you have?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='select')
        assert ans_m == "15 Days"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "15" in ans_a
        assert "4" not in ans_a
        assert score_a >= 0.90

    def test_official_notice_period_in_days(self, matcher, agent):
        q = "What is your official notice period - Mention in days?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert ans_m == "15"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "15"
        assert score_a >= 0.90

    def test_whats_official_notice_period(self, matcher, agent):
        q = "Whats your official notice period?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert ans_m in ("15", "15 days")
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a in ("15", "15 days", "Less than 30 days")
        assert score_a >= 0.90

    def test_shift_preference_checkbox(self, matcher, agent):
        q = "Please share your shift preference"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='checkbox')
        assert ans_m == "Day Job"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "Day" in ans_a
        assert score_a >= 0.90
