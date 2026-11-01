#!/usr/bin/env python3
"""
Apply pattern fixes and additions for questions identified in qa_results.csv on Oct 28, 2026.
Issues addressed:
1. Work authorization for Navan / indefinite basis ('authorized to work now and in the future, no employer sponsorship required' matching 'No' on binary selects).
2. Primary base in non-Bangalore city ('Can you confirm if your primary base is Chennai?') answered 'Yes' instead of 'No'.
3. Notice period question containing 'years' ('How many years of notice period do you have?') answering '4' instead of '15 Days'.
4. Official notice period ('Whats your official notice period?', 'What is your official notice period - Mention in days?') answering '30' instead of '15'.
5. Multi-select / checkbox shift preference ('Please share your shift preference' with opts 'Night Job, Day Job, Flex Job') answering 'Yes' instead of 'Day Job'.
6. 'attend' removed from negative_patterns in city_presence_no so valid city presence questions aren't disqualified.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from patterns.input_type_sanitizer import build_input_type_defaults

PATTERNS_FILE = "config/qa_patterns.json"

def apply_fixes():
    print(f"Loading {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    patterns = data.setdefault("patterns", {})

    # 1. Update work_authorization_select
    if "work_authorization_select" in patterns:
        p = patterns["work_authorization_select"]
        p["default"] = "Yes"
        p["input_type_defaults"] = build_input_type_defaults(p, {
            "radio": "Yes",
            "select": "Yes",
            "text": "Yes, Indian citizen authorized to work without sponsorship",
            "textarea": "Yes, I am legally authorized to work in India and do not require employer sponsorship.",
            "checkbox": "Yes",
            "number": "1"
        })
        print("Updated work_authorization_select")

    # 2. Update official_notice_period
    if "official_notice_period" in patterns:
        p = patterns["official_notice_period"]
        p["default"] = "15 days"
        p["input_type_defaults"] = build_input_type_defaults(p, {
            "text": "15 days",
            "number": "15",
            "radio": "Less than 30 days",
            "select": "Less than 30 days",
            "textarea": "15 days",
            "checkbox": "15"
        })
        new_official_pats = [
            "whats your official notice period?",
            "whats your official notice period",
            "what is your official notice period - mention in days?",
            "what is your official notice period - mention in days",
            "official notice period - mention in days",
            "official notice period mention in days",
            "official notice period in days"
        ]
        curr_pats = p.setdefault("patterns", [])
        for np_pat in new_official_pats:
            if np_pat not in curr_pats:
                curr_pats.append(np_pat)
        print("Updated official_notice_period")

    # 3. Update city_presence_no
    if "city_presence_no" in patterns:
        p = patterns["city_presence_no"]
        negs = p.setdefault("negative_patterns", [])
        if "attend" in negs:
            negs.remove("attend")
        curr_pats = p.setdefault("patterns", [])
        for pat in [
            "can you confirm if your primary base is chennai",
            "can you confirm if your primary base is chennai?",
            "is your primary base chennai",
            "is your primary base chennai?",
            "primary base is chennai",
            "primary base is hyderabad",
            "primary base is pune",
            "primary base is mumbai",
            "primary base is delhi",
            "primary base is noida",
            "primary base is gurgaon"
        ]:
            if pat not in curr_pats:
                curr_pats.append(pat)
        print("Updated city_presence_no")

    # 4. Update naukri_shift_preference
    if "naukri_shift_preference" in patterns:
        p = patterns["naukri_shift_preference"]
        p["default"] = "Day Job"
        p["input_type_defaults"] = build_input_type_defaults(p, {
            "radio": "Day Job",
            "select": "Day Job",
            "text": "Day Job",
            "textarea": "Day Job",
            "checkbox": "Day Job",
            "number": "0"
        })
        curr_pats = p.setdefault("patterns", [])
        for pat in [
            "please share your shift preference",
            "please share your shift preference?",
            "share your shift preference",
            "share your shift preference?",
            "what is your shift preference"
        ]:
            if pat not in curr_pats:
                curr_pats.append(pat)
        print("Updated naukri_shift_preference")

    # 5. New patterns
    new_patterns = {
        "eligible_and_authorized_to_work_indefinite": {
            "patterns": [
                "are you currently eligible to work in the country outlined for this position, and authorized to work for navan on an ongoing indefinite basis?",
                "are you currently eligible to work in the country outlined for this position, and authorized to work for navan on an ongoing indefinite basis",
                "are you currently eligible to work in the country outlined for this position",
                "authorized to work for navan on an ongoing indefinite basis",
                "authorized to work for navan on an ongoing indefinite basis?",
                "authorized to work on an ongoing indefinite basis?",
                "authorized to work on an ongoing indefinite basis",
                "eligible to work in the country outlined for this position",
                "authorized to work for navan"
            ],
            "category": "work_authorization",
            "default": "Yes",
            "priority": 22,
            "input_type_defaults": {
                "radio": "Yes",
                "select": "Yes",
                "text": "Yes",
                "textarea": "Yes, I am legally eligible and authorized to work on an ongoing indefinite basis.",
                "checkbox": "Yes",
                "number": "1"
            }
        },
        "primary_base_non_bangalore": {
            "patterns": [
                "can you confirm if your primary base is chennai?",
                "can you confirm if your primary base is chennai",
                "is your primary base chennai?",
                "is your primary base chennai",
                "confirm if your primary base is chennai",
                "primary base is chennai",
                "can you confirm if your primary base is hyderabad",
                "can you confirm if your primary base is pune",
                "can you confirm if your primary base is mumbai",
                "can you confirm if your primary base is delhi",
                "can you confirm if your primary base is noida",
                "can you confirm if your primary base is gurgaon",
                "can you confirm if your primary base is ahmedabad",
                "primary base is hyderabad",
                "primary base is pune",
                "primary base is mumbai",
                "primary base is delhi",
                "primary base is noida",
                "primary base is gurgaon",
                "primary base is ahmedabad"
            ],
            "category": "location",
            "default": "No",
            "priority": 22,
            "input_type_defaults": {
                "radio": "No",
                "select": "No",
                "text": "No, currently based in Bengaluru but open to relocation",
                "textarea": "No, I am currently based in Bengaluru, Karnataka, but open to relocation.",
                "checkbox": "No",
                "number": "0"
            }
        },
        "notice_period_years_phrase": {
            "patterns": [
                "how many years of notice period do you have?",
                "how many years of notice period do you have",
                "how many years of notice period",
                "years of notice period do you have?",
                "years of notice period do you have",
                "years of notice period"
            ],
            "category": "notice_period",
            "default": "15 Days",
            "priority": 22,
            "input_type_defaults": {
                "select": "15 Days",
                "radio": "15 Days",
                "text": "15 days",
                "textarea": "15 days",
                "checkbox": "15",
                "number": "15"
            }
        },
        "official_notice_period_in_days": {
            "patterns": [
                "what is your official notice period - mention in days?",
                "what is your official notice period - mention in days",
                "what is your official notice period in days?",
                "what is your official notice period in days",
                "official notice period - mention in days?",
                "official notice period - mention in days",
                "official notice period mention in days",
                "official notice period in days",
                "official notice period (in days)",
                "whats your official notice period?",
                "whats your official notice period"
            ],
            "category": "notice_period",
            "default": "15",
            "priority": 22,
            "input_type_defaults": {
                "text": "15",
                "number": "15",
                "radio": "15",
                "select": "15 Days",
                "textarea": "15",
                "checkbox": "15"
            }
        },
        "shift_preference_options": {
            "patterns": [
                "please share your shift preference",
                "please share your shift preference?",
                "share your shift preference",
                "share your shift preference?",
                "what is your shift preference",
                "what is your shift preference?"
            ],
            "category": "preference",
            "default": "Day Job",
            "priority": 20,
            "input_type_defaults": {
                "checkbox": "Day Job",
                "radio": "Day Job",
                "select": "Day Job",
                "text": "Day Job",
                "textarea": "Day Job",
                "number": "0"
            }
        }
    }

    for pid, pdata in new_patterns.items():
        pdata["input_type_defaults"] = build_input_type_defaults(pdata, pdata.get("input_type_defaults"))
        patterns[pid] = pdata
        print(f"Added pattern: {pid}")

    print(f"Total patterns in memory: {len(patterns)}")
    print(f"Writing to {PATTERNS_FILE}...")
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Done writing qa_patterns.json!")

if __name__ == "__main__":
    apply_fixes()
