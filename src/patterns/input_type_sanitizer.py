"""
Input-type aware answer sanitisation and derivation.

The QA corpus contains ~60k patterns.  Historically many patterns stored a
canonical answer plus a mechanically-derived ``input_type_defaults`` map.  The
mechanical derivation produced values such as:

* ``"number": "."`` for a text answer
* ``"number": "3646."`` for an email address
* ``"number": "710"`` for the rating ``"7/10"``
* 32-character sentence prefixes for radio options
* ``"Yes"`` on a checkbox whose canonical answer is ``"No"``

This module provides one deterministic place to turn a canonical answer and
question intent into a value that is safe for a given HTML control, and to
sanitise values at runtime even when the JSON on disk is stale.

The derivation rules are intentionally conservative: they prefer explicit
numbers/booleans already present in the canonical answer, then fall back to the
candidate profile constants (4.2 years, 23/30 LPA, 15 days notice, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Candidate profile constants (single source of truth for derived fallbacks)
# ---------------------------------------------------------------------------

CURRENT_CTC_LPA = 23.0
EXPECTED_CTC_LPA = 30.0
CURRENT_CTC_INR = 2_300_000
EXPECTED_CTC_INR = 3_000_000
CURRENT_MONTHLY_INR = 191_667
EXPECTED_MONTHLY_INR = 250_000
NOTICE_PERIOD_DAYS = 15
NOTICE_PERIOD_MONTHS = 0.5
TOTAL_EXPERIENCE_YEARS = 4.2
TOTAL_EXPERIENCE_MONTHS = 50
CANDIDATE_PHONE = "7905828880"
CANDIDATE_PINCODE = "560001"
CANDIDATE_CITY = "Bengaluru"
CANDIDATE_STATE = "Karnataka"
CANDIDATE_COUNTRY = "India"
CANDIDATE_NATIONALITY = "Indian"
CANDIDATE_DOB = "17/12/2000"
GRADUATION_YEAR = 2022
CGPA = 8.51

CORE_INPUT_TYPES = ("text", "textarea", "radio", "select", "checkbox", "number")

# Some callers use aliases (agent.py uses "button" for LinkedIn buttons).
INPUT_TYPE_ALIASES = {
    "button": "radio",
    "numeric": "number",
    "select-ctc": "text",
}

NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
DYNAMIC_MARKER_RE = re.compile(r"__DYNAMIC_[A-Z_]+__")
# Numeric date markers resolve to DDMMYYYY so they can safely be typed into a
# number input while still moving with the calendar.
LWD_NUMERIC_MARKER = "__DYNAMIC_LWD_DDMMYYYY__"
TODAY_NUMERIC_MARKER = "__DYNAMIC_TODAY_DDMMYYYY__"
# ISO markers are required for HTML <input type="date">.
LWD_ISO_MARKER = "__DYNAMIC_LWD_ISO__"
TODAY_ISO_MARKER = "__DYNAMIC_TODAY_ISO__"
DATE_VALUE_RES = (
    re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}$"),
    re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$"),
)

YES_WORDS = ("yes", "y", "true", "authorized", "authorised", "agree", "confirmed")
NO_WORDS = ("no", "n", "false", "not applicable", "not required", "none", "never", "decline")

RATING_WORDS = {
    "beginner": 2,
    "novice": 2,
    "basic": 2,
    "intermediate": 3,
    "medium": 3,
    "moderate": 3,
    "advanced": 4,
    "expert": 5,
    "fluent": 5,
    "professional": 4,
    "native": 5,
}

OPEN_ENDED_RE = re.compile(
    r"\b(describe|explain|why|tell us|tell me|walk (?:us|me) through|give (?:an |a )?example|"
    r"share (?:an |a )?example|what would you|what do you|what are your|where do you see|"
    r"how do you|how would you|how does|how did|why do you|why are you|"
    r"your experience|background|summary of|strengths|weaknesses|achievements|approach|"
    r"motivat|aspiration|career goals|career plan|5 year plan|five year plan|"
    r"cover letter|elevator pitch|day to day|day-to-day)\b",
    re.IGNORECASE,
)
WH_QUESTION_RE = re.compile(
    r"^(what|where|when|why|how|who|which|describe|explain|tell|share|walk|give|list|mention|elaborate)\b",
    re.IGNORECASE,
)
OPEN_AUXILIARY_RE = re.compile(
    r"^(?:can|could|would|will|do|does|did|have|has|are|is)\s+(?:you|he|she|they|we)?\s*"
    r"(?:please\s+)?(?:explain|describe|share|give|gave|provide|tell|walk|list|elaborate|mention|brief)\b",
    re.IGNORECASE,
)

YES_NO_START_RE = re.compile(
    r"^(do|does|did|have|has|are|is|was|were|can|could|will|would|should|may|am)\b",
    re.IGNORECASE,
)
YES_NO_PHRASES = (
    "willing to",
    "comfortable with",
    "comfortable working",
    "open to",
    "ok with",
    "okay with",
    "interested in",
    "authorized to",
    "authorised to",
    "eligible to",
    "consent to",
    "agree to",
    "confirm that",
    "currently serving",
    "available for",
    "available to",
    "able to",
    "require sponsorship",
    "need sponsorship",
    "require visa",
    "need visa",
    "have you",
    "do you",
)

SALARY_RE = re.compile(
    r"\b(salary|ctc|compensation|package|remuneration|pay|payroll|take[- ]home|in[- ]hand)\b",
    re.IGNORECASE,
)
NOTICE_RE = re.compile(
    r"\b(notice|lwd|last working|serving|joining|join us|joining date|start date|"
    r"earliest start|available to start|how soon|how quickly)\b",
    re.IGNORECASE,
)
LOCATION_RE = re.compile(
    r"\b(location|city|country|state|province|reside|residing|relocat|based in|currently in|"
    r"where do you live|where are you located|pincode|pin code|postal|zip|address)\b",
    re.IGNORECASE,
)
STATE_RE = re.compile(r"\b(state|province)\b", re.IGNORECASE)
COUNTRY_RE = re.compile(r"\b(country|nation)\b", re.IGNORECASE)
NATIONALITY_RE = re.compile(r"\b(nationality|citizen|citizenship)\b", re.IGNORECASE)
ADDRESS_RE = re.compile(r"\b(address|street|residence|residing at|house no|flat no)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
PASSPORT_RE = re.compile(r"\b[A-PR-WY][1-9]\d{6}\b")
YEARS_RE = re.compile(
    r"\b(how many years|how many yrs|years of experience|years experience|yrs of experience|"
    r"total experience|total exp|total years|relevant years|experience in years|yoe|"
    r"how long have you|how much experience|number of years|years of exp|working experience|"
    r"professional experience|work experience)\b",
    re.IGNORECASE,
)
RATING_RE = re.compile(
    r"\b(rate|rating|scale of|out of (?:5|10)|1\s*[-–]\s*(?:5|10)|1\s*to\s*(?:5|10)|"
    r"proficiency level|skill level|expertise level|how would you rate|rate yourself|"
    r"rate your)\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(date|dob|date of birth|last working day|last working date|lwd|start date|"
    r"joining date|date of joining|today|current date)\b",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"\b(phone|mobile|contact number|contact no|whatsapp|telephone|tel)\b", re.IGNORECASE)
# Broader matcher used only for PII classification and leak guards.  Reference
# and emergency contacts are stored in ``personal_info`` patterns too, but they
# are not "phone" questions for intent/derivation purposes.
PII_PHONE_RE = re.compile(
    r"\b(phone|mobile|contact number|contact no|whatsapp|telephone|tel|"
    r"(?:alternate|secondary|other|reference|referee|emergency)\s+"
    r"(?:number|phone|mobile|contact|contact number|phone number))\b",
    re.IGNORECASE,
)
AADHAAR_RE = re.compile(r"(?<!\d)[2-9]\d{11}(?!\d)")
AADHAAR_QUESTION_RE = re.compile(r"\b(aadhaar|aadhar|uidai)\b", re.IGNORECASE)
PINCODE_RE = re.compile(r"\b(pin ?code|postal|zip ?code|zip)\b", re.IGNORECASE)
EDU_SCORE_RE = re.compile(r"\b(cgpa|gpa|percentage|percent|marks|aggregate|score|grade)\b", re.IGNORECASE)
TEAM_SIZE_RE = re.compile(r"\b(team size|team strength|how many people|reportees|direct reports)\b", re.IGNORECASE)
PROJECT_COUNT_RE = re.compile(r"\b(how many projects|project count|number of projects)\b", re.IGNORECASE)
AGE_RE = re.compile(r"\b(age|how old)\b", re.IGNORECASE)
VERSION_RE = re.compile(r"\b(version|which version|what version)\b", re.IGNORECASE)
NUMERIC_HINT_RE = re.compile(
    r"\b(how many|number of|count|months?|percent|percentage|age|size|version|"
    r"year|years?|yrs?|score|marks|cgpa|gpa|rating|rate|salary|ctc|notice|days?)\b",
    re.IGNORECASE,
)
LIST_RE = re.compile(
    r"\b(which|list|technologies|technology|tools?|skills?|frameworks?|libraries|"
    r"databases?|services|stack|platforms?|areas?|domains?|industries)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuestionIntent:
    question: str
    category: str
    default: str
    is_yes_no: bool
    is_years: bool
    is_rating: bool
    is_salary: bool
    is_expected_salary: bool
    is_notice: bool
    is_lwd: bool
    is_start_date: bool
    is_date: bool
    is_dob: bool
    is_location: bool
    is_relocation: bool
    is_state: bool
    is_country: bool
    is_nationality: bool
    is_address: bool
    is_phone: bool
    is_pincode: bool
    is_education_score: bool
    is_team_size: bool
    is_project_count: bool
    is_age: bool
    is_graduation_year: bool
    is_open_ended: bool
    is_list: bool
    is_version: bool
    is_not_applicable: bool
    affirmative: bool
    negative: bool


def normalize_input_type(input_type: Optional[str]) -> Optional[str]:
    if not input_type:
        return None
    normalized = str(input_type).strip().lower()
    return INPUT_TYPE_ALIASES.get(normalized, normalized)


def _first_question(data: Dict[str, Any]) -> str:
    patterns = data.get("patterns") or []
    if isinstance(patterns, list) and patterns:
        return str(patterns[0])
    return ""


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


VARIABLE_PAY_MARKERS = (
    "variable pay",
    "variable compensation",
    "bonus",
    "rsu",
    "esop",
    "equity",
    "unvested",
)


def _is_variable_pay_question(question: str, default: str = "") -> bool:
    """True only when the question asks for the variable component itself.

    CTC questions often describe the package as "ctc includes fix salary,
    variable pay, pf...".  Those still ask for the total CTC and must not be
    collapsed to ``0`` just because the word "variable pay" appears in the
    question text.
    """
    text = f"{question or ''} {default or ''}".lower()
    if not _contains_any(text, VARIABLE_PAY_MARKERS):
        return False
    if re.search(
        r"\b(ctc|cost to company|total compensation|total salary|annual salary|gross salary|package)\b",
        text,
    ):
        return False
    return True


def _leading_answer(text: str) -> Optional[str]:
    """Return 'yes'/'no' when the text clearly starts with a boolean answer."""
    value = (text or "").strip().lower()
    if not value:
        return None
    first = re.split(r"[\s,;:.!?]", value, maxsplit=1)[0]
    if first in ("yes", "y", "true") or value.startswith(("yes ", "yes,", "yes.", "yes:", "yes;")):
        return "yes"
    if first in ("no", "n", "false") or value.startswith(("no ", "no,", "no.", "no:", "no;")):
        return "no"
    if value.startswith(("not applicable", "not required", "none", "never", "decline")):
        return "no"
    return None


def _explicit_boolean(text: str) -> Optional[str]:
    """Return 'yes'/'no' only when the text starts with an explicit boolean.

    ``None``/``Not applicable`` are useful negative answers for validation, but
    they do not by themselves prove that the question is a yes/no question.
    """
    value = (text or "").strip().lower()
    if not value:
        return None
    first = re.split(r"[\s,;:.!?]", value, maxsplit=1)[0]
    if first in ("yes", "y", "true") or value.startswith(("yes ", "yes,", "yes.", "yes:", "yes;")):
        return "yes"
    if first in ("no", "n", "false") or value.startswith(("no ", "no,", "no.", "no:", "no;")):
        return "no"
    return None


def _normalize_boolean_text(text: str) -> str:
    """Lowercase and normalise typographic apostrophes for boolean matching."""
    return (
        str(text or "")
        .strip()
        .lower()
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u02bc", "'")
        .replace("`", "'")
    )


NEGATION_PREFIXES = (
    "not ",
    "none",
    "never",
    "n/a",
    "na ",
    "decline",
    "i have not",
    "i have never",
    "i have no",
    "i do not",
    "i don't",
    "i am not",
    "i haven't",
    "i did not",
    "i didn't",
    "no experience",
    "not experienced",
    "i lack",
)


def _is_affirmative(text: str) -> bool:
    lower = _normalize_boolean_text(text)
    if _leading_answer(lower) == "yes":
        return True
    # Negations such as "I don't have a disability" start with "I do"; they are
    # not affirmative answers and must not be collapsed to "Yes".
    if lower.startswith(NEGATION_PREFIXES):
        return False
    return lower.startswith(
        (
            "i have",
            "i am",
            "i do",
            "i hold",
            "i bring",
            "i led",
            "i lead",
            "i built",
            "i designed",
            "i drove",
            "i managed",
            "i implemented",
            "i architected",
            "i migrated",
            "i created",
            "i developed",
            "i optimized",
            "i optimised",
            "i improved",
            "i reduced",
            "i owned",
            "i work",
            "i worked",
            "successfully",
            "authorized",
            "authorised",
            "available",
            "comfortable",
            "willing",
            "expert",
            "advanced",
            "fluent",
            "proficient",
            "experienced",
        )
    )


def _is_negative(text: str) -> bool:
    lower = _normalize_boolean_text(text)
    if _leading_answer(lower) == "no":
        return True
    return lower.startswith(NEGATION_PREFIXES)


def _as_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not NUMERIC_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _numbers_in(text: str) -> List[float]:
    """Extract plausible numbers, ignoring emails, URLs, dates and times."""
    cleaned = str(text or "")
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\S+@\S+", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}\s*(?:am|pm)\b", " ", cleaned, flags=re.IGNORECASE)
    numbers: List[float] = []
    for match in re.finditer(r"\d+(?:\.\d+)?", cleaned):
        try:
            numbers.append(float(match.group(0)))
        except ValueError:
            continue
    return numbers


def _salary_numbers(text: str) -> List[float]:
    """Numbers that represent money, excluding percentages such as "100% fixed"."""
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*%", " ", str(text or ""))
    return _numbers_in(cleaned)


def _first_number(text: str, *, allow_large: bool = False, allow_year: bool = False) -> Optional[float]:
    for number in _numbers_in(text):
        if not allow_year and 1900 <= number <= 2100:
            continue
        if not allow_large and number > 100_000:
            continue
        return number
    return None


def _range_midpoint(text: str) -> Optional[float]:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)",
        str(text or ""),
        re.IGNORECASE,
    )
    if not match:
        return None
    low = float(match.group(1))
    high = float(match.group(2))
    midpoint = (low + high) / 2.0
    if low.is_integer() and high.is_integer():
        return float(int(midpoint))
    return midpoint


def _format_number(value: float) -> str:
    """Format without scientific notation (2.3e+06 is not a form value)."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def _rating_scale(question: str, default: str) -> int:
    lower = f"{question} {default}".lower()
    if re.search(r"(?:out of|scale of|1\s*[-–]\s*|1\s*to\s*)5\b", lower) or "1-5" in lower or "1–5" in lower:
        return 5
    if re.search(r"(?:/|out of|scale of|1\s*[-–]\s*|1\s*to\s*)10\b", lower) or "1-10" in lower or "1–10" in lower:
        return 10
    # If the default is a numeric value 6-10, infer a 10-point scale
    number = _first_number(default)
    if number is not None and 6 <= number <= 10:
        return 10
    return 5


