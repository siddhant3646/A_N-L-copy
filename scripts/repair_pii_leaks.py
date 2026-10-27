#!/usr/bin/env python3
"""Targeted repair for the PII-leaking QA patterns.

The full-corpus audit only inspects each pattern's canonical ``default``.  It
therefore misses PII that has already been baked into ``input_type_defaults``
for derived controls (``number``/``tel``).  This script fixes both classes:

1. Patterns whose canonical answer is PII get ``sensitive``/``requires_exact_match``
   flags so the audit and the runtime treat them as PII.
2. Patterns whose canonical answer is *not* PII but whose derived ``number``/
   ``tel`` defaults contain the candidate's real phone number are rewritten to
   an honest non-PII placeholder (``1`` for affirmative/available answers).

The script is idempotent and writes an atomic backup before touching the file.

Usage:
    .venv/bin/python scripts/repair_pii_leaks.py --dry-run
    .venv/bin/python scripts/repair_pii_leaks.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path("config/qa_patterns.json")

# Patterns whose canonical default is PII and therefore need the flags.
# pattern_id -> (sensitive, requires_exact_match)
PII_FLAGS: dict[str, tuple[bool, bool]] = {
    "aadhaar_number": (True, True),
    "personal_aadhaar_number": (True, True),
    "preference_3544": (True, True),
    "personal_secondary_contact": (True, True),
    "personal_emergency_contact": (True, True),
}

# Patterns whose canonical default is NOT PII, but whose derived number/tel
# fields contain the candidate's real phone number.  Replace with "1" to
# encode "yes/available" without leaking the number.
# ``tel`` must be 7-15 digits to pass the audit's structural check.  "1" is a
# valid boolean encoding for the ``number`` control but not for ``tel``, so use
# an all-zero placeholder that is structurally valid and clearly non-PII.
ITD_OVERRIDES: dict[str, dict[str, str]] = {
    "ref_reference_phone": {"number": "1", "tel": "0000000000"},
    "personal_info_9627": {"number": "1", "tel": "0000000000"},
}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _backup_path() -> Path:
    return CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.bak-{_timestamp()}")


def _load() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _apply(data: dict, dry_run: bool) -> list[str]:
    patterns = data.get("patterns")
    if not isinstance(patterns, dict):
        raise SystemExit("config/qa_patterns.json: 'patterns' is not a dict")

    changes: list[str] = []

    for pattern_id, (sensitive, exact) in PII_FLAGS.items():
        entry = patterns.get(pattern_id)
        if not isinstance(entry, dict):
            changes.append(f"MISSING pattern {pattern_id}")
            continue
        changed = False
        if entry.get("sensitive") is not sensitive:
            entry["sensitive"] = sensitive
            changed = True
        if entry.get("requires_exact_match") is not exact:
            entry["requires_exact_match"] = exact
            changed = True
        if changed:
            changes.append(
                f"{pattern_id}: sensitive={sensitive} requires_exact_match={exact}"
            )

    for pattern_id, overrides in ITD_OVERRIDES.items():
        entry = patterns.get(pattern_id)
        if not isinstance(entry, dict):
            changes.append(f"MISSING pattern {pattern_id}")
            continue
        itd = entry.get("input_type_defaults")
        if not isinstance(itd, dict):
            changes.append(f"{pattern_id}: input_type_defaults missing")
            continue
        for field, value in overrides.items():
            if itd.get(field) != value:
                old = itd.get(field)
                itd[field] = value
                changes.append(f"{pattern_id}.{field}: {old!r} -> {value!r}")

    if not dry_run and changes:
        backup = _backup_path()
        shutil.copy2(CONFIG_PATH, backup)
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        changes.append(f"backup: {backup}")

    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="report without writing")
    mode.add_argument("--apply", action="store_true", help="write the repaired file")
    args = parser.parse_args(argv)

    data = _load()
    changes = _apply(data, dry_run=args.dry_run)

    if not changes:
        print("No changes required (already repaired).")
        return 0

    print(f"{'Would apply' if args.dry_run else 'Applied'} {len(changes)} change(s):")
    for change in changes:
        print(f"  - {change}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
