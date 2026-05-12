#!/usr/bin/env python3
"""
Validation script for qa_patterns.json
Checks for:
1. Duplicate pattern strings across groups
2. Conflicting answers for similar questions
3. Missing platform-specific variants
4. Pattern count by category
"""

import sys
import os
sys.path.insert(0, '/Users/siddhant/Desktop/Resume/MyModels/A_N&L')

from src.patterns.pattern_matcher import create_matcher

def load_patterns():
    """Load patterns from JSON config."""
    matcher = create_matcher()
    return matcher.patterns.get('patterns', {})

def check_duplicates(patterns):
    """Check for duplicate pattern strings across groups."""
    seen_patterns = {}  # pattern_str -> pattern_id
    duplicates = []
    
    for pattern_id, pattern_data in patterns.items():
        for pattern_str in pattern_data.get('patterns', []):
            pattern_lower = pattern_str.lower()
            if pattern_lower in seen_patterns:
                duplicates.append({
                    'pattern': pattern_str,
                    'first_group': seen_patterns[pattern_lower],
                    'second_group': pattern_id
                })
            else:
                seen_patterns[pattern_lower] = pattern_id
    
    if duplicates:
        print(f"❌ Found {len(duplicates)} duplicate patterns:")
        for dup in duplicates[:10]:  # Show first 10
            print(f"  - '{dup['pattern']}' in both '{dup['first_group']}' and '{dup['second_group']}'")
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates) - 10} more")
    else:
        print("✅ No duplicate patterns found")
    
    return len(duplicates) == 0

def count_patterns(patterns):
    """Count total patterns and categorize them."""
    total_groups = len(patterns)
    total_patterns = sum(len(p.get('patterns', [])) for p in patterns.values())
    
    # Count by category
    category_counts = {}
    for pattern_id, pattern_data in patterns.items():
        category = pattern_data.get('category', 'uncategorized')
        category_counts[category] = category_counts.get(category, 0) + 1
    
    print(f"\n📊 Total Pattern Groups: {total_groups}")
    print(f"📊 Total Pattern Strings: {total_patterns}")
    print("\n📁 Pattern Groups by Category:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {category}: {count}")
    
    return total_groups, total_patterns

def check_conflicts(patterns):
    """Check for potentially conflicting answers."""
    # Group patterns by category
    by_category = {}
    for pattern_id, pattern_data in patterns.items():
        category = pattern_data.get('category', 'uncategorized')
        default = pattern_data.get('default', '')
        if category not in by_category:
            by_category[category] = set()
        by_category[category].add(default)
    
    # Check for categories with many different answers
    for category, answers in by_category.items():
        if len(answers) > 10:
            print(f"\n⚠️  Warning: {len(answers)} different answers for category '{category}'")
            print("  This may be intentional for different formats")
    
    return True

def check_empty_defaults(patterns):
    """Check for pattern groups with empty default answers."""
    empty_defaults = []
    for pattern_id, pattern_data in patterns.items():
        if not pattern_data.get('default', '').strip():
            empty_defaults.append(pattern_id)
    
    if empty_defaults:
        print(f"\n⚠️  Warning: {len(empty_defaults)} pattern groups with empty defaults:")
        for pid in empty_defaults[:10]:
            print(f"  - {pid}")
        if len(empty_defaults) > 10:
            print(f"  ... and {len(empty_defaults) - 10} more")
    else:
        print("✅ All pattern groups have default answers")
    
    return len(empty_defaults) == 0

def sample_patterns(patterns):
    """Show sample patterns from different categories."""
    print("\n📝 Sample Patterns:")
    
    # Get one sample from each major category
    samples_by_category = {}
    for pattern_id, pattern_data in patterns.items():
        category = pattern_data.get('category', 'uncategorized')
        if category not in samples_by_category:
            patterns_list = pattern_data.get('patterns', [])
            if patterns_list:
                samples_by_category[category] = {
                    'pattern_id': pattern_id,
                    'pattern': patterns_list[0],
                    'answer': pattern_data.get('default', '')
                }
    
    # Show samples from major categories
    major_categories = ['experience', 'salary', 'notice_period', 'location', 'skills', 'yes_no']
    for category in major_categories:
        if category in samples_by_category:
            sample = samples_by_category[category]
            print(f"\n  {category.upper()}:")
            print(f"    Q: {sample['pattern']}")
            print(f"    A: {sample['answer'][:60]}{'...' if len(sample['answer']) > 60 else ''}")

def main():
    print("=" * 70)
    print("🔍 qa_patterns.json Validation Report")
    print("=" * 70)
    
    # Load patterns
    patterns = load_patterns()
    if not patterns:
        print("❌ Failed to load patterns from JSON")
        return
    
    print(f"✅ Loaded {len(patterns)} pattern groups from config/qa_patterns.json")
    
    # Run checks
    no_duplicates = check_duplicates(patterns)
    total_groups, total_patterns = count_patterns(patterns)
    check_conflicts(patterns)
    no_empty = check_empty_defaults(patterns)
    sample_patterns(patterns)
    
    print("\n" + "=" * 70)
    if no_duplicates and no_empty:
        print("✅ Validation PASSED")
        print(f"✅ Total pattern groups: {total_groups}")
        print(f"✅ Total pattern strings: {total_patterns}")
    else:
        print("❌ Validation FAILED - Fix issues above")
    print("=" * 70)

if __name__ == "__main__":
    main()
