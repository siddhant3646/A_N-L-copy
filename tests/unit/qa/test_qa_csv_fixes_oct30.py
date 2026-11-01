"""
Unit tests for QA pattern fixes identified from the qa_results.csv audit on Oct 30, 2026.

Audited fixes cover:
1. Budget-bounded expected CTC questions ("What is your Expected CTC? Max budget is upto 25LPA") -> "30 LPA (Flexible)" / "3000000" (NOT "No")
2. Degree institution questions ("Which institution did you complete your B.Tech from?") -> "VIT Bhopal University" (NOT "Yes")
3. System design experience questions ("No. of year of exp on System Design like HLD, LLD?") -> "4.2 Years" / "4" (NOT "Yes")
4. SDLC / Software development lifecycle practices ("Software development practices/lifecycle that you are familiar with?") -> SDLC practices string (NOT "Yes")
5. Mobile / Phone number questions ("Mobile phone number", "Cell phone number") -> "7905828880" (NOT "4")
6. Shift preference inquiries ("Please share your shift preference") -> "Day Job" (NOT "Yes")
7. Afternoon / Evening shift readiness ("Its a shift job starting from 4.00pm onwards are you ready for the same") -> "Yes" (NOT "Day Job")
8. 10th / 12th percentage and CGPA distinctions -> 88 / 70 / 8.8
9. Social URL empty string defaults -> "" (NOT "__LEAVE_BLANK__")
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


class TestQACSVFixesOct30:
    """Test suite for QA CSV audit fixes on Oct 30, 2026."""

    def test_expected_ctc_with_budget_clause_text(self, matcher, agent):
        q = "What is your Expected CTC? Max budget is upto 25LPA"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert "30" in ans_m
        assert ans_m != "No"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "30" in ans_a
        assert ans_a != "No"
        assert score_a >= 0.90

    def test_expected_ctc_with_budget_clause_textarea(self, matcher, agent):
        q = "What is your Expected CTC? Max budget is upto 25LPA"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='textarea')
        assert "30" in ans_m
        assert ans_m != "No"
        assert score_m >= 0.90

    def test_which_institution_btech(self, matcher, agent):
        q = "Which institution did you complete your B.Tech from?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert "VIT Bhopal" in ans_m
        assert ans_m != "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "VIT Bhopal" in ans_a
        assert ans_a != "Yes"
        assert score_a >= 0.90

    def test_system_design_experience(self, matcher, agent):
        q = "No. of year of exp on System Design like HLD, LLD?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert "4" in ans_m
        assert ans_m != "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "4" in ans_a
        assert ans_a != "Yes"
        assert score_a >= 0.90

    def test_software_development_practices(self, matcher, agent):
        q = "Software development practices/lifecycle that you are familiar with?"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert any(k in ans_m.lower() for k in ["agile", "scrum", "ci/cd", "microservices"])
        assert ans_m != "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert any(k in ans_a.lower() for k in ["agile", "scrum", "ci/cd", "microservices"])
        assert ans_a != "Yes"
        assert score_a >= 0.90

    def test_mobile_phone_number(self, matcher, agent):
        q = "Mobile phone number"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert ans_m == "7905828880"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "7905828880"
        assert score_a >= 0.90

    def test_cell_phone_number(self, matcher, agent):
        q = "Cell phone number"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='text')
        assert ans_m == "7905828880"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "7905828880"
        assert score_a >= 0.90

    def test_share_shift_preference(self, matcher, agent):
        q = "Please share your shift preference"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='checkbox')
        assert "Day" in ans_m
        assert ans_m != "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert "Day" in ans_a
        assert ans_a != "Yes"
        assert score_a >= 0.90

    def test_shift_job_4pm_readiness(self, matcher, agent):
        q = "Its a shift job starting from 4.00pm onwards are you ready for the same"
        ans_m, score_m = matcher.fuzzy_match(q, input_type='radio')
        assert ans_m == "Yes"
        assert score_m >= 0.90

        ans_a, score_a = agent._fuzzy_match_question(q)
        assert ans_a == "Yes"
        assert score_a >= 0.90

    def test_tenth_percentage(self, agent):
        ans, score = agent._fuzzy_match_question("Percentage in 10th")
        assert ans == "88"
        assert score >= 0.90

    def test_twelfth_percentage(self, agent):
        ans, score = agent._fuzzy_match_question("Percentage in 12th")
        assert ans == "70"
        assert score >= 0.90

    def test_tenth_cgpa(self, agent):
        ans, score = agent._fuzzy_match_question("CGPA in 10th")
        assert ans == "8.8"
        assert score >= 0.90

    def test_social_urls_empty_not_marker(self, matcher):
        ans_fb, _ = matcher.fuzzy_match("Facebook profile URL")
        assert ans_fb == "__LEAVE_BLANK__"

        ans_tw, _ = matcher.fuzzy_match("Twitter handle or URL")
        assert ans_tw == "__LEAVE_BLANK__"
