"""Script to apply pattern fixes and new patterns identified in qa_results.csv audit (Nov 07, 2026)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_qa_input_types as audit
from patterns.input_type_sanitizer import build_input_type_defaults, CORE_INPUT_TYPES


def append_unique_patterns(entry: dict, new_patterns: list[str]) -> None:
    """Append new pattern variants while preserving existing patterns and their order."""
    existing = list(entry.get("patterns", []))
    for p in new_patterns:
        if p not in existing:
            existing.append(p)
    entry["patterns"] = existing


def add_negative_patterns(entry: dict, new_negs: list[str]) -> None:
    """Add negative patterns to entry as a sorted unique list."""
    negs = set(entry.get("negative_patterns", []))
    negs.update(new_negs)
    entry["negative_patterns"] = sorted(list(negs))


def main():
    json_path = ROOT / "config" / "qa_patterns.json"
    bak_path = ROOT / "config" / "qa_patterns.json.bak"

    print(f"Loading base data from {bak_path} if present, else {json_path}...")
    source_path = bak_path if bak_path.exists() else json_path
    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    patterns = data.setdefault("patterns", {})

    # 1. data_consent: Remove generic word 'confirm'
    if "data_consent" in patterns:
        pats = patterns["data_consent"].get("patterns", [])
        patterns["data_consent"]["patterns"] = [p for p in pats if p.strip().lower() != "confirm"]
        print("Fixed data_consent: removed 'confirm'")

    # 2. currently_working: negative patterns
    if "currently_working" in patterns:
        add_negative_patterns(
            patterns["currently_working"],
            ["technologies", "tech stack", "stack", "tools", "relative", "relatives", "family"],
        )
        print("Updated currently_working negative_patterns")

    # 3. employment_commitment: negative patterns
    if "employment_commitment" in patterns:
        add_negative_patterns(
            patterns["employment_commitment"],
            ["overlap", "u.s.", "us hours", "timezone", "time zone"],
        )
        print("Updated employment_commitment negative_patterns")

    # 4. cpp_experience: negative patterns
    if "cpp_experience" in patterns:
        add_negative_patterns(
            patterns["cpp_experience"],
            ["which of these", "hands-on with -", "c++, java or golang", "c++ java or golang", "which of these development", "programming tool"],
        )
        print("Updated cpp_experience negative_patterns")

    # 5. go_experience: negative patterns
    if "go_experience" in patterns:
        add_negative_patterns(
            patterns["go_experience"],
            ["which of these", "hands-on with -", "c++, java or golang", "c++ java or golang", "which of these development", "programming tool"],
        )
        print("Updated go_experience negative_patterns")

    # 6. certifications: negative patterns
    if "certifications" in patterns:
        add_negative_patterns(
            patterns["certifications"],
            ["dp - 700", "dp-700", "az-104", "az-400", "dp 700", "az 104", "az 400"],
        )
        print("Updated certifications negative_patterns")

    # 7. splunk_experience: negative patterns
    if "splunk_experience" in patterns:
        add_negative_patterns(
            patterns["splunk_experience"],
            ["rating", "rate", "self rating"],
        )
        print("Updated splunk_experience negative_patterns")

    # 8. current_np_status: candidate is serving notice period with 15 days remaining
    if "current_np_status" in patterns:
        patterns["current_np_status"]["default"] = "Serving Notice Period (15 days remaining)"
        patterns["current_np_status"]["priority"] = 18
        patterns["current_np_status"]["input_type_defaults"] = {
            "radio": "Currently In Notice or Serving Notice",
            "select": "Currently In Notice or Serving Notice",
            "text": "Serving Notice Period (15 days remaining)",
            "textarea": "Serving Notice Period (15 days remaining)",
            "checkbox": "Currently In Notice or Serving Notice",
            "number": "15",
        }
        print("Updated current_np_status to reflect serving notice period")

    # 9. relatives_employed_by_company: add general relative questions
    if "relatives_employed_by_company" in patterns:
        grp = patterns["relatives_employed_by_company"]
        append_unique_patterns(
            grp,
            [
                "are any relatives currently employed here? if yes, give the full name of employee working in inchcape",
                "are any relatives currently employed here? if yes, give the full name of employee working in",
                "are any relatives currently employed here? if yes, give the full name",
                "are any relatives currently employed here? if yes",
                "are any relatives currently employed here",
                "are any relatives currently employed",
                "any relatives currently employed here",
                "any relatives currently employed",
                "relatives currently employed here",
                "relatives currently employed",
                "relatives employed here",
                "relatives employed",
                "relatives currently working here",
                "any relatives working here",
                "do you have any relatives currently employed",
                "do you have any relatives currently working",
            ],
        )
        grp["priority"] = 20
        grp["default"] = "No"
        grp["input_type_defaults"] = {
            "text": "No",
            "textarea": "No",
            "radio": "No",
            "select": "No",
            "checkbox": "No",
            "number": "0",
        }
        print("Updated relatives_employed_by_company")

    # 10. us_time_overlap: add 2-4 hours overlap questions
    if "us_time_overlap" in patterns:
        grp = patterns["us_time_overlap"]
        append_unique_patterns(
            grp,
            [
                "are you able to overlap at least 2-4 hours with u.s. working hours",
                "are you able to overlap at least 2-4 hours with us working hours",
                "are you able to overlap at least 2 to 4 hours with u.s. working hours",
                "are you able to overlap at least 2 to 4 hours with us working hours",
                "able to overlap at least 2-4 hours with u.s. working hours",
                "able to overlap at least 2-4 hours with us working hours",
                "overlap at least 2-4 hours with u.s. working hours",
                "overlap at least 2-4 hours with us working hours",
                "overlap at least 2-4 hours",
                "overlap 2-4 hours with u.s. working hours",
                "overlap 2-4 hours with us working hours",
                "overlap 2 to 4 hours with u.s. working hours",
                "overlap 2 to 4 hours with us working hours",
                "overlap 2-4 hours",
                "overlap 2 to 4 hours",
            ],
        )
        grp["priority"] = 20
        grp["default"] = "Yes"
        print("Updated us_time_overlap")

    # 11. location_state: add confirm state patterns while preserving patterns[0]
    if "location_state" in patterns:
        grp = patterns["location_state"]
        append_unique_patterns(
            grp,
            [
                "if the state you currently live in is not listed above, please confirm which state you reside in",
                "if the state you currently live in is not listed above please confirm which state you reside in",
                "if the state you currently live in is not listed above",
                "please confirm which state you reside in",
                "confirm which state you reside in",
                "which state you reside in",
                "state you reside in",
                "confirm state you reside in",
            ],
        )
        grp["priority"] = 18
        print("Updated location_state")

    # 12. immediate_joining_syn: add immediate basis / 7 days
    if "immediate_joining_syn" in patterns:
        grp = patterns["immediate_joining_syn"]
        append_unique_patterns(
            grp,
            [
                "can you join on immediate basis ? max 7 days ? noida location ?",
                "can you join on immediate basis ? max 7 days",
                "can you join on immediate basis",
                "join on immediate basis",
                "max 7 days",
                "max 7 days ? noida location",
            ],
        )
        grp["priority"] = 18
        print("Updated immediate_joining_syn")

    # 13. background_check_and_education_verification_consent: add truncated pattern
    if "background_check_and_education_verification_consent" in patterns:
        grp = patterns["background_check_and_education_verification_consent"]
        append_unique_patterns(
            grp,
            [
                "as part of the employment process, all candidates are subject to employment and education verificati",
                "as part of the employment process, all candidates are subject to employment and education verification",
                "all candidates are subject to employment and education verificati",
                "all candidates are subject to employment and education verification",
            ],
        )
        print("Updated background_check_and_education_verification_consent")

    # 14. NEW: development_programming_tool_hands_on_c_java_golang
    patterns["development_programming_tool_hands_on_c_java_golang"] = {
        "patterns": [
            "which of these development/programming tool are you hands-on with - c++, java or golang",
            "which of these development programming tool are you hands on with - c++, java or golang",
            "which of these development/programming tool are you hands-on with",
            "which of these development programming tool are you hands-on with",
            "which of these development programming tools are you hands-on with",
            "which of these development programming tools are you hands on with",
            "development/programming tool are you hands-on with - c++, java or golang",
            "development programming tool are you hands-on with - c++, java or golang",
            "development programming tool are you hands-on with",
            "development/programming tool are you hands-on with",
            "c++, java or golang",
            "c++ java or golang",
            "c++, java, or golang",
            "which development/programming tool are you hands-on with",
            "which development programming tool are you hands-on with",
            "which programming tool are you hands-on with",
        ],
        "category": "skills",
        "default": "Java",
        "priority": 20,
        "input_type_defaults": {
            "text": "Java",
            "textarea": "Java",
            "radio": "Java",
            "select": "Java",
            "checkbox": "Java",
            "number": "",
        },
    }
    print("Added development_programming_tool_hands_on_c_java_golang")

    # 15. NEW: full_stack_technologies_currently_working_with
    patterns["full_stack_technologies_currently_working_with"] = {
        "patterns": [
            "which full-stack technologies are you currently working with",
            "which full stack technologies are you currently working with",
            "which full-stack technologies are you working with",
            "which full stack technologies are you working with",
            "full-stack technologies are you currently working with",
            "full stack technologies are you currently working with",
            "what full-stack technologies are you currently working with",
            "what full stack technologies are you currently working with",
            "which technologies are you currently working with",
            "technologies are you currently working with",
            "technologies you are currently working with",
            "which full stack technologies do you work with",
            "which full-stack technologies do you work with",
        ],
        "category": "technical",
        "default": "Java, Spring Boot, React, Node.js, Python, PostgreSQL, MongoDB, AWS, Kafka",
        "priority": 20,
        "input_type_defaults": {
            "text": "Java, Spring Boot, React, Node.js, Python, AWS, Kafka",
            "textarea": "Java, Spring Boot, React, Node.js, Python, PostgreSQL, MongoDB, AWS, Kafka",
            "select": "Java, Spring Boot, React",
            "radio": "Java, Spring Boot, React",
            "checkbox": "Java",
            "number": "",
        },
    }
    print("Added full_stack_technologies_currently_working_with")

    # 16. NEW: certifications_dp700_az104_az400
    patterns["certifications_dp700_az104_az400"] = {
        "patterns": [
            "have you done any of the certification below ( dp - 700 or az-104 or az-400)",
            "have you done any of the certification below ( dp-700 or az-104 or az-400)",
            "have you done any of the certification below (dp - 700 or az-104 or az-400)",
            "have you done any of the certification below dp - 700 or az-104 or az-400",
            "have you done any of the certification below",
            "certification below ( dp - 700 or az-104 or az-400)",
            "certification below (dp - 700 or az-104 or az-400)",
            "dp - 700 or az-104 or az-400",
            "dp-700 or az-104 or az-400",
            "dp 700 or az 104 or az 400",
        ],
        "category": "compliance",
        "default": "None",
        "priority": 19,
        "input_type_defaults": {
            "text": "None",
            "textarea": "None",
            "radio": "No",
            "select": "No",
            "checkbox": "No",
            "number": "0",
        },
    }
    print("Added certifications_dp700_az104_az400")

    # 17. NEW: independently_designed_architecture_web_applications
    patterns["independently_designed_architecture_web_applications"] = {
        "patterns": [
            "have you independently designed the architecture of web applications",
            "independently designed the architecture of web applications",
            "have you independently designed the architecture",
            "independently designed the architecture",
            "designed the architecture of web applications",
            "designed architecture of web applications",
            "architecture of web applications",
        ],
        "category": "skills",
        "default": "Yes, I have independently designed and implemented scalable web application architectures using Java Spring Boot microservices, React, and AWS cloud infrastructure.",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "checkbox": "Yes",
            "text": "Yes",
            "textarea": "Yes, I have independently designed and implemented scalable web application architectures using Java Spring Boot microservices, React, and AWS cloud infrastructure.",
            "number": "1",
        },
    }
    print("Added independently_designed_architecture_web_applications")

    # 18. NEW: available_in_30_days_notice_period
    patterns["available_in_30_days_notice_period"] = {
        "patterns": [
            "are you available in 30 days notice period",
            "available in 30 days notice period",
            "are you available in 30 days notice",
            "available in 30 days notice",
            "are you available in 30 days",
            "available in 30 days",
            "are you available within 30 days notice period",
            "available within 30 days notice period",
            "are you available within 30 days notice",
            "available within 30 days notice",
        ],
        "category": "notice_period",
        "default": "Yes",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "text": "Yes",
            "textarea": "Yes, I am available within 15 days.",
            "checkbox": "Yes",
            "number": "15",
        },
    }
    print("Added available_in_30_days_notice_period")

    # 19. NEW: expected_salary_not_more_than_threshold
    patterns["expected_salary_not_more_than_threshold"] = {
        "patterns": [
            "expected salary should not be more than 18 or 19 lpa",
            "expected salary should not be more than",
            "salary should not be more than",
            "expected ctc should not be more than",
            "ctc should not be more than",
        ],
        "category": "salary",
        "default": "Yes",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "text": "Yes",
            "textarea": "Yes",
            "checkbox": "Yes",
            "number": "1",
        },
    }
    print("Added expected_salary_not_more_than_threshold")

    # 20. NEW: notice_period_immediate_to_30_days
    patterns["notice_period_immediate_to_30_days"] = {
        "patterns": [
            "notice period should be immediate to 30 days",
            "notice period should be immediate",
            "notice period should be 0 to 30 days",
            "notice period should be 0-30 days",
            "notice period should be within 30 days",
        ],
        "category": "notice_period",
        "default": "Yes",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "text": "Yes",
            "textarea": "Yes",
            "checkbox": "Yes",
            "number": "15",
        },
    }
    print("Added notice_period_immediate_to_30_days")

    # 21. NEW: self_rating_splunk_dynatrace
    patterns["self_rating_splunk_dynatrace"] = {
        "patterns": [
            "self rating in splunk",
            "self rating in dynatrace",
            "self rating in",
        ],
        "category": "skills",
        "default": "4",
        "priority": 18,
        "input_type_defaults": {
            "radio": "4/5_Advanced",
            "select": "4/5_Advanced",
            "text": "4",
            "textarea": "4",
            "checkbox": "4",
            "number": "4",
        },
    }
    print("Added self_rating_splunk_dynatrace")

    # 22. NEW: position_applied_for
    patterns["position_applied_for"] = {
        "patterns": [
            "position applied for",
            "role applied for",
            "which position are you applying for",
            "position you are applying for",
            "role you are applying for",
        ],
        "category": "role",
        "default": "Software Engineer",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Software Engineer",
            "select": "Software Engineer",
            "text": "Software Engineer 2 (SDE-2)",
            "textarea": "Software Engineer 2 (SDE-2)",
            "checkbox": "Software Engineer",
            "number": "",
        },
    }
    print("Added position_applied_for")

    # 23. NEW: english_communication_and_us_overlap
    patterns["english_communication_and_us_overlap"] = {
        "patterns": [
            "clear written and spoken english and availability for agreed overlap with us eastern am business ho",
            "clear written and spoken english and availability for agreed overlap with us eastern am business hours",
            "clear written and spoken english and availability for agreed overlap",
            "clear written and spoken english",
            "availability for agreed overlap with us eastern am business hours",
            "overlap with us eastern am business hours",
        ],
        "category": "availability",
        "default": "Yes",
        "priority": 18,
        "input_type_defaults": {
            "radio": "Yes",
            "select": "Yes",
            "text": "Yes",
            "textarea": "Yes",
            "checkbox": "Yes",
            "number": "1",
        },
    }
    print("Added english_communication_and_us_overlap")

    # Ensure all modified / new entries have fully compliant input_type_defaults
    checked_keys = [
        "data_consent",
        "currently_working",
        "employment_commitment",
        "cpp_experience",
        "go_experience",
        "certifications",
        "splunk_experience",
        "current_np_status",
        "relatives_employed_by_company",
        "us_time_overlap",
        "location_state",
        "immediate_joining_syn",
        "background_check_and_education_verification_consent",
        "development_programming_tool_hands_on_c_java_golang",
        "full_stack_technologies_currently_working_with",
        "certifications_dp700_az104_az400",
        "independently_designed_architecture_web_applications",
        "available_in_30_days_notice_period",
        "expected_salary_not_more_than_threshold",
        "notice_period_immediate_to_30_days",
        "self_rating_splunk_dynatrace",
        "position_applied_for",
        "english_communication_and_us_overlap",
    ]

    for k in checked_keys:
        if k in patterns:
            patterns[k]["input_type_defaults"] = build_input_type_defaults(
                patterns[k], patterns[k].get("input_type_defaults")
            )

    print("Running audit_qa_input_types on in-memory patterns...")
    audit_res = audit.audit_patterns(data)
    if audit_res["violation_count"] != 0:
        print(f"ERROR: Found {audit_res['violation_count']} violations!", file=sys.stderr)
        for code, examples in audit_res["examples"].items():
            print(f"  {code}: {examples}", file=sys.stderr)
        sys.exit(1)

    print("Audit passed cleanly with 0 violations!")
    print(f"Writing updated data back to {json_path}...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Successfully updated qa_patterns.json!")


if __name__ == "__main__":
    main()
