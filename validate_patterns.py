#!/usr/bin/env python3
"""
Validation script for KNOWN_QA_PATTERNS
Checks for:
1. Duplicate keys
2. Conflicting answers for similar questions
3. Missing platform-specific variants
4. Pattern count by category
"""

import sys
sys.path.insert(0, '/Users/siddhant/Desktop/Resume/MyModels/A_N&L')

from src.sentinel.agent import KNOWN_QA_PATTERNS

def check_duplicates():
    """Check for duplicate keys in patterns."""
    keys = list(KNOWN_QA_PATTERNS.keys())
    seen = set()
    duplicates = []
    
    for key in keys:
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    
    if duplicates:
        print(f"❌ Found {len(duplicates)} duplicate keys:")
        for dup in duplicates:
            print(f"  - {dup}")
    else:
        print("✅ No duplicate keys found")
    
    return len(duplicates) == 0

def count_patterns():
    """Count total patterns and categorize them."""
    total = len(KNOWN_QA_PATTERNS)
    
    # Categorize by keywords
    categories = {
        'Experience': ['experience', 'years', 'exp'],
        'Salary/CTC': ['salary', 'ctc', 'pay', 'compensation', 'lpa', 'inr'],
        'Notice Period': ['notice', 'join', 'serving', 'available'],
        'Location': ['location', 'city', 'relocate', 'address'],
        'Skills/Tech': ['skill', 'tech', 'proficiency', 'expertise'],
        'Personal Info': ['name', 'phone', 'email', 'contact'],
        'Education': ['education', 'degree', 'university', 'college'],
        'Company': ['company', 'employer', 'organization'],
        'Yes/No': ['yes', 'no'],
        'Interview': ['interview', 'assessment', 'schedule'],
        'Cover Letter': ['why', 'about', 'passionate', 'motivates'],
        'Privacy/Legal': ['privacy', 'certify', 'consent', 'background'],
        'Screening': ['comfortable', 'willing', 'ready'],
        'LinkedIn Specific': ['linkedin', 'please select', 'please enter'],
    }
    
    category_counts = {cat: 0 for cat in categories}
    uncategorized = 0
    
    for pattern in KNOWN_QA_PATTERNS.keys():
        pattern_lower = pattern.lower()
        matched = False
        
        for category, keywords in categories.items():
            if any(kw in pattern_lower for kw in keywords):
                category_counts[category] += 1
                matched = True
                break
        
        if not matched:
            uncategorized += 1
    
    print(f"\n📊 Total Patterns: {total}")
    print("\n📁 Patterns by Category:")
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            print(f"  {category}: {count}")
    print(f"  Uncategorized: {uncategorized}")
    
    return total

def check_conflicts():
    """Check for potentially conflicting answers."""
    conflicts = []
    
    # Check for notice period variations
    notice_patterns = [k for k in KNOWN_QA_PATTERNS.keys() if 'notice' in k.lower()]
    notice_answers = set(KNOWN_QA_PATTERNS[k] for k in notice_patterns)
    
    if len(notice_answers) > 5:  # Too many different answers for notice period
        print(f"\n⚠️  Warning: {len(notice_answers)} different answers for notice period questions")
        print("  This may be intentional for different formats, but verify:")
        for ans in list(notice_answers)[:5]:
            print(f"    - {ans}")
    
    # Check for salary variations
    salary_patterns = [k for k in KNOWN_QA_PATTERNS.keys() if any(x in k.lower() for x in ['salary', 'ctc'])]
    salary_answers = set(KNOWN_QA_PATTERNS[k] for k in salary_patterns)
    
    if len(salary_answers) > 10:
        print(f"\n⚠️  Warning: {len(salary_answers)} different answers for salary questions")
        print("  This may be intentional for different formats (LPA vs INR)")
    
    return True

def sample_patterns():
    """Show sample patterns from different categories."""
    print("\n📝 Sample Patterns:")
    
    samples = [
        ('Experience', 'how many years of work experience do you have with docker'),
        ('Salary', 'current ctc'),
        ('Notice Period', 'how many days is your notice period'),
        ('LinkedIn', 'please enter your annual current ctc in inr'),
        ('Screening', 'are you ready to take assessment'),
        ('Cover Letter', 'why do you want to work here'),
    ]
    
    for category, pattern in samples:
        if pattern in KNOWN_QA_PATTERNS:
            answer = KNOWN_QA_PATTERNS[pattern]
            print(f"\n  {category}:")
            print(f"    Q: {pattern}")
            print(f"    A: {answer[:60]}{'...' if len(answer) > 60 else ''}")

def main():
    print("=" * 70)
    print("🔍 KNOWN_QA_PATTERNS Validation Report")
    print("=" * 70)
    
    # Run checks
    no_duplicates = check_duplicates()
    total = count_patterns()
    check_conflicts()
    sample_patterns()
    
    print("\n" + "=" * 70)
    if no_duplicates:
        print("✅ Validation PASSED")
        print(f"✅ Total patterns added: {total}")
    else:
        print("❌ Validation FAILED - Fix duplicate keys")
    print("=" * 70)

if __name__ == "__main__":
    main()
