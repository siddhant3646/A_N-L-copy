#!/usr/bin/env python3
"""Repair over-broad / mis-owned QA pattern strings found by the overlap audit.

Each change is scoped to a concrete wrong-answer risk and is idempotent:

1. ``preference_8139`` (monthly gross) also owned the *annual* expectation
   phrasings "financial expectations" / "what are your financial expectations"
   with a monthly value (250000).  Those strings belong to the annual expected
   CTC answer, so they are removed from the monthly pattern.
2. ``additional_months`` disqualified itself: its ``negative_patterns`` included
   the very words ("experience", "years of experience") contained in its own
   canonical phrasing "additional years of experience", so the generic
   experience answer hijacked the question.  The two over-broad negatives are
   dropped; the targeted ones (total/how many years) remain.
3. ``joining_date`` (notice days, "15") owned the *date* wordings
   "earliest joining date" / "tentative joining date" and outranked
   ``desired_start_date`` (a dynamic date).  Date wordings are moved to the
   start-date pattern.
4. ``rest_api`` (boolean "Yes") owned the numeric year wordings
   ("years of experience in rest api development", ...).  ``negative_patterns``
   now route those to the numeric experience answer.

Usage::

    python scripts/repair_pattern_overlap_edgecases.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ROOT / "config" / "qa_patterns.json"

REMOVE_PATTERNS = {
    "preference_8139": [
        "what are your financial expectations",
        "financial expectations",
    ],
    "joining_date": [
        "earliest joining date",
        "tentative joining date",
    ],
}

ADD_PATTERNS = {
    "desired_start_date": [
        "earliest joining date",
        "tentative joining date",
    ],
}

REMOVE_NEGATIVES = {
    "additional_months": ["experience", "years of experience"],
}

SET_NEGATIVES = {
    "rest_api": ["years of experience", "how many years", "years of work", "years of"],
}

# Free-text years answers must carry their unit so a text/textarea control shows
# a readable "4.2 Years" instead of a bare "4.2".
SET_INPUT_TYPE_DEFAULTS = {
    "tech_specific_experience": {"text": "4.2 Years", "textarea": "4.2 Years"},
}


def _norm(text: str) -> str:
    return str(text).strip().lower()


def repair(patterns: Dict[str, Any]) -> List[str]:
    changes: List[str] = []

    for pid, remove in REMOVE_PATTERNS.items():
        entry = patterns.get(pid)
        if not entry:
            continue
        current = list(entry.get("patterns") or [])
        keep = [p for p in current if _norm(p) not in {_norm(r) for r in remove}]
        if len(keep) != len(current):
            entry["patterns"] = keep
            changes.append(f"{pid}: removed {len(current) - len(keep)} over-broad pattern(s)")

    for pid, add in ADD_PATTERNS.items():
        entry = patterns.get(pid)
        if not entry:
            continue
        current = list(entry.get("patterns") or [])
        existing = {_norm(p) for p in current}
        added = [p for p in add if _norm(p) not in existing]
        if added:
            entry["patterns"] = current + added
            changes.append(f"{pid}: added {added}")

    for pid, remove in REMOVE_NEGATIVES.items():
        entry = patterns.get(pid)
        if not entry:
            continue
        current = list(entry.get("negative_patterns") or [])
        keep = [n for n in current if _norm(n) not in {_norm(r) for r in remove}]
        if len(keep) != len(current):
            entry["negative_patterns"] = keep
            changes.append(f"{pid}: dropped over-broad negative(s) {remove}")

    for pid, negatives in SET_NEGATIVES.items():
        entry = patterns.get(pid)
        if not entry:
            continue
        current = list(entry.get("negative_patterns") or [])
        if {_norm(n) for n in current} != {_norm(n) for n in negatives}:
            entry["negative_patterns"] = negatives
            changes.append(f"{pid}: set negative_patterns={negatives}")

    for pid, overrides in SET_INPUT_TYPE_DEFAULTS.items():
        entry = patterns.get(pid)
        if not entry:
            continue
        itd = dict(entry.get("input_type_defaults") or {})
        changed = {k: v for k, v in overrides.items() if itd.get(k) != v}
        if changed:
            itd.update(changed)
            entry["input_type_defaults"] = itd
            changes.append(f"{pid}: set input_type_defaults {changed}")

    return changes


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair overlap edge cases.")
    parser.add_argument("--patterns", default=str(DEFAULT_PATTERNS))
    parser.add_argument("--apply", action="store_true", help="write changes atomically")
    args = parser.parse_args(argv)

    path = Path(args.patterns)
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    changes = repair(document["patterns"])
    if not changes:
        print("No changes required (already repaired).")
        return 0

    print("Planned changes:")
    for change in changes:
        print(f"  - {change}")

    if not args.apply:
        print("\n(dry run; pass --apply to write)")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-overlap-edge-{stamp}")
    shutil.copy2(path, backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(path)
    print(f"\nApplied. Backup: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
