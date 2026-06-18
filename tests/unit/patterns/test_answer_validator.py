import pytest
from src.patterns.answer_validator import AnswerValidator, _fix_answer, _normalize_answer


class TestAnswerValidatorValidate:
    def test_salary_valid_with_number(self):
        assert AnswerValidator.validate('23 LPA', 'salary', '')[0]

    def test_salary_valid_numeric_only(self):
        assert AnswerValidator.validate('23', 'salary', '')[0]

    def test_salary_invalid_empty(self):
        assert not AnswerValidator.validate('', 'salary', '')[0]

    def test_salary_invalid_no_number(self):
        assert not AnswerValidator.validate('Yes', 'salary', '')[0]

    def test_salary_invalid_whitespace_only(self):
        assert not AnswerValidator.validate('   ', 'salary', '')[0]

    def test_experience_valid_with_years(self):
        assert AnswerValidator.validate('4 Years', 'experience', '')[0]

    def test_experience_valid_numeric(self):
        assert AnswerValidator.validate('4', 'experience', '')[0]

    def test_experience_invalid_empty(self):
        assert not AnswerValidator.validate('', 'experience', '')[0]

    def test_experience_invalid_no_number(self):
        assert not AnswerValidator.validate('None', 'experience', '')[0]

    def test_notice_period_valid(self):
        assert AnswerValidator.validate('15 days', 'notice_period', '')[0]

    def test_notice_period_empty(self):
        assert not AnswerValidator.validate('', 'notice_period', '')[0]

    def test_location_valid_city(self):
        assert AnswerValidator.validate('Noida', 'location', '')[0]

    def test_location_valid_full_address(self):
        assert AnswerValidator.validate('Noida, Uttar Pradesh', 'location', '')[0]

    def test_location_invalid_pure_number(self):
        assert not AnswerValidator.validate('42', 'location', '')[0]

    def test_location_invalid_empty(self):
        assert not AnswerValidator.validate('', 'location', '')[0]

    def test_yes_no_valid_yes(self):
        assert AnswerValidator.validate('Yes', 'yes_no', '')[0]

    def test_yes_no_valid_no(self):
        assert AnswerValidator.validate('No', 'yes_no', '')[0]

    def test_yes_no_valid_other(self):
        assert AnswerValidator.validate('Maybe', 'yes_no', '')[0]

    def test_yes_no_invalid_empty(self):
        assert not AnswerValidator.validate('', 'yes_no', '')[0]

    def test_date_valid(self):
        assert AnswerValidator.validate('2024-01-01', 'date', '')[0]

    def test_date_invalid_empty(self):
        assert not AnswerValidator.validate('', 'date', '')[0]

    def test_numeric_valid_number(self):
        assert AnswerValidator.validate('7', 'numeric', '')[0]

    def test_numeric_valid_decimal(self):
        assert AnswerValidator.validate('3.5', 'numeric', '')[0]

    def test_numeric_valid_number_in_text(self):
        assert AnswerValidator.validate('4 years', 'numeric', '')[0]

    def test_numeric_invalid_empty(self):
        assert not AnswerValidator.validate('', 'numeric', '')[0]

    def test_numeric_invalid_no_number(self):
        assert not AnswerValidator.validate('Yes', 'numeric', '')[0]

    def test_skills_valid(self):
        assert AnswerValidator.validate('Python, Java', 'skills', '')[0]

    def test_skills_invalid_empty(self):
        assert not AnswerValidator.validate('', 'skills', '')[0]

    def test_unknown_category_always_valid(self):
        assert AnswerValidator.validate('anything', 'unknown_category', '')[0]

    def test_unknown_category_empty(self):
        assert AnswerValidator.validate('', 'unknown_category', '')[0]