def _rating_number(question: str, default: str) -> float:
    lower = default.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+)", lower)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:out of)\s*(\d+)", lower)
    if match:
        return float(match.group(1))
    number = _first_number(default)
    scale = _rating_scale(question, default)
    if number is not None and 0 <= number <= scale:
        return number
    for word, value in RATING_WORDS.items():
        if word in lower:
            if scale == 5:
                return float(value)
            return float(min(scale, value + 3))
    return 5.0


def _salary_number(question: str, default: str) -> float:
    lower = f"{question} {default}".lower()
    if _is_variable_pay_question(question, default):
        return 0.0

    expected = bool(re.search(r"\b(expected|expectation|ectc|ex[- ]?ctc|desired|asking|target)\b", lower))
    if "offer in hand" in lower or "offered" in lower:
        expected = True
    lpa = EXPECTED_CTC_LPA if expected else CURRENT_CTC_LPA
    inr = EXPECTED_CTC_INR if expected else CURRENT_CTC_INR
    monthly = EXPECTED_MONTHLY_INR if expected else CURRENT_MONTHLY_INR

    numbers = _salary_numbers(default)
    if numbers:
        large = [value for value in numbers if value >= 100_000]
        if large:
            inr = large[0]
        small = [value for value in numbers if 0 < value <= 100]
        if small:
            lpa = small[0]

    midpoint = _range_midpoint(default)
    if midpoint is not None:
        if "lpa" in lower or "lakh" in lower or "lac" in lower:
            lpa = midpoint
        elif any(value >= 100_000 for value in numbers):
            inr = midpoint

    question_lower = question.lower()
    if "percentage" in question_lower or "%" in question_lower or "hike" in question_lower:
        if "variable" in question_lower or "bonus" in question_lower:
            return 0.0
        return 30.0
    if "monthly" in lower or "per month" in lower or "take home" in lower or "take-home" in lower or "in-hand" in lower:
        if numbers:
            for value in numbers:
                if 10_000 <= value <= 1_000_000:
                    return value
        return monthly
    if "inr" in lower or "annual" in lower or "per annum" in lower or "gross" in lower or "amount" in lower:
        return inr
    if "lpa" in lower or "lakh" in lower or "lac" in lower:
        return lpa
    if any(value >= 100_000 for value in numbers):
        return inr
    if numbers:
        for value in numbers:
            if 10_000 <= value <= 1_000_000:
                return value
    return lpa


