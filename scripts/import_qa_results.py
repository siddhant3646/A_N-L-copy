"""
Script to auto-learn new QA patterns from the consolidated qa_results.csv.

Reads the QA results CSV, groups questions by frequency, and proposes new
pattern entries for questions that:
  - Appear 3+ times (high frequency = worth covering)
  - Are not already matched by existing patterns in qa_patterns.json
  - Have a consistent, high-confidence answer

Usage:
    python scripts/import_qa_results.py [--csv PATH] [--dry-run] [--min-frequency N]

The script will:
1. Load qa_patterns.json
2. Load qa_results.csv
3. For each unique question with frequency >= min_frequency:
   a. Check if it matches any existing pattern
   b. If not, propose a new pattern entry
4. Print a summary of proposed new patterns
5. Optionally write them to qa_patterns.json (unless --dry-run)
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

DEFAULT_CSV = os.path.expanduser("~/Desktop/sentinel_errors/qa_results.csv")
PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "qa_patterns.json")
MIN_FREQUENCY = 3
MIN_CONFIDENCE = 0.80


def load_patterns(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_csv(path):
    """Return dict of {question: {count, top_answer, platform, input_type}}."""
    questions = defaultdict(lambda: {"count": 0, "answers": defaultdict(int),
                                      "platforms": set(), "input_types": set()})
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("question") or "").strip()
            a = (row.get("answer") or "").strip()
            if not q or not a:
                continue
            info = questions[q]
            info["count"] += 1
            info["answers"][a] += 1
            if row.get("platform"):
                info["platforms"].add(row["platform"])
            if row.get("input_type"):
                info["input_types"].add(row["input_type"])
    return questions


def question_matches_existing(question, patterns_data):
    """Check if a question matches any existing pattern (fuzzy)."""
    ql = question.lower().strip()
    best_score = 0.0
    for cat_id, pdata in patterns_data["patterns"].items():
        for pat in pdata.get("patterns", []):
            pl = pat.lower().strip()
            if pl in ql or ql in pl:
                return True, 1.0, cat_id
            ratio = SequenceMatcher(None, ql, pl).ratio()
            if ratio > best_score:
                best_score = ratio
                best_cat = cat_id
    return False, best_score, best_cat if best_score > 0 else None


def categorize_question(question, answer):
    """Guess the category for a new pattern based on question/answer text."""
    ql = question.lower()
    al = answer.lower().strip()

    if any(k in ql for k in ["ctc", "salary", "lpa", "compensation", "package"]):
        return "salary"
    if any(k in ql for k in ["notice", "serving", "lwd", "last working"]):
        return "notice_period"
    if any(k in ql for k in ["location", "relocate", "city", "based in"]):
        return "location"
    if any(k in ql for k in ["year", "experience", "exp"]):
        return "experience"
    if any(k in ql for k in ["rate", "proficiency", "scale"]):
        return "skills"
    if any(k in ql for k in ["education", "degree", "qualification"]):
        return "education"
    if al in ("yes", "no") or al.startswith("yes,") or al.startswith("no,"):
        return "yes_no"
    if any(k in ql for k in ["email", "phone", "name", "pan", "dob"]):
        return "personal_info"
    if any(k in ql for k in ["available", "start date", "interview"]):
        return "availability"
    return "preference"


def generate_pattern_id(question, existing_keys):
    """Generate a unique pattern ID from the question text."""
    words = re.findall(r"[a-z]+", question.lower())
    meaningful = [w for w in words if len(w) > 2 and w not in
                  ("the", "and", "for", "are", "you", "your", "what", "how",
                   "have", "been", "with", "from", "this", "that", "please",
                   "mention", "enter", "provide", "share", "list")][:3]
    if not meaningful:
        meaningful = words[:3] if words else ["unknown"]
    base = "_".join(meaningful)
    pid = base
    counter = 1
    while pid in existing_keys:
        pid = f"{base}_{counter}"
        counter += 1
    return pid


def extract_pattern_strings(question):
    """Extract 3-5 pattern string variants from a real question."""
    ql = question.lower().strip().rstrip("?").strip()
    variants = [ql]

    # Remove leading "what is your" / "what is" / "please"
    stripped = re.sub(r"^(what is your|what is|please mention|please enter|please provide|please share|mention|enter|provide|share)\s+", "", ql)
    if stripped and stripped != ql:
        variants.append(stripped)

    # Add a shorter form (first few words)
    words = ql.split()
    if len(words) > 3:
        short = " ".join(words[:4])
        if short not in variants:
            variants.append(short)

    # Add "your X" form
    if not ql.startswith("your "):
        variants.append(f"your {stripped}")

    # Deduplicate and cap at 5
    seen = set()
    unique = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique[:5]


def main():
    parser = argparse.ArgumentParser(description="Auto-learn patterns from QA results CSV")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to qa_results.csv")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to JSON, just print proposals")
    parser.add_argument("--min-frequency", type=int, default=MIN_FREQUENCY,
                        help=f"Minimum occurrence count (default {MIN_FREQUENCY})")
    parser.add_argument("--min-confidence", type=float, default=MIN_CONFIDENCE,
                        help=f"Minimum answer consistency (default {MIN_CONFIDENCE})")
    parser.add_argument("--output", default=PATTERNS_FILE, help="Output JSON file")
    args = parser.parse_args()

    csv_path = os.path.expanduser(args.csv)
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    patterns_data = load_patterns(args.output)
    questions = load_csv(csv_path)

    print(f"Loaded {len(questions)} unique questions from {csv_path}")
    print(f"Loaded {len(patterns_data['patterns'])} existing pattern categories")
    print(f"Min frequency: {args.min_frequency}, Min confidence: {args.min_confidence}")
    print()

    proposals = []
    skipped_matched = 0
    skipped_low_freq = 0
    skipped_inconsistent = 0

    for q, info in sorted(questions.items(), key=lambda x: -x[1]["count"]):
        if info["count"] < args.min_frequency:
            skipped_low_freq += 1
            continue

        # Check answer consistency
        top_answer, top_count = max(info["answers"].items(), key=lambda x: x[1])
        consistency = top_count / info["count"]
        if consistency < args.min_confidence:
            skipped_inconsistent += 1
            continue

        # Check if already matched
        matched, score, matched_cat = question_matches_existing(q, patterns_data)
        if matched:
            skipped_matched += 1
            continue

        # Propose new pattern
        category = categorize_question(q, top_answer)
        pattern_id = generate_pattern_id(q, patterns_data["patterns"].keys())
        pattern_strings = extract_pattern_strings(q)

        proposals.append({
            "id": pattern_id,
            "question": q,
            "count": info["count"],
            "answer": top_answer,
            "consistency": f"{consistency:.0%}",
            "category": category,
            "platforms": list(info["platforms"]),
            "input_types": list(info["input_types"]),
            "proposed_patterns": pattern_strings,
        })

    print(f"=== Summary ===")
    print(f"Proposed new patterns: {len(proposals)}")
    print(f"Skipped (already matched): {skipped_matched}")
    print(f"Skipped (low frequency): {skipped_low_freq}")
    print(f"Skipped (inconsistent answer): {skipped_inconsistent}")
    print()

    if not proposals:
        print("No new patterns to add. All frequent questions are already covered.")
        return

    print("=== Proposed New Patterns ===")
    for p in proposals[:30]:
        print(f"\n  [{p['count']}x] {p['id']} (cat={p['category']}, consistency={p['consistency']})")
        print(f"    Q: {p['question'][:80]}")
        print(f"    A: {p['answer'][:60]}")
        print(f"    Patterns: {p['proposed_patterns']}")

    if len(proposals) > 30:
        print(f"\n... and {len(proposals) - 30} more proposals")

    if args.dry_run:
        print("\n[DRY RUN] No changes written. Remove --dry-run to apply.")
        return

    answer = input(f"\nAdd {len(proposals)} new patterns to {args.output}? (y/N): ")
    if answer.lower().strip() != "y":
        print("Aborted. No changes made.")
        return

    added = 0
    for p in proposals:
        entry = {
            "patterns": p["proposed_patterns"],
            "category": p["category"],
            "default": p["answer"],
            "input_type_defaults": {
                "text": p["answer"],
            },
            "priority": 5,
            "auto_learned": True,
        }
        patterns_data["patterns"][p["id"]] = entry
        added += 1

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(patterns_data, f, indent=2)

    print(f"Added {added} new pattern categories to {args.output}")
    print(f"Total categories now: {len(patterns_data['patterns'])}")


if __name__ == "__main__":
    main()