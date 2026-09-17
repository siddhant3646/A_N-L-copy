# Project Plan — Generation 5 Orchestrator

## Objective
Execute and verify the final phases of the Sentinel Q&A audit project:
1. Verify Milestone 1 & 2 completions from prior workers (DONE).
2. Execute Milestone 3: Test Suite Expansion & Automated Validation (cover all 29 audit questions across input types, run `pytest tests/unit/qa/ -v` and `pytest tests/unit/platforms/ -v` ensuring 100% pass).
3. Execute Milestone 4: Independent Adversarial Review & Forensic Audit (Reviewers, Challenger, Auditor).
4. Report final completion to parent (the Sentinel).

## Milestones Overview
| # | Milestone | Scope | Owner | Status |
|---|-----------|-------|-------|--------|
| 1 | Textarea & Platform Form Guards Optimization | `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py` | worker_m1 | COMPLETED |
| 2 | QA Pattern Implementation & Priority Calibration | `config/qa_patterns.json`, `src/sentinel/agent.py` | worker_m2 | COMPLETED |
| 3 | Test Suite Expansion & Automated Validation | `tests/unit/qa/`, `pytest tests/unit/qa/`, `pytest tests/unit/platforms/` | worker_m3 | COMPLETED |
| 4 | Independent Review & Forensic Audit | Full codebase & pattern integrity verification | reviewers / challenger / auditor | IN_PROGRESS |

## Detailed Plan for Milestone 3
1. Worker M3 (`teamwork_preview_worker`):
   - Review `tests/unit/qa/test_qa_csv_audit_fixes.py` against the 29 cataloged issues in `audit_report.md`.
   - Expand tests to comprehensively verify:
     - All input types (radio, select, text, number, checkbox, textarea)
     - Input-type-aware resolving and platform overrides (LinkedIn whole number vs Naukri "X Years")
     - Rule R4 (.NET/C#, Calypso, AEM) total experience preservation (4.2 Years / 4)
     - Schema compliance via `validate_patterns`
   - Run verification commands:
     - `./.venv/bin/pytest tests/unit/qa/ -v`
     - `./.venv/bin/pytest tests/unit/platforms/ -v`
   - Report pass results in handoff report at `.agents/worker_m3/handoff.md`.

## Detailed Plan for Milestone 4
1. Spawn 2 Reviewers (`teamwork_preview_reviewer`):
   - Review code quality, test coverage, pattern calibration, and rule R4 compliance.
2. Spawn 2 Challengers (`teamwork_preview_challenger`):
   - Adversarially challenge edge cases (boundary inputs, Spanish placeholders, textarea inputs).
3. Spawn 1 Forensic Auditor (`teamwork_preview_auditor`):
   - Verify integrity, no cheating/hardcoding/dummy implementations, clean patterns.
4. Gate: Evaluate all verdicts in `GATE_STATUS.md`.
5. Synthesize results and report completion to parent.
