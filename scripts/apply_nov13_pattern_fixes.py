import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "config" / "qa_patterns.json"

print(f"Loading {JSON_PATH}...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

patterns = data.setdefault("patterns", {})

# 1. lever_application: set requires_exact_match to True
if "lever_application" in patterns:
    patterns["lever_application"]["requires_exact_match"] = True
    print("Fixed lever_application: set requires_exact_match=True")

# 2. pan_card & personal_pan: add variants
pan_variants = [
    "pan no, mandatory for uploading the profile.",
    "pan no, mandatory for uploading the profile",
    "pan no mandatory for uploading the profile",
    "pan no",
    "pan no.",
    "pan number",
    "enter pan",
    "enter your pan",
]
for k in ["pan_card", "personal_pan"]:
    if k in patterns:
        existing = list(patterns[k].get("patterns", []))
        for pv in pan_variants:
            if pv not in existing:
                existing.append(pv)
        patterns[k]["patterns"] = existing
        patterns[k]["priority"] = 22
        print(f"Updated {k} with PAN variants")

# 3. work_authorization_us: update patterns, default, priority, input_type_defaults
us_auth_pats = [
    "are you able to work in the united states?",
    "are you able to work in the united states",
    "able to work in the united states",
    "are you able to work in the us?",
    "are you able to work in the us",
    "able to work in the us",
    "able to work in us",
    "are you able to work in the u.s.?",
    "are you able to work in the u.s.",
    "able to work in the u.s.",
    "are you legally authorized to work in the united states?",
    "are you legally authorized to work in the united states",
    "legally authorized to work in the united states",
    "authorized to work in the united states",
    "are you authorized to work in the united states",
    "are you authorized to work in the us",
    "authorized to work in the us",
]
if "work_authorization_us" in patterns:
    existing = list(patterns["work_authorization_us"].get("patterns", []))
    for p in us_auth_pats:
        if p not in existing:
            existing.append(p)
    patterns["work_authorization_us"]["patterns"] = existing
    patterns["work_authorization_us"]["default"] = "No"
    patterns["work_authorization_us"]["priority"] = 22
    patterns["work_authorization_us"]["input_type_defaults"] = {
        "radio": "No",
        "select": "No",
        "checkbox": "No",
        "text": "No",
        "textarea": "No",
        "number": "0",
    }
    print("Updated work_authorization_us")

# 4. exp_cloudformation: add negative patterns
if "exp_cloudformation" in patterns:
    negs = list(patterns["exp_cloudformation"].get("negative_patterns", []))
    for n in ["explain", "please explain", "describe", "experience with"]:
        if n not in negs:
            negs.append(n)
    patterns["exp_cloudformation"]["negative_patterns"] = negs
    print("Updated exp_cloudformation negative_patterns")

# 5. cloudformation_experience_explanation
patterns["cloudformation_experience_explanation"] = {
    "patterns": [
        "have you worked with cloudformation? please explain your experience.",
        "have you worked with cloudformation? please explain your experience",
        "have you worked with cloudformation please explain your experience",
        "have you worked with cloudformation",
        "please explain your cloudformation experience",
        "explain your experience with cloudformation",
    ],
    "category": "technical_screening",
    "default": "Yes, I have worked with AWS CloudFormation and Terraform to automate infrastructure provisioning, defining YAML templates for VPCs, ECS task definitions, S3 buckets, and RDS instances with automated rollback and parameterization.",
    "priority": 22,
    "input_type_defaults": {
        "text": "Yes, I have worked with AWS CloudFormation and Terraform to automate infrastructure provisioning, defining YAML templates for VPCs, ECS task definitions, S3 buckets, and RDS instances with automated rollback and parameterization.",
        "textarea": "Yes, I have worked with AWS CloudFormation and Terraform to automate infrastructure provisioning, defining YAML templates for VPCs, ECS task definitions, S3 buckets, and RDS instances with automated rollback and parameterization.",
        "radio": "Yes",
        "select": "Yes",
        "checkbox": "Yes",
        "number": "1",
    },
}
print("Added cloudformation_experience_explanation")

# 6. us_hours_acceptable
patterns["us_hours_acceptable"] = {
    "patterns": [
        "this job requires working us hours i.e. from 7pm india time to 4am india time. is that acceptable? i",
        "this job requires working us hours i.e. from 7pm india time to 4am india time. is that acceptable?",
        "this job requires working us hours i.e. from 7pm india time to 4am india time",
        "working us hours i.e. from 7pm india time to 4am india time",
        "working us hours from 7pm india time to 4am india time",
        "this job requires working us hours",
    ],
    "category": "work_mode",
    "default": "Yes",
    "priority": 22,
    "input_type_defaults": {
        "radio": "Yes",
        "select": "Yes",
        "checkbox": "Yes",
        "text": "Yes",
        "textarea": "Yes",
        "number": "1",
    },
}
print("Added us_hours_acceptable")

# 7. exp_gate_over_5_years
patterns["exp_gate_over_5_years"] = {
    "patterns": [
        "do you have 7–10 years of overall it experience?",
        "do you have 7–10 years of overall it experience",
        "do you have 7-10 years of overall it experience",
        "do you have 7 to 10 years of overall it experience",
        "do you have 6+ years of experience with node.js and typescript development?",
        "do you have 6+ years of  experience with node.js and typescript development?",
        "do you have 6+ years of experience with node.js and typescript development",
        "do you have at least 5 to 7 years of hands-on production experience using both react.js/react native",
        "do you have at least 5 to 7 years of hands-on production experience",
        "do you have 10 plus years of experience?",
        "do you have 10 plus years of experience",
        "do you have 10+ years of experience",
        "do you have 8+ years of experience",
        "do you have 7+ years of experience",
        "do you have 6+ years of experience",
        "do you have 5+ years of experience",
    ],
    "category": "experience",
    "default": "No",
    "priority": 22,
    "input_type_defaults": {
        "radio": "No",
        "select": "No",
        "checkbox": "No",
        "text": "No - I have 4.2 years of total professional software engineering experience.",
        "textarea": "No - I have 4.2 years of total professional software engineering experience.",
        "number": "4",
    },
}
print("Added exp_gate_over_5_years")

# 8. notice_period_in_weeks
patterns["notice_period_in_weeks"] = {
    "patterns": [
        "what is your notice period? in weeks?",
        "what is your notice period in weeks?",
        "what is your notice period in weeks",
        "notice period? in weeks?",
        "notice period in weeks?",
        "notice period in weeks",
        "notice period? in weeks",
        "notice period (in weeks)",
        "notice period (weeks)",
        "notice period in no of weeks",
        "notice period in number of weeks",
    ],
    "category": "notice_period",
    "default": "2 Weeks",
    "priority": 22,
    "input_type_defaults": {
        "number": "2",
        "text": "2 Weeks",
        "textarea": "2 Weeks (15 days notice period, currently serving)",
        "radio": "2",
        "select": "2 Weeks",
        "checkbox": "2",
    },
}
print("Added notice_period_in_weeks")

# 9. serving_notice_period_when_is_lwd
patterns["serving_notice_period_when_is_lwd"] = {
    "patterns": [
        "if serving notice period, when is your last working day with your employer?",
        "if serving notice period when is your last working day with your employer",
        "if serving notice period, when is your last working day",
        "if serving notice period when is your last working day",
        "when is your last working day with your employer",
        "when is your last working day with your current employer",
        "mention your last working day with your employer",
        "mention your last working day",
    ],
    "category": "notice_period",
    "default": "__DYNAMIC_LWD__",
    "dynamic_answer": True,
    "priority": 22,
    "input_type_defaults": {
        "text": "__DYNAMIC_LWD__",
        "textarea": "__DYNAMIC_LWD__",
        "date": "__DYNAMIC_LWD__",
        "radio": "Serving Notice Period",
        "select": "Serving Notice Period",
        "checkbox": "Serving Notice Period",
        "number": "15",
    },
}
print("Added serving_notice_period_when_is_lwd")

# 10. official_notice_period_or_serving_lwd
patterns["official_notice_period_or_serving_lwd"] = {
    "patterns": [
        "your official notice period or if serving lwd?",
        "your official notice period or if serving lwd",
        "official notice period or if serving lwd",
        "official notice period or if serving lwd?",
        "what is your official notice period or if serving lwd",
    ],
    "category": "notice_period",
    "default": "15 Days (Serving Notice Period, LWD: __DYNAMIC_LWD__)",
    "dynamic_answer": True,
    "priority": 22,
    "input_type_defaults": {
        "text": "15 Days (Serving Notice Period, LWD: __DYNAMIC_LWD__)",
        "textarea": "15 Days (Serving Notice Period, LWD: __DYNAMIC_LWD__)",
        "number": "15",
        "radio": "15 Days",
        "select": "15 Days",
        "checkbox": "15 Days",
    },
}
print("Added official_notice_period_or_serving_lwd")

# 11. production_grade_application_description
patterns["production_grade_application_description"] = {
    "patterns": [
        "briefly describe a production-grade application you built or significantly contributed to. what was the scale and your specific role?",
        "briefly describe a production-grade application you built or significantly contributed to",
        "describe a production-grade application you built or significantly contributed to",
        "describe a production-grade application you built",
        "describe a production grade application you built",
        "production-grade application you built or significantly contributed to",
        "production-grade application you built",
        "production grade application you built",
    ],
    "category": "technical_screening",
    "default": "At Everbridge, I architected and built an event-driven notification dispatch pipeline using Java 21, Spring Boot, and Apache Kafka handling over 10M alerts daily. My role was backend lead: designed the multi-AZ deployment on AWS ECS/EKS, PostgreSQL with read replicas, Redis caching for recipient state (<5ms latency), and implemented Transactional Outbox pattern with idempotent consumers to guarantee zero message loss.",
    "priority": 22,
    "input_type_defaults": {
        "text": "At Everbridge, I architected and built an event-driven notification dispatch pipeline using Java 21, Spring Boot, and Apache Kafka handling over 10M alerts daily. My role was backend lead: designed the multi-AZ deployment on AWS ECS/EKS, PostgreSQL with read replicas, Redis caching for recipient state (<5ms latency), and implemented Transactional Outbox pattern with idempotent consumers to guarantee zero message loss.",
        "textarea": "At Everbridge, I architected and built an event-driven notification dispatch pipeline using Java 21, Spring Boot, and Apache Kafka handling over 10M alerts daily. My role was backend lead: designed the multi-AZ deployment on AWS ECS/EKS, PostgreSQL with read replicas, Redis caching for recipient state (<5ms latency), and implemented Transactional Outbox pattern with idempotent consumers to guarantee zero message loss.",
        "radio": "Yes",
        "select": "Yes",
        "checkbox": "Yes",
        "number": "1",
    },
}
print("Added production_grade_application_description")

# 12. loc_current_in_vizag
patterns["loc_current_in_vizag"] = {
    "patterns": [
        "are you currently in vizag?",
        "are you currently in vizag",
        "are you in vizag",
        "currently in vizag",
        "if you are not currently in vizag are you originally from vizag or nearby?",
        "if you are not currently in vizag are you originally from vizag or nearby",
        "are you originally from vizag or nearby",
    ],
    "category": "location",
    "default": "No",
    "priority": 22,
    "input_type_defaults": {
        "radio": "No",
        "select": "No",
        "checkbox": "No",
        "text": "No, currently based in Bengaluru but open to relocation.",
        "textarea": "No, currently based in Bengaluru but open to relocation.",
        "number": "0",
    },
}
print("Added loc_current_in_vizag")

# 13. loc_based_in_delhi
patterns["loc_based_in_delhi"] = {
    "patterns": [
        "are you based in delhi?",
        "are you based in delhi",
        "currently based in delhi",
        "are you located in delhi",
    ],
    "category": "location",
    "default": "No",
    "priority": 22,
    "negative_patterns": ["relocate", "relocation", "willing to relocate", "open to relocate", "ready to relocate"],
    "input_type_defaults": {
        "radio": "No",
        "select": "No",
        "checkbox": "No",
        "text": "No, currently based in Bengaluru but open to relocation.",
        "textarea": "No, currently based in Bengaluru but open to relocation.",
        "number": "0",
    },
}
print("Added loc_based_in_delhi")

# 14. lang_arabic
patterns["lang_arabic"] = {
    "patterns": [
        "are you fluent in arabic (spoken and written)?",
        "are you fluent in arabic (spoken and written)",
        "are you fluent in arabic?",
        "are you fluent in arabic",
        "fluent in arabic",
        "do you speak arabic",
        "arabic language proficiency",
        "arabic fluency",
    ],
    "category": "skills",
    "default": "No",
    "priority": 22,
    "input_type_defaults": {
        "radio": "No",
        "select": "Not Fluent",
        "text": "No",
        "textarea": "No",
        "checkbox": "No",
        "number": "0",
    },
}
print("Added lang_arabic")

# 15. shift_preference: ensure Day Job default
if "shift_preference" in patterns:
    patterns["shift_preference"]["default"] = "Day Job"
    patterns["shift_preference"]["priority"] = 22
    patterns["shift_preference"]["input_type_defaults"] = {
        "checkbox": "Day Job",
        "radio": "Day Job",
        "select": "Day Job",
        "text": "Day Job",
        "textarea": "Day Job",
        "number": "1",
    }
    existing = list(patterns["shift_preference"].get("patterns", []))
    for sp in ["please share your shift preference", "share your shift preference"]:
        if sp not in existing:
            existing.append(sp)
    patterns["shift_preference"]["patterns"] = existing
    print("Updated shift_preference to Day Job")

# Save back to json
tmp_path = str(JSON_PATH) + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
os.replace(tmp_path, JSON_PATH)
print("Successfully written updated qa_patterns.json")
