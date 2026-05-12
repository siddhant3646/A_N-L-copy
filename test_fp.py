import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.sentinel.question_fingerprint import QuestionFingerprinter
from src.patterns.pattern_matcher import create_matcher
import json

# Load patterns from JSON (single source of truth)
matcher = create_matcher()
json_patterns = matcher.patterns.get('patterns', {})

# Convert JSON patterns to flat dict for QuestionFingerprinter
flat_patterns = {}
for pattern_id, pattern_data in json_patterns.items():
    answer = pattern_data.get('default', '')
    for pattern_str in pattern_data.get('patterns', []):
        flat_patterns[pattern_str.lower()] = answer

fp = QuestionFingerprinter()
fp.build_index(flat_patterns)

q = 'are you currently employed'
fingerprint = fp.get_fingerprint(q)
print("Fingerprint for '{}': '{}'".format(q, fingerprint))

ans, conf = fp.find_best_match(q)
print("Best match for '{}': '{}' (conf: {})".format(q, ans, conf))

# Let's find what question it matched from the index
for k, v in fp.fingerprint_to_answer.items():
    if k == fingerprint:
        print("Matches fingerprint from index with answer:", v)
