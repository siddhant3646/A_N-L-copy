#!/usr/bin/env python3
"""
Script to add input_type_defaults to qa_patterns.json

This script reads the existing qa_patterns.json and adds input_type_defaults
field to patterns that need different answers based on input type.
"""

import json
import sys
from pathlib import Path


def get_input_type_defaults(pattern_id: str, category: str, default: str) -> dict:
    """
    Generate appropriate input_type_defaults based on pattern characteristics.
    
    Args:
        pattern_id: The pattern ID
        category: The pattern category
        default: The default answer
        
    Returns:
        Dictionary with input_type_defaults
    """
    defaults = {}
    default_lower = default.lower()
    
    # Boolean/Yes-No patterns
    if category == "yes_no" or default_lower in ['yes', 'no']:
        if default_lower.startswith('yes'):
            defaults = {
                "radio": "Yes",
                "checkbox": True,
                "select": "Yes",
                "text": default
            }
        elif default_lower.startswith('no'):
            defaults = {
                "radio": "No",
                "checkbox": False,
                "select": "No",
                "text": default
            }
    
    # Experience patterns
    elif category == "experience":
        # Extract numeric value
        import re
        match = re.search(r'(\d+\.?\d*)', default)
        if match:
            numeric_val = match.group(1)
            defaults = {
                "radio": numeric_val,  # For range matching
                "select": default,
                "text": default,
                "number": numeric_val
            }
    
    # Salary patterns
    elif category == "salary":
        import re
        match = re.search(r'(\d+\.?\d*)', default)
        if match:
            numeric_val = match.group(1)
            defaults = {
                "radio": numeric_val,
                "select": default,
                "text": default,
                "number": numeric_val
            }
    
    # Notice period patterns
    elif category == "notice_period":
        import re
        match = re.search(r'(\d+)', default)
        if match:
            numeric_val = match.group(1)
            defaults = {
                "radio": "Yes" if "serving" in default_lower else numeric_val,
                "checkbox": True if "serving" in default_lower else False,
                "select": default,
                "text": default,
                "number": numeric_val
            }
    
    # Location patterns
    elif category == "location":
        defaults = {
            "radio": default.split(',')[0] if ',' in default else default,
            "checkbox": True,
            "select": default,
            "text": default
        }
    
    # Skills patterns
    elif category == "skills":
        # Check if it's a rating/proficiency question
        if default.isdigit() or (len(default) <= 2 and default.replace('.', '').isdigit()):
            defaults = {
                "radio": default,
                "select": default,
                "text": default,
                "number": default
            }
        else:
            defaults = {
                "radio": default.split(',')[0] if ',' in default else default,
                "checkbox": True,
                "select": default,
                "text": default
            }
    
    # Education patterns
    elif category == "education":
        defaults = {
            "radio": default,
            "select": default,
            "text": default
        }
    
    # Personal info patterns
    elif category == "personal_info":
        defaults = {
            "radio": default,
            "select": default,
            "text": default
        }
    
    # Work/Employment patterns
    elif category == "work":
        if default_lower.startswith('yes'):
            defaults = {
                "radio": "Yes",
                "checkbox": True,
                "select": "Yes",
                "text": default
            }
        elif default_lower.startswith('no'):
            defaults = {
                "radio": "No",
                "checkbox": False,
                "select": "No",
                "text": default
            }
        else:
            defaults = {
                "radio": default,
                "select": default,
                "text": default
            }
    
    # Availability patterns
    elif category == "availability":
        if default_lower.startswith('yes'):
            defaults = {
                "radio": "Yes",
                "checkbox": True,
                "select": "Yes",
                "text": default
            }
        else:
            defaults = {
                "radio": default.split(',')[0] if ',' in default else default,
                "select": default,
                "text": default
            }
    
    # Preference patterns
    elif category == "preference":
        defaults = {
            "radio": default.split(',')[0] if ',' in default else default,
            "select": default,
            "text": default
        }
    
    # Self-identification patterns
    elif category == "self_identification":
        defaults = {
            "radio": default,
            "select": default,
            "text": default
        }
    
    # Default for other categories
    else:
        # For long text answers, provide simplified versions for radio/checkbox
        if len(default) > 50:
            # Extract first sentence or key phrase
            simplified = default.split('.')[0].split(',')[0]
            if len(simplified) > 50:
                simplified = simplified[:47] + "..."
            defaults = {
                "radio": "Yes" if default_lower.startswith('yes') else simplified,
                "checkbox": default_lower.startswith('yes'),
                "select": default,
                "text": default
            }
        else:
            defaults = {
                "radio": default,
                "checkbox": True,
                "select": default,
                "text": default
            }
    
    return defaults


def process_patterns(json_path: str, output_path: str):
    """
    Process the qa_patterns.json file and add input_type_defaults.
    
    Args:
        json_path: Path to input JSON file
        output_path: Path to output JSON file
    """
    print(f"Reading patterns from: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    patterns = data.get('patterns', {})
    updated_count = 0
    
    for pattern_id, pattern_data in patterns.items():
        if not isinstance(pattern_data, dict):
            continue
        
        category = pattern_data.get('category', 'unknown')
        default = pattern_data.get('default', '')
        
        # Skip if already has input_type_defaults
        if 'input_type_defaults' in pattern_data:
            continue
        
        # Generate input_type_defaults
        input_type_defaults = get_input_type_defaults(pattern_id, category, default)
        
        if input_type_defaults:
            pattern_data['input_type_defaults'] = input_type_defaults
            updated_count += 1
            print(f"  ✓ Added defaults to: {pattern_id}")
    
    # Write updated JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Updated {updated_count} patterns")
    print(f"✅ Output written to: {output_path}")


if __name__ == "__main__":
    # Determine paths
    base_dir = Path(__file__).parent.parent
    input_path = base_dir / "config" / "qa_patterns.json"
    output_path = base_dir / "config" / "qa_patterns_v2.json"
    
    process_patterns(str(input_path), str(output_path))
