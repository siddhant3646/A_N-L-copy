# Project Plan: Sentinel QA Pattern & Form-Filling Optimization (Gen 3)

## Architecture
Sentinel form automation operates on a multi-tier Q&A architecture:
1. Python side: `SentinelAgent._fuzzy_match_question` (Phase 0 skip, Phase 0.1 compliance intercepts, Phase 0.5 fingerprint, Phase 0.6 learned patterns, Phase 1 keyword intercepts, Phase 2 JSON pattern matcher, Phase 3 smart category fallback).
2. JSON configuration: `config/qa_patterns.json` v3.0 schema containing 11,576+ pattern groups across 27 categories with platform overrides and input-type defaults.
3. Injected JavaScript: `fuzzyMatch` inside LinkedIn (`_handle_scripted_fallback`) and Naukri (`_handle_chatbot_loop`) form automation.

## Milestones

### Milestone 1: Textarea & Platform Form Guards Optimization
- **Target Files**: `src/sentinel/agent.py` and `src/patterns/pattern_matcher.py`
- **Scope**:
  1. Fix `src/sentinel/agent.py` where concise answers (`Yes`, `No`, numeric figures, notice periods, salaries) in `<textarea>` were unconditionally overwritten with the 508-char technical summary essay.
  2. Implement context-aware textarea handling: only provide technical engineering essays when the field explicitly requests background, project details, or open-ended experience summary.
  3. Ensure dropdown/select handlers in `agent.py` filter out localized prompt placeholders like `Selecciona una opción` or `Select an option` to prevent infinite submit retry loops.
  4. Optimize `pattern_matcher.py` textarea resolving so category defaults for `yes_no`, `salary`, `notice_period`, and `location` remain concise and accurate.
- **Dependencies**: None
- **Status**: DONE (Verified with 342 passing tests in 199s)

### Milestone 2: QA Pattern Implementation & Priority Calibration
- **Target Files**: `config/qa_patterns.json` and `src/sentinel/agent.py`
- **Scope**:
  1. CRITICAL (R4): Fix `dotnet_core_exp` in `config/qa_patterns.json` to set `default: "4.2 Years"` (LinkedIn: `"4"`) with appropriate numeric defaults, strictly preserving candidate total experience without zeroing out. Add `rel_exp_dotnetcore` and ensure Calypso, .NET/C#, and AEM backend questions strictly return 4.2 Years / 4.
  2. Implement missing/erroneous QA patterns identified in CSV audit report (29 discrepancies):
     - Internal referral check: `No` (priority 20)
     - Ex-employee check: `No` (priority 19)
     - Non-earned degrees (MBA, PhD): `No` (priority 19)
     - Problem diagnosis/solving capability: `Yes` (priority 19)
     - Candidate designation: `Software Engineer 2` (priority 19)
     - Candidate current employer: `Everbridge` (priority 19)
     - Candidate GitHub link: `https://github.com/siddhant3646` (priority 19)
     - 1-5 rating scale questions: bounded to 5 (priority 19)
     - Notice period 2-digit confirmation: `15` (priority 19)
     - Compound CTC (Current & Expected): `2300000 / 3000000` or `23 LPA / 30 LPA`
     - Instahyre expected CTC: `30 LPA`
     - Select dropdowns for experience: return appropriate years (e.g. `4 years`, `3-5 years`) rather than `Yes`
  3. Maintain strict v3.0 schema compliance in `config/qa_patterns.json`.
- **Dependencies**: Milestone 1
- **Status**: DONE (Verified 0 schema errors, 662 unit tests passing)

### Milestone 3: Test Suite Expansion & Automated Validation
- **Target Files**: `tests/unit/qa/test_qa_csv_audit_fixes.py` and test verification
- **Scope**:
  1. Validate JSON schema integrity with `src.patterns.pattern_loader.load_patterns()`.
  2. Ensure comprehensive automated unit tests in `tests/unit/qa/` covering all newly added/repaired question patterns across various input types.
  3. Verify `./.venv/bin/pytest tests/unit/qa/ -v` passes 100% (zero failures, zero regressions).
  4. Verify `./.venv/bin/pytest tests/unit/platforms/ -v` passes 100%.
- **Dependencies**: Milestone 2
- **Status**: IN_PROGRESS

### Milestone 4: Independent Adversarial Review & Forensic Audit
- **Scope**:
  1. Dispatch Reviewer and Forensic Auditor to independently verify code integrity, test coverage, absence of regressions, and absence of cheating or dummy fallbacks.
  2. Binary Veto gate check on auditor report.
  3. Aggregate results into `GATE_STATUS.md` and create final handoff/completion report for the user / Sentinel.
- **Dependencies**: Milestone 3
- **Status**: PLANNED
