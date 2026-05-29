"""
Test script for improved fuzzy pattern matching
"""
import json

# Load the patterns
with open('config/qa_patterns.json', 'r') as f:
    patterns_data = json.load(f)

# Build the patterns dict (same as agent.py does)
patterns_dict = {}
patterns = patterns_data.get('patterns', {})
for pattern_id, pattern_data in patterns.items():
    answer = pattern_data.get('default', '')
    if not answer:
        continue
    for pattern_str in pattern_data.get('patterns', []):
        patterns_dict[pattern_str.lower()] = answer

# Test cases - questions that should match known patterns
test_cases = [
    # Yes/No questions (should answer "Yes")
    ("Have you owned backend architecture end to end, from design to production deployment?", "Yes"),
    ("Do you have experience with backend architecture?", "Yes"),
    ("Owned backend architecture end to end", "Yes"),
    ("Backend architecture end to end from design", "Yes"),
    
    # These should match the qualification_experience category (default: Yes)
    ("Have you led technical architecture for systems?", "Yes"),
    ("Designed system architecture", "Yes"),
    ("Built scalable systems", "Yes"),
    
    # These should match employability category (default: No)
    ("Do you have a non-compete agreement?", "No"),
    ("Currently employed as a contractor", "No"),
    
    # Experience questions
    ("How many years of experience", "3.8 Years"),
    ("How much experience do you have?", "3.8 Years"),
    
    # Salary questions  
    ("What is your current salary?", "15.3 LPA"),
    ("Current CTC", "1530000"),
    
    # Notice period
    ("What is your notice period?", "Serving Notice Period"),
    ("Notice period in days", "7"),
]

# Simplified matching logic (what the JS does)
def fuzzy_match_simple(question, known_patterns):
    """Simplified version of the JS fuzzyMatch"""
    if not question:
        return None
    q_lower = question.lower().strip()
    best_match = None
    best_key_len = 0
    
    sorted_patterns = sorted(known_patterns.items(), key=lambda x: -len(x[0]))
    
    # Pass 1: Substring match
    for key, val in sorted_patterns:
        key_lower = key.lower()
        if q_lower == key_lower:
            return val
        if key_lower in q_lower:

            if key_lower == 'years' and any(x in q_lower for x in ['salary', 'ctc', 'pay', 'inr']):
                continue
            if len(key) > best_key_len:
                best_match = val
                best_key_len = len(key)
    
    # Pass 2: Contains-words match (all significant words exist)
    if not best_match:
        q_words = set(q_lower.split())
        best_score = 0
        for key, val in sorted_patterns:
            key_lower = key.lower()
            key_words = [w for w in key_lower.split() if len(w) > 2]
            if len(key_words) < 2:
                continue
            all_found = all((w in q_words) or (w in q_lower) for w in key_words)
            if all_found:
                score = len(key_words) / max(len(q_lower.split()), len(key_words))
                if score > best_score or (score == best_score and len(key) > best_key_len):
                    best_match = val
                    best_key_len = len(key)
                    best_score = score
    
    # Pass 3: Smart defaults
    if not best_match:
        if 'salary' in q_lower or 'ctc' in q_lower:
            return '2400000'
        elif 'notice' in q_lower and 'period' in q_lower:
            return '30'
        elif 'experience' in q_lower or 'years' in q_lower:
            return '3.8 Years'
    
    return best_match

# Run tests
print("="*80)
print("Testing improved fuzzy matching")
print("="*80)

correct = 0
wrong = 0

for question, expected in test_cases:
    result = fuzzy_match_simple(question, patterns_dict)
    status = "✓ PASS" if result == expected else "✗ FAIL"
    if result == expected:
        correct += 1
    else:
        wrong += 1
    print(f"{status} | Question: {question[:60]}...")
    print(f"         Expected: {expected}, Got: {result}")
    print()

print("="*80)
print(f"Results: {correct}/{len(test_cases)} correct ({100*correct//len(test_cases)}%)")
print(f"Failed: {wrong}/{len(test_cases)}")
print("="*80)

# Show all Yes patterns to verify category defaults
if wrong > 0:
    print("\nDebugging failed cases:")
    for question, expected in test_cases:
        result = fuzzy_match_simple(question, patterns_dict)
        if result != expected:
            print(f"FAILED: '{question}'")
            print(f"  Expected: {expected}, Got: {result}")
            # Check which patterns match
            q_lower = question.lower()
            for key, val in sorted(patterns_dict.items(), key=lambda x: -len(x[0])):
                if q_lower in key.lower() or key.lower() in q_lower:
                    print(f"  Found pattern: '{key}' -> '{val}'")
                    break
            else:
                print("  No substring match found")
                # Check contains-words
                q_words = set(q_lower.split())
                for key, val in sorted(patterns_dict.items(), key=lambda x: -len(x[0])):
                    key_words = [w for w in key.lower().split() if len(w) > 2]
                    if len(key_words) >= 2:
                        all_found = all(w in q_words or w in q_lower for w in key_words)
                        if all_found:
                            print(f"  Contains-words match: '{key}' -> '{val}'")
                            break
            print()
