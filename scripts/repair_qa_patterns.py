"""
Repair and prune config/qa_patterns.json.

Subcommands (all dry-run unless --apply; every apply is atomic with a
timestamped .bak backup next to the JSON):

    report      Scan only: family counts, template counts, duplicate triggers,
                conflict samples. Writes CSV report with --report-out.
    prune       Delete approved mechanically-generated families:
                  - key prefix in {prof_, star_, hr_, worked_, yn_, comp_}
                  - key suffix *_troubleshooting
                  - adv_ groups whose default matches a template marker
    dedup       Resolve duplicate trigger strings. Same-default duplicates:
                keep trigger in winner only. Conflicting defaults: winner =
                highest (priority, pattern-count, key); trigger removed from
                losers; groups left with no patterns are dropped and logged.
    fix-data    Correct known-bad data: Noida-addressed groups -> Bengaluru,
                delete field_* groups carrying https://example.com/profile,
                set Indian-citizen visa groups to not-applicable, fill PII
                groups from --values JSON when provided.
    validate    Post-check: schema, empty pattern lists, duplicate scan.

Usage:
    python scripts/repair_qa_patterns.py report [--report-out conflicts.csv]
    python scripts/repair_qa_patterns.py prune --apply
    python scripts/repair_qa_patterns.py dedup --apply [--report-out conflicts.csv]
    python scripts/repair_qa_patterns.py fix-data --apply --values values.json
    python scripts/repair_qa_patterns.py validate
"""

import argparse
import copy
import csv
import json
import os
import shutil
import sys
import time
from collections import defaultdict

PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "qa_patterns.json")

PRUNE_PREFIXES = ("prof_", "star_", "hr_", "worked_", "yn_", "comp_")
PRUNE_SUFFIX = "_troubleshooting"
ADV_PREFIX = "adv_"
TEMPLATE_MARKERS = (
    "Yes, extensive hands-on experience implementing",
    "Architected robust distributed components using",
    "When architecting with",
    "To troubleshoot",
    "Troubleshoot ",
    "Core best practices for",
    "Yes, fully confident explaining",
)
FIELD_JUNK_DEFAULT = "https://example.com/profile"
FIELD_JUNK_DELETE = [
    "field_twitter_handle", "field_personal_website", "field_blog_url",
    "field_cover_letter", "field_resume_cv", "field_transcript",
    "field_certification_document", "field_reference_contact",
    "field_emergency_contact", "field_pan_card", "field_aadhaar",
    "field_passport_number", "field_visa_status",
]
NOIDA_FIX = {
    "location_preference_noida_pune": "Bengaluru",
    "job_application_location": "Bengaluru",
}
VISA_NOT_APPLICABLE = {
    "personal_visa_validity": "Not applicable - Indian citizen",
    "personal_visa_expiry": "Not applicable - Indian citizen",
    "personal_work_permit_number": "Not applicable - Indian citizen",
}
PII_VALUE_KEYS = [
    "aadhaar_number", "personal_aadhaar_number",
    "passport_number", "personal_passport_number",
    "emergency_contact_name", "emergency_contact_phone",
    "personal_emergency_contact", "personal_relationship_with_emergency_contact",
    "personal_blood_group", "personal_marital_status",
]


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write(path, data):
    backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o644)
    return backup


def is_adv_template(group):
    d = str(group.get("default", ""))
    return d.startswith(TEMPLATE_MARKERS)


def prune_set(pats):
    keys = set()
    for k in pats:
        if k.startswith(PRUNE_PREFIXES) or k.endswith(PRUNE_SUFFIX):
            keys.add(k)
        elif k.startswith(ADV_PREFIX) and is_adv_template(pats[k]):
            keys.add(k)
    return keys


def trigger_map(pats):
    tmap = defaultdict(list)
    for k, v in pats.items():
        for p in v.get("patterns", []):
            tmap[p.lower().strip()].append(k)
    return tmap


def pick_winner(keys, pats):
    def sort_key(k):
        g = pats[k]
        return (-g.get("priority", 5), -len(g.get("patterns", [])), k)
    return sorted(keys, key=sort_key)[0]


