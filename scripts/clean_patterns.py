"""
Script to clean and restructure qa_patterns.json:
1. Split willing_relocate mega-pattern into focused patterns
2. Remove auto-learned patterns that duplicate canonical ones
3. Deduplicate pattern strings across patterns
4. Add priority and negative_patterns fields
5. Keep auto-learned patterns with unique answers
"""

import json
import re
import sys
from collections import defaultdict

INPUT_FILE = "config/qa_patterns.json"
OUTPUT_FILE = "config/qa_patterns.json"
BACKUP_FILE = "config/qa_patterns_backup.json"

with open(INPUT_FILE) as f:
    data = json.load(f)

patterns = data.get('patterns', {})

# Step 1: Identify canonical vs auto-learned
def is_auto_learned(pid):
    parts = pid.split('_')
    return len(parts) >= 2 and parts[-1].isdigit()

canonical = {pid: pdata for pid, pdata in patterns.items() if not is_auto_learned(pid)}
auto_learned = {pid: pdata for pid, pdata in patterns.items() if is_auto_learned(pid)}

print(f"Canonical: {len(canonical)}, Auto-learned: {len(auto_learned)}")

# Step 2: Map canonical defaults for dedup detection
canonical_defaults = defaultdict(set)
for pid, pdata in canonical.items():
    canonical_defaults[pdata.get('default', '')].add(pid)

# Step 3: Find auto-learned to remove (same default as canonical + same category)
auto_to_remove = set()
for pid, pdata in auto_learned.items():
    default = pdata.get('default', '')
    category = pdata.get('category', '')
    for cp_id, cp_data in canonical.items():
        if cp_data.get('default', '') == default and cp_data.get('category', '') == category:
            auto_to_remove.add(pid)
            break

print(f"Auto-learned to remove (same answer+category as canonical): {len(auto_to_remove)}")

# Also remove auto-learned with same default AND same answer as any canonical,
# even if category differs, when the pattern strings are generic
for pid, pdata in auto_learned.items():
    if pid in auto_to_remove:
        continue
    default = pdata.get('default', '')
    if default in ('Yes', 'No', '15', '15 days', '4', '3.8 Years', 'Everbridge', 'Fiserv'):
        for cp_id, cp_data in canonical.items():
            if cp_data.get('default', '') == default:
                pat_strings = pdata.get('patterns', [])
                cp_strings = cp_data.get('patterns', [])
                overlap = set(s.lower() for s in pat_strings) & set(s.lower() for s in cp_strings)
                if overlap or len(pat_strings) <= 2:
                    auto_to_remove.add(pid)
                    break

print(f"After expanded removal: {len(auto_to_remove)}")

# Step 4: Split willing_relocate
willing_patterns = set(s.lower() for s in patterns.get('willing_relocate', {}).get('patterns', []))

