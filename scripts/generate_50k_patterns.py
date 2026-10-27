"""
Generate 50,000+ resilient Q&A patterns for Job Platforms (LinkedIn, Naukri, Instahyre).
Strictly follows the schemas, priorities, and candidate profile in AGENTS.md.
"""

import argparse
import copy
import json
import os
import re
import shutil
import sys
import time
from typing import Dict, Any, List, Set, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import scripts.taxonomy_data as td

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "qa_patterns.json")

def clean_trigger(text: str) -> str:
    """Normalize trigger string: lowercase, remove punctuation, single spaces."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split()).strip()

def sanitize_slug(text: str) -> str:
    """Create a clean snake_case slug."""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def generate_non_technical_patterns(
    existing_patterns: Dict[str, Any],
    existing_triggers: Set[str],
    new_patterns: Dict[str, Any],
    new_triggers: Set[str]
):
    """Generate comprehensive non-technical patterns for job applications."""
    # 1. Locations across India and major international hubs
    locations = [
        ("bangalore", "Bangalore"), ("bengaluru", "Bengaluru"), ("hyderabad", "Hyderabad"),
        ("pune", "Pune"), ("mumbai", "Mumbai"), ("gurgaon", "Gurgaon"), ("gurugram", "Gurugram"),
        ("noida", "Noida"), ("delhi", "Delhi"), ("delhi_ncr", "Delhi NCR"), ("chennai", "Chennai"),
        ("kolkata", "Kolkata"), ("ahmedabad", "Ahmedabad"), ("kochi", "Kochi"), ("chandigarh", "Chandigarh"),
        ("jaipur", "Jaipur"), ("indore", "Indore"), ("coimbatore", "Coimbatore"), ("bhubaneswar", "Bhubaneswar"),
        ("trivandrum", "Trivandrum"), ("thiruvananthapuram", "Thiruvananthapuram"), ("nagpur", "Nagpur"),
        ("mysore", "Mysore"), ("mysuru", "Mysuru"), ("vadodara", "Vadodara"), ("visakhapatnam", "Visakhapatnam"),
        ("lucknow", "Lucknow"), ("kanpur", "Kanpur"), ("dehradun", "Dehradun"), ("bhopal", "Bhopal"),
        ("united_states", "United States"), ("united_kingdom", "United Kingdom"), ("canada", "Canada"),
        ("singapore", "Singapore"), ("dubai", "Dubai"), ("remote_india", "Remote anywhere in India")
    ]

    for loc_slug, loc_name in locations:
        loc_lower = loc_name.lower()
        
        # Relocation willingness
        pid = f"loc_relocate_openness_{loc_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                f"are you open to relocate to {loc_lower}",
                f"willing to relocate to {loc_lower}",
                f"are you willing to relocate to {loc_lower}",
                f"comfortable relocating to {loc_lower} for this opportunity",
                f"open to moving to {loc_lower} for this position"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": "location",
                    "default": "Yes",
                    "priority": 8,
                    "input_type_defaults": {"radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "Yes"}
                }

        # Current location confirmation
        pid2 = f"loc_current_residence_{loc_slug}"
        if pid2 not in existing_patterns and pid2 not in new_patterns:
            trigs2 = []
            for t in [
                f"do you currently reside in {loc_lower}",
                f"are you currently based in {loc_lower}",
                f"is your current home location {loc_lower}",
                f"are you located in {loc_lower}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs2.append(c)
                    new_triggers.add(c)
            if trigs2:
                ans = "Yes" if "bangalore" in loc_slug or "bengaluru" in loc_slug else "No, currently in Bengaluru but open to relocate"
                new_patterns[pid2] = {
                    "patterns": trigs2,
                    "category": "location",
                    "default": ans,
                    "priority": 8,
                    "input_type_defaults": {"radio": "Yes" if "bangalore" in loc_slug or "bengaluru" in loc_slug else "No", "select": ans, "text": ans}
                }

        # Preferred interview location
        pid3 = f"loc_interview_preference_{loc_slug}"
        if pid3 not in existing_patterns and pid3 not in new_patterns:
            trigs3 = []
            for t in [
                f"preferred interview location {loc_lower}",
                f"can you attend interview in {loc_lower}",
                f"available for in person interview in {loc_lower}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs3.append(c)
                    new_triggers.add(c)
            if trigs3:
                new_patterns[pid3] = {
                    "patterns": trigs3,
                    "category": "availability",
                    "default": "Yes, available for in-person or virtual interviews",
                    "priority": 8,
                    "input_type_defaults": {"radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "Yes"}
                }

    # 2. Work Mode & Shift Timings
    work_modes = [
        ("hybrid_model", "hybrid work model", "Yes, fully comfortable working in a hybrid arrangement"),
        ("work_from_office_5days", "working 5 days from office", "Yes, 100% open to working from office"),
        ("work_from_office_3days", "working 3 days from office and 2 days remote", "Yes, fully comfortable with 3 days in office"),
        ("work_from_office_2days", "working 2 days from office and 3 days remote", "Yes, fully comfortable with 2 days in office"),
        ("rotational_shifts", "working in rotational shifts", "Yes, comfortable with rotational shifts"),
        ("us_shift_overlap", "working in US time zone overlap hours", "Yes, comfortable with US shift overlap"),
        ("uk_shift_overlap", "working in UK European time zone hours", "Yes, comfortable with UK European hours"),
        ("night_shift_flexibility", "working in night shifts when required", "Yes, open and flexible with night shifts"),
        ("weekend_oncall_support", "providing weekend on-call production support", "Yes, experienced with on-call rotation and production support"),
        ("24_7_incident_rotation", "participating in 24 7 incident response rotation", "Yes, experienced with 24/7 incident response"),
        ("travel_readiness", "readiness to travel for client meetings or company events", "Yes, ready and willing to travel as needed"),
        ("bring_your_own_device", "bring your own device byod policy compliance", "Yes, comply with company BYOD security standards"),
        ("dedicated_home_workspace", "having a quiet dedicated workspace and high-speed internet", "Yes, have a dedicated quiet home workspace with high-speed fiber internet and power backup")
    ]

    for wm_slug, wm_text, wm_ans in work_modes:
        pid = f"work_mode_preference_{wm_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                f"are you comfortable with {wm_text}",
                f"open to {wm_text}",
                f"willingness for {wm_text}",
                f"can you commit to {wm_text}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": "work_mode",
                    "default": wm_ans,
                    "priority": 9,
                    "input_type_defaults": {"radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "Yes", "textarea": wm_ans}
                }

    # 3. Notice Period, Joining & Availability
    notice_scenarios = [
        ("serving_notice_confirmation", "are you currently serving your notice period", "Yes, currently serving notice period"),
        ("15_days_official_notice", "is your official notice period 15 days", "Yes, 15 days"),
        ("immediate_joining_possibility", "can you join immediately or within 15 days", "Yes, can join in 15 days"),
        ("buyout_negotiation_openness", "is notice period buyout an option", "Yes, open to buyout discussions if required"),
        ("last_working_day_inquiry", "do you have a confirmed last working day", "__DYNAMIC_LWD__"),
        ("resignation_submitted_status", "have you officially submitted your resignation", "Yes, resignation submitted and serving notice"),
        ("early_release_negotiable", "is an early release possible with your current employer", "Yes, early release is negotiable within 15 days"),
        ("joining_timeline_in_days", "how many days do you need to join after offer", "15 days"),
        ("notice_period_duration_in_days", "what is your notice period in days", "15 days"),
        ("available_for_video_call", "are you available for a video call interview", "Yes, available on Google Meet, Zoom, or Teams"),
        ("interview_slot_flexibility", "are you flexible with interview scheduling slots", "Yes, flexible across morning, afternoon, and evening slots")
    ]

    for np_slug, np_q, np_ans in notice_scenarios:
        pid = f"np_scenario_{np_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                np_q,
                f"please confirm {np_q}",
                f"candidate inquiry {np_q}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": "notice_period",
                    "default": np_ans,
                    "priority": 10,
                    "input_type_defaults": {
                        "radio": "Yes" if "Yes" in np_ans else "15",
                        "select": np_ans,
                        "text": np_ans,
                        "number": "15" if "15" in np_ans else None,
                        "textarea": np_ans
                    }
                }

    # 4. Compensation & Salary
    comp_scenarios = [
        ("current_ctc_fixed_lpa", "what is your current fixed ctc in lpa", "23 LPA"),
        ("current_annual_gross_inr", "what is your current annual gross salary in inr", "2300000"),
        ("expected_ctc_fixed_lpa", "what is your expected fixed ctc in lpa", "30 LPA"),
        ("expected_annual_gross_inr", "what is your expected annual gross salary in inr", "3000000"),
        ("variable_pay_current_percentage", "what is your current variable pay percentage", "0% (100% Fixed CTC)"),
        ("current_take_home_monthly", "what is your approximate monthly take home salary", "150000 INR"),
        ("salary_slips_availability", "can you provide the last 3 months salary slips", "Yes, all salary slips and bank statements are available"),
        ("holding_competing_offers", "do you currently have any competing job offers in hand", "No, no active offers in hand"),
        ("expected_hike_percentage", "what percentage hike are you expecting on your current ctc", "30%"),
        ("form_16_tax_documents", "can you provide form 16 and income tax computation", "Yes, Form 16 and tax returns are available")
    ]

    for comp_slug, comp_q, comp_ans in comp_scenarios:
        pid = f"comp_scenario_{comp_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                comp_q,
                f"please mention {comp_q}",
                f"details of {comp_q}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": "salary",
                    "default": comp_ans,
                    "priority": 10,
                    "input_type_defaults": {
                        "radio": "23" if "23" in comp_ans else ("30" if "30" in comp_ans else "Yes"),
                        "select": comp_ans,
                        "text": comp_ans,
                        "number": "2300000" if "2300000" in comp_ans else ("3000000" if "3000000" in comp_ans else None),
                        "text_inr": "2300000" if "23" in comp_ans else "3000000",
                        "textarea": comp_ans
                    }
                }

    # 5. Education, Academics & Credentials
    edu_scenarios = [
        ("highest_qualification_degree", "what is your highest educational qualification", "B.Tech in Computer Science"),
        ("undergraduate_college_name", "which university or institute did you graduate from", "VIT Bhopal University"),
        ("graduation_completion_year", "what was your year of graduation from college", "2022"),
        ("active_backlogs_status", "do you have any active backlogs or supplementary exams", "No, 0 backlogs"),
        ("education_gap_years", "do you have any gap years during your education", "No, 0 years gap"),
        ("regular_fulltime_degree", "was your degree program regular and full time", "Yes, regular full-time campus program"),
        ("educational_certificates_availability", "do you possess all original degree certificates and mark sheets", "Yes, all degree certificates and transcripts are available"),
        ("btech_computer_science_specialization", "did you major in computer science and engineering", "Yes, B.Tech in Computer Science and Engineering"),
        ("academic_cgpa_percentage", "what was your overall academic score or cgpa", "8.2 CGPA"),
        ("tenth_standard_board_details", "what was your 10th standard secondary board", "CBSE Board - 88%"),
        ("twelfth_standard_board_details", "what was your 12th standard senior secondary board", "CBSE Board - 85%")
    ]

    for edu_slug, edu_q, edu_ans in edu_scenarios:
        pid = f"edu_scenario_{edu_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                edu_q,
                f"state your {edu_q}",
                f"verification of {edu_q}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": "education",
                    "default": edu_ans,
                    "priority": 9,
                    "input_type_defaults": {
                        "radio": "Yes" if "Yes" in edu_ans else ("No" if "No" in edu_ans else "B.Tech"),
                        "select": edu_ans,
                        "text": edu_ans,
                        "textarea": edu_ans
                    }
                }

    # 6. Compliance, Legal & Work Authorization
    comp_legal = [
        ("indian_citizenship_status", "are you an indian citizen", "Yes, Indian citizen"),
        ("work_authorization_india", "are you legally authorized to work in india", "Yes, authorized to work in India"),
        ("visa_sponsorship_needed", "do you require visa sponsorship now or in the future", "No, no sponsorship needed"),
        ("criminal_records_check", "have you ever been convicted of any criminal offense", "No, clear criminal record"),
        ("pending_court_proceedings", "are there any pending legal or criminal proceedings against you", "No, none"),
        ("past_disciplinary_actions", "have you faced any disciplinary action at previous employers", "No, none"),
        ("non_compete_restrictive_covenants", "are you bound by any non compete or non solicitation agreement", "No, no restrictive covenants"),
        ("conflict_of_interest_clients", "do you have any conflict of interest with our organization or clients", "No, no conflict of interest"),
        ("background_verification_consent", "do you consent to a standard third party background verification bgv", "Yes, fully consent to background verification"),
        ("valid_passport_possession", "do you hold a valid passport for official travel", "Yes, possess a valid Indian passport"),
        ("pan_and_aadhaar_identification", "do you possess a valid pan card and aadhaar card", "Yes, have valid PAN and Aadhaar")
    ]

    for leg_slug, leg_q, leg_ans in comp_legal:
        pid = f"compliance_legal_{leg_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                leg_q,
                f"confirmation on whether {leg_q}",
                f"declaration {leg_q}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                cat = "work_authorization" if "visa" in leg_slug or "citizen" in leg_slug or "work_auth" in leg_slug else "compliance"
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": cat,
                    "default": leg_ans,
                    "priority": 9,
                    "input_type_defaults": {
                        "radio": "Yes" if "Yes" in leg_ans else "No",
                        "select": leg_ans,
                        "text": leg_ans,
                        "checkbox": "Yes" if "Yes" in leg_ans else "No"
                    }
                }

    # 7. Employment History & Role Details
    emp_scenarios = [
        ("current_employer_name", "who is your current employer or organization", "Everbridge"),
        ("current_job_title", "what is your current designation or job title", "Software Engineer 2 (SDE-2)"),
        ("current_employment_type", "what is your current employment type permanent or contract", "Full-time Permanent"),
        ("total_software_engineering_exp", "what is your total professional software engineering experience", "4.2 Years"),
        ("team_size_current_role", "what is the size of your current engineering team", "6-10 engineers"),
        ("reason_for_job_change", "what is your primary reason for seeking a job change", "Seeking new technical challenges, career advancement, and high-impact distributed systems engineering opportunities"),
        ("individual_contributor_vs_lead", "are you an individual contributor or people manager", "Individual Contributor (SDE-2)"),
        ("daily_agile_ceremonies", "do you participate in daily standups and agile sprint ceremonies", "Yes, actively participate in daily standups, sprint planning, retrospectives, and backlog refinement"),
        ("peer_code_review_process", "do you conduct regular peer code reviews and pr approvals", "Yes, review code daily ensuring design patterns, test coverage, static analysis, and security best practices"),
        ("incident_oncall_triage", "experience triaging live production incidents and outages", "Yes, experience participating in on-call rotations, diagnosing live issues via distributed traces, metrics, and logs, and writing post-mortem RCAs")
    ]

    for emp_slug, emp_q, emp_ans in emp_scenarios:
        pid = f"employment_details_{emp_slug}"
        if pid not in existing_patterns and pid not in new_patterns:
            trigs = []
            for t in [
                emp_q,
                f"state your {emp_q}",
                f"provide details for {emp_q}"
            ]:
                c = clean_trigger(t)
                if c and c not in existing_triggers and c not in new_triggers:
                    trigs.append(c)
                    new_triggers.add(c)
            if trigs:
                cat = "experience" if "exp" in emp_slug else "employment"
                new_patterns[pid] = {
                    "patterns": trigs,
                    "category": cat,
                    "default": emp_ans,
                    "priority": 9,
                    "input_type_defaults": {
                        "radio": "4.2" if "4.2" in emp_ans else "Yes",
                        "select": emp_ans,
                        "text": emp_ans,
                        "textarea": emp_ans
                    }
                }

def generate_technical_patterns(
    target_count: int,
    existing_patterns: Dict[str, Any],
    existing_triggers: Set[str],
    new_patterns: Dict[str, Any],
    new_triggers: Set[str]
):
    """
    Generate technical patterns across 5 orthogonal dimensions for each (technology, feature) pair
    until target count is reached.
    """
    total_needed = target_count - len(new_patterns)
    if total_needed <= 0:
        return

    print(f"Generating technical patterns to reach target (needed: {total_needed})...")

    # Dimensions definition:
    # 1. Experience: exp_{tech}_{feature}
    # 2. Hands-on Skill: skill_{tech}_{feature}_hands_on
    # 3. Rating: rate_{tech}_{feature}_proficiency
    # 4. Enterprise Architecture: arch_{tech}_{feature}_enterprise
    # 5. Automated QA Testing: test_{tech}_{feature}_validation

    for tech_slug, tech_name in td.TECHNOLOGIES:
        for feat_slug, feat_name in td.FEATURES:
            if len(new_patterns) >= target_count:
                break

            tech_clean = clean_trigger(tech_name)
            feat_clean = clean_trigger(feat_name)

            # DIMENSION 1: Experience in years
            pid1 = f"exp_{tech_slug}_{feat_slug}"
            if pid1 not in existing_patterns and pid1 not in new_patterns:
                trigs1 = []
                for t in [
                    f"how many years of experience do you have with {tech_clean} {feat_clean}",
                    f"years of experience in {tech_clean} {feat_clean}",
                    f"professional experience with {tech_clean} {feat_clean}"
                ]:
                    c = clean_trigger(t)
                    if c and c not in existing_triggers and c not in new_triggers:
                        trigs1.append(c)
                        new_triggers.add(c)
                if trigs1:
                    new_patterns[pid1] = {
                        "patterns": trigs1,
                        "category": "experience",
                        "default": "4.2 Years",
                        "priority": 10,
                        "negative_patterns": ["salary", "ctc", "notice period", "expected ctc", "current ctc"],
                        "input_type_defaults": {
                            "radio": "4.2",
                            "select": "4.2 Years",
                            "text": "4.2 Years",
                            "number": "4.2",
                            "textarea": f"4.2 Years of professional experience applying {tech_name} for {feat_name}."
                        }
                    }

            if len(new_patterns) >= target_count:
                break

            # DIMENSION 2: Hands-on skills & production implementation
            pid2 = f"skill_{tech_slug}_{feat_slug}_hands_on"
            if pid2 not in existing_patterns and pid2 not in new_patterns:
                trigs2 = []
                for t in [
                    f"do you have hands on experience with {tech_clean} {feat_clean}",
                    f"have you worked with {tech_clean} {feat_clean} in production",
                    f"are you proficient in {tech_clean} {feat_clean}"
                ]:
                    c = clean_trigger(t)
                    if c and c not in existing_triggers and c not in new_triggers:
                        trigs2.append(c)
                        new_triggers.add(c)
                if trigs2:
                    default_ans = f"Yes, extensive hands-on experience in production environments: implementing and optimizing {tech_name} for {feat_name} with high reliability and performance."
                    new_patterns[pid2] = {
                        "patterns": trigs2,
                        "category": "skills",
                        "default": default_ans,
                        "priority": 12,
                        "input_type_defaults": {
                            "radio": "Yes",
                            "select": "Yes",
                            "text": "Yes",
                            "checkbox": "Yes",
                            "textarea": default_ans
                        }
                    }

            if len(new_patterns) >= target_count:
                break

            # DIMENSION 3: Skill rating out of 5
            pid3 = f"rate_{tech_slug}_{feat_slug}_proficiency"
            if pid3 not in existing_patterns and pid3 not in new_patterns:
                trigs3 = []
                for t in [
                    f"rate your proficiency in {tech_clean} {feat_clean} on a scale of 1 to 5",
                    f"rate your skill in {tech_clean} {feat_clean} 1 to 5",
                    f"how would you rate your expertise in {tech_clean} {feat_clean} out of 5"
                ]:
                    c = clean_trigger(t)
                    if c and c not in existing_triggers and c not in new_triggers:
                        trigs3.append(c)
                        new_triggers.add(c)
                if trigs3:
                    new_patterns[pid3] = {
                        "patterns": trigs3,
                        "category": "skills",
                        "default": "5",
                        "priority": 11,
                        "input_type_defaults": {
                            "radio": "5",
                            "select": "5",
                            "text": "5",
                            "number": "5"
                        }
                    }

            if len(new_patterns) >= target_count:
                break

            # DIMENSION 4: Architecture & Enterprise Best Practices
            pid4 = f"arch_{tech_slug}_{feat_slug}_enterprise"
            if pid4 not in existing_patterns and pid4 not in new_patterns:
                trigs4 = []
                for t in [
                    f"how do you architect {tech_clean} {feat_clean} at scale",
                    f"best practices for {tech_clean} {feat_clean} in enterprise systems",
                    f"production architecture for {tech_clean} {feat_clean}"
                ]:
                    c = clean_trigger(t)
                    if c and c not in existing_triggers and c not in new_triggers:
                        trigs4.append(c)
                        new_triggers.add(c)
                if trigs4:
                    arch_ans = f"Architected and deployed {tech_name} {feat_name} following industry best practices: automated failover, distributed tracing, sub-second latency, and horizontal scalability."
                    new_patterns[pid4] = {
                        "patterns": trigs4,
                        "category": "skills",
                        "default": arch_ans,
                        "priority": 13,
                        "input_type_defaults": {
                            "radio": "Yes",
                            "select": "Yes",
                            "text": "Yes",
                            "textarea": arch_ans
                        }
                    }

            if len(new_patterns) >= target_count:
                break

            # DIMENSION 5: Automated Testing & Validation QA
            pid5 = f"test_{tech_slug}_{feat_slug}_validation"
            if pid5 not in existing_patterns and pid5 not in new_patterns:
                trigs5 = []
                for t in [
                    f"experience with automated testing and validation for {tech_clean} {feat_clean}",
                    f"how do you test and verify {tech_clean} {feat_clean} in ci cd",
                    f"automated test strategy for {tech_clean} {feat_clean}"
                ]:
                    c = clean_trigger(t)
                    if c and c not in existing_triggers and c not in new_triggers:
                        trigs5.append(c)
                        new_triggers.add(c)
                if trigs5:
                    test_ans = f"Yes, comprehensive automated testing for {tech_name} {feat_name} with unit tests, integration testcontainers, and automated validation in CI/CD pipelines."
                    new_patterns[pid5] = {
                        "patterns": trigs5,
                        "category": "skills",
                        "default": test_ans,
                        "priority": 12,
                        "input_type_defaults": {
                            "radio": "Yes",
                            "select": "Yes",
                            "text": "Yes",
                            "checkbox": "Yes",
                            "textarea": test_ans
                        }
                    }

        if len(new_patterns) >= target_count:
            break

def main():
    parser = argparse.ArgumentParser(description="Generate 50,000+ Q&A patterns for Job Platforms")
    parser.add_argument("--target-count", type=int, default=50000, help="Number of new pattern groups to generate")
    parser.add_argument("--file", default=PATTERNS_FILE, help="Path to config/qa_patterns.json")
    parser.add_argument("--apply", action="store_true", help="Write changes to qa_patterns.json")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without modifying files")
    args = parser.parse_args()

    target_count = args.target_count
    file_path = os.path.abspath(args.file)

    print(f"Loading patterns from {file_path}...")
    t0 = time.time()
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_patterns = data.get("patterns", {})
    existing_triggers = set()
    for gid, gdata in existing_patterns.items():
        for p in gdata.get("patterns", []):
            existing_triggers.add(p.lower().strip())

    initial_groups = len(existing_patterns)
    initial_strings = sum(len(v.get("patterns", [])) for v in existing_patterns.values())
    print(f"Initial status: {initial_groups} groups, {initial_strings} question strings ({len(existing_triggers)} unique triggers).")

    new_patterns: Dict[str, Any] = {}
    new_triggers: Set[str] = set()

    # Step 1: Generate rich non-technical domain patterns
    print("Generating non-technical domain patterns...")
    generate_non_technical_patterns(existing_patterns, existing_triggers, new_patterns, new_triggers)
    print(f"Non-technical patterns generated: {len(new_patterns)} groups, {len(new_triggers)} triggers.")

    # Step 2: Generate technical patterns to reach target count
    print(f"Generating technical patterns up to target count {target_count}...")
    generate_technical_patterns(target_count, existing_patterns, existing_triggers, new_patterns, new_triggers)

    total_new_groups = len(new_patterns)
    total_new_strings = sum(len(v.get("patterns", [])) for v in new_patterns.values())

    print("\n" + "="*60)
    print("PATTERN GENERATION SUMMARY:")
    print(f"  New pattern groups generated: {total_new_groups}")
    print(f"  New question variants (triggers): {total_new_strings}")
    print(f"  Total groups after merge: {initial_groups + total_new_groups}")
    print(f"  Total question strings after merge: {initial_strings + total_new_strings}")
    print("="*60 + "\n")

    if total_new_groups < target_count:
        print(f"WARNING: Target count of {target_count} was not reached (generated {total_new_groups}).")
        return 1

    if not args.apply:
        print("[DRY RUN] Finished without modifying file. Use --apply to write changes.")
        return 0

    # Write changes atomically
    print("Merging new patterns into qa_patterns.json...")
    updated_data = copy.deepcopy(data)
    updated_data["patterns"].update(new_patterns)

    backup_path = f"{file_path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    print(f"Creating backup at {backup_path}...")
    shutil.copy2(file_path, backup_path)

    tmp_path = f"{file_path}.tmp"
    print(f"Writing updated JSON to temporary file {tmp_path}...")
    t_write_start = time.time()
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, file_path)
    os.chmod(file_path, 0o644)
    print(f"Successfully applied in {time.time() - t_write_start:.2f}s!")
    print(f"Updated {file_path}: {len(updated_data['patterns'])} groups.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
