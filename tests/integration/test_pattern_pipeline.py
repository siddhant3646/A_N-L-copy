"""
Integration tests for the full pattern pipeline:
  PatternLoader -> PatternMatcher -> AnswerValidator
"""

import pytest
import json
import os
from src.patterns.pattern_loader import PatternLoader
from src.patterns.pattern_matcher import PatternMatcher, create_matcher
from src.patterns.answer_validator import AnswerValidator


def get_config_path():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'qa_patterns.json')
    return os.path.abspath(path)


class TestPatternPipeline:
    """Test the full pipeline from loading to matching."""

    def setup_method(self):
        config_path = get_config_path()
        if not os.path.exists(config_path):
            pytest.skip("qa_patterns.json not found")
        self.config_path = config_path

    def test_loader_loads_valid_json(self):
        loader = PatternLoader(self.config_path)
        patterns = loader.load()
        assert 'patterns' in patterns
        assert len(patterns['patterns']) > 300

    def test_matcher_created_from_json(self):
        matcher = create_matcher(self.config_path)
        assert isinstance(matcher, PatternMatcher)

    def test_salary_question_matches(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("What is your current salary?")
        assert answer is not None
        assert confidence > 0.5

    def test_experience_question_matches(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("How many years of experience do you have?")
        assert answer is not None
        assert confidence > 0.5

    def test_notice_period_question_matches(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("What is your notice period?")
        assert answer is not None
        assert confidence > 0.5

    def test_location_question_matches(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("What is your current location?")
        assert answer is not None
        assert confidence > 0.5

    def test_answer_validator_on_matched_salary(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("What is your current salary?")
        if answer:
            is_valid, err = AnswerValidator.validate(answer, 'salary', 'What is your current salary?')
            assert is_valid, f"Salary answer '{answer}' failed validation: {err}"

    def test_answer_validator_on_matched_experience(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("How many years of experience?")
        if answer:
            is_valid, err = AnswerValidator.validate(answer, 'experience', 'How many years of experience?')
            assert is_valid, f"Experience answer '{answer}' failed validation: {err}"

    def test_answer_validator_on_matched_location(self):
        matcher = create_matcher(self.config_path)
        answer, confidence = matcher.fuzzy_match("What is your current location?")
        if answer:
            is_valid, err = AnswerValidator.validate(answer, 'location', 'What is your current location?')
            assert is_valid, f"Location answer '{answer}' failed validation: {err}"

    def test_critical_categories_validate(self):
        """Verify core numeric categories have valid defaults."""
        matcher = create_matcher(self.config_path)
        check_patterns = {
            'current_salary': 'salary',
            'expected_salary': 'salary',
            'experience': 'experience',
            'notice_period': 'notice_period',
            'location_current': 'location',
            'immediate_joiner': 'yes_no',
        }
        for pid, expected_cat in check_patterns.items():
            pdata = matcher.patterns.get('patterns', {}).get(pid)
            if pdata:
                default = pdata.get('default', '')
                assert default, f"Pattern '{pid}' has empty default"
                is_valid, err = AnswerValidator.validate(default, expected_cat, '')
                assert is_valid, f"Pattern '{pid}' default '{default}' failed {expected_cat} validation: {err}"

    def test_patterns_have_non_empty_patterns(self):
        matcher = create_matcher(self.config_path)
        empty = [pid for pid, pdata in matcher.patterns.get('patterns', {}).items()
                 if not pdata.get('patterns', [])]
        assert len(empty) == 0, f"Patterns with no pattern strings: {empty[:10]}"

    def test_top_level_structure(self):
        with open(self.config_path) as f:
            data = json.load(f)
        assert 'patterns' in data
        assert isinstance(data['patterns'], dict)