# Define where each willing_relocate string should go
relocation_map = {
    'relocation_general': [
        'open to relocate', 'willing to relocate', 'relocate to', 'relocation',
        'willingness to travel', 'ready to relocate', 'accept relocation',
        'fine with relocation', 'comfortable to relocate', 'ok to relocate',
    ],
    'data_consent': [
        'data consent', 'consent to collect', 'collect store and process',
        'process my data', 'consent to collect store and process',
        'i consent to the privacy', 'i consent to the', 'consent to privacy',
        'privacy policy consent', 'consent to the privacy policy',
        'consent to process data', 'data collection consent',
    ],
    'interview_availability': [
        'f2f interview', 'interested for interview', 'interested for f2f interview',
        'face to face interview', 'virtual interview', 'telephonic interview',
        'video interview', 'face-to-face discussion', 'face to face discussion',
    ],
    'assessment_willingness': [
        'online test as the first round', 'online test first round',
        'take an online test', 'online evaluation', 'written test', 'aptitude test',
        'comfortable taking an online test', 'comfortable taking online',
        'comfortable with online test', 'take a technical assessment',
        'technical assessment', 'available for assessment', 'coding assessment',
        'online assessment', 'available to take a technical assessment',
        'comfortable taking an online', 'take an online evaluation',
        'take an aptitude test', 'take an mcq test', 'take a skill test',
        'take a screening test', 'appear for an online test', 'appear for a test',
        'appear for coding round', 'take a technical test', 'take a coding test',
        'first round of evaluation',
    ],
    'work_mode_wfo': [
        'work from office', '5 days working from office', '5 days wfo',
        'wfo', 'work from office 5 days', 'work from office 6 days',
        'full-time on-site', 'comfortable for 5 days',
        'comfortable to work from office', 'working from office',
        'come to the office', 'available to come', 'would you be available',
        'come to office', 'visit the office', 'visit our office',
        'office this saturday', 'available full-time on-site',
        'available to work full-time on-site', 'hybrid work',
    ],
    'work_authorization': [
        'authorized to work in', 'authorized to work', 'authorized to lawfully work',
        'authorized to lawfully work for', 'are you legally authorized to work in india',
        'are you legally authorized to work', 'are you authorized to lawfully work',
        'do you have the right to work', 'eligible to work in india',
        'lawfully authorized to work', 'work authorization',
        'background check', 'drug test',
    ],
    'travel_acceptance': [
        'willingness to travel', 'accept travel', 'ready to travel',
        'fine with travel', 'comfortable to travel', 'ok to travel',
        'willing to travel',
    ],
    'us_hours': [
        'comfortable working us hours', 'overlapping us hours',
        'us hours weekly calls', 'are you comfortable working during overlapping us hours',
    ],
    'contract_role': [
        'contract to hire', 'contract role', 'interested in c2h',
        'c2h position', 'contract to hire position',
    ],
    'shift_comfort': [
        'night shift', 'rotational shift', 'shift timing',
        'comfortable working in shift',
    ],
    'commute': [
        'comfortable commuting', 'commuting to this job\'s location',
        'commuting to', 'comfortable commuting to this job',
    ],
    'interview_general': [
        'available for interview', 'available for a discussion',
        'available for discussion', 'immediate requirement',
        'urgent requirement', 'immediate opening',
        'can you join immediately or currently serving np',
        'immediately or within 15-30 days',
        'available on', 'asap', 'as soon as possible',
    ],
    'tech_yes_no': [
        'database knowledge', 'strong knowledge in db', 'knowledge in db',
        'db knowledge', 'sql knowledge', 'must have strong knowledge',
        'do you have proficiency', 'strong proficiency', 'good grasp',
        'etl concepts', 'good understanding of', 'good grasp of etl',
        'designed database architecture', 'database architecture from scratch',
        'rest api', 'restful apis', 'designed and developed restful apis',
        'ci cd pipelines', 'cicd pipelines', 'ci/cd pipelines',
        'leading architecture decisions', 'kafka', 'docker', 'kubernetes',
        'docker or kubernetes', 'aws vps independently', 'deployed applications to cloud',
        'deployed frontend applications', 'openai anthropic', 'ai apis',
        'cloud servers aws', 'diverse enterprise platforms',
        'end-to-end full stack projects', 'end to end full stack',
        'full stack projects', 'full stack java developer', 'java developer',
        'managed a team', 'led a team', 'production systems',
        'owned a project', 'integrated any ai apis',
    ],
    'company_compliance': [
        'employed at fiserv', 'are you currently employed by fiserv',
        'currently employed by fiserv', 'have you been employed by fiserv',
        'employed by fiserv', 'employment consent', 'temporary employee',
        'considering me for employment', 'employment consideration',
        'currently based in mumbai or pune', 'are you currently based in mumbai or pune',
        'can it be negotiated', 'negotiated with your current employer',
    ],
    'consent_company_specific': [
        'highradius data consent', 'highradius has my consent', 'highradius consent',
        'black duck has my consent', 'black duck consent',
        'greenhouse consent', 'smartbear has my consent',
        'for up to 730 days', '730 days', '730 days thereafter',
        'up to 730 days', '365 days', 'for up to 365 days', 'up to 365 days',
        '1825 days', '1825 days thereafter',
    ],
    'salary_acceptance': [
        'will you be okay with that', 'okay with that',
    ],
    'test_willingness': [
        'okay to take a test', 'ok to take test', 'ok to take a test',
        'are you okay to take', 'are you ok to take',
        'are you fine to take a test', 'fine with taking a test', 'fine to take a test',
        'willing to take a test', 'willing to take test',
        'are you willing to take a test', 'ready to take a test', 'ready to take test',
        'comfortable to take a test', 'comfortable taking a test',
        'open to take a test', 'open to taking a test', 'open to an assessment',
        'okay to give a test', 'ok to give test', 'are you okay with a test',
        'are you ok with a test', 'happy to take a test',
        'fine to appear for test', 'okay to appear for test', 'willing to appear for test',
        'willing to give a test', 'ok with giving a test',
        'comfortable with test', 'comfortable for test',
        'okay with a technical test', 'fine with a technical test',
        'okay with online assessment', 'fine with online assessment',
        'willing for assessment', 'open to assessment',
        'take a technical test', 'can you take a test',
        'okay to take test',
    ],
    'misc_generic_yes': [
        'bfsi', 'banking domain', 'fintech', 'will you be okay with that',
    ],
}

