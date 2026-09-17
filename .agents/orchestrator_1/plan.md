# Plan: Sentinel QA Pattern & Form-Filling Optimization

## Objectives
1. Audit all 1,275 entries in `~/Desktop/sentinel_errors/qa_results.csv` across LinkedIn, Naukri, Instahyre.
2. Fix textarea handling in `src/sentinel/agent.py` and `src/patterns/pattern_matcher.py` (prevent generic 500-word engineering essays for simple questions).
3. Update/add QA patterns in `config/qa_patterns.json` and intercept guards/JS form filling in `src/sentinel/agent.py`.
4. Strictly preserve tool exemptions (Calypso, .NET/C#, AEM backend experience returning 4.2 Years / 4).
5. Expand unit tests in `tests/unit/qa/` and verify full suite passes with 100% success rate (0 failures).

## Steps
- [ ] **Step 0: Survey & Full Scope Mapping**
  - Spawn 3 Explorers / Spec Miners in parallel:
    - Explorer 1 (CSV Auditor): Full analysis of `~/Desktop/sentinel_errors/qa_results.csv`.
    - Explorer 2 (Codebase & Textarea Guard Analyst): Examine `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py`, and `input_aware_resolver.py`.
    - Explorer 3 (QA Pattern & Test Suite Analyst): Examine `config/qa_patterns.json`, tool rules (Calypso, .NET/C#, AEM), and existing tests in `tests/unit/qa/`.
  - Synthesize reports into `PROJECT.md` with full Feature Inventory.
- [ ] **Step 1: Textarea & Input-Aware Guard Optimization**
  - Dispatch Worker to implement textarea guards and prevent verbose essay fallbacks for simple Yes/No, Salary, Notice Period, and Location questions.
  - Review, Challenge, Audit, and Gate check.
- [ ] **Step 2: QA Pattern Calibration & Intercept Implementation**
  - Dispatch Worker to add/update pattern groups in `config/qa_patterns.json` (validating schema v3.0) and update Phase 0.1/Phase 1 intercepts / JS logic in `src/sentinel/agent.py`.
  - Verify tool rule exemptions (Calypso, .NET/C#, AEM => 4.2 Years / 4).
  - Review, Challenge, Audit, and Gate check.
- [ ] **Step 3: Test Suite Expansion & Regression Verification**
  - Dispatch Test Writer / Worker to add comprehensive tests in `tests/unit/qa/` covering all resolved questions, textarea guards, and tool exemptions.
  - Run full test suite: `./.venv/bin/pytest tests/unit/qa/ -q`.
  - Review, Challenge, Audit, and Gate check.
- [ ] **Step 4: Final Synthesis & Sentinel Report**
  - Synthesize all findings and gate results.
  - Send complete handoff report to Sentinel parent agent.
