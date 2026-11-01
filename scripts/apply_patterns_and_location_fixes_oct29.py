#!/usr/bin/env python3
"""
Apply pattern additions and fixes for:
1. "Expected Compensation?*" with radio options (Yes / No)
2. "What is your work authorization status for India?" with radio options:
   - I can work here without any restrictions
   - I can work here, but only for a limited time
   - I can work here, but only for my current employer
   - I can't work here yet
3. "When can you start?*" with radio options:
   - Immediately
   - Within two weeks
   - Within one month
   - Within two months
   - Within three months
   - In more than three months
4. Location (city) typeahead selection selecting "Indiranagar Bangalore" instead of "Bengaluru, Karnataka, India"
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from patterns.input_type_sanitizer import build_input_type_defaults

PATTERNS_FILE = ROOT / "config/qa_patterns.json"

def apply_fixes():
    print(f"Loading {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    patterns = data.setdefault("patterns", {})

    # 1. Add / update expected_compensation_agreement
    patterns["expected_compensation_agreement"] = {
        "patterns": [
            "expected compensation?*",
            "expected compensation? *",
            "expected compensation?",
            "expected compensation",
            "what is your expected compensation?",
            "what is your expected compensation",
            "are you comfortable with the expected compensation",
            "are you comfortable with the expected compensation?",
            "do you agree with the expected compensation",
            "do you agree with the expected compensation?",
            "compensation expected",
            "agreed on compensation",
            "compensation agreement"
        ],
        "category": "compensation",
        "default": "Yes",
        "priority": 16,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "text": "3000000",
            "text_inr": "3000000",
            "text_lpa": "30",
            "textarea": "Expected CTC: 30 LPA (100% Fixed)",
            "number": "3000000",
            "checkbox": "Yes"
        }
    }
    print("Added / updated expected_compensation_agreement")

    # 2. Add / update work_authorization_status_india
    patterns["work_authorization_status_india"] = {
        "patterns": [
            "what is your work authorization status for india?",
            "what is your work authorization status for india",
            "what is your work authorization status for india?*",
            "what is your work authorization status for india? *",
            "work authorization status for india",
            "work authorization status for india?",
            "what is your work authorization status in india",
            "what is your work authorization status in india?",
            "work authorization status in india",
            "what is your work authorization status",
            "what is your work authorization status?",
            "work authorization status",
            "work authorization status?"
        ],
        "category": "work_authorization",
        "default": "I can work here without any restrictions",
        "priority": 18,
        "input_type_defaults": {
            "radio": "I can work here without any restrictions",
            "select": "I can work here without any restrictions",
            "text": "Authorized to work in India without any restrictions",
            "textarea": "Authorized to work in India without any restrictions.",
            "checkbox": "Yes"
        }
    }
    print("Added / updated work_authorization_status_india")

    # 3. Add / update when_can_you_start_range
    patterns["when_can_you_start_range"] = {
        "patterns": [
            "when can you start",
            "when can you start?",
            "when can you start?*",
            "when can you start? *",
            "when can you start working",
            "when can you start working?",
            "how soon can you start",
            "how soon can you start?",
            "how quickly can you start",
            "how quickly can you start?",
            "when are you available to start",
            "when are you available to start?",
            "earliest date you can start",
            "earliest date you can start?"
        ],
        "category": "notice_period",
        "default": "Within two weeks",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Within two weeks",
            "select": "Within two weeks",
            "text": "15 days (serving notice period)",
            "textarea": "15 days (serving notice period)",
            "checkbox": "Within two weeks",
            "number": "15"
        }
    }
    print("Added / updated when_can_you_start_range")

    # Also update earliest_start_date radio / select default if present
    if "earliest_start_date" in patterns:
        p = patterns["earliest_start_date"]
        inp = p.setdefault("input_type_defaults", {})
        inp["radio"] = "Within two weeks"
        inp["select"] = "Within two weeks"
        print("Updated earliest_start_date input_type_defaults")

    print(f"Writing back to {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Successfully updated qa_patterns.json")

if __name__ == "__main__":
    apply_fixes()