# Assign willing_relocate strings to target patterns
new_patterns = {}
for target_id, strings in relocation_map.items():
    for s in strings:
        new_patterns.setdefault(target_id, set()).add(s.lower())

# Count how many willing_relocate strings got assigned
assigned = set()
for target_id, strings in new_patterns.items():
    assigned |= strings
unassigned = willing_patterns - assigned
if unassigned:
    print(f"WARNING: {len(unassigned)} willing_relocate strings unassigned:")
    for s in sorted(unassigned):
        print(f"  '{s}'")

# Step 5: Build priority map for canonical patterns
priority_map = {
    'salary_5206': 9, 'salary_7532': 9, 'fixed_component': 9, 'variable_component': 9,
    'ctc_in_lakhs': 8, 'expected_ctc_lakhs': 8, 'monthly_salary': 8, 'take_home_salary': 8,
    'net_salary': 8, 'salary_range': 8, 'current_salary': 7, 'expected_salary': 7,
    'offer_ctc': 7,
    'linkedin_salary_expectation': 9, 'linkedin_specific_skill_yoe': 8,
    'linkedin_current_company': 8, 'linkedin_current_title': 8,
    'linkedin_notice_period_days': 8, 'linkedin_year_of_graduation': 8,
    'linkedin_language_proficiency': 7,
    'linkedin_gender_identity': 7, 'linkedin_disability_status': 7, 'linkedin_veteran_status': 7,
    'linkedin_completed_degree': 7, 'linkedin_certifications': 7,
    'linkedin_remote_preference': 7, 'linkedin_work_mode': 7, 'linkedin_passport_travel': 7,
    'naukri_total_experience': 8, 'naukri_relevant_experience': 8,
    'naukri_current_salary_lpa': 8, 'naukri_key_skills': 7,
    'naukri_highest_qualification': 7, 'naukri_preferred_location': 7,
    'naukri_offer_in_hand': 7, 'naukri_marital_status': 7,
    'naukri_industry_preference': 7, 'naukri_functional_area': 7,
    'naukri_job_type': 7, 'naukri_shift_preference': 7, 'naukri_working_hours': 7,
    'naukri_resume_headline': 7, 'naukri_work_from_home': 7,
    'rel_exp_java': 8, 'rel_exp_react': 8, 'rel_exp_spring_boot': 8,
    'rel_exp_angular': 8, 'rel_exp_python': 8, 'rel_exp_node': 8,
    'kafka_experience': 8, 'azure_experience': 8, 'gcp_experience': 8,
    'tech_specific_experience': 7,
    'relevant_experience': 7, 'total_exp': 7, 'experience_months': 7,
    'years_experience_check': 7,
    'worked_with_fiserv': 9, 'worked_with_visa': 9,
    'compliance_general': 8, 'applied_to_company': 8,
    'data_consent': 8, 'highradius_consent': 8,
    'non_compete_agreement': 8,
    'notice_period': 7, 'joining_date': 7, 'desired_start_date': 7,
    'notice_period_negotiable': 7,
    'contact_phone': 9, 'contact_email': 9, 'pan_card': 9, 'personal_pan': 9,
    'personal_dob': 9, 'street_address': 9, 'state': 9, 'zip_code': 9, 'country': 9,
    'self_id_name': 9, 'self_id_gender': 9, 'self_id_date': 9,
    'company_current': 8, 'current_role': 8, 'current_designation': 8, 'current_organization': 8,
    'location_current': 7, 'location_preferred': 7, 'preferred_city': 7, 'current_address': 7,
    'pune_relocation': 7, 'candidates_from_mumbai': 7,
    'location_5864': 7, 'location_1393': 7, 'location_4369': 7,
    'location_8084': 7, 'location_5589': 7,
    'skills_tech_stack': 7, 'skills_languages': 6,
    'proficiency_rating': 7, 'dsa': 7,
    'proficiency_typescript': 8, 'proficiency_javascript': 8, 'proficiency_react': 8,
    'proficiency_java': 8, 'proficiency_python': 8, 'proficiency_angular': 8,
    'proficiency_node': 8, 'proficiency_aws': 8, 'proficiency_sql': 8,
    'english_proficiency': 7, 'talking_to_us_customers': 7,
    'tools_used': 6, 'configuration_tools': 6, 'deployment_tools': 6,
    'monitoring_tools': 6, 'automation_tools': 6,
    'frontend_security': 6, 'trading_platform': 6,
    'genai_llm_experience': 7, 'cloud_platform_experience': 7,
    'microservices_architecture': 7, 'agile_scrum_experience': 7,
    'client_interaction': 7, 'code_review_practices': 7,
    'system_design_experience': 7, 'testing_automation': 7,
    'security_practices': 7, 'data_structures_algorithms': 7,
    'database_design': 7, 'api_design': 7,
    'performance_optimization': 7, 'monitoring_logging': 7,
    'message_queues': 7, 'team_size_managed': 7,
    'product_based_org': 7, 'product_based': 7,
    'work_from_home': 7, 'comfortable_us_hours': 7,
    'willing_to_travel': 7, 'contract_to_hire': 7,
    'immediate_joiner': 7, 'offer_in_hand': 7,
    'career_break': 7, 'salary_acceptance': 7,
    'online_test': 7, 'previously_interviewed': 7,
    'docker_kubernetes': 7, 'kafka_yes_no': 7, 'rest_api': 7, 'ci_cd': 7,
    'ai_tools': 7, 'database_knowledge': 7,
    'full_stack_project': 7, 'coding_comfort': 7,
    'enterprise_platforms': 6, 'ci_cd_setup': 6,
    'tcs_registration': 7, 'walk_in_interview': 7,
    'shift_timings': 7, 'reference_check': 6,
    'willing_to_relocate_specific': 7,
    'experience': 3, 'worked_on_projects': 5,
    'willing_relocate': 2,
    'education_degree': 7, 'education_bachelor': 7,
    'education_university': 7, 'education_cgpa': 7,
    'specialization': 7, 'institute': 7, 'highest_qualification': 7,
    'job_change_reason': 6, 'preferred_role': 6, 'preferred_position': 6,
    'referral': 7, 'referral_source': 6,
    'joining_bonus': 5, 'portfolio_url': 5, 'linkedin_url': 5, 'github_url': 5,
    'message_to_hiring_manager': 5, 'why_join_company': 5,
    'what_can_you_bring': 5, 'last_professional_experience': 5,
    'relevant_experience_desc': 5, 'share_your_ctc': 5,
    'programming_language': 6, 'area_of_experience': 6,
    'project_count': 6, 'which_database': 6,
    'e_commerce_experience': 7,
    'leetcode_solved': 5, 'team_leadership': 6,
    'where_do_you_see_yourself': 5, 'career_objective': 5,
    'take_home_assignment': 7,
    'additional_months': 7, 'additional_years': 7,
    'current_project': 6, 'project_and_skills': 6,
    'authorization': 7, 'visa_sponsorship': 7,
    'qualification_experience': 6,
    'interview_availability': 6, 'interview_slots': 6,
    'assessment_availability': 6, 'assessment_date': 6,
    'ai_apis': 7, 'designed_database_architecture': 7,
    'deployed_applications_to_cloud': 7,
    'production_applications_end_to_end': 6,
    'photo_upload': 9,
}

