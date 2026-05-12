#!/usr/bin/env python3
"""
Migration script to convert KNOWN_QA_PATTERNS dict to JSON format.
"""
import json
import re
from pathlib import Path

def extract_patterns_from_agent():
    """Extract patterns from agent.py file."""
    agent_path = Path(__file__).parent / "src" / "sentinel" / "agent.py"
    
    with open(agent_path, 'r') as f:
        content = f.read()
    
    # Find the dict
    pattern = r"KNOWN_QA_PATTERNS = \{([^}]+)\}"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("Could not find KNOWN_QA_PATTERNS dict")
        return {}
    
    # Parse the dict content
    dict_content = match.group(1)
    
    # Extract key-value pairs
    patterns = {}
    # Match 'key': 'value' or "key": "value" patterns
    kv_pattern = r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]"
    
    for match in re.finditer(kv_pattern, dict_content):
        key = match.group(1)
        value = match.group(2)
        patterns[key] = value
    
    return patterns

def categorize_pattern(pattern_text, answer):
    """Categorize a pattern based on its content."""
    text_lower = pattern_text.lower()
    
    # Category detection rules
    if any(kw in text_lower for kw in ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc', 'hike', 'monthly salary', 'take home']):
        return 'salary'
    elif any(kw in text_lower for kw in ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']):
        return 'experience'
    elif any(kw in text_lower for kw in ['notice', 'serving', 'join', 'availability', 'lwd', 'joining date']):
        return 'notice_period'
    elif any(kw in text_lower for kw in ['location', 'city', 'relocate', 'preferred location', 'based in', 'live in']):
        return 'location'
    elif any(kw in text_lower for kw in ['phone', 'mobile', 'email', 'dob', 'date of birth', 'pan', 'aadhar', 'address']):
        return 'personal_info'
    elif any(kw in text_lower for kw in ['degree', 'graduation', 'cgpa', 'percentage', 'college', 'university', 'education', 'qualification']):
        return 'education'
    elif any(kw in text_lower for kw in ['skill', 'tech stack', 'programming', 'language', 'framework']):
        return 'skills'
    elif any(kw in text_lower for kw in ['visa', 'sponsorship', 'authorized', 'work authorization']):
        return 'yes_no'
    elif answer.lower() in ['yes', 'no']:
        return 'yes_no'
    elif any(kw in text_lower for kw in ['company', 'employer', 'organization', 'fiserv', 'visa']):
        return 'employment'
    else:
        return 'preference'

def convert_to_json_format(patterns_dict):
    """Convert flat dict to structured JSON format."""
    json_patterns = {}
    
    # Group patterns by category and answer
    category_groups = {}
    
    for pattern_text, answer in patterns_dict.items():
        category = categorize_pattern(pattern_text, answer)
        
        # Create a pattern ID based on category and answer
        key = f"{category}_{hash(pattern_text) % 10000}"
        
        if key not in category_groups:
            category_groups[key] = {
                'patterns': [],
                'category': category,
                'default': answer
            }
        
        category_groups[key]['patterns'].append(pattern_text)
    
    # Merge patterns with same answer within same category
    merged = {}
    for key, data in category_groups.items():
        answer = data['default']
        category = data['category']
        
        # Create a cleaner ID
        clean_id = f"{category}_{hash(answer) % 10000}"
        
        if clean_id not in merged:
            merged[clean_id] = data
        else:
            merged[clean_id]['patterns'].extend(data['patterns'])
    
    return merged

def main():
    print("Extracting patterns from agent.py...")
    patterns = extract_patterns_from_agent()
    print(f"Found {len(patterns)} patterns")
    
    print("\nConverting to JSON format...")
    json_patterns = convert_to_json_format(patterns)
    print(f"Converted to {len(json_patterns)} pattern groups")
    
    # Save to file
    output = {
        "version": "2.0",
        "description": "Question-Answer patterns for job application automation - MIGRATED",
        "patterns": json_patterns,
        "categories": {
            "experience": {"description": "Work experience", "smart_fallback": True},
            "salary": {"description": "Compensation", "smart_fallback": True},
            "notice_period": {"description": "Availability", "smart_fallback": True},
            "location": {"description": "Location", "smart_fallback": True},
            "personal_info": {"description": "Personal details", "smart_fallback": False},
            "education": {"description": "Education", "smart_fallback": True},
            "skills": {"description": "Technical skills", "smart_fallback": True},
            "yes_no": {"description": "Binary questions", "smart_fallback": True, "default": "Yes"},
            "employment": {"description": "Employment history", "smart_fallback": True},
            "preference": {"description": "Preferences", "smart_fallback": True}
        }
    }
    
    output_path = Path(__file__).parent / "config" / "qa_patterns_migrated.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to {output_path}")
    print(f"Total pattern groups: {len(json_patterns)}")
    
    # Show category breakdown
    categories = {}
    for pid, pdata in json_patterns.items():
        cat = pdata['category']
        categories[cat] = categories.get(cat, 0) + 1
    
    print("\nCategory breakdown:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    main()
