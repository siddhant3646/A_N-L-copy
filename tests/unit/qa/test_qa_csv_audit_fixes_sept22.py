"""
Unit tests for Q&A audit fixes from qa_results.csv (September 22, 2026).

Covers:
1. CTC / Salary questions specified 'in Lacs per annum' / 'in Lakhs' returning LPA/numeric defaults instead of full INR.
2. CTC / Salary questions with '(Cost to Company)' correctly identified as salary rather than company name.
3. Ex-Infosys / Ex-employee questions asking to mention employee ID or write NA returning 'NA'.
4. Ex-Freshworks employment check returning 'No'.
5. Input-type-aware defaults for the newly added patterns.
"""

import pytest
from src.patterns.pattern_loader import load_patterns, validate_patterns
from src.patterns.pattern_matcher import PatternMatcher
from src.sentinel.agent import SentinelAgent
from src.sentinel.question_classifier import QuestionClassifier
from src.sentinel.question_fingerprint import FingerprintMatcher


class DummyAgent(SentinelAgent):
    """Test agent instance with loaded patterns."""
    def __init__(self, platform='naukri'):
        self._current_platform = platform
        patterns = load_patterns('config/qa_patterns.json')
        self._pattern_matcher = PatternMatcher(patterns)
        self._fingerprint_matcher = FingerprintMatcher()
        self._question_classifier = QuestionClassifier()
        self._learned_patterns = {}
        self._self_healing = None


class TestQACSVAuditFixesSept22:
    """Test suite verifying all CSV audit fixes."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.patterns = load_patterns('config/qa_patterns.json')
        self.matcher = PatternMatcher(self.patterns)
        self.agent_naukri = DummyAgent(platform='naukri')
        self.agent_linkedin = DummyAgent(platform='linkedin')

    def test_json_patterns_schema_valid(self):
        """Ensure config/qa_patterns.json remains 100% schema valid."""
        errors = validate_patterns(self.patterns)
        assert len(errors) == 0, f"Pattern validation errors: {errors}"

    def test_ctc_in_lacs_current(self):
        """Current CTC in Lacs per annum should return '23' or '23 LPA'."""
        questions = [
            "What is your current CTC in Lacs per annum?",
            "What is your current CTC in Lacs per annum",
            "What is your current CTC in Lakhs per annum?",
            "current ctc in lacs per annum",
            "What is your current CTC in Lacs?",
            "What is your current CTC in LPA?"
        ]
        for q in questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert ans in ['23', '23 LPA'], f"Failed for question '{q}': got {ans}"
            assert conf >= 0.90

    def test_ctc_in_lacs_expected(self):
        """Expected CTC in Lacs per annum should return '30' or '30 LPA'."""
        questions = [
            "What is your expected CTC in Lacs per annum?",
            "What is your expected CTC in Lacs per annum",
            "What is your expected CTC in Lakhs per annum?",
            "expected ctc in lacs per annum",
            "What is your expected CTC in Lacs?",
            "What is your expected CTC in LPA?"
        ]
        for q in questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert ans in ['30', '30 LPA'], f"Failed for question '{q}': got {ans}"
            assert conf >= 0.90

    def test_cost_to_company_not_confused_with_company_name(self):
        """Questions containing 'Cost to Company' must resolve to salary (23/30 LPA), not 'Everbridge'."""
        q_curr = "What’s your current CTC (Cost to Company)?"
        q_exp = "What’s your expected CTC (Cost to Company)?"
        
        ans_curr, conf_curr = self.agent_linkedin._fuzzy_match_question(q_curr)
        assert ans_curr in ['23', '23 LPA', '2300000'], f"Failed for '{q_curr}': got {ans_curr}"
        assert ans_curr != 'Everbridge'
        assert ans_curr != '4'

        ans_exp, conf_exp = self.agent_linkedin._fuzzy_match_question(q_exp)
        assert ans_exp in ['30', '30 LPA', '3000000'], f"Failed for '{q_exp}': got {ans_exp}"
        assert ans_exp != 'Everbridge'
        assert ans_exp != '4'

    def test_ex_infosys_employee_id_or_na(self):
        """Ex-Infosys with employee ID or write NA must return 'NA'."""
        questions = [
            "Are you ex-infosys employee ?if yes mention your infosys employee id if not, write NA",
            "Are you ex-infosys employee ?if yes mention your infosys employee id if not write na",
            "Have you previously worked in infosys?(If yes provide ex-infy id)",
            "Are you ex-infosys employee? if yes mention your infosys employee id if not, write NA"
        ]
        for q in questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert ans == 'NA', f"Failed for question '{q}': got {ans}"
            assert conf >= 0.95

    def test_ex_freshworks_employee(self):
        """Ex-Freshworks question must return 'No'."""
        questions = [
            "Have you been previously employed with Freshworks? \nRequired",
            "Have you been previously employed with Freshworks?",
            "Have you been previously employed with Freshworks? Required",
            "Previously employed with Freshworks"
        ]
        for q in questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert ans == 'No', f"Failed for question '{q}': got {ans}"
            assert conf >= 0.95

    def test_input_type_defaults_for_new_patterns(self):
        """Verify input_type_defaults for the newly registered pattern groups."""
        patterns_dict = self.patterns.get('patterns', {})
        
        # Current CTC in Lacs
        curr_pattern = patterns_dict.get('ctc_in_lacs_per_annum_current')
        assert curr_pattern is not None
        assert curr_pattern['input_type_defaults']['text'] == '23'
        assert curr_pattern['input_type_defaults']['number'] == '23'
        assert curr_pattern['input_type_defaults']['select'] == '23 LPA'
        assert curr_pattern['input_type_defaults']['text_inr'] == '2300000'

        # Expected CTC in Lacs
        exp_pattern = patterns_dict.get('ctc_in_lacs_per_annum_expected')
        assert exp_pattern is not None
        assert exp_pattern['input_type_defaults']['text'] == '30'
        assert exp_pattern['input_type_defaults']['number'] == '30'
        assert exp_pattern['input_type_defaults']['select'] == '30 LPA'
        assert exp_pattern['input_type_defaults']['text_inr'] == '3000000'

        # Ex-Infosys NA
        infy_pattern = patterns_dict.get('ex_infosys_employee_id_or_na')
        assert infy_pattern is not None
        assert infy_pattern['input_type_defaults']['text'] == 'NA'
        assert infy_pattern['input_type_defaults']['radio'] == 'No'
        assert infy_pattern['input_type_defaults']['select'] == 'No'