# Negative patterns for cross-category prevention
negative_patterns_map = {
    'experience': [
        'java experience', 'react experience', 'python experience', 'nodejs experience',
        'angular experience', 'typescript experience', 'spring boot experience',
        'kafka experience', 'docker experience', 'kubernetes experience',
        'aws experience', 'azure experience', 'gcp experience',
        'devops experience', 'cloud experience', 'microservices experience',
        'backend experience', 'frontend experience', 'full stack experience',
        'node experience', 'javascript experience', 'vue experience',
        'current salary', 'expected salary', 'ctc', 'salary',
        'notice period', 'notice',
    ],
    'current_salary': [
        'expected ctc', 'expected salary', 'ectc', 'expected',
        'notice period', 'experience',
    ],
    'expected_salary': [
        'current ctc', 'current salary', 'cctc', 'current',
        'notice period',
    ],
    'notice_period': [
        'current salary', 'expected salary', 'ctc', 'salary',
        'experience',
    ],
    'location_current': [
        'preferred location', 'preferred city', 'relocate',
    ],
    'location_preferred': [
        'current location', 'where do you live', 'where do you stay',
    ],
    'proficiency_rating': [
        'experience', 'years', 'ctc', 'salary',
    ],
    'dsa': [
        'experience', 'years of experience', 'ctc', 'salary',
    ],
    'joining_date': [
        'salary', 'ctc', 'experience',
    ],
}

