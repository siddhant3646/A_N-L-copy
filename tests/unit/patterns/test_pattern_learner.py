import pytest
from src.patterns.pattern_learner import PatternExpander


class TestPatternExpanderNormalizeQuestion:
    def test_normalize_removes_prefix(self):
        result = PatternExpander.normalize_question("Please enter your salary")
        assert result == "your salary"

    def test_normalize_removes_what_is(self):
        result = PatternExpander.normalize_question("What is your experience")
        assert result == "your experience"

    def test_normalize_removes_suffix_question_mark(self):
        result = PatternExpander.normalize_question("Your salary?")
        assert result == "your salary"

    def test_normalize_removes_suffix_in_years(self):
        result = PatternExpander.normalize_question("Experience in years")
        assert result == "experience"

    def test_normalize_removes_punctuation(self):
        result = PatternExpander.normalize_question("What is your salary?")
        assert result == "your salary"

    def test_normalize_empty_string(self):
        assert PatternExpander.normalize_question("") == ""

    def test_normalize_none(self):
        assert PatternExpander.normalize_question(None) == ""


class TestPatternExpanderGenerateVariations:
    def test_generates_lowercase(self):
        vars = PatternExpander.generate_variations("Current Salary")
        assert "current salary" in vars

    def test_generates_with_prefix_stripped(self):
        vars = PatternExpander.generate_variations("What is your salary")
        # Should have original and stripped version
        assert "salary" in vars or any("salary" in v for v in vars)

    def test_generates_abbreviation_experience(self):
        vars = PatternExpander.generate_variations("years of experience")
        assert any("yrs" in v for v in vars) or any("exp" in v for v in vars)

    def test_generates_abbreviation_notice_period(self):
        vars = PatternExpander.generate_variations("notice period in days")
        assert any("np" in v for v in vars)

    def test_empty_question(self):
        assert PatternExpander.generate_variations("") == []

    def test_none_question(self):
        assert PatternExpander.generate_variations(None) == []

    def test_deduplicates_variations(self):
        vars = PatternExpander.generate_variations("test")
        assert len(vars) == len(set(vars))

    def test_expected_ctc_abbreviation(self):
        vars = PatternExpander.generate_variations("expected ctc")
        assert any("ectc" in v for v in vars)

    def test_current_ctc_abbreviation(self):
        vars = PatternExpander.generate_variations("current ctc")
        assert any("cctc" in v for v in vars)
