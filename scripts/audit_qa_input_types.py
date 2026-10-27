#!/usr/bin/env python3
"""
Audit input-type applicability and wrong-answer risks in config/qa_patterns.json.

The script is read-only. It checks every QA pattern for:

* Missing or empty core input-type defaults
    (text, textarea, radio, select, checkbox, number)
* Null / placeholder junk values ("None", "null", "undefined", "dynamic_date")
* Numeric defaults that are not pure numbers (".", "4.2 Years", "710", ...)
* Date defaults that are neither a supported date format nor a dynamic marker
* Over-long sentence answers used for radio/select/checkbox controls
* Truncated 32-character prefixes of the canonical default
* Yes/No defaults that conflict with the choice-control answer
* Location/INR/LPA/telephone values that are not usable by their control

Usage:
    python scripts/audit_qa_input_types.py
    python scripts/audit_qa_input_types.py --json report.json
    python scripts/audit_qa_input_types.py --max-examples 20

Exit code is 0 when no violations are found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ROOT / "config" / "qa_patterns.json"
sys.path.insert(0, str(ROOT / "src"))

from patterns.input_type_sanitizer import (  # noqa: E402
    LWD_NUMERIC_MARKER,
    TODAY_NUMERIC_MARKER,
    detect_intent,
    detect_pii_kind,
    is_static_date_value,
    is_valid_value,
    number_value_is_honest,
)

CORE_INPUT_TYPES = ("text", "textarea", "radio", "select", "checkbox", "number")
SPECIAL_INPUT_TYPES = (
    "date",
    "tel",
    "text_inr",
    "text_lpa",
    "select-aggressive",
    "select-education",
    "select-location",
    "select-ctc",
)
CHOICE_INPUT_TYPES = ("radio", "select", "checkbox")
MAX_CHOICE_LENGTH = {"radio": 80, "select": 120, "checkbox": 120}

PLACEHOLDER_JUNK = {"null", "undefined", "nan", "dynamic_date"}
NONE_JUNK_INPUT_TYPES = {"number", "date", "tel", "text_inr", "text_lpa"}
NUMERIC_DATE_MARKERS = {LWD_NUMERIC_MARKER, TODAY_NUMERIC_MARKER}
DYNAMIC_MARKER_RE = re.compile(r"__DYNAMIC_[A-Z_]+__")
DATE_VALUE_RES = (
    re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$"),          # 17/12/2000, 17-12-2000
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),                      # 2000-12-17
    re.compile(r"^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}$"),        # 17 Dec 2000
    re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$"),                # 17-Dec-00
)
NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
YES_VALUES = {"yes", "y", "true", "1"}
NO_VALUES = {"no", "n", "false", "0"}


def load_patterns(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_date_value(value: str) -> bool:
    if DYNAMIC_MARKER_RE.fullmatch(value):
        return True
    return any(regex.match(value) for regex in DATE_VALUE_RES)


def _is_ddmmyyyy(value: str) -> bool:
    if not re.fullmatch(r"\d{8}", value):
        return False
    day, month, year = int(value[0:2]), int(value[2:4]), int(value[4:8])
    return 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100


def _leading_boolean(value: str) -> Optional[str]:
    """Return 'yes'/'no' when the text starts with an explicit boolean answer."""
    text = value.strip().lower()
    if not text:
        return None
    # "0" / "1" are booleans only as the whole answer; "0.5 months" is not.
    if text in YES_VALUES:
        return "yes"
    if text in NO_VALUES:
        return "no"
    first = re.split(r"[\s,;:.!?]", text, maxsplit=1)[0]
    if first in ("yes", "y", "true") or text.startswith(("yes ", "yes,", "yes.", "yes:", "yes;")):
        return "yes"
    if first in ("no", "n", "false") or text.startswith(("no ", "no,", "no.", "no:", "no;")):
        return "no"
    return None


def _looks_truncated(value: str, default: str) -> bool:
    if len(value) < 20 or len(default) <= len(value):
        return False
    if not default.lower().startswith(value.lower()):
        return False
    return default[len(value) : len(value) + 1] not in (" ", ",", ".", ";", ":", "/", "|")


def audit_patterns(patterns: Dict[str, Any], max_examples: int = 5) -> Dict[str, Any]:
    pattern_map = patterns.get("patterns", {})
    counts: Counter[str] = Counter()
    examples: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    per_type_missing: Counter[str] = Counter()
    per_type_invalid: Counter[str] = Counter()

    def report(code: str, pattern_id: str, field: str, value: Any, detail: str = "") -> None:
        counts[code] += 1
        if len(examples[code]) < max_examples:
            examples[code].append(
                {
                    "pattern_id": pattern_id,
                    "category": str(pattern_map[pattern_id].get("category", "")),
                    "field": field,
                    "value": "" if value is None else str(value)[:160],
                    "detail": detail,
                }
            )

    for pattern_id, data in pattern_map.items():
        if not isinstance(data, dict):
            report("invalid_pattern_entry", pattern_id, "", data)
            continue

        defaults = data.get("input_type_defaults")
        if not isinstance(defaults, dict):
            report("missing_input_type_defaults", pattern_id, "input_type_defaults", defaults)
            defaults = {}

        canonical = str(data.get("default", "")).strip()
        if not canonical:
            report("empty_default", pattern_id, "default", canonical)
        question = str((data.get("patterns") or [""])[0])
        intent = detect_intent(question, str(data.get("category", "")), canonical)

        pii_kind = detect_pii_kind(question, canonical)
        if pii_kind:
            if data.get("sensitive") is not True:
                report("pii_missing_sensitive", pattern_id, "sensitive", data.get("sensitive"), pii_kind)
            if data.get("requires_exact_match") is not True:
                report("pii_missing_exact_match", pattern_id, "requires_exact_match", data.get("requires_exact_match"), pii_kind)

        employment_date = intent.is_lwd or intent.is_start_date or (intent.is_notice and intent.is_date)
        if employment_date and is_static_date_value(canonical):
            report("stale_lwd_default", pattern_id, "default", canonical)

        for input_type in CORE_INPUT_TYPES:
            if input_type not in defaults:
                per_type_missing[input_type] += 1
                report(f"missing_{input_type}", pattern_id, input_type, None)
                continue
            value = defaults.get(input_type)
            if value is None:
                per_type_invalid[input_type] += 1
                report(f"null_{input_type}", pattern_id, input_type, value)
                continue
            text = str(value).strip()
            if not text:
                if input_type == "number" and number_value_is_honest("", canonical, intent):
                    # Intentional blank: the question has no numeric answer and
                    # typing "0" would invent one.
                    continue
                per_type_invalid[input_type] += 1
                report(f"empty_{input_type}", pattern_id, input_type, value)
                continue
            low = text.lower()
            if low in PLACEHOLDER_JUNK:
                report(f"placeholder_{input_type}", pattern_id, input_type, value, low)
                continue
            if low == "none" and input_type in NONE_JUNK_INPUT_TYPES:
                report(f"placeholder_{input_type}", pattern_id, input_type, value, low)
                continue
            if "{{" in text or "}}" in text:
                report(f"template_leak_{input_type}", pattern_id, input_type, value)

            if input_type == "number":
                if text in NUMERIC_DATE_MARKERS:
                    continue
                if not NUMERIC_RE.match(text):
                    if intent.is_not_applicable and low in (
                        "n/a",
                        "na",
                        "none",
                        "not applicable",
                        "not required",
                        "nil",
                    ):
                        pass
                    else:
                        per_type_invalid[input_type] += 1
                        report("invalid_number", pattern_id, input_type, value, f"default={canonical[:80]}")
                else:
                    number = float(text)
                    if not number_value_is_honest(text, canonical, intent):
                        # A number the canonical answer never supported is an
                        # invented measurement; forms read it as real.
                        report("number_on_non_quantity", pattern_id, input_type, value, f"default={canonical[:60]}")
                    category = str(data.get("category", ""))
                    is_numeric_date = bool(re.fullmatch(r"\d{8}", text)) and _is_ddmmyyyy(text)
                    percentage_question = bool(re.search(r"\b(percent|percentage|%)\b", question, re.IGNORECASE))
                    if category == "experience" and not (0 <= number <= (100 if percentage_question else 50)):
                        report("number_out_of_range_experience", pattern_id, input_type, value)
                    elif category == "notice_period" and not is_numeric_date and not (0 <= number <= 365):
                        report("number_out_of_range_notice", pattern_id, input_type, value)
                    elif category == "salary" and not (0 <= number <= 100_000_000):
                        report("number_out_of_range_salary", pattern_id, input_type, value)
                    expected = _leading_boolean(canonical)
                    if intent.is_yes_no and expected == "yes" and number == 0:
                        report("number_yes_no_conflict", pattern_id, input_type, value, "default=Yes")
                    elif intent.is_yes_no and expected == "no" and number == 1:
                        report("number_yes_no_conflict", pattern_id, input_type, value, "default=No")
                    if employment_date and is_static_date_value(text):
                        report("stale_lwd_number", pattern_id, input_type, value, f"default={canonical[:60]}")

            elif input_type == "date":
                if not _is_date_value(text):
                    report("invalid_date", pattern_id, input_type, value, f"default={canonical[:80]}")

            elif input_type == "tel":
                digits = re.sub(r"\D", "", text)
                if not 7 <= len(digits) <= 15:
                    report("invalid_tel", pattern_id, input_type, value)

            elif input_type == "text_inr":
                if not NUMERIC_RE.match(text.replace(",", "")):
                    report("invalid_text_inr", pattern_id, input_type, value)

            elif input_type == "text_lpa":
                if not NUMERIC_RE.match(text.replace(",", "")):
                    report("invalid_text_lpa", pattern_id, input_type, value)

            elif input_type == "select-location":
                yes_no_allowed = intent.is_yes_no or intent.is_relocation
                if not yes_no_allowed and (low in YES_VALUES or low in NO_VALUES or NUMERIC_RE.match(text)):
                    report("invalid_select_location", pattern_id, input_type, value)

            elif input_type in CHOICE_INPUT_TYPES:
                limit = MAX_CHOICE_LENGTH[input_type]
                if len(text) > limit:
                    per_type_invalid[input_type] += 1
                    report(f"choice_too_long_{input_type}", pattern_id, input_type, value, f"len={len(text)}")
                if _looks_truncated(text, canonical):
                    per_type_invalid[input_type] += 1
                    report(f"choice_truncated_{input_type}", pattern_id, input_type, value)
                expected = _leading_boolean(canonical)
                actual = _leading_boolean(text)
                if expected == "yes" and actual == "no":
                    report(f"yes_no_conflict_{input_type}", pattern_id, input_type, value, f"default={canonical[:60]}")
                elif expected == "no" and actual == "yes":
                    report(f"yes_no_conflict_{input_type}", pattern_id, input_type, value, f"default={canonical[:60]}")
                if input_type == "checkbox" and intent.is_list and low in YES_VALUES | NO_VALUES:
                    # A list question can legitimately be a single confirmation
                    # checkbox when the canonical answer is affirmative/negative
                    # ("I have experience...") or explicitly N/A.
                    if (
                        expected is None
                        and not intent.affirmative
                        and not intent.negative
                        and not intent.is_not_applicable
                    ):
                        report("checkbox_yes_no_for_list", pattern_id, input_type, value, f"default={canonical[:60]}")
                if input_type in ("radio", "select") and low in ("yes", "no", "true", "false"):
                    if not intent.is_yes_no and expected is None and not intent.is_not_applicable:
                        report("choice_yes_no_non_boolean", pattern_id, input_type, value, f"default={canonical[:60]}")

            elif input_type in ("text", "textarea"):
                if employment_date and is_static_date_value(text):
                    report(f"stale_lwd_{input_type}", pattern_id, input_type, value, f"default={canonical[:60]}")
                expected = _leading_boolean(canonical)
                actual = _leading_boolean(text)
                if expected == "yes" and actual == "no":
                    report(f"yes_no_conflict_{input_type}", pattern_id, input_type, value, f"default={canonical[:60]}")
                elif expected == "no" and actual == "yes":
                    report(f"yes_no_conflict_{input_type}", pattern_id, input_type, value, f"default={canonical[:60]}")

        # Conditional specialised types: only checked when present.
        for input_type in SPECIAL_INPUT_TYPES:
            if input_type not in defaults:
                continue
            value = defaults.get(input_type)
            if value is None:
                report(f"null_{input_type}", pattern_id, input_type, value)
                continue
            text = str(value).strip()
            if not text:
                report(f"empty_{input_type}", pattern_id, input_type, value)
                continue
            if text.lower() in PLACEHOLDER_JUNK:
                report(f"placeholder_{input_type}", pattern_id, input_type, value, text.lower())
            elif input_type == "date" and not _is_date_value(text):
                report("invalid_date", pattern_id, input_type, value, f"default={canonical[:80]}")
            elif input_type == "tel":
                digits = re.sub(r"\D", "", text)
                if not 7 <= len(digits) <= 15:
                    report("invalid_tel", pattern_id, input_type, value)
            elif input_type in ("text_inr", "text_lpa"):
                if not is_valid_value(text, input_type):
                    report(f"invalid_{input_type}", pattern_id, input_type, value)
            elif input_type == "select-location":
                yes_no_allowed = intent.is_yes_no or intent.is_relocation
                if not yes_no_allowed and (text.lower() in YES_VALUES or text.lower() in NO_VALUES or NUMERIC_RE.match(text)):
                    report("invalid_select_location", pattern_id, input_type, value)

        # Dynamic markers must never appear in controls that would type the
        # marker literally.  Date-like choices are resolved before matching.
        for input_type, value in defaults.items():
            if input_type == "date" or value is None:
                continue
            text = str(value)
            if not DYNAMIC_MARKER_RE.search(text):
                continue
            if input_type in ("text", "textarea", "select", "radio"):
                continue
            if input_type == "number" and text in NUMERIC_DATE_MARKERS:
                continue
            if input_type == "checkbox" and intent.is_date:
                continue
            report(f"dynamic_marker_on_{input_type}", pattern_id, input_type, value)

    total = len(pattern_map)
    violation_total = sum(counts.values())
    return {
        "pattern_count": total,
        "violation_count": violation_total,
        "violation_codes": dict(counts.most_common()),
        "missing_by_type": dict(per_type_missing),
        "invalid_by_type": dict(per_type_invalid),
        "examples": {code: rows for code, rows in examples.items()},
        "clean": violation_total == 0,
    }


def print_report(result: Dict[str, Any], max_examples: int = 5) -> None:
    print(f"Patterns scanned: {result['pattern_count']}")
    print(f"Violations:       {result['violation_count']}")
    print(f"Clean:            {result['clean']}")
    if result["missing_by_type"]:
        print("\nMissing core input types:")
        for key, count in sorted(result["missing_by_type"].items(), key=lambda item: -item[1]):
            print(f"  {key:12s} {count:6d}")
    if result["violation_codes"]:
        print("\nViolation codes:")
        for code, count in result["violation_codes"].items():
            print(f"  {code:36s} {count:6d}")
            for row in result["examples"].get(code, [])[:max_examples]:
                print(
                    f"      - {row['pattern_id']} [{row['category']}] "
                    f"{row['field']}={row['value']!r} {row['detail']}"
                )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit QA pattern input-type defaults.")
    parser.add_argument("--patterns", default=str(DEFAULT_PATTERNS), help="Path to qa_patterns.json")
    parser.add_argument("--json", dest="json_out", default=None, help="Write the full report as JSON")
    parser.add_argument("--max-examples", type=int, default=5, help="Examples printed per violation code")
    args = parser.parse_args(list(argv) if argv is not None else None)

    path = Path(args.patterns)
    if not path.exists():
        print(f"Patterns file not found: {path}", file=sys.stderr)
        return 2

    result = audit_patterns(load_patterns(path), max_examples=args.max_examples)
    print_report(result, max_examples=args.max_examples)

    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nJSON report written to {out}")

    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