# Step 6: Build deduplicated patterns
# For each pattern string, assign it to the highest-priority pattern
string_to_all_pids = defaultdict(list)
for pid, pdata in canonical.items():
    for s in pdata.get('patterns', []):
        string_to_all_pids[s.lower()].append(pid)

# For auto-learned that we're keeping
kept_auto = {pid: pdata for pid, pdata in auto_learned.items() if pid not in auto_to_remove}
for pid, pdata in kept_auto.items():
    for s in pdata.get('patterns', []):
        string_to_all_pids[s.lower()].append(pid)

# For each duplicate string, keep only the highest-priority pattern
print(f"\nDeduplication: {len(string_to_all_pids)} unique strings, {sum(1 for v in string_to_all_pids.values() if len(v) > 1)} have duplicates")

deduped = {}
for pid, pdata in {**canonical, **kept_auto}.items():
    new_pats = []
    for s in pdata.get('patterns', []):
        key = s.lower()
        candidates = string_to_all_pids[key]
        if len(candidates) == 1:
            new_pats.append(s)
        else:
            # Pick highest priority
            best = max(candidates, key=lambda p: priority_map.get(p, 3))
            if best == pid:
                new_pats.append(s)
    deduped[pid] = new_pats

# Step 7: Merge willing_relocate strings into target patterns
for target_id, new_strings in new_patterns.items():
    if target_id in canonical:
        existing = set(s.lower() for s in canonical[target_id].get('patterns', []))
        added = 0
        for s in new_strings:
            if s not in existing:
                canonical[target_id].setdefault('patterns', []).append(s)
                added += 1
        if added:
            print(f"  Added {added} strings to existing '{target_id}'")
    elif target_id == 'relocation_general':
        # This stays in willing_relocate but slimmed down
        canonical['willing_relocate']['patterns'] = list(new_strings)
        print(f"  Replaced willing_relocate with {len(new_strings)} relocation strings")
    elif target_id == 'test_willingness':
        # Merge into online_test
        existing = set(s.lower() for s in canonical.get('online_test', {}).get('patterns', []))
        added = 0
        for s in new_strings:
            if s not in existing:
                canonical.setdefault('online_test', canonical.get('online_test', {}))
                canonical['online_test'].setdefault('patterns', []).append(s)
                added += 1
        if added:
            print(f"  Added {added} test_willingness strings to online_test")
    elif target_id == 'salary_acceptance':
        # Already exists as canonical
        existing = set(s.lower() for s in canonical.get('salary_acceptance', {}).get('patterns', []))
        added = 0
        for s in new_strings:
            if s not in existing:
                canonical['salary_acceptance'].setdefault('patterns', []).append(s)
                added += 1
    elif target_id == 'misc_generic_yes':
        # These are too generic, add to product_based
        existing = set(s.lower() for s in canonical.get('product_based', {}).get('patterns', []))
        added = 0
        for s in new_strings:
            if s not in existing:
                canonical['product_based'].setdefault('patterns', []).append(s)
                added += 1
    elif target_id == 'tech_yes_no':
        # These belong to specific tech patterns
        for s in new_strings:
            s_lower = s.lower()
            if 'database' in s_lower or 'db' in s_lower or 'sql' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('database_knowledge', {}).get('patterns', [])):
                    canonical['database_knowledge'].setdefault('patterns', []).append(s)
            elif 'kafka' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('kafka_yes_no', {}).get('patterns', [])):
                    canonical['kafka_yes_no'].setdefault('patterns', []).append(s)
            elif 'docker' in s_lower or 'kubernetes' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('docker_kubernetes', {}).get('patterns', [])):
                    canonical['docker_kubernetes'].setdefault('patterns', []).append(s)
            elif 'ci' in s_lower or 'pipeline' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('ci_cd', {}).get('patterns', [])):
                    canonical['ci_cd'].setdefault('patterns', []).append(s)
            elif 'rest' in s_lower or 'api' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('rest_api', {}).get('patterns', [])):
                    canonical['rest_api'].setdefault('patterns', []).append(s)
            elif 'ai' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('ai_apis', {}).get('patterns', [])):
                    canonical['ai_apis'].setdefault('patterns', []).append(s)
            elif 'project' in s_lower or 'team' in s_lower or 'led' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('full_stack_project', {}).get('patterns', [])):
                    canonical['full_stack_project'].setdefault('patterns', []).append(s)
            elif 'enterprise' in s_lower or 'diverse' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('enterprise_platforms', {}).get('patterns', [])):
                    canonical['enterprise_platforms'].setdefault('patterns', []).append(s)
            elif 'deployed' in s_lower or 'production' in s_lower or 'cloud' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('deployed_applications_to_cloud', {}).get('patterns', [])):
                    canonical['deployed_applications_to_cloud'].setdefault('patterns', []).append(s)
    elif target_id == 'company_compliance':
        for s in new_strings:
            s_lower = s.lower()
            if 'fiserv' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('worked_with_fiserv', {}).get('patterns', [])):
                    canonical['worked_with_fiserv'].setdefault('patterns', []).append(s)
            elif 'mumbai' in s_lower or 'pune' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('candidates_from_mumbai', {}).get('patterns', [])):
                    canonical['candidates_from_mumbai'].setdefault('patterns', []).append(s)
            elif 'negotiate' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('notice_period_negotiable', {}).get('patterns', [])):
                    canonical['notice_period_negotiable'].setdefault('patterns', []).append(s)
            elif 'employment' in s_lower or 'temporary' in s_lower or 'consent' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('compliance_general', {}).get('patterns', [])):
                    canonical['compliance_general'].setdefault('patterns', []).append(s)
    elif target_id == 'consent_company_specific':
        for s in new_strings:
            s_lower = s.lower()
            if 'highradius' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('highradius_consent', {}).get('patterns', [])):
                    canonical['highradius_consent'].setdefault('patterns', []).append(s)
            elif 'black duck' in s_lower or 'duck' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('highradius_consent', {}).get('patterns', [])):
                    canonical['highradius_consent'].setdefault('patterns', []).append(s)
            elif 'smartbear' in s_lower or 'greenhouse' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('data_consent', {}).get('patterns', [])):
                    canonical['data_consent'].setdefault('patterns', []).append(s)
            elif 'day' in s_lower:
                if s_lower not in set(x.lower() for x in canonical.get('highradius_consent', {}).get('patterns', [])):
                    canonical['highradius_consent'].setdefault('patterns', []).append(s)
    else:
        # interview_general, commute, shift_comfort - create or add to existing
        if target_id == 'shift_comfort':
            existing = set(s.lower() for s in canonical.get('shift_timings', {}).get('patterns', []))
            for s in new_strings:
                if s not in existing:
                    canonical['shift_timings'].setdefault('patterns', []).append(s)
        elif target_id == 'commute':
            canonical['pune_relocation'].setdefault('patterns', []).extend(
                [s for s in new_strings if s not in set(x.lower() for x in canonical.get('pune_relocation', {}).get('patterns', []))]
            )
        elif target_id == 'interview_general':
            existing = set(s.lower() for s in canonical.get('immediate_joiner', {}).get('patterns', []))
            for s in new_strings:
                if s not in existing:
                    canonical['immediate_joiner'].setdefault('patterns', []).append(s)

