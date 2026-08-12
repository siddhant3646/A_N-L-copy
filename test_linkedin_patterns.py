"""Smoke test for LinkedIn/Microsoft affiliation patterns."""
import sys
sys.path.insert(0, 'src')
from patterns.pattern_loader import PatternLoader
from patterns.pattern_matcher import PatternMatcher

loader = PatternLoader('config/qa_patterns.json')
data = loader.load()
pm = PatternMatcher(data)

test_cases = [
    ("Do you currently or have you previously worked at LinkedIn or Microsoft in any capacity?", "checkbox"),
    ("If you currently or previously worked at LinkedIn or Microsoft, please select the company and employment type.", "checkbox"),
    ("Worked at LinkedIn or Microsoft", "radio"),
    ("LinkedIn or Microsoft employment type", "select"),
    ("LinkedIn Microsoft affiliation", "text"),
]

print("=" * 70)
print("LinkedIn/Microsoft Pattern Smoke Test")
print("=" * 70)
all_passed = True
for question, input_type in test_cases:
    answer, confidence = pm.fuzzy_match(question, input_type)
    status = "✅ PASS" if answer == "Not Applicable" and confidence > 0.7 else "❌ FAIL"
    if status == "❌ FAIL":
        all_passed = False
    print(f"\n{status} | confidence={confidence:.2f}")
    print(f"  Q: {question[:65]}")
    print(f"  A: {answer!r} (input_type={input_type})")

print("\n" + "=" * 70)
print("Overall:", "✅ ALL PASSED" if all_passed else "❌ SOME FAILED")