def _years_number(question: str, default: str) -> float:
    number = _first_number(default)
    if number is not None and 0 <= number <= 50:
        return number
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:years?|yrs?)", default, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return TOTAL_EXPERIENCE_YEARS


def _notice_number(question: str, default: str) -> float:
    lower = f"{question} {default}".lower()
    if "month" in lower and not re.search(r"\bdays?\b", lower):
        number = _first_number(default)
        if number is not None and 0 <= number <= 12:
            return number
        return NOTICE_PERIOD_MONTHS
    number = _first_number(default)
    if number is not None and 0 <= number <= 365:
        return number
    return float(NOTICE_PERIOD_DAYS)


def _phone_digits(text: str) -> str:
    value = str(text or "")
    # Combined email+phone answers otherwise concatenate the email's digits.
    if "@" in value:
        match = re.search(r"(?<!\d)(?:\+?91[- ]?)?([6-9]\d{9})(?!\d)", value)
        if match:
            return match.group(1)
        return CANDIDATE_PHONE
    digits = re.sub(r"\D", "", value)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if 7 <= len(digits) <= 15:
        return digits
    return CANDIDATE_PHONE


def _looks_like_phone_number(text: str) -> bool:
    """Strict phone shape: 10-15 digits with an optional +91-style prefix.

    Unlike ``_has_phone_digits`` this rejects 7-8 digit runs such as the
    digit soup inside a DD/MM/YYYY date, so date or salary answers can never
    be coerced into the candidate's number.
    """
    digits = re.sub(r"\D", "", str(text or ""))
    if digits.startswith("91") and len(digits) in (12, 13):
        digits = digits[2:]
    return 10 <= len(digits) <= 15


def _has_phone_digits(text: str) -> bool:
    """True when the text already carries a phone-length number of its own.

    ``_phone_digits`` intentionally falls back to the candidate's real number
    for genuine phone questions.  Derivation must not use that fallback when
    the canonical answer contains no number of its own (``Available upon
    request``, ``Yes, available for phone screening``), otherwise the
    candidate's PII leaks into unrelated controls.
    """
    digits = re.sub(r"\D", "", str(text or ""))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return 7 <= len(digits) <= 15


def detect_intent(question: str = "", category: str = "", default: str = "") -> QuestionIntent:
    data = {"patterns": [question] if question else [], "category": category, "default": default}
    return _detect_intent(question, category, default, data)


def _detect_intent(question: str, category: str, default: str, data: Dict[str, Any]) -> QuestionIntent:
    q = (question or _first_question(data)).lower().strip()
    category = (category or str(data.get("category", ""))).lower()
    default = str(default if default is not None else data.get("default", "")).strip()
    lower_default = default.lower()

    is_salary = category == "salary" or bool(SALARY_RE.search(q))
    is_notice = category == "notice_period" or bool(NOTICE_RE.search(q))
    is_years = bool(YEARS_RE.search(q)) or (category == "experience" and bool(re.search(r"\b(year|yrs|yoe)\b", q)))
    is_rating = bool(RATING_RE.search(q)) and not is_years
    is_date = bool(DATE_RE.search(q))
    is_lwd = bool(re.search(r"\b(last working day|last working date|lwd)\b", q))
    is_start_date = bool(re.search(r"\b(start date|joining date|date of joining|available to start|earliest start)\b", q))
    is_dob = bool(re.search(r"\b(dob|date of birth|birth date)\b", q))
    is_location = category == "location" or bool(LOCATION_RE.search(q))
    is_relocation = bool(re.search(r"\b(relocat|willing to move|open to moving)\b", q))
    is_state = bool(STATE_RE.search(q)) and not bool(PINCODE_RE.search(q))
    is_country = bool(COUNTRY_RE.search(q)) and not bool(PHONE_RE.search(q))
    is_nationality = bool(NATIONALITY_RE.search(q))
    is_address = bool(ADDRESS_RE.search(q)) and not bool(PINCODE_RE.search(q))
    is_phone = category == "personal_info" and bool(PHONE_RE.search(q))
    is_pincode = bool(PINCODE_RE.search(q))
    is_edu_score = bool(EDU_SCORE_RE.search(q)) and not is_rating and not is_salary
    is_team_size = bool(TEAM_SIZE_RE.search(q))
    is_project_count = bool(PROJECT_COUNT_RE.search(q))
    is_age = bool(AGE_RE.search(q))
    is_graduation_year = bool(re.search(r"\b(graduation year|year of graduation|year of passing|graduated in)\b", q))
    is_open_ended = bool(OPEN_ENDED_RE.search(q))
    is_list = bool(LIST_RE.search(q)) and not is_open_ended
    is_version = bool(VERSION_RE.search(q))

    # "Offers in hand: None" mentions a joining date but is not a date or
    # notice-period question.
    default_is_none = lower_default in ("n/a", "na", "none", "not applicable", "not required", "nil")
    if default_is_none:
        is_date = False
        is_lwd = False
        is_start_date = False
        is_notice = False

    is_yes_no = False
    explicit_boolean = _explicit_boolean(default)
    wh_question = bool(WH_QUESTION_RE.search(q))
    open_auxiliary = bool(OPEN_AUXILIARY_RE.search(q))
    starts_with_auxiliary = bool(YES_NO_START_RE.search(q)) and not open_auxiliary
    has_boolean_phrase = any(
        q.startswith(phrase) or (phrase in q and not wh_question and not open_auxiliary)
        for phrase in YES_NO_PHRASES
    )
    if explicit_boolean is not None and not is_rating:
        # A canonical Yes/No is the strongest possible signal, even for
        # notice/salary/location categories ("zero notice?", "offers in hand?").
        is_yes_no = True
    elif not is_open_ended and not is_years and not is_rating:
        if starts_with_auxiliary:
            is_yes_no = True
        elif has_boolean_phrase and not is_list:
            is_yes_no = True
        elif category in ("yes_no", "compliance", "work_authorization", "data_consent", "screening", "work_mode"):
            is_yes_no = True
        # Salary questions are only boolean when they actually ask a yes/no
        # question; "what is your current CTC" must stay numeric.
        if is_salary and not starts_with_auxiliary:
            is_yes_no = False

    is_not_applicable = lower_default in ("n/a", "na", "none", "not applicable", "not required", "nil")
    affirmative = _is_affirmative(default)
    negative = _is_negative(default)

    return QuestionIntent(
        question=q,
        category=category,
        default=default,
        is_yes_no=is_yes_no,
        is_years=is_years,
        is_rating=is_rating,
        is_salary=is_salary,
        is_expected_salary=bool(re.search(r"\b(expected|expectation|ectc|ex[- ]?ctc|desired|asking|target)\b", q)),
        is_notice=is_notice,
        is_lwd=is_lwd,
        is_start_date=is_start_date,
        is_date=is_date,
        is_dob=is_dob,
        is_location=is_location,
        is_relocation=is_relocation,
        is_state=is_state,
        is_country=is_country,
        is_nationality=is_nationality,
        is_address=is_address,
        is_phone=is_phone,
        is_pincode=is_pincode,
        is_education_score=is_edu_score,
        is_team_size=is_team_size,
        is_project_count=is_project_count,
        is_age=is_age,
        is_graduation_year=is_graduation_year,
        is_open_ended=is_open_ended,
        is_list=is_list,
        is_version=is_version,
        is_not_applicable=is_not_applicable,
        affirmative=affirmative,
        negative=negative,
    )