# Now rebuild the final patterns dict
final_patterns = {}

# Add canonical patterns (with deduped pattern lists)
for pid, pdata in canonical.items():
    if pid == 'willing_relocate':
        continue  # Replaced by relocation_general in willing_relocate
    entry = {}
    # Deduplicate patterns within this entry
    seen = set()
    unique_pats = []
    for s in pdata.get('patterns', []):
        if s.lower() not in seen:
            seen.add(s.lower())
            unique_pats.append(s)
    entry['patterns'] = unique_pats
    # Copy other fields
    for k, v in pdata.items():
        if k != 'patterns' and k != 'priority' and k != 'negative_patterns':
            entry[k] = v
    # Add priority
    entry['priority'] = priority_map.get(pid, 5)
    # Add negative patterns
    if pid in negative_patterns_map:
        entry['negative_patterns'] = negative_patterns_map[pid]
    final_patterns[pid] = entry

# Add willing_relocate with only relocation strings
wr_pats = canonical.get('willing_relocate', {}).get('patterns', [])
# Keep only strings that are actually about relocation
wr_keep = []
for s in wr_pats:
    s_lower = s.lower()
    if any(w in s_lower for w in ['relocate', 'relocation', 'travel', 'shift', 'commut']):
        wr_keep.append(s)
