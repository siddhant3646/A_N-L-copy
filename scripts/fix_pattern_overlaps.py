#!/usr/bin/env python3
"""Resolve ambiguous/overlapping QA patterns that could yield wrong answers.

This is a targeted, idempotent repair for semantic collisions between pattern
groups whose ``patterns`` arrays share identical question strings.  Because the
matcher resolves equal-priority duplicates by JSON insertion order, such
collisions are non-deterministic *and* can return a semantically wrong answer
when the two owners encode different intents (e.g. "Non-Disclosure Agreement"
= "Yes, I agree" vs "No, I am not bound").

It performs three kinds of fix:

1.  **Partition shared pattern strings** so each string has exactly one owner,
    keeping the intent that matches the observed production behaviour
    (``Non-Disclosure Agreement`` -> "I Agree", per qa_results.csv).
2.  **Remove over-broad strings** from a pattern group when a more specific
    group already owns the correct answer.
3.  **De-redact / correct a malformed default** (emergency-contact details).

Run with ``--dry-run`` to inspect the diff without writing.

Usage::

    .venv/bin/python scripts/fix_pattern_overlaps.py --dry-run
    .venv/bin/python scripts/fix_pattern_overlaps.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATTERNS_FILE = REPO / "config" / "qa_patterns.json"

# -- Intent partitions -------------------------------------------------------

# Generic "NDA / confidentiality agreement" labels are acknowledgment prompts:
# the observed production answer for the LinkedIn/GREENHOUSE field
# "Non-Disclosure Agreement" was "I Agree".  The dedicated "currently bound"
# phrasings stay with ``confidentiality_agreement`` (answer "No").
WILLING_NDA_PATTERNS = [
    "willing to sign nda",
    "non-disclosure agreement",
    "non disclosure agreement",
    "nda agreement",
    "confidentiality agreement",
    "willing to sign a non-disclosure",
    "sign an nda",
    "nda consent",
    "nda",
    "non-disclosure",
    "i agree to the nda",
    "agree to the confidentiality agreement",
    "agree to nda",
]
WILLING_NDA_NEGATIVE = [
    "do you have",
    "bound by",
    "current employer",
    "restrict",
    "restrictive",
    "non-compete",
    "noncompete",
]

BOUND_NDA_PATTERNS = [
    "do you have nda",
    "do you have an nda",
    "bound by confidentiality",
    "bound by a confidentiality agreement",
    "existing confidentiality agreement",
    "current nda",
    "nda with current employer",
    "confidentiality agreement with current employer",
]
# NOTE: never use the bare token "agree" -- it is a substring of "agreement".
BOUND_NDA_NEGATIVE = [
    "willing to",
    "i agree",
    "agree to sign",
    "consent to",
    "acknowledge",
    "willingness to sign",
]

# "non-disclosure agreement" / "nda agreement" are owned by the compliance
# group; the legacy yes_no group keeps only its distinct "sign ..." phrasings.
REMOVE_FROM_NDA_SIGN = [
    "nda agreement",
    "non-disclosure agreement",
]

TIME_SLOT_9_3 = [
    "time slot in between 9-3 pm",
    "time slot in between 9- 3 pm",
    "kindly mention the time slot in between 9- 3 pm",
    "kindly mention the time slot in between 9- 3 pm at what time you will be available",
    "kindly mention the time slot in between 9- 3 pm at what time you will be available?",
]

# bare "criminal background check" belongs to the criminal-record owners
# (answer "No"), not to the police-verification consent group (answer "Yes").
REMOVE_FROM_POLICE = ["criminal background check"]

# Explicit consent phrasings ("willing to undergo ... criminal background
# check") are background-verification consents (answer "Yes"), not criminal
# record disclosures (answer "No").  Production evidence: a Greenhouse consent
# statement ending "asked to provide authorization before any such checks" was
# answered "Yes".
CRIMINAL_CONSENT_PHRASINGS = [
    "willing to undergo an employment education and criminal background check",
    "willing to undergo employment education and criminal background",
    "employment education and criminal background check",
]
BACKGROUND_VERIFICATION_EXTRA = CRIMINAL_CONSENT_PHRASINGS + [
    "comprehensive background check",
    "employment and education verification",
]
# Keep blocking genuine conviction questions, but allow explicit consent.
BACKGROUND_VERIFICATION_NEGATIVE = [
    "felony",
    "misdemeanor",
    "conviction",
    "convicted",
    "arrested",
    "criminal record",
    "criminal history",
    "criminal charges",
    "criminal charge",
]

# "require sponsorship for employment visa status" is a generic question and
# must resolve to "No"; the "Not applicable" group keeps only US-specific
# phrasings (H-1B / "roles posted in the US only").
REMOVE_FROM_VISA_US = [
    "require sponsorship for employment visa status",
    "sponsorship for employment visa status",
]

# emergency contact number must be owned by the sensitive, exact-match
# ``emergency_contact_phone`` group, not by the "comprehensive" group whose
# redacted default has no digits (and therefore leaked the candidate phone).
REMOVE_FROM_EMERGENCY_COMPREHENSIVE = ["emergency contact number"]
EMERGENCY_COMPREHENSIVE_DEFAULT = "Rohan Singh (Brother): +91-6263066371"
EMERGENCY_COMPREHENSIVE_ITD = {
    "radio": "Brother",
    "select": "Brother",
    "text": "Brother - Rohan Singh, +91-6263066371",
    "textarea": "Emergency Contact: Rohan Singh (Brother), +91-6263066371",
    "checkbox": "Yes",
    "number": "6263066371",
    "tel": "6263066371",
}


def _remove(patterns: list[str], to_remove: list[str]) -> list[str]:
    drop = {p.strip().lower() for p in to_remove}
    return [p for p in patterns if str(p).strip().lower() not in drop]


def apply_fixes(data: dict) -> list[str]:
    pats = data["patterns"]
    log: list[str] = []

    def get(pid: str) -> dict:
        if pid not in pats:
            raise KeyError(f"pattern id not found: {pid}")
        return pats[pid]

    # 1. First-time-application NDA partition.
    will = get("willing_to_sign_nda")
    will["patterns"] = WILLING_NDA_PATTERNS
    will["negative_patterns"] = WILLING_NDA_NEGATIVE
    log.append("willing_to_sign_nda: repartitioned -> Yes/agreement owner")

    bound = get("confidentiality_agreement")
    bound["patterns"] = BOUND_NDA_PATTERNS
    bound["negative_patterns"] = BOUND_NDA_NEGATIVE
    log.append("confidentiality_agreement: narrowed to 'currently bound' phrasings -> No")

    # 1b. Legacy NDA yes/no group: keep only its distinct "sign ..." phrasings.
    nda_sign = get("nda_sign")
    before = len(nda_sign.get("patterns") or [])
    nda_sign["patterns"] = _remove(nda_sign.get("patterns") or [], REMOVE_FROM_NDA_SIGN)
    log.append(
        f"nda_sign: removed {before - len(nda_sign['patterns'])} string(s) shared with willing_to_sign_nda"
    )

    # 2. Time-slot duplication.
    slot = get("interview_time_slot_specific")
    before = len(slot.get("patterns") or [])
    slot["patterns"] = _remove(slot.get("patterns") or [], TIME_SLOT_9_3)
    log.append(
        f"interview_time_slot_specific: removed {before - len(slot['patterns'])} shared 9-3 strings"
    )

    # 3. Over-broad police-verification string.
    police = get("police_verification_consent")
    before = len(police.get("patterns") or [])
    police["patterns"] = _remove(police.get("patterns") or [], REMOVE_FROM_POLICE)
    log.append(
        f"police_verification_consent: removed {before - len(police['patterns'])} criminal-record string(s)"
    )

    # 3b. Move explicit background-check consent phrasings from the criminal
    #     record group to the background-verification consent group.
    cbg = get("criminal_background")
    before = len(cbg.get("patterns") or [])
    cbg["patterns"] = _remove(cbg.get("patterns") or [], CRIMINAL_CONSENT_PHRASINGS)
    log.append(
        f"criminal_background: removed {before - len(cbg['patterns'])} consent phrasing(s)"
    )
    bgv = get("background_verification")
    bgv["patterns"] = list(
        dict.fromkeys((bgv.get("patterns") or []) + BACKGROUND_VERIFICATION_EXTRA)
    )
    bgv["negative_patterns"] = BACKGROUND_VERIFICATION_NEGATIVE
    log.append("background_verification: adopted consent phrasings -> Yes")

    # 4. Visa sponsorship generic strings.
    visa = get("visa_sponsorship_us_roles")
    before = len(visa.get("patterns") or [])
    visa["patterns"] = _remove(visa.get("patterns") or [], REMOVE_FROM_VISA_US)
    log.append(
        f"visa_sponsorship_us_roles: removed {before - len(visa['patterns'])} generic sponsorship string(s)"
    )

    # 5. Emergency contact comprehensive.
    emerg = get("emergency_contact_comprehensive")
    before = len(emerg.get("patterns") or [])
    emerg["patterns"] = _remove(
        emerg.get("patterns") or [], REMOVE_FROM_EMERGENCY_COMPREHENSIVE
    )
    emerg["default"] = EMERGENCY_COMPREHENSIVE_DEFAULT
    itd = dict(emerg.get("input_type_defaults") or {})
    itd.update(EMERGENCY_COMPREHENSIVE_ITD)
    emerg["input_type_defaults"] = itd
    # The de-redacted answer now embeds a real phone number, so it must be
    # treated as PII: never chosen by fuzzy/substring matching, and redacted
    # in logs.
    emerg["sensitive"] = True
    emerg["requires_exact_match"] = True
    log.append(
        f"emergency_contact_comprehensive: removed {before - len(emerg['patterns'])} phone string(s); "
        "de-redacted default; marked PII (sensitive + requires_exact_match)"
    )

    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with PATTERNS_FILE.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    log = apply_fixes(data)

    print("Planned/Applied changes:")
    for line in log:
        print("  -", line)

    if args.dry_run:
        print("\n[dry-run] no file written")
        return 0

    # Atomic write with timestamped backup.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = PATTERNS_FILE.with_suffix(PATTERNS_FILE.suffix + f".bak-overlaps-{stamp}")
    shutil.copy2(PATTERNS_FILE, backup)
    tmp = PATTERNS_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(PATTERNS_FILE)
    print(f"\nBackup: {backup.name}")
    print(f"Wrote : {PATTERNS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