def _is_compound_salary_question(question: str, default: str = "") -> bool:
    q = f"{question or ''} {default or ''}".lower()
    current = re.search(r"\b(current|present|existing)\b", q) or "current ctc" in q
    expected = re.search(r"\b(expected|expectation|desired|target|ectc|ex[- ]?ctc)\b", q)
    return bool(
        (current and expected and re.search(r"\b(ctc|salary|compensation|package)\b", q))
        or (re.search(r"\bectc\b", q) and re.search(r"\bctc\b", q))
    )


def _salary_choice(intent: QuestionIntent, *, long_form: bool) -> str:
    expected = intent.is_expected_salary
    lower = f"{intent.question} {intent.default}".lower()
    if _is_variable_pay_question(intent.question, intent.default):
        return "0"
    if _is_compound_salary_question(intent.question, intent.default):
        if "inr" in lower or "annual" in lower or "amount" in lower or "gross" in lower:
            return f"{CURRENT_CTC_INR} / {EXPECTED_CTC_INR}"
        return f"{CURRENT_CTC_LPA:g} LPA / {EXPECTED_CTC_LPA:g} LPA"
    if "monthly" in lower or "per month" in lower or "take home" in lower or "take-home" in lower or "in-hand" in lower:
        return _format_number(_salary_number(intent.question, intent.default))
    if "inr" in lower or "annual" in lower or "amount" in lower or "gross" in lower:
        return _format_number(_salary_number(intent.question, intent.default))
    if long_form:
        return f"{EXPECTED_CTC_LPA if expected else CURRENT_CTC_LPA:g} LPA"
    return f"{EXPECTED_CTC_LPA if expected else CURRENT_CTC_LPA:g}"


def _years_choice(intent: QuestionIntent, *, long_form: bool) -> str:
    value = _years_number(intent.question, intent.default)
    if long_form:
        return f"{value:g} Years"
    return f"{value:g}"


def _notice_choice(intent: QuestionIntent, *, long_form: bool) -> str:
    lower = f"{intent.question} {intent.default}".lower()
    if "serving" in lower or intent.affirmative and "notice" in lower:
        return "Serving Notice Period"
    if "month" in lower and "day" not in lower:
        return f"{NOTICE_PERIOD_MONTHS:g}"
    if long_form:
        return f"{NOTICE_PERIOD_DAYS} days"
    return str(NOTICE_PERIOD_DAYS)


def _education_choice(intent: QuestionIntent) -> str:
    lower = intent.default.lower()
    if "b.tech" in lower or "b.e" in lower or "bachelor" in lower:
        return "Bachelor's Degree"
    if "master" in lower or "m.tech" in lower:
        return "Master's Degree"
    if "diploma" in lower:
        return "Diploma"
    return intent.default


def _first_list_item(text: str) -> str:
    item = re.split(r"[,;/|]", text, maxsplit=1)[0].strip(" .")
    return item


def _fit_list(text: str, limit: int) -> str:
    """Pack comma-separated list items into ``limit`` characters."""
    items = [item.strip(" .") for item in re.split(r"[,;/|]", str(text or "")) if item.strip()]
    selected: List[str] = []
    for item in items:
        candidate = ", ".join(selected + [item])
        if len(candidate) > limit:
            break
        selected.append(item)
    return ", ".join(selected)


def _choice_fallback(intent: QuestionIntent, *, long_form: bool) -> str:
    if intent.is_not_applicable:
        return "Not applicable" if long_form else "No"
    if intent.negative:
        return "No"
    if intent.affirmative:
        return "Yes"
    if intent.is_yes_no:
        return "Yes"
    return "Yes"


def derive_value(
    default: str,
    input_type: str,
    question: str = "",
    category: str = "",
) -> Optional[str]:
    """Derive a control-safe value from a canonical answer.

    Returns ``None`` only for date inputs whose question is not date-related,
    because adding a random date would be worse than leaving the field alone.
    """
    original_type = normalize_input_type(input_type)
    if original_type is None:
        return default
    input_type = original_type
    intent = detect_intent(question, category, default)

    if input_type in ("text_inr", "text_lpa") and _is_variable_pay_question(
        intent.question, intent.default
    ):
        return "0"

    if input_type == "number":
        return _derive_number(intent)
    if input_type == "date":
        return _derive_date(intent)
    if input_type == "tel":
        # Storing the candidate's phone beside a salary/date answer leaks PII
        # into a control that will never select it.
        if _looks_like_phone_number(default) or intent.is_phone:
            return _phone_digits(default)
        return None
    if input_type == "text_inr":
        if intent.is_not_applicable or (intent.is_yes_no and _explicit_boolean(default) == "no"):
            return "0"
        if _is_compound_salary_question(intent.question, default):
            numbers = [value for value in _salary_numbers(default) if value >= 100_000]
            if len(numbers) >= 2:
                return " / ".join(_format_number(value) for value in numbers[:2])
            return f"{CURRENT_CTC_INR} / {EXPECTED_CTC_INR}"
        if intent.is_yes_no and _explicit_boolean(default) is not None:
            return "1"
        return str(int(_salary_intent_number(intent, unit="inr")))
    if input_type == "text_lpa":
        if intent.is_not_applicable or (intent.is_yes_no and _explicit_boolean(default) == "no"):
            return "0"
        if _is_compound_salary_question(intent.question, default):
            numbers = [value for value in _salary_numbers(default) if 5 <= value <= 100]
            if len(numbers) >= 2:
                return " / ".join(_format_number(value) for value in numbers[:2])
            return f"{CURRENT_CTC_LPA:g} / {EXPECTED_CTC_LPA:g}"
        if intent.is_yes_no and _explicit_boolean(default) is not None:
            return "1"
        return _format_number(_salary_intent_number(intent, unit="lpa"))
    if input_type == "select-location":
        if intent.is_yes_no or intent.is_relocation:
            return "No" if intent.negative and not intent.affirmative else "Yes"
        return CANDIDATE_CITY
    if input_type == "select-education":
        return _education_choice(intent)
    if input_type == "select-aggressive":
        return "No" if intent.negative else "Yes"
    if input_type == "select-ctc":
        return f"{CURRENT_CTC_LPA:g} - {EXPECTED_CTC_LPA:g} LPA"
    if input_type == "button":
        return _derive_choice(intent, long_form=False)
    if input_type == "radio":
        return _derive_choice(intent, long_form=False)
    if input_type in ("select", "checkbox"):
        if input_type == "checkbox":
            return _derive_checkbox(intent)
        return _derive_choice(intent, long_form=True)
    if input_type in ("text", "textarea"):
        if str(default).strip().lower() == "dynamic_date":
            return _date_text_placeholder(intent) or "__DYNAMIC_LWD__"
        corrected = correct_stale_date_default(question, category, default)
        if corrected != str(default):
            return corrected
        return str(default) if str(default).strip() else "N/A"
    return default


def _salary_intent_number(intent: QuestionIntent, *, unit: str) -> float:
    lower = f"{intent.question} {intent.default}".lower()
    expected = intent.is_expected_salary
    numbers = _salary_numbers(intent.default)
    large = [value for value in numbers if value >= 100_000]
    small = [value for value in numbers if 5 <= value <= 100]
    monthly = any(
        marker in lower
        for marker in ("monthly", "per month", "take home", "take-home", "in-hand")
    )
    annual = any(marker in lower for marker in ("inr", "annual", "per annum", "gross", "amount"))
    lpa_hint = any(marker in lower for marker in ("lpa", "lakh", "lac"))

    question_lower = intent.question.lower()
    if "percentage" in question_lower or "%" in question_lower or "hike" in question_lower:
        return 0.0 if ("variable" in question_lower or "bonus" in question_lower) else 30.0

    if unit == "inr":
        if monthly:
            for value in numbers:
                if 10_000 <= value <= 1_000_000:
                    return value
            return float(EXPECTED_MONTHLY_INR if expected else CURRENT_MONTHLY_INR)
        if large:
            return large[0]
        midpoint = _range_midpoint(intent.default)
        if lpa_hint and midpoint is not None:
            return midpoint * 100_000
        if lpa_hint and small:
            return small[0] * 100_000
        if annual:
            return float(EXPECTED_CTC_INR if expected else CURRENT_CTC_INR)
        return float(EXPECTED_CTC_INR if expected else CURRENT_CTC_INR)

    if monthly:
        for value in numbers:
            if 10_000 <= value <= 1_000_000:
                return value / 100_000
        return float(EXPECTED_MONTHLY_INR if expected else CURRENT_MONTHLY_INR) / 100_000
    midpoint = _range_midpoint(intent.default)
    if midpoint is not None and any(marker in lower for marker in ("lpa", "lakh", "lac")):
        return midpoint
    if small:
        return small[0]
    if large:
        return large[0] / 100_000
    return float(EXPECTED_CTC_LPA if expected else CURRENT_CTC_LPA)


