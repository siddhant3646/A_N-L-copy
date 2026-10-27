#!/usr/bin/env python3
"""Audit over-broad / overlapping QA patterns for wrong-answer risk.

``scripts/audit_qa_input_types.py`` validates the *shape* of every
``input_type_defaults`` value.  It cannot see the two overlap hazards that also
need checking:

1. **Equal-priority contradictions** — two pattern groups that own the *same*
   question string at the *same* priority but return materially different
   answers.  The matcher then resolves the tie by JSON insertion order, so the
   answer is nondeterministic.  This class must be empty and is a hard gate.

2. **Over-broad steals** — a short, generic question string ``A`` (e.g.
   ``background check``) that is a proper substring of a longer, more specific
   string ``B`` (e.g. ``criminal background check``) owned by another group.
   Merely being a substring is *not* a bug: the matcher resolves an exact
   question by the exact owner and, for non-exact questions, prefers the
   longest substring owner, so ``B`` normally wins.  A *real* steal is only
   when the matcher, run on the specific question, actually returns the broad
   owner's answer.  Those are verified empirically (sampled) against the live
   matcher; unguarded substring pairs are additionally listed for review.

The script is read-only and exits non-zero when an actionable conflict exists.

Usage::

    python scripts/audit_pattern_overlaps.py
    python scripts/audit_pattern_overlaps.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:  # pragma: no cover - import guard for standalone use
    from patterns.input_type_sanitizer import detect_intent
except Exception:  # pragma: no cover
    detect_intent = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ROOT / "config" / "qa_patterns.json"
sys.path.insert(0, str(ROOT / "src"))

# Strings analysed as potential over-broad owners.
MAX_BROAD_LEN = 40
MAX_BROAD_WORDS = 5
# Cap on live-matcher probes so the audit stays fast.
MAX_PROBES = 400
# Distinct specific children sampled per broad string.
CHILDREN_PER_BROAD = 4

_BOOL_RE = re.compile(r"^(yes|y|true|no|n|false)\b")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_UNIT_RE = re.compile(r"\b(lpa|lakh|lakhs|lac|inr|per annum|p\.a\.)\b", re.IGNORECASE)


def load_patterns(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _leading_bool(value: str) -> Optional[str]:
    match = _BOOL_RE.match(str(value).strip().lower())
    if not match:
        return None
    token = match.group(1)
    return "yes" if token in ("yes", "y", "true") else "no"


def _numbers(value: str) -> set:
    return {float(n) for n in _NUM_RE.findall(_YEAR_RE.sub(" ", str(value)))}


def _has_unit(value: str) -> bool:
    return bool(_UNIT_RE.search(str(value)))


def answers_conflict(a: str, b: str) -> bool:
    """Heuristic: do two canonical answers mean materially different things?"""
    beta_a, beta_b = _leading_bool(a), _leading_bool(b)
    if beta_a or beta_b:
        return beta_a != beta_b
    nums_a, nums_b = _numbers(a), _numbers(b)
    if nums_a and nums_b:
        if nums_a & nums_b:
            return False
        if _has_unit(a) != _has_unit(b):
            for x in nums_a:
                for y in nums_b:
                    if abs(x * 100000 - y) <= 1 or abs(y * 100000 - x) <= 1:
                        return False
        return True
    return _norm(a) != _norm(b)


def _norm(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value).strip().lower())
    return re.sub(r"[\s,.;:/|-]+$", "", text)


_NA_VALUES = ("n/a", "na", "none", "not applicable", "not required", "nil")


def _fits_intent(question: str, category: str, default: str) -> Optional[bool]:
    """Does ``default`` look like a type-appropriate answer for the question?

    Returns True/False when the intent type is recognised, else None.  Used to
    tell a *real* steal (matcher returned the broad answer while the specific
    owner held the appropriate one) from a *benign* overlap (the specific
    owner's own default is the type-inappropriate one).
    """
    if detect_intent is None:
        return None
    intent = detect_intent(question, category, default)
    value = str(default).strip()
    lower = value.lower()
    is_na = lower in _NA_VALUES
    has_number = bool(re.search(r"\d", value))
    question_lower = question.lower()

    # Yes/no intent: a leading/embedded boolean is appropriate.
    if intent.is_yes_no:
        if is_na:
            return None
        return _leading_bool(value) is not None
    # A "how many"/quantity intent needs a number.
    if any(
        [
            intent.is_years,
            intent.is_rating,
            intent.is_salary,
            intent.is_notice,
            intent.is_age,
            intent.is_education_score,
            intent.is_team_size,
            intent.is_project_count,
        ]
    ):
        if is_na:
            return None
        return has_number
    # Date-ish intent needs a date, a dynamic marker, or N/A.
    if any([intent.is_date, intent.is_start_date, intent.is_lwd, intent.is_dob]):
        return has_number or is_na or "__DYNAMIC" in value
    if intent.is_open_ended:
        return len(value) > 30
    # Fallback: a boolean default only fits a boolean-style prompt.
    if _leading_bool(value) is not None:
        return bool(re.search(r"\b(do you|have you|are you|can you|will you|would you|is it|did you)\b", question_lower))
    return None


def audit(patterns: Dict[str, Any], max_examples: int = 40) -> Dict[str, Any]:
    pattern_map = patterns.get("patterns", {})

    owners: Dict[str, List[str]] = defaultdict(list)
    for pid, data in pattern_map.items():
        for pat in data.get("patterns") or []:
            owners[_norm(pat)].append(pid)

    def answer(pid: str) -> str:
        return str(pattern_map[pid].get("default", ""))

    def priority(pid: str) -> int:
        return int(pattern_map[pid].get("priority", 5))

    duplicates = 0
    equal_conflicts: List[Dict[str, Any]] = []
    for text, pids in owners.items():
        uniq = list(dict.fromkeys(pids))
        if len(uniq) < 2:
            continue
        duplicates += 1
        top = max(priority(p) for p in uniq)
        top_ids = [p for p in uniq if priority(p) == top]
        if len(top_ids) < 2:
            continue
        if any(
            answers_conflict(answer(x), answer(y))
            for i, x in enumerate(top_ids)
            for y in top_ids[i + 1 :]
        ):
            equal_conflicts.append(
                {
                    "question": text,
                    "owners": [
                        {"id": p, "priority": priority(p), "default": answer(p)[:120]}
                        for p in sorted(top_ids, key=lambda q: -priority(q))
                    ],
                }
            )

    # Inverted index of question strings by word, for substring discovery.
    index: Dict[str, List[str]] = defaultdict(list)
    for text in owners:
        for word in set(text.split()):
            index[word].append(text)

    # Candidate over-broad pairs (a proper substring owned by a conflicting group).
    candidates: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for text, pids in owners.items():
        if len(text) > MAX_BROAD_LEN or len(text.split()) > MAX_BROAD_WORDS:
            continue
        broad_owner = pids[0]
        negs = [
            str(n).strip().lower()
            for n in (pattern_map[broad_owner].get("negative_patterns") or [])
        ]
        rarest = min(set(text.split()), key=lambda w: len(index[w]))
        for candidate in index[rarest]:
            if candidate == text or len(candidate) <= len(text) or text not in candidate:
                continue
            for other in dict.fromkeys(owners[candidate]):
                if other == broad_owner:
                    continue
                if not answers_conflict(answer(broad_owner), answer(other)):
                    continue
                if any(neg and neg in candidate for neg in negs):
                    continue
                key = (text, other)
                candidates.setdefault(
                    key,
                    {
                        "broad": text,
                        "broad_id": broad_owner,
                        "broad_default": answer(broad_owner),
                        "specific": candidate,
                        "specific_id": other,
                        "specific_default": answer(other),
                    },
                )

    # Empirically confirm which candidates are real steals using the live matcher.
    real_steals: List[Dict[str, Any]] = []
    benign_steals: List[Dict[str, Any]] = []
    probes = 0
    if candidates:
        try:
            from patterns.pattern_matcher import create_matcher

            matcher = create_matcher(str(DEFAULT_PATTERNS))
        except Exception as exc:  # pragma: no cover - defensive
            matcher = None  # type: ignore[assignment]
            print(f"  (matcher unavailable: {exc})", file=sys.stderr)
        if matcher is not None:
            per_broad: Dict[str, int] = defaultdict(int)
            for row in candidates.values():
                if probes >= MAX_PROBES:
                    break
                if per_broad[row["broad"]] >= CHILDREN_PER_BROAD:
                    continue
                per_broad[row["broad"]] += 1
                probes += 1
                got, _ = matcher.fuzzy_match(row["specific"], input_type="text")
                if got is None:
                    continue
                # A candidate steal = the matcher returned the BROAD owner's
                # answer for the specific question (agrees with broad, disagrees
                # with the specific owner).
                if not (
                    not answers_conflict(str(got), row["broad_default"])
                    and answers_conflict(str(got), row["specific_default"])
                ):
                    continue
                row = dict(row, matcher_answer=str(got))
                # Classify: a *real* steal is one where the answer the matcher
                # produced is type-inappropriate for the question while the
                # specific owner actually held a type-appropriate answer.  When
                # the specific owner's own default is the inappropriate one the
                # overlap is benign (the broad answer is at least as good).
                category = str(
                    pattern_map.get(row["specific_id"], {}).get("category", "")
                )
                fits_got = _fits_intent(row["specific"], category, str(got))
                fits_specific = _fits_intent(
                    row["specific"], category, row["specific_default"]
                )
                if fits_got is False and fits_specific is True:
                    real_steals.append(row)
                else:
                    benign_steals.append(row)

    return {
        "pattern_count": len(pattern_map),
        "distinct_strings": len(owners),
        "duplicate_strings": duplicates,
        "equal_priority_conflicts": equal_conflicts[:max_examples],
        "equal_priority_conflict_count": len(equal_conflicts),
        "over_broad_candidates": len(candidates),
        "over_broad_probes": probes,
        "over_broad_steals": real_steals[:max_examples],
        "over_broad_steal_count": len(real_steals),
        "benign_overlaps": benign_steals[:max_examples],
        "benign_overlap_count": len(benign_steals),
        "clean": not equal_conflicts and not real_steals,
    }


def print_report(result: Dict[str, Any]) -> None:
    print(f"Patterns scanned:              {result['pattern_count']}")
    print(f"Distinct question strings:     {result['distinct_strings']}")
    print(f"Duplicate-owned strings:       {result['duplicate_strings']}")
    print(f"Equal-priority conflicts:      {result['equal_priority_conflict_count']}")
    print(f"Over-broad substring pairs:    {result['over_broad_candidates']}")
    print(f"  probed against live matcher: {result['over_broad_probes']}")
    print(f"  real steals (gating):        {result['over_broad_steal_count']}")
    print(f"  benign overlaps (reported):  {result.get('benign_overlap_count', 0)}")
    print(f"Clean:                         {result['clean']}")
    for row in result["equal_priority_conflicts"]:
        print(f"\n  [equal-priority] {row['question']!r}")
        for owner in row["owners"]:
            print(f"      pri={owner['priority']} {owner['id']:<40} {owner['default']!r}")
    for row in result["over_broad_steals"]:
        print(
            f"\n  [real steal] {row['specific']!r} -> {row['matcher_answer']!r}"
            f"\n      broad {row['broad']!r} ({row['broad_id']}={row['broad_default']!r})"
            f" vs specific ({row['specific_id']}={row['specific_default']!r})"
        )
    for row in result.get("benign_overlaps", []):
        print(
            f"\n  [benign] {row['specific']!r} -> {row['matcher_answer']!r}"
            f"\n      broad {row['broad']!r} ({row['broad_id']}={row['broad_default']!r})"
            f" vs specific ({row['specific_id']}={row['specific_default']!r})"
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit overlapping QA patterns.")
    parser.add_argument("--patterns", default=str(DEFAULT_PATTERNS))
    parser.add_argument("--json", dest="json_out", default=None)
    parser.add_argument("--max-examples", type=int, default=40)
    args = parser.parse_args(argv)

    result = audit(load_patterns(Path(args.patterns)), max_examples=args.max_examples)
    print_report(result)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
