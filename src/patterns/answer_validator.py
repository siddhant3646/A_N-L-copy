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
            return match.group(1)
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
    return None