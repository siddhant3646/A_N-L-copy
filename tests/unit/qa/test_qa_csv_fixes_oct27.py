"""
Unit tests for CSV audit pattern fixes identified on Oct 27, 2026.
Tests cover:
- 0-5 self rating scale (backend/db -> 4, ai/llm -> 3)
- Workday technical/functional consultant experience -> 0 / None
- Health care experience (with space) -> 0 Years / 0
- Expected CTC vs Current CTC (EX-CTC -> 30, base+variable -> 23)
- CTC threshold gates ('is your current/expected ctc up to ₹45 lpa?') -> Yes
- Experience threshold gates (8+ yrs -> No, 10-15 yrs -> No, 4-9 yrs -> Yes)
- Location vs Price Elasticity non-collision ('price elasticity of demand' not matched to Bengaluru)
- Specific location gate ('are you currently located in ahmedabad or gandhinagar?') -> No
- Notice period serving ('are you currently servicing notice period?') -> Yes
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


class TestQACSVFixesOct27:
    """Test suite for QA CSV audit fixes on Oct 27, 2026."""

    def test_rating_scale_backend(self, matcher, agent):
        q = "what would be your self-rating on backend with any web frameworks? rate yourself on a scale of (0-5)"
        ans_m, score_m = matcher.fuzzy_match(q)
        assert ans_m == "4"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "4"
        assert score_a >= 0.90

    def test_rating_scale_database(self, matcher, agent):
        q = "what would be your self-rating on database design? rate yourself on a scale of (0-5)"
        ans_m, score_m = matcher.fuzzy_match(q)
        assert ans_m == "4"
        assert score_m >= 0.90

    def test_rating_scale_ai_agents(self, matcher, agent):
        q = "what would be your self-rating on understanding of frameworks to build ai agents? rate yourself on a scale of (0-5)"
        ans_m, score_m = matcher.fuzzy_match(q)
        assert ans_m == "3"
        assert score_m >= 0.90

    def test_rating_scale_llm_evals(self, matcher, agent):
        q = "what would be your self-rating on llm-based evals? rate yourself on a scale of (0-5)"
        ans_m, score_m = matcher.fuzzy_match(q)
        assert ans_m == "3"
        assert score_m >= 0.90

    def test_workday_consultant_experience(self, matcher, agent):
        q1 = "How many years of experience do you have in Workday Technical Consultant?"
        ans1, _ = matcher.fuzzy_match(q1)
        assert "0" in ans1

        ans1_a, _ = agent._fuzzy_match_question(q1)
        assert "0" in ans1_a

        q2 = "How many years of experience do you have in Workday Integration Consultant?"
        ans2, _ = matcher.fuzzy_match(q2)
        assert "0" in ans2

    def test_workday_functional_modules(self, matcher, agent):
        q = "What are the primary modules in workday functional"
        ans, score = matcher.fuzzy_match(q)
        assert ans in ("None", "N/A")
        assert score >= 0.90

    def test_healthcare_domain_experience(self, matcher, agent):
        q = "how many years of health care experience do you currently have (in years)?"
        ans, _ = matcher.fuzzy_match(q)
        assert "0" in ans

        ans_a, _ = agent._fuzzy_match_question(q)
        assert "0" in ans_a

    def test_expected_ctc_ex_ctc(self, matcher, agent):
        q = "What is your EX-CTC?"
        ans, score = matcher.fuzzy_match(q)
        assert "30" in ans
        assert score >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "30" in ans_a
        assert score_a >= 0.90

    def test_ctc_base_plus_variable(self, matcher, agent):
        q = "what is your current ctc? base + variable?"
        ans, score = matcher.fuzzy_match(q)
        assert "23" in ans
        assert ans != "0"
        assert score >= 0.90

    def test_ctc_threshold_gate_up_to_45_lpa(self, matcher, agent):
        q = "is your current/expected ctc up to ₹45 lpa?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_experience_gate_8_plus_years(self, matcher, agent):
        q = "pl confirm if you have overall 8 + yrs and above experience . incase if you have  less than 8 yrs,  your resume will get rejected. kindly pl confirm ."
        ans, score = matcher.fuzzy_match(q)
        assert ans == "No"
        assert score >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "No"
        assert score_a >= 0.90

    def test_experience_gate_10_to_15_years(self, matcher, agent):
        q = "we are looking for candidates with 10–15 years of total experience only. candidates with more than 15 years of experience will not be considered?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "No"
        assert score >= 0.90

    def test_experience_req_4_to_9_years(self, matcher, agent):
        q = "•\t4-9 years of experience in full stack, frontend, or backend software development."
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_price_elasticity_no_location_collision(self, matcher, agent):
        q = "how would you calculate price elasticity of demand"
        ans, _ = matcher.fuzzy_match(q)
        assert ans != "Bengaluru"
        assert ans != "Bengaluru, Karnataka, India"

        ans_a, _ = agent._fuzzy_match_question(q)
        assert ans_a != "Bengaluru"
        assert ans_a != "Bengaluru, Karnataka, India"

    def test_location_ahmedabad_gandhinagar(self, matcher, agent):
        q = "are you currently located in ahmedabad or gandhinagar?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "No"
        assert score >= 0.90

    def test_currently_servicing_notice_period(self, matcher, agent):
        q = "are you currently servicing notice period?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Yes"
        assert score >= 0.90