def cmd_report(args):
    data = load(args.file)
    pats = data["patterns"]
    prune = prune_set(pats)
    tmap = trigger_map(pats)
    dups = {t: ks for t, ks in tmap.items() if len(ks) > 1}
    benign = conflict = 0
    rows = []
    for t, ks in sorted(dups.items()):
        defaults = {str(pats[k].get("default", "")).strip().lower() for k in ks}
        kind = "benign" if len(defaults) == 1 else "conflict"
        if kind == "benign":
            benign += 1
        else:
            conflict += 1
        winner = pick_winner(ks, pats)
        for k in ks:
            if k != winner or kind == "conflict":
                rows.append({
                    "trigger": t, "kind": kind, "winner": winner,
                    "group": k, "default": pats[k].get("default", ""),
                    "priority": pats[k].get("priority", 5),
                })
    n_strings = sum(len(pats[k].get("patterns", [])) for k in prune)
    n_all = sum(len(v.get("patterns", [])) for v in pats.values())
    print(f"groups total           : {len(pats)}")
    print(f"prune-set groups       : {len(prune)} ({n_strings}/{n_all} strings, {n_strings * 100 // max(n_all, 1)}%)")
    print(f"duplicate triggers     : {len(dups)} (benign {benign}, conflict {conflict})")
    if rows:
        if args.report_out:
            with open(args.report_out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(f"detail report          : {args.report_out} ({len(rows)} rows)")
        print("\nSample conflicts:")
        for r in rows:
            if r["kind"] == "conflict":
                print(f"  {r['trigger'][:45]!r}: {r['group']} -> {str(r['default'])[:50]!r}")
                if sum(1 for x in rows[:rows.index(r) + 1] if x["kind"] == "conflict") >= 8:
                    break
    return 0


def cmd_prune(args):
    data = load(args.file)
    pats = data["patterns"]
    doomed = prune_set(pats)
    print(f"Would delete {len(doomed)} groups (of {len(pats)})")
    if not doomed:
        return 0
    if not args.apply:
        for k in sorted(doomed)[:15]:
            print(f"  - {k}")
        if len(doomed) > 15:
            print(f"  ... and {len(doomed) - 15} more")
        print("[DRY RUN] use --apply to write")
        return 0
    for k in doomed:
        del pats[k]
    backup = atomic_write(args.file, data)
    print(f"Deleted {len(doomed)} groups. Backup: {backup}")
    print(f"Groups now: {len(pats)}")
    return 0


def cmd_dedup(args):
    data = load(args.file)
    pats = data["patterns"]
    tmap = trigger_map(pats)
    dups = {t: ks for t, ks in tmap.items() if len(ks) > 1}
    print(f"Duplicate triggers: {len(dups)}")
    if not dups:
        return 0

    original = copy.deepcopy(pats)
    removed_strings = 0
    dropped_groups = []
    report_rows = []

    for t, ks in dups.items():
        winner = pick_winner(ks, pats)
        defaults = {str(original[k].get("default", "")).strip().lower() for k in ks}
        kind = "benign" if len(defaults) == 1 else "conflict"
        for k in ks:
            if k == winner:
                continue
            before = pats[k].get("patterns", [])
            after = [p for p in before if p.lower().strip() != t]
            removed_strings += len(before) - len(after)
            report_rows.append({
                "trigger": t, "kind": kind, "winner": winner, "loser": k,
                "loser_default": original[k].get("default", ""),
                "winner_default": original[winner].get("default", ""),
            })
            if not after:
                dropped_groups.append(k)
                del pats[k]
            else:
                pats[k]["patterns"] = after

    print(f"Trigger strings removed: {removed_strings}")
    print(f"Groups dropped (emptied): {len(dropped_groups)}")
    for k in dropped_groups[:10]:
        print(f"  - {k}")
    if args.report_out and report_rows:
        with open(args.report_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            w.writeheader()
            w.writerows(report_rows)
        print(f"Detail report: {args.report_out} ({len(report_rows)} rows)")
    if not args.apply:
        print("[DRY RUN] use --apply to write")
        return 0
    backup = atomic_write(args.file, data)
    print(f"Applied. Backup: {backup}. Groups now: {len(pats)}")
    return 0


def cmd_fix_data(args):
    data = load(args.file)
    pats = data["patterns"]
    changes = []

    for key, new_default in NOIDA_FIX.items():
        if key in pats and pats[key].get("default") != new_default:
            changes.append((key, pats[key].get("default"), new_default))
            pats[key]["default"] = new_default

    for key in FIELD_JUNK_DELETE:
        if key in pats and pats[key].get("default") == FIELD_JUNK_DEFAULT:
            changes.append((key, pats[key].get("default"), "<deleted>"))
            del pats[key]

    for key, val in VISA_NOT_APPLICABLE.items():
        if key in pats and pats[key].get("default") != val:
            changes.append((key, pats[key].get("default"), val))
            pats[key]["default"] = val
            itd = pats[key].get("input_type_defaults")
            if isinstance(itd, dict):
                for t in list(itd):
                    if itd[t] == "Please provide":
                        itd[t] = val

    values = {}
    if args.values:
        with open(os.path.expanduser(args.values), "r", encoding="utf-8") as f:
            values = json.load(f)
    for key in PII_VALUE_KEYS:
        if key in values and key in pats:
            val = str(values[key])
            if pats[key].get("default") != val:
                old_default = pats[key].get("default")
                changes.append((key, old_default, val))
                pats[key]["default"] = val
                itd = pats[key].get("input_type_defaults")
                if isinstance(itd, dict):
                    for t in list(itd):
                        if itd[t] in ("Please provide",) or itd[t] == old_default:
                            itd[t] = val

    placeholder_defaults = {"please provide", "emergency contact",
                            "123456789012", "a1234567", "9876543210"}
    missing = [k for k in PII_VALUE_KEYS
               if k not in values
               and str(pats.get(k, {}).get("default", "")).strip().lower() in placeholder_defaults]
    print(f"Changes: {len(changes)}")
    for key, old, new in changes:
        print(f"  {key}: {str(old)[:40]!r} -> {str(new)[:50]!r}")
    if missing:
        print(f"\nAwaiting user values for: {missing}")
    if not changes:
        print("Nothing to do.")
        return 0
    if not args.apply:
        print("[DRY RUN] use --apply to write")
        return 0
    backup = atomic_write(args.file, data)
    print(f"Applied. Backup: {backup}. Groups now: {len(pats)}")
    return 0


def cmd_validate(args):
    data = load(args.file)
    pats = data["patterns"]
    errors = []
    for k, v in pats.items():
        p_list = v.get("patterns")
        if not isinstance(p_list, list) or not p_list:
            errors.append(f"{k}: patterns missing/empty")
        if not isinstance(v.get("default"), str) or not v["default"].strip():
            errors.append(f"{k}: default missing/empty")
        if "category" not in v:
            errors.append(f"{k}: category missing")
    tmap = trigger_map(pats)
    dups = {t: ks for t, ks in tmap.items() if len(ks) > 1}
    print(f"groups: {len(pats)}, strings: {sum(len(v.get('patterns', [])) for v in pats.values())}")
    print(f"schema errors: {len(errors)}, duplicate triggers: {len(dups)}")
    for e in errors[:10]:
        print(f"  ! {e}")
    if errors or dups:
        return 1
    print("OK")
    return 0


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--file", default=PATTERNS_FILE)
    common.add_argument("--report-out", default="")
    common.add_argument("--apply", action="store_true")
    common.add_argument("--values", default="", help="JSON file with PII values for fix-data")
    parser = argparse.ArgumentParser(description="Repair qa_patterns.json", parents=[common])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("report", "prune", "dedup", "fix-data", "validate"):
        sub.add_parser(name, parents=[common])
    args = parser.parse_args()
    args.file = os.path.abspath(args.file)
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return {"report": cmd_report, "prune": cmd_prune, "dedup": cmd_dedup,
            "fix-data": cmd_fix_data, "validate": cmd_validate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
