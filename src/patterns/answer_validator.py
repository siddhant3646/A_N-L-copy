import re
from typing import Optional, Tuple


class AnswerValidator:
    VALIDATORS = {
        'salary': lambda a, q: _validate_salary(a, q),
        'experience': lambda a, q: _validate_experience(a, q),
        'notice_period': lambda a, q: _validate_notice_period(a, q),
        'location': lambda a, q: _validate_location(a, q),
        'yes_no': lambda a, q: _validate_yes_no(a, q),
        'date': lambda a, q: _validate_date(a, q),
        'numeric': lambda a, q: _validate_numeric(a, q),
        'skills': lambda a, q: _validate_skills(a, q),
    }

    @classmethod
    def validate(cls, answer: str, category: str, question: str = "") -> Tuple[bool, Optional[str]]:
        validator = cls.VALIDATORS.get(category)
        if not validator:
            return True, None
        return validator(answer, question)

    @classmethod
    def fix(cls, answer: str, category: str, question: str = "", platform: str = "") -> str:
        is_valid, error = cls.validate(answer, category, question)
        if not is_valid:
            fixed = _fix_answer(answer, category, question, platform)
            return fixed if fixed is not None else answer
        return _normalize_answer(answer, category, question, platform) or answer


def _validate_salary(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty salary answer"
    has_number = bool(re.search(r'\d+\.?\d*', answer))
    if not has_number:
        return False, f"Salary answer has no number: {answer}"
    return True, None


def _validate_experience(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty experience answer"
    has_number = bool(re.search(r'\d+\.?\d*', answer))
    if not has_number:
        return False, f"Experience answer has no number: {answer}"
    return True, None


def _validate_notice_period(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty notice period answer"
    if ('in months' in question.lower() or '(in months)' in question.lower()) and answer.strip().isdigit() and int(answer.strip()) > 11:
        return False, f"Notice period in months cannot exceed 12 months: {answer}"
    return True, None


def _validate_location(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty location answer"
    if answer.strip().isdigit():
        return False, f"Location answer is just a number: {answer}"
    return True, None


def _validate_yes_no(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty yes/no answer"
    stripped = answer.strip().lower()
    if stripped.startswith('yes') or stripped.startswith('no'):
        return True, None
    return True, None


def _validate_date(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty date answer"
    return True, None


def _validate_numeric(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty numeric answer"
    has_number = bool(re.search(r'\d+\.?\d*', answer))
    if not has_number:
        return False, f"Numeric answer has no number: {answer}"
    if ('1-5' in question or '1–5' in question or 'scale of 1-5' in question.lower() or 'scale of 1–5' in question.lower()):
        match = re.search(r'(\d+)', answer)
        if match and int(match.group(1)) > 5:
            return False, f"Rating scale exceeds maximum 5: {answer}"
    return True, None


def _validate_skills(answer: str, question: str) -> Tuple[bool, Optional[str]]:
    if not answer or not answer.strip():
        return False, "Empty skills answer"
    return True, None


def _normalize_answer(answer: str, category: str, question: str, platform: str) -> Optional[str]:
    if category == 'salary':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            return match.group(1)
    elif category == 'experience':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            val = match.group(1)
            if 'month' in question.lower():
                return str(int(float(val) * 12))
            return f"{val} Years"
    elif category == 'numeric':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            val = match.group(1)
            if ('1-5' in question or '1–5' in question) and int(float(val)) > 5:
                return '5'
            return val
    elif category == 'notice_period':
        if 'in month' in question.lower() or '(in months)' in question.lower():
            return '0.5'
        if answer.strip().lower() in ('yes', 'no', 'true', 'false', 'serving notice period'):
            return answer
        if platform == 'linkedin':
            match = re.search(r'(\d+)', answer)
            if match:
                return match.group(1)
            return '15'
        else:
            match = re.search(r'(\d+)', answer)
            if match:
                return f"{match.group(1)} days"
            return '15 days'
    return answer


def _fix_answer(answer: str, category: str, question: str, platform: str) -> Optional[str]:
    if category == 'salary':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            return match.group(1)
    elif category == 'experience':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            val = match.group(1)
            if 'month' in question.lower():
                return str(int(float(val) * 12))
            return f"{val} Years"
    elif category == 'location':
        if answer.strip().isdigit():
            return None
    elif category == 'numeric':
        match = re.search(r'(\d+\.?\d*)', answer)
        if match:
            return match.group(1)
    elif category == 'notice_period':
        if answer.strip().lower() in ('yes', 'no', 'true', 'false', 'serving notice period'):
            return None
        if platform == 'linkedin':
            match = re.search(r'(\d+)', answer)
            if match:
                return match.group(1)
            return '15'
        else:
            match = re.search(r'(\d+)', answer)
            if match:
                return f"{match.group(1)} days"
            return '15 days'
    return None