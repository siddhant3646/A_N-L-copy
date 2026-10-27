#!/usr/bin/env python3
"""
Repair ``input_type_defaults`` across config/qa_patterns.json.

The script is intentionally deterministic:

* Every pattern gets explicit values for the six core controls
  (text, textarea, radio, select, checkbox, number).
* Values are derived from the question intent and the canonical answer by
  ``src/patterns/input_type_sanitizer.py`` so the JSON and runtime paths share
  one source of truth.
* Specialised controls (date, tel, text_inr, text_lpa, select-location,
  select-education) are added when the question clearly needs them.
* A small number of known-bad data points (stale Noida address/ZIP, the stale
  TCS registration default) are corrected before derivation.
* Existing intentional values that are structurally valid are preserved.

Usage:
    python scripts/repair_input_type_defaults.py --dry-run
    python scripts/repair_input_type_defaults.py --apply
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = ROOT / "config" / "qa_patterns.json"
sys.path.insert(0, str(ROOT / "src"))

from patterns.input_type_sanitizer import (  # noqa: E402
    CORE_INPUT_TYPES,
    build_input_type_defaults,
    correct_stale_date_default,
    detect_pii_kind,
    normalize_input_type,
)

# Canonical answers that are known to be stale in the corpus.  The values on
# the individual controls already say "No"; only the canonical default was
# left behind by an earlier CSV import.
DEFAULT_OVERRIDES: Dict[str, str] = {
    "tcs_registered_check": "No",
}

# The candidate lives in Bengaluru (560001).  Older groups still carried the
# previous Noida address, and a few controls disagreed with their own default.
FIELD_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "street_address": {
        "default": "Bengaluru, Karnataka",
        "text": "Bengaluru, Karnataka",
        "textarea": "Bengaluru, Karnataka, India",
        "radio": "Bengaluru",
        "select": "Bengaluru",
    },
    "address_line2": {
        "default": "Karnataka, India",
        "text": "Karnataka, India",
        "textarea": "Karnataka, India",
        "radio": "Bengaluru",
        "select": "Bengaluru",
    },
    "current_address": {
        "default": "Bengaluru, Karnataka, India - 560001",
        "text": "Bengaluru, Karnataka, India - 560001",
        "textarea": "Bengaluru, Karnataka, India - 560001",
        "radio": "Bengaluru",
        "select": "Bengaluru",
    },
    "zip_code": {
        "default": "560001",
        "text": "560001",
        "textarea": "560001",
        "radio": "560001",
        "select": "560001",
        "number": "560001",
    },
    # The question offers only Noida/Pune; answer one of the actual options so
    # the value can be selected instead of producing a non-option city.
    "location_preference_noida_pune": {
        "default": "Noida",
        "radio": "Noida",
        "select": "Noida",
        "text": "Noida",
        "textarea": "Noida",
    },
    "job_application_location": {
        "radio": "Bengaluru",
        "select": "Bengaluru",
        "text": "Bengaluru",
        "textarea": "Bengaluru",
    },
}

UPDATABLE_NUMERIC_ALIASES = ("numeric_default", "inr_default", "lpa_default")


def load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path: Path, data: Dict[str, Any]) -> Path:
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
    shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o644)
    return backup


def _apply_known_overrides(pattern_id: str, data: Dict[str, Any]) -> List[str]:
    changes: List[str] = []
    if pattern_id in DEFAULT_OVERRIDES:
        new_default = DEFAULT_OVERRIDES[pattern_id]
        if str(data.get("default", "")) != new_default:
            data["default"] = new_default
            changes.append("default")
    overrides = FIELD_OVERRIDES.get(pattern_id)
    if not overrides:
        return changes
    defaults = data.get("input_type_defaults")
    if not isinstance(defaults, dict):
        defaults = {}
        data["input_type_defaults"] = defaults
    for field, value in overrides.items():
        if field == "default":
            if str(data.get("default", "")) != str(value):
                data["default"] = value
                changes.append("default")
            continue
        if defaults.get(field) != value:
            defaults[field] = value
            changes.append(field)
    return changes


def _apply_semantic_corrections(pattern_id: str, data: Dict[str, Any]) -> List[str]:
    """Correct stale dates and mark direct personal identifiers as PII."""
    changes: List[str] = []
    question = str((data.get("patterns") or [""])[0])
    category = str(data.get("category", ""))
    default = str(data.get("default", ""))

    corrected = correct_stale_date_default(question, category, default)
    if corrected != default:
        data["default"] = corrected
        changes.append("dynamic_date")

    pii_kind = detect_pii_kind(question, str(data.get("default", "")))
    if pii_kind:
        if data.get("sensitive") is not True:
            data["sensitive"] = True
            changes.append(f"{pii_kind}_sensitive")
        if data.get("requires_exact_match") is not True:
            data["requires_exact_match"] = True
            changes.append(f"{pii_kind}_exact")
    return changes


def _sync_aliases(data: Dict[str, Any], new_defaults: Dict[str, Any]) -> None:
    """Keep numeric/inr/lpa aliases aligned with the repaired type matrix."""
    if "numeric_default" in data:
        value = new_defaults.get("number")
        if value is not None and str(data.get("numeric_default")) != str(value):
            data["numeric_default"] = str(value)
    if "inr_default" in data:
        value = new_defaults.get("text_inr") or new_defaults.get("number")
        if value is not None and str(data.get("inr_default")) != str(value):
            data["inr_default"] = str(value)
    if "lpa_default" in data:
        value = new_defaults.get("text_lpa") or new_defaults.get("number")
        if value is not None and str(data.get("lpa_default")) != str(value):
            data["lpa_default"] = str(value)


def repair(patterns: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    pattern_map = patterns.get("patterns", {})
    if not isinstance(pattern_map, dict):
        raise SystemExit("config/qa_patterns.json has no 'patterns' object")

    core_added = Counter()
    core_replaced = Counter()
    special_added = Counter()
    known_changes: List[Tuple[str, str]] = []
    semantic_changes: List[Tuple[str, str]] = []
    alias_changes = 0

    for pattern_id, data in pattern_map.items():
        if not isinstance(data, dict):
            continue
        known = _apply_known_overrides(pattern_id, data)
        semantic = _apply_semantic_corrections(pattern_id, data)
        known = known + semantic
        if known:
            known_changes.append((pattern_id, ", ".join(sorted(set(known)))))
        if semantic:
            semantic_changes.append((pattern_id, ", ".join(sorted(set(semantic)))))

        existing = data.get("input_type_defaults")
        if not isinstance(existing, dict):
            existing = {}
        before = dict(existing)
        repaired = build_input_type_defaults(data, existing)

        for input_type in CORE_INPUT_TYPES:
            if input_type not in before:
                core_added[input_type] += 1
            elif before.get(input_type) != repaired.get(input_type):
                core_replaced[input_type] += 1
        for input_type in repaired:
            if input_type not in before:
                special_added[input_type] += 1

        data["input_type_defaults"] = repaired
        alias_before = {key: copy.deepcopy(data.get(key)) for key in UPDATABLE_NUMERIC_ALIASES}
        _sync_aliases(data, repaired)
        if any(alias_before[key] != data.get(key) for key in UPDATABLE_NUMERIC_ALIASES):
            alias_changes += 1

    stats = {
        "patterns": len(pattern_map),
        "core_added": dict(core_added),
        "core_replaced": dict(core_replaced),
        "special_added": dict(special_added),
        "alias_changes": alias_changes,
        "known_changes": known_changes,
        "semantic_changes": semantic_changes,
    }
    return patterns, stats


def print_stats(stats: Dict[str, Any]) -> None:
    print(f"Patterns scanned: {stats['patterns']}")
    print("\nCore input types added:")
    for input_type in CORE_INPUT_TYPES:
        print(f"  {input_type:10s} {stats['core_added'].get(input_type, 0):6d}")
    print("\nCore input types replaced:")
    for input_type in CORE_INPUT_TYPES:
        print(f"  {input_type:10s} {stats['core_replaced'].get(input_type, 0):6d}")
    print("\nSpecialised input types added:")
    for input_type, count in sorted(stats["special_added"].items(), key=lambda item: -item[1]):
        if input_type not in CORE_INPUT_TYPES:
            print(f"  {input_type:18s} {count:6d}")
    print(f"\nNumeric/inr/lpa aliases updated: {stats['alias_changes']}")
    if stats["semantic_changes"]:
        kinds = Counter()
        for _, fields in stats["semantic_changes"]:
            for field in fields.split(", "):
                kinds[field] += 1
        print("\nSemantic/PII corrections:")
        for kind, count in sorted(kinds.items(), key=lambda item: -item[1]):
            print(f"  {kind:24s} {count:5d}")
    if stats["known_changes"]:
        print("\nKnown data corrections (sample):")
        for pattern_id, fields in stats["known_changes"][:20]:
            print(f"  {pattern_id}: {fields}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair QA input_type_defaults.")
    parser.add_argument("--patterns", default=str(DEFAULT_PATTERNS), help="Path to qa_patterns.json")
    parser.add_argument("--apply", action="store_true", help="Write the repaired JSON (default is dry-run)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    path = Path(args.patterns)
    if not path.exists():
        print(f"Patterns file not found: {path}", file=sys.stderr)
        return 2

    patterns = load(path)
    repaired, stats = repair(patterns)
    print_stats(stats)

    if not args.apply:
        print("\n[DRY RUN] no files were written; pass --apply to write the repaired JSON")
        return 0

    backup = atomic_write(path, repaired)
    print(f"\nApplied. Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