def _derive_number(intent: QuestionIntent) -> str:
    lower = f"{intent.question} {intent.default}".lower()

    if intent.is_not_applicable:
        # "Not applicable" has no numeric representation.  Use an explicit
        # sentinel instead of an empty string so the value is visibly
        # intentional and the audit can allow it for optional controls.
        return "N/A"

    if intent.is_years:
        return f"{_years_number(intent.question, intent.default):g}"

    if intent.is_notice and intent.negative and not intent.affirmative:
        return "0"

    if intent.is_notice and not intent.is_lwd and not intent.is_start_date:
        return f"{_notice_number(intent.question, intent.default):g}"

    if intent.is_date:
        if intent.is_dob:
            return CANDIDATE_DOB.replace("/", "")
        if intent.is_lwd or intent.is_start_date or intent.is_notice:
            # A number control cannot hold a DDMMYYYY date. When the question
            # explicitly asks for days ("Mention in Days", "number of days",
            # "days remaining"), honor the day count instead of injecting a
            # date marker that would be typed into a numeric field.
            ql = intent.question.lower()
            if (
                "in days" in ql
                or "number of days" in ql
                or "days remaining" in ql
                or "days left" in ql
            ):
                return f"{_notice_number(intent.question, intent.default):g}"
            return LWD_NUMERIC_MARKER
        return TODAY_NUMERIC_MARKER

    if intent.is_salary:
        if intent.is_yes_no and _explicit_boolean(intent.default) is not None:
            return "0" if _explicit_boolean(intent.default) == "no" else "1"
        value = _salary_number(intent.question, intent.default)
        return _format_number(value)

    if _is_variable_pay_question(intent.question, intent.default):
        return "0"

    if intent.is_rating:
        return f"{_rating_number(intent.question, intent.default):g}"
    if intent.is_phone:
        if "email" in intent.question:
            return "0"
        return _phone_digits(intent.default)
    if intent.is_pincode:
        number = _first_number(intent.default, allow_large=True)
        if number is not None and 100_000 <= number <= 999_999:
            return str(int(number))
        return CANDIDATE_PINCODE
    if intent.is_dob:
        return "17122000"
    if intent.is_education_score:
        if "cgpa" in lower or "gpa" in lower:
            number = _first_number(intent.default)
            return f"{number:g}" if number is not None and 0 <= number <= 10 else f"{CGPA:g}"
        if "10th" in lower or "ssc" in lower:
            return "85"
        if "12th" in lower or "hsc" in lower:
            return "70"
        number = _first_number(intent.default)
        if number is not None and 0 <= number <= 100:
            return f"{number:g}"
        return "85"
    if intent.is_graduation_year:
        number = _first_number(intent.default, allow_year=True)
        return str(int(number)) if number is not None and 1900 <= number <= 2100 else str(GRADUATION_YEAR)
    if intent.is_team_size:
        midpoint = _range_midpoint(intent.default)
        if midpoint is not None:
            return f"{midpoint:g}"
        number = _first_number(intent.default)
        return f"{number:g}" if number is not None else "1"
    if intent.is_project_count:
        number = _first_number(intent.default)
        return f"{number:g}" if number is not None and 0 <= number <= 100 else "4"
    if intent.is_age:
        number = _first_number(intent.default)
        return f"{number:g}" if number is not None and 0 <= number <= 100 else "25"
    if intent.is_version and not intent.is_yes_no:
        number = _first_number(intent.default)
        return f"{number:g}" if number is not None else "0"

    if intent.is_yes_no or intent.category in ("yes_no", "compliance", "work_authorization", "data_consent", "screening"):
        return "0" if intent.negative and not intent.affirmative else "1"
    if intent.is_not_applicable:
        return "N/A"
    # A quantity signal in the question ("how many", "years", "CTC") means the
    # number control legitimately holds the measurement; anything else must not
    # receive a literal 0, which forms and auditors read as a real value.
    if not _is_quantity_intent(intent):
        return ""

    number = _first_number(intent.default)
    if number is not None and 0 <= number <= 100_000:
        return f"{number:g}"
    return "0"


def _derive_choice(intent: QuestionIntent, *, long_form: bool) -> str:
    default = intent.default.strip()
    lower = f"{intent.question} {default}".lower()

    if not default:
        return "N/A"

    explicit_boolean = _explicit_boolean(default)
    if explicit_boolean is not None and not intent.is_rating:
        # Boolean canonical answers win over category heuristics.  This keeps
        # "zero notice?" -> No and "competing offers?" -> No even though the
        # categories are notice_period and salary.
        return "No" if explicit_boolean == "no" else "Yes"

    if intent.is_not_applicable:
        return "N/A"

    if intent.is_rating:
        return f"{_rating_number(intent.question, default):g}"
    if intent.is_salary:
        return _salary_choice(intent, long_form=long_form)
    if intent.is_years:
        return _years_choice(intent, long_form=long_form)
    if intent.is_notice:
        return _notice_choice(intent, long_form=long_form)
    if intent.is_dob:
        return CANDIDATE_DOB
    if intent.is_date:
        if intent.is_lwd or intent.is_start_date or intent.is_notice:
            return "Serving Notice Period" if long_form else str(NOTICE_PERIOD_DAYS)
        return "Today"
    if intent.is_phone:
        return _phone_digits(default)
    if intent.is_pincode:
        return CANDIDATE_PINCODE
    if intent.is_nationality:
        return CANDIDATE_NATIONALITY
    if intent.is_country:
        return CANDIDATE_COUNTRY
    if intent.is_state:
        return CANDIDATE_STATE
    if intent.is_address and not intent.is_yes_no:
        return f"{CANDIDATE_CITY}, {CANDIDATE_STATE}"
    if intent.is_location:
        if intent.is_relocation or intent.is_yes_no:
            return "No" if intent.negative and not intent.affirmative else "Yes"
        return CANDIDATE_CITY
    if intent.is_education_score:
        number = _first_number(default)
        if number is not None:
            return f"{number:g}"
        return "85"
    if intent.is_graduation_year:
        number = _first_number(default, allow_year=True)
        return str(int(number)) if number is not None and 1900 <= number <= 2100 else str(GRADUATION_YEAR)
    if intent.is_team_size:
        midpoint = _range_midpoint(default)
        if midpoint is not None:
            return _format_number(midpoint)
        number = _first_number(default)
        if number is not None and 0 <= number <= 1000:
            return _format_number(number)
        return _condense(default, 120 if long_form else 80) or default
    if intent.is_project_count:
        number = _first_number(default)
        return f"{number:g}" if number is not None else default
    if intent.is_age:
        number = _first_number(default)
        return f"{number:g}" if number is not None else "25"

    if intent.is_yes_no:
        if intent.negative and not intent.affirmative:
            return "No"
        if intent.affirmative:
            return "Yes"
        # Degree answers ("Very comfortable", "Advanced") are valid options on
        # their own; collapsing them to "Yes" loses the actual choice.
        condensed = _condense(default, 120 if long_form else 80)
        if condensed:
            return condensed
        return "Yes"

    # Keep short, option-like answers verbatim.  Selects can carry a longer
    # comma-separated list; radios/checkboxes cannot.
    if default and len(default) <= (120 if long_form else 60) and not intent.is_open_ended:
        return default

    if intent.is_list:
        if long_form:
            fitted = _fit_list(default, 120 if long_form else 60)
            if fitted:
                return fitted
        first = _first_list_item(default)
        if first:
            if len(first) <= (120 if long_form else 60):
                return first

    # Open-ended answers cannot be used as a single radio/select option.  A
    # clean first sentence is still a better fallback than an unrelated "Yes".
    if intent.is_open_ended:
        condensed = _condense(default, 120 if long_form else 80)
        if condensed:
            return condensed

    if default:
        condensed = _condense(default, 120 if long_form else 80)
        if condensed:
            return condensed

    return _choice_fallback(intent, long_form=long_form)