if wr_keep:
    final_patterns['willing_relocate'] = {
        'patterns': wr_keep,
        'category': 'yes_no',
        'default': 'Yes',
        'priority': 5,
        'input_type_defaults': {'radio': 'Yes', 'checkbox': True, 'select': 'Yes', 'text': 'Yes'}
    }

# Add kept auto-learned patterns (with priority=4, lower than canonical)
for pid, pdata in kept_auto.items():
    entry = {}
    seen = set()
    unique_pats = []
    for s in pdata.get('patterns', []):
        if s.lower() not in seen:
            seen.add(s.lower())
            unique_pats.append(s)
    entry['patterns'] = unique_pats
    for k, v in pdata.items():
        if k != 'patterns':
            entry[k] = v
    entry['priority'] = 4
    final_patterns[pid] = entry

# Final dedup pass: for each string, keep only in highest-priority pattern
string_owner = {}
for pid in sorted(final_patterns.keys(), key=lambda p: final_patterns[p].get('priority', 5), reverse=True):
    new_pats = []
    for s in final_patterns[pid].get('patterns', []):
        key = s.lower()
        if key not in string_owner:
            string_owner[key] = pid
            new_pats.append(s)
    final_patterns[pid]['patterns'] = new_pats

# Build final JSON
data['patterns'] = final_patterns
data['version'] = '3.0'

# Stats
total_strings = sum(len(p.get('patterns', [])) for p in final_patterns.values())
total_ids = len(final_patterns)
print(f"\nFinal: {total_ids} patterns, {total_strings} total strings")

# Save
with open(OUTPUT_FILE, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Saved to {OUTPUT_FILE}")
print("Done!")
