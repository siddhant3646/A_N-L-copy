import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.sentinel.question_fingerprint import QuestionFingerprinter
from src.sentinel.agent import KNOWN_QA_PATTERNS
import json

fp = QuestionFingerprinter()
fp.build_index(KNOWN_QA_PATTERNS)

q = 'are you currently employed'
fingerprint = fp.get_fingerprint(q)
print("Fingerprint for '{}': '{}'".format(q, fingerprint))

ans, conf = fp.find_best_match(q)
print("Best match for '{}': '{}' (conf: {})".format(q, ans, conf))

# Let's find what question it matched from the index
for k, v in fp.fingerprint_to_answer.items():
    if k == fingerprint:
        print("Matches fingerprint from index with answer:", v)