def _condense(text: str, limit: int) -> str:
    """Trim a long prose answer to a clean, option-sized prefix."""
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    if len(sentence) <= limit:
        return sentence
    cut = sentence[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut or sentence[:limit]


QUANTITY_INTENT_FIELDS = (
    "is_years",
    "is_rating",
    "is_salary",
    "is_notice",
    "is_education_score",
    "is_team_size",
    "is_project_count",
    "is_age",
    "is_graduation_year",
    "is_pincode",
)


def _is_quantity_intent(intent: QuestionIntent) -> bool:
    """Return True when the question asks for a measurable value.

    Quantity questions ("what is your notice period", "current CTC", "years of
    experience") occasionally render as a checkbox/radio control.  Collapsing
    those answers to "Yes" ticks a meaningless confirmation, so the numeric
    value must be preserved instead.  An explicit yes/no intent always wins,
    because "zero notice?" and "offers in hand?" are genuine booleans even
    though their categories look numeric.
    """
    if intent.is_yes_no:
        return False
    if intent.is_phone and "email" not in intent.question:
        return True
    return any(getattr(intent, field, False) for field in QUANTITY_INTENT_FIELDS)


def number_value_is_honest(text: str, default: str, intent: Optional["QuestionIntent"] = None) -> bool:
    """True when a stored number-control value is a defensible answer.

    A literal number on a question with no measurable answer (``9`` for a DSA
    rating written as prose) is an invented measurement that forms read as
    real.  Values are honest when the intent is measurable, when they are
    boolean 0/1 encodings, when they are derived from the canonical answer
    (dates, versions, pincodes), or when the canonical answer contains them.
    """
    text = str(text or "").strip()
    if not text:
        return intent is not None and not _is_quantity_intent(intent)
    if DYNAMIC_MARKER_RE.fullmatch(text):
        return True
    if intent is not None and _derive_number(intent) == text:
        # The value is exactly what the shared derivation produces (day counts,
        # DDMMYYYY dates, N/A sentinels, boolean codes); repair and audit must
        # not disagree about it.
        return True
    number = _as_number(text)
    if number is None:
        return False
    if number in (0.0, 1.0):
        return True
    if intent is not None and _is_quantity_intent(intent):
        return True
    if intent is not None and (
        intent.is_dob
        or intent.is_version
        or intent.is_pincode
        or intent.is_date
        or intent.is_rating
        or intent.is_education_score
    ):
        return True
    if intent is not None and intent.is_notice:
        # Notice questions legitimately answer with a day/month count even
        # when phrased as yes/no ("Currently serving notice?").
        return True
    return bool(re.search(rf"(?<!\d){re.escape(text)}(?!\d)", str(default or "")))


def _derive_checkbox(intent: QuestionIntent) -> str:
    """Derive a safe value for a checkbox control.

    Checkboxes in application forms are usually confirmations ("I agree",
    "Yes") or multi-select groups.  Existing corpus data overwhelmingly uses
    Yes/No for single checkboxes, so missing values follow that convention.
    Multi-select groups keep their list items instead of collapsing to Yes,
    which would tick an unrelated option.
    """
    explicit_boolean = _explicit_boolean(intent.default)
    if explicit_boolean is not None:
        return "No" if explicit_boolean == "no" else "Yes"

    numeric_default = _as_number(intent.default)
    if numeric_default is not None and numeric_default == 0:
        return "No"

    if intent.is_not_applicable or intent.negative:
        return "No"
    if intent.affirmative:
        return "Yes"
    if intent.is_list:
        fitted = _fit_list(intent.default, 120)
        if fitted:
            return fitted
    if intent.is_yes_no:
        return "No" if intent.negative and not intent.affirmative else "Yes"
    if _is_quantity_intent(intent):
        # A checkbox cannot represent a quantity; "Yes" would tick a meaningless
        # confirmation.  Keep the measured value so callers can match it against
        # numeric/range option labels or leave the box unticked.
        return _derive_choice(intent, long_form=False)
    if not intent.default.strip():
        return "No"

    # A prose answer on an open-ended/list question cannot truthfully become
    # "Yes"; keep a short prefix so a free-text checkbox/option can still use it.
    if intent.is_list or intent.is_open_ended:
        condensed = _condense(intent.default, 120)
        if condensed:
            return condensed
    return "Yes"


def _date_text_placeholder(intent: QuestionIntent) -> Optional[str]:
    """Return the best dynamic marker for a free-text date field."""
    q = intent.question.lower()
    if not (intent.is_date or intent.is_lwd or intent.is_start_date or intent.is_notice):
        return None
    if re.search(r"\bdd[\s/-]?mmm[\s/-]?yy\b", q) or "mmm-yy" in q or "mmm/yy" in q:
        return "__DYNAMIC_LWD_SHORT__"
    negative_notice = intent.is_notice and intent.negative and not intent.affirmative
    if (
        re.search(r"\bdd[\s/-]?mm[\s/-]?yyyy\b", q)
        or "ddmmyyyy" in q
        or re.search(r"\benter as \d{8}\b", q)
        or re.search(r"\b\d{8}\b", q)
    ):
        if negative_notice:
            return TODAY_NUMERIC_MARKER
        return LWD_NUMERIC_MARKER if (intent.is_lwd or intent.is_start_date or intent.is_notice) else TODAY_NUMERIC_MARKER
    if negative_notice:
        return "__DYNAMIC_TODAY_TEXT__"
    if intent.is_lwd or intent.is_start_date or intent.is_notice:
        return "__DYNAMIC_LWD__"
    if intent.is_date:
        return "__DYNAMIC_TODAY_TEXT__"
    return None


def _derive_date(intent: QuestionIntent) -> Optional[str]:
    default = intent.default.strip()
    if intent.is_dob:
        return "2000-12-17"
    if intent.is_notice and intent.negative and not intent.affirmative:
        return TODAY_ISO_MARKER
    if intent.is_lwd or intent.is_start_date or (intent.is_notice and not intent.is_dob):
        return LWD_ISO_MARKER
    if intent.is_date:
        return TODAY_ISO_MARKER
    if DYNAMIC_MARKER_RE.fullmatch(default):
        return default
    if any(regex.match(default) for regex in DATE_VALUE_RES):
        return default
    if default.lower() in ("n/a", "na", "not applicable", "none"):
        return default
    return None


def is_static_date_value(value: str) -> bool:
    """Return True for a concrete calendar date (not a marker)."""
    text = str(value or "").strip()
    if not text or DYNAMIC_MARKER_RE.fullmatch(text):
        return False
    if re.fullmatch(r"\d{8}", text):
        day, month, year = int(text[0:2]), int(text[2:4]), int(text[4:8])
        return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100
    return any(regex.match(text) for regex in DATE_VALUE_RES)


def correct_stale_date_default(question: str, category: str, default: str) -> str:
    """Replace concrete LWD/start-date answers with a moving marker.

    A stored date such as ``23102026`` becomes wrong the day after it is
    written.  Only employment dates are corrected; dates of birth remain
    concrete.
    """
    intent = detect_intent(question, category, default)
    employment_date = intent.is_lwd or intent.is_start_date or (intent.is_notice and intent.is_date)
    if not employment_date or intent.is_dob:
        return default
    text = str(default or "").strip()
    if text.lower() == "dynamic_date":
        return _date_text_placeholder(intent) or "__DYNAMIC_LWD__"
    if is_static_date_value(text):
        # Preserve the author's numeric DDMMYYYY shape when that is what was
        # stored; otherwise use the format named in the question.
        if re.fullmatch(r"\d{8}", text):
            return TODAY_NUMERIC_MARKER if (intent.is_notice and intent.negative) else LWD_NUMERIC_MARKER
        return _date_text_placeholder(intent) or "__DYNAMIC_LWD__"
    return default


def detect_pii_kind(question: str, default: str) -> Optional[str]:
    """Classify a pattern that stores or asks for personal identifiers."""
    q = str(question or "").lower()
    value = str(default or "").strip()
    lower = value.lower()

    if EMAIL_RE.search(value) or (
        re.search(r"\b(e-?mail id|e-?mail address|your e-?mail|enter e-?mail)\b", q)
        and lower not in ("yes", "no", "true", "false")
    ):
        return "email"
    if PAN_RE.search(value):
        return "pan"
    boolean_placeholder = lower in ("yes", "no", "true", "false")
    # Passport: either the stored value looks like a passport number, or the
    # question asks for one without being a travel-authorisation question.
    if not boolean_placeholder and (
        PASSPORT_RE.search(value)
        or (
            re.search(r"\bpassport\b", q)
            and not re.search(r"\b(travel|authoriz|authoris|visa|valid)\b", q)
        )
    ):
        return "passport"
    digits = re.sub(r"\D", "", value)
    if (
        AADHAAR_QUESTION_RE.search(q)
        and len(digits) == 12
        and digits[0] in "23456789"
        and not boolean_placeholder
    ):
        return "aadhaar"
    if re.search(r"\b(dob|date of birth|birth date)\b", q) and is_static_date_value(value):
        return "dob"
    if (
        re.search(r"\b(pin ?code|postal code|zip ?code|zip)\b", q)
        and lower not in ("yes", "no", "true", "false", "n/a", "none", "")
    ):
        return "pincode"
    non_disclosure = lower in (
        "yes",
        "no",
        "true",
        "false",
        "n/a",
        "na",
        "none",
        "",
        "available upon request",
        "available on request",
        "upon request",
        "shared upon request",
        "shared on request",
        "prefer not to say",
        "not disclosed",
        "will share later",
    )
    if not non_disclosure and PII_PHONE_RE.search(q) and 7 <= len(digits) <= 15:
        return "phone"
    if not non_disclosure and re.search(
        r"\b(phone number|mobile number|contact number|whatsapp number|telephone number)\b", q
    ):
        return "phone"
    if re.search(r"\b(address|street|residence|residing at|house no|flat no)\b", q) and lower not in (
        "yes",
        "no",
        "true",
        "false",
        "n/a",
        "none",
    ):
        return "address"
    if lower in ("siddhant", "singh", "siddhant singh") or re.search(
        r"\b(full name|first name|last name|candidate name|your name)\b", q
    ):
        if lower not in ("yes", "no", "true", "false", "n/a", "none", ""):
            return "name"
    return None


# ---------------------------------------------------------------------------
# Validation and runtime sanitisation
# ---------------------------------------------------------------------------

def _is_numeric_amount_series(text: str) -> bool:
    """Accept 2300000, 2300000 / 3000000 and 23 LPA / 30 LPA."""
    cleaned = text.replace(",", "").strip()
    parts = [part.strip() for part in re.split(r"\s*(?:/|&|\band\b)\s*", cleaned) if part.strip()]
    if not parts:
        return False
    for part in parts:
        part = re.sub(r"\s*(?:lpa|lakhs?|lac|inr|rs\.?)\s*$", "", part, flags=re.IGNORECASE)
        if not NUMERIC_RE.match(part):
            return False
    return True


def is_valid_value(value: Any, input_type: str, intent: Optional[QuestionIntent] = None) -> bool:
    """Return True when a value is structurally usable by the control."""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        # A blank number control is intentional for questions without a
        # measurable answer; every other blank control is a gap.
        if normalize_input_type(input_type) == "number" and intent is not None:
            return not _is_quantity_intent(intent)
        return False
    low = text.lower()
    if low == "dynamic_date":
        return False
    if "{{" in text or "}}" in text:
        return False
    normalized = normalize_input_type(input_type)
    if normalized == "number":
        if intent is not None and intent.is_not_applicable and low in (
            "n/a",
            "na",
            "none",
            "not applicable",
            "not required",
            "nil",
        ):
            return True
        return bool(NUMERIC_RE.match(text)) or text in (LWD_NUMERIC_MARKER, TODAY_NUMERIC_MARKER)
    if normalized == "date":
        return bool(DYNAMIC_MARKER_RE.fullmatch(text)) or any(regex.match(text) for regex in DATE_VALUE_RES)
    if normalized == "tel":
        return 7 <= len(re.sub(r"\D", "", text)) <= 15
    if normalized in ("text_inr", "text_lpa"):
        return _is_numeric_amount_series(text)
    if normalized == "select-location":
        return not NUMERIC_RE.match(text)
    if normalized in ("radio", "button"):
        return len(text) <= 80
    if normalized == "select":
        return len(text) <= 120
    if normalized == "checkbox":
        return len(text) <= 120
    return True


def _is_truncated(value: str, default: str) -> bool:
    """Detect a sentence prefix cut in the middle of a word.

    Older imports truncated some radio values at 32 characters, but other
    imports cut at 30.  Short option values (``Java`` from ``Java, Spring``)
    are safe because the next character is punctuation/whitespace.
    """
    text = str(value or "")
    source = str(default or "")
    if len(text) < 20 or len(source) <= len(text):
        return False
    if not source.lower().startswith(text.lower()):
        return False
    return source[len(text) : len(text) + 1] not in (" ", ",", ".", ";", ":", "/", "|")


def _number_is_contradictory(existing: float, derived: float, intent: QuestionIntent) -> bool:
    if existing == derived:
        return False
    lower = f"{intent.question} {intent.default}".lower()
    # Salary values may be expressed in LPA or INR; both are acceptable.
    if intent.is_salary and {existing, derived} <= {23.0, 30.0, 2_300_000.0, 3_000_000.0, 191_667.0, 250_000.0}:
        return False
    # Experience years may be rounded for whole-number controls.
    if intent.is_years and abs(existing - derived) <= 0.5:
        return False
    # Notice may be expressed in days or months.
    if intent.is_notice and {existing, derived} <= {15.0, 0.5, 30.0, 1.0}:
        return False
    # Rating values within the detected scale are all valid.
    if intent.is_rating:
        scale = _rating_scale(intent.question, intent.default)
        if 0 <= existing <= scale:
            return False
    # A different explicit number in the canonical answer (e.g. Angular 15 vs
    # stored 18) is a contradiction.
    if intent.is_version:
        return True
    return False


def sanitize_answer(
    answer: Any,
    input_type: Optional[str],
    question: str = "",
    category: str = "",
    default: str = "",
) -> Any:
    """Return a control-safe version of ``answer``.

    The function is fail-open: unknown input types and empty answers are
    returned unchanged.
    """
    normalized = normalize_input_type(input_type)
    if normalized is None or answer is None:
        return answer
    text = str(answer).strip()
    if not text:
        return answer
    intent = detect_intent(question, category, default or text)

    if normalized == "number":
        if not text or text in (LWD_NUMERIC_MARKER, TODAY_NUMERIC_MARKER):
            return text or ""
        number = _as_number(text)
        if number is not None:
            if intent.is_date:
                return _derive_number(intent)
            derived_raw = _derive_number(intent)
            if not derived_raw:
                # A blank derivation means the question has no measurable
                # answer; but honest numbers that came with the canonical
                # answer ("4.2" beside "4.2 Years") or boolean 0/1 codes must
                # survive instead of being blanked.
                if number_value_is_honest(text, intent.default, intent):
                    return _format_number(number)
                return ""
            derived = float(derived_raw)
            if _number_is_contradictory(number, derived, intent):
                return derived_raw
            return _format_number(number)
        # Non-numeric text: a blank derived value means the question has no
        # numeric answer; typing "0" would invent one.
        return _derive_number(intent)

    if normalized == "date":
        if DYNAMIC_MARKER_RE.fullmatch(text) and text in (LWD_ISO_MARKER, TODAY_ISO_MARKER):
            return text
        if intent.is_dob:
            return "2000-12-17"
        if intent.is_notice and intent.negative and not intent.affirmative:
            return TODAY_ISO_MARKER
        if intent.is_lwd or intent.is_start_date or intent.is_notice:
            return LWD_ISO_MARKER
        if intent.is_date:
            return TODAY_ISO_MARKER
        if DYNAMIC_MARKER_RE.fullmatch(text):
            return text
        if any(regex.match(text) for regex in DATE_VALUE_RES):
            return text
        derived = _derive_date(intent)
        return derived if derived is not None else answer

    if normalized == "tel":
        # Never launder a non-phone answer ("23 LPA", "4.2 Years") into the
        # candidate's real number; only phone-shaped text or phone intent may.
        if _looks_like_phone_number(text):
            return _phone_digits(text)
        if intent.is_phone and "email" not in intent.question:
            return _phone_digits(text)
        return answer

    if normalized in ("text_inr", "text_lpa"):
        # These synthetic controls are attached to salary questions; coercing
        # an unrelated answer would inject the candidate CTC into it.
        if not intent.is_salary:
            return answer
        number = _as_number(text.replace(",", ""))
        if number is None:
            derived = derive_value(default or text, normalized, question, category)
            return derived if _is_numeric_amount_series(str(derived or "")) else answer
        return _format_number(number)

    if normalized == "select-location":
        if intent.is_yes_no or intent.is_relocation:
            return "No" if intent.negative and not intent.affirmative else "Yes"
        if text.lower() in ("yes", "no", "true", "false") or NUMERIC_RE.match(text):
            return CANDIDATE_CITY
        return text

    if normalized in ("radio", "button", "select", "checkbox"):
        limit = {"radio": 80, "button": 80, "select": 120, "checkbox": 120}[normalized]
        long_form = normalized in ("select", "checkbox")
        quantity = _is_quantity_intent(intent)
        if quantity and not _numbers_in(text):
            # A boolean/prose answer on a quantity control ("Yes" beside "15"
            # notice days) must not survive; keep the measured value instead.
            if normalized == "checkbox":
                return _derive_checkbox(intent)
            return _derive_choice(intent, long_form=long_form)
        if len(text) <= limit and not _is_truncated(text, default or intent.default):
            expected = _leading_answer(default or intent.default)
            actual = _leading_answer(text)
            if expected and actual and expected != actual:
                if normalized == "checkbox" and not quantity:
                    return "No" if expected == "no" else "Yes"
                return _derive_choice(intent, long_form=long_form)
            return text
        if normalized == "checkbox" and quantity:
            return _derive_checkbox(intent)
        derived = _derive_choice(intent, long_form=long_form)
        return derived

    if normalized in ("text", "textarea"):
        if text.lower() == "dynamic_date":
            return _date_text_placeholder(intent) or "__DYNAMIC_LWD__"
        corrected = correct_stale_date_default(question, category, text)
        if corrected != text:
            return corrected
        return text

    return answer


def build_input_type_defaults(data: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Repair a pattern's input_type_defaults in place-safe form.

    Missing core values are added.  Structurally invalid or contradictory
    values are replaced.  Valid intentional values (e.g. "Citizen (India)" for
    a select) are preserved.
    """
    category = str(data.get("category", ""))
    default = str(data.get("default", ""))
    question = _first_question(data)
    intent = _detect_intent(question, category, default, data)
    result: Dict[str, Any] = dict(existing or {})

    for input_type in CORE_INPUT_TYPES:
        current = result.get(input_type)
        derived = derive_value(default, input_type, question, category)
        if derived is None:
            continue

        if current is None or not is_valid_value(current, input_type, intent):
            result[input_type] = derived
            continue

        text = str(current).strip()
        low = text.lower()

        if input_type == "number":
            if intent.is_not_applicable:
                # "Not applicable"/"N/A" has no numeric representation; a "0"
                # would be read as a real measurement.  Use the explicit
                # sentinel so optional describe/follow-up questions stay honest.
                result[input_type] = "N/A"
                continue
            if intent.is_date:
                result[input_type] = derived
                continue
            if detect_pii_kind(question, default) in ("email", "pan", "passport", "name", "address"):
                # Digits inside an email/PAN/passport/name are not a number.
                result[input_type] = derived
                continue
            if (
                (intent.is_open_ended or intent.is_list)
                and not intent.is_rating
                and not intent.is_years
                and not intent.is_salary
                and not intent.is_notice
                and not NUMERIC_HINT_RE.search(question)
            ):
                # A stray "4" on an architecture question is not a numeric answer.
                result[input_type] = derived
                continue
            existing_number = _as_number(text)
            derived_number = _as_number(derived)
            if existing_number is None:
                result[input_type] = derived
            elif derived_number is not None and _number_is_contradictory(existing_number, derived_number, intent):
                result[input_type] = derived
            elif not number_value_is_honest(text, default, intent):
                # Legacy imports stored invented measurements ("9" for a DSA
                # rating) on questions with no numeric answer; blank the
                # control instead of letting the bot type a fake number.
                result[input_type] = ""
            continue

        if input_type in ("radio", "select", "checkbox"):
            if input_type == "checkbox" and _as_number(default) is not None:
                # A numeric answer (0% disability, 0 unvested options) is not a
                # yes/no answer even when the category looks boolean-ish.
                result[input_type] = derived
                continue
            if input_type == "checkbox" and _is_quantity_intent(intent):
                # "15" notice days or "23" LPA must survive as the checkbox
                # default; "Yes" would tick a meaningless confirmation.
                result[input_type] = derived
                continue
            if input_type == "checkbox" and intent.is_not_applicable:
                # "N/A" on a confirmation checkbox means unchecked.
                result[input_type] = derived
                continue
            if input_type == "checkbox" and (
                intent.is_date or intent.is_dob or intent.is_lwd or intent.is_start_date or intent.is_notice
            ):
                # A stale "No" beside a date answer is contradictory; the
                # checkbox only confirms the date is being provided.
                result[input_type] = derived
                continue
            if _is_truncated(text, default):
                result[input_type] = derived
                continue
            expected = _leading_answer(default)
            actual = _leading_answer(text)
            if expected and actual and expected != actual:
                if input_type == "checkbox":
                    result[input_type] = "No" if expected == "no" else "Yes"
                else:
                    result[input_type] = derived
                continue
            if low in ("dynamic_date",):
                result[input_type] = derived
                continue
            if input_type == "checkbox" and intent.is_yes_no and actual is None:
                result[input_type] = derived
                continue
            if input_type == "checkbox" and intent.is_yes_no:
                positive_default = bool(
                    re.search(
                        r"\b(comfortable|proficient|confident|experienced|familiar|strong|excellent|good|advanced|expert|yes)\b",
                        default,
                        re.IGNORECASE,
                    )
                )
                if (intent.affirmative or positive_default) and actual == "no":
                    result[input_type] = "Yes"
                    continue
                if intent.negative and actual == "yes":
                    result[input_type] = "No"
                    continue
            if input_type == "checkbox" and intent.is_yes_no and low in ("none", "n/a", "not applicable"):
                result[input_type] = derived
                continue
            if input_type == "checkbox" and intent.is_list and _explicit_boolean(default) is None:
                result[input_type] = derived
                continue
            if input_type in ("radio", "select") and low in ("yes", "no", "true", "false"):
                if not intent.is_yes_no and _explicit_boolean(default) is None:
                    result[input_type] = derived
                    continue
            if input_type in ("radio", "checkbox") and len(text) > 80 and not intent.is_list:
                result[input_type] = derived
                continue
            if input_type == "select" and len(text) > 120:
                result[input_type] = derived
                continue

        if input_type in ("text", "textarea"):
            if low == "dynamic_date":
                result[input_type] = derived
                continue
            expected = _leading_answer(default)
            actual = _leading_answer(text)
            if expected and actual and expected != actual:
                result[input_type] = default
                continue
            corrected = correct_stale_date_default(question, category, text)
            if corrected != text:
                result[input_type] = corrected
                continue
            corrected = correct_stale_date_default(question, category, default)
            if corrected != default:
                result[input_type] = corrected

    # Specialised keys are repaired when present, and added when the question
    # intent clearly requires them.
    for input_type in required_special_input_types(intent):
        if input_type not in result:
            derived = derive_value(default, input_type, question, category)
            if derived is not None:
                result[input_type] = derived

    for input_type in (
        "date",
        "tel",
        "text_inr",
        "text_lpa",
        "select-aggressive",
        "select-education",
        "select-location",
        "select-ctc",
    ):
        if input_type not in result:
            continue
        if input_type == "tel" and not intent.is_phone and not _has_phone_digits(default):
            # Legacy imports stored the candidate phone beside salary/date
            # questions; drop the key instead of "repairing" it to the same PII.
            result.pop(input_type, None)
            continue
        derived = derive_value(default, input_type, question, category)
        if derived is None:
            continue
        current = result.get(input_type)
        if input_type == "date" and (
            intent.is_date
            or intent.is_dob
            or intent.is_lwd
            or intent.is_start_date
            or (intent.is_notice and intent.negative)
        ):
            result[input_type] = derived
            continue
        if input_type in ("text_inr", "text_lpa") and intent.is_salary:
            result[input_type] = derived
            continue
        if input_type in ("text_inr", "text_lpa") and intent.is_yes_no and _explicit_boolean(default) is not None:
            result[input_type] = derived
            continue
        if input_type == "date" and str(current).strip().lower() in ("n/a", "na", "none", "not applicable"):
            # A date control cannot accept a textual N/A; omit the optional key
            # rather than storing an unusable value.
            result.pop(input_type, None)
            continue
        if not is_valid_value(current, input_type, intent):
            result[input_type] = derived

    return result


def required_special_input_types(intent: QuestionIntent) -> List[str]:
    """Return specialised input types that the question clearly needs."""
    required: List[str] = []
    if intent.is_date or intent.is_dob or intent.is_lwd or intent.is_start_date:
        required.append("date")
    if intent.is_phone:
        required.append("tel")
    if (
        intent.is_salary
        and not intent.is_not_applicable
        and not (intent.is_yes_no and _explicit_boolean(intent.default) is not None)
    ):
        required.extend(("text_inr", "text_lpa"))
    if intent.is_pincode:
        required.append("text")
    if (
        intent.is_location
        and not intent.is_yes_no
        and not intent.is_pincode
        and not re.search(r"\b(country|nationality|state|timezone|travel|percentage|remote)\b", intent.question)
        and re.search(r"\b(city|location|address|based in|reside|relocat|where do you live|prefer)\b", intent.question)
    ):
        required.append("select-location")
    if (
        intent.category == "education"
        and not intent.is_graduation_year
        and not re.search(r"\b(year of passing|graduation year|graduated in)\b", intent.question)
        and re.search(
            r"\b(degree|qualification|highest education|education level|graduation|bachelor|master|b\.?tech|b\.?e)\b",
            intent.question,
        )
    ):
        required.append("select-education")
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(required))


def iter_input_type_values(data: Dict[str, Any]) -> Iterable[tuple[str, Any]]:
    defaults = data.get("input_type_defaults") or {}
    for key, value in defaults.items():
        yield str(key), value