class TestAnswerValidatorFix:
    def test_fix_salary_extracts_number(self):
        assert AnswerValidator.fix('23 LPA', 'salary', '') == '23'

    def test_fix_salary_extracts_float(self):
        assert AnswerValidator.fix('13.5 LPA', 'salary', '') == '13.5'

    def test_fix_salary_no_number_returns_original(self):
        assert AnswerValidator.fix('Not specified', 'salary', '') == 'Not specified'

    def test_fix_experience_formats_with_years(self):
        assert AnswerValidator.fix('4', 'experience', '') == '4 Years'

    def test_fix_experience_with_years_suffix(self):
        assert AnswerValidator.fix('4 Years', 'experience', '') == '4 Years'

    def test_fix_experience_months(self):
        result = AnswerValidator.fix('4', 'experience', 'How many months?')
        assert result == '48'

    def test_fix_experience_no_number_returns_original(self):
        assert AnswerValidator.fix('N/A', 'experience', '') == 'N/A'

    def test_fix_numeric_extracts_number(self):
        assert AnswerValidator.fix('7 days', 'numeric', '') == '7'

    def test_fix_numeric_no_number_returns_original(self):
        assert AnswerValidator.fix('Unknown', 'numeric', '') == 'Unknown'

    def test_fix_location_pure_number_returns_original(self):
        assert AnswerValidator.fix('42', 'location', '') == '42'

    def test_fix_location_valid_returns_normalized(self):
        result = AnswerValidator.fix('  Noida  ', 'location', '')
        assert result == '  Noida  '

    def test_fix_valid_answer_normalized(self):
        result = AnswerValidator.fix('23', 'salary', '')
        assert result == '23'


class TestNormalizeAnswer:
    def test_normalize_salary_extracts_number(self):
        result = _normalize_answer('23 LPA', 'salary', '', '')
        assert result == '23'

    def test_normalize_salary_no_match_returns_original(self):
        result = _normalize_answer('Not specified', 'salary', '', '')
        assert result == 'Not specified'

    def test_normalize_experience_with_years(self):
        result = _normalize_answer('4', 'experience', '', '')
        assert result == '4 Years'

    def test_normalize_experience_months_context(self):
        result = _normalize_answer('4', 'experience', 'How many months?', '')
        assert result == '48'

    def test_normalize_experience_no_number(self):
        result = _normalize_answer('Yes', 'experience', '', '')
        assert result == 'Yes'

    def test_normalize_numeric_extracts_number(self):
        result = _normalize_answer('7 days', 'numeric', '', '')
        assert result == '7'

    def test_normalize_other_category_returns_original(self):
        result = _normalize_answer('Some answer', 'location', '', '')
        assert result == 'Some answer'

    def test_normalize_numeric_no_match_returns_original(self):
        result = _normalize_answer('None', 'numeric', '', '')
        assert result == 'None'


class TestFixAnswer:
    def test_fix_salary_extracts_number(self):
        result = _fix_answer('23 LPA', 'salary', '', '')
        assert result == '23'

    def test_fix_salary_no_number_returns_none(self):
        result = _fix_answer('No number', 'salary', '', '')
        assert result is None

    def test_fix_experience_with_years(self):
        result = _fix_answer('4', 'experience', '', '')
        assert result == '4 Years'

    def test_fix_experience_months(self):
        result = _fix_answer('4', 'experience', 'How many months?', '')
        assert result == '48'

    def test_fix_experience_no_number_returns_none(self):
        result = _fix_answer('Yes', 'experience', '', '')
        assert result is None

    def test_fix_location_pure_number_returns_none(self):
        result = _fix_answer('42', 'location', '', '')
        assert result is None

    def test_fix_location_text_returns_none(self):
        result = _fix_answer('Noida', 'location', '', '')
        assert result is None

    def test_fix_numeric_extracts_number(self):
        result = _fix_answer('7 days', 'numeric', '', '')
        assert result == '7'

    def test_fix_numeric_no_number_returns_none(self):
        result = _fix_answer('Yes', 'numeric', '', '')
        assert result is None

    def test_fix_unknown_category_returns_none(self):
        result = _fix_answer('anything', 'unknown', '', '')
        assert result is None
