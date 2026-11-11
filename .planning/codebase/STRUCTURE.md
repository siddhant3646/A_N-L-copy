---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# Codebase Structure

**Analysis Date:** 2026-11-11

## Directory Layout

```text
A_N&L/
├── sentinel                  # Executable CLI launcher -> src/sentinel/cli.py
├── src/
│   ├── core/                 # Environment config + candidate profile store
│   ├── patterns/             # Corpus loading, matching, sanitizing, option resolution
│   └── sentinel/             # Agent, runner, prompts, resilience, classifier, LLM, CLI
├── config/
│   ├── qa_patterns.json      # 77.8 MB Q&A corpus (v3.0) — single source of truth
│   └── qa_patterns.json.bak-* # Dated backups (gitignored)
├── profiles/
│   └── resume.json           # Candidate profile (gitignored; loaded by ProfileStore)
├── scripts/                  # Corpus maintenance, audits, live platform harnesses
├── tests/
│   ├── conftest.py           # Session corpus fixtures + mocked Playwright objects
│   ├── unit/
│   │   ├── qa/               # 49 test modules — pattern/answer regressions
│   │   ├── platforms/        # 20 test modules — per-portal handler tests
│   │   ├── patterns/         # 5 test modules — loader/matcher/validator/resolver
│   │   ├── sentinel/         # 8 test modules — agent utilities, CSV coverage, LLM, session
│   │   ├── core/             # 2 test modules — config + profile store
│   │   └── browser/          # 1 test module — human behavior
│   └── integration/
│       └── test_pattern_pipeline.py
├── tasks/                    # todo.md / lessons.md (human notes, not executed)
├── .agents/                  # Multi-agent run artifacts (BRIEFING/DISPATCH/plan/progress)
├── .opencode/                # Editor/agent plan notes
├── .planning/codebase/       # These mapping documents
├── live_test_output_instahyre/  # Screenshots from live Instahyre runs (gitignored)
├── live_test_output_naukri/     # Screenshots from live Naukri runs (gitignored)
├── .env                      # Local secrets/config (gitignored — never commit)
├── AGENTS.md                 # Project operations manual / Q&A contract
├── IMPLEMENTATION_SUMMARY.md # Input-type-aware answer design notes
├── INDEED_HIRIST_FIXES.md    # Indeed/Hirist change-set notes
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## Directory Purposes

**`src/sentinel/`:**
- Purpose: runtime automation. Nearly all behavioral logic lives here.
- Contains: `SentinelAgent` and platform handlers (`agent.py`), process runner/`Browser` (`run.py`), task prompts (`prompts.py`), answer classification/fingerprinting, LLM client, resilience utilities, CLI.
- Key files: `src/sentinel/agent.py` (26,034 lines), `src/sentinel/run.py` (1,117 lines), `src/sentinel/prompts.py` (468), `src/sentinel/llm_client.py` (841), `src/sentinel/question_fingerprint.py` (1,014), `src/sentinel/question_classifier.py` (891), `src/sentinel/ui_error_detector.py` (723), `src/sentinel/self_healing.py` (499), `src/sentinel/human_behavior.py` (396), `src/sentinel/cli.py` (343), `src/sentinel/schemas.py` (28).

**`src/patterns/`:**
- Purpose: everything that turns question text into a control-safe answer.
- Contains: corpus loader, 3-tier matcher, input-type sanitizer/deriver, option resolver, validators.
- Key files: `pattern_matcher.py` (1,327), `input_type_sanitizer.py` (1,950), `input_aware_resolver.py` (611), `pattern_loader.py` (373), `enhanced_answer_validator.py` (172), `answer_validator.py` (169), `__init__.py` (re-exports the public API).

**`src/core/`:**
- Purpose: environment and identity configuration.
- Contains: `config.py` (stdlib `.env` parser; exports `CHROME_USER_DATA`, `CHROME_EXECUTABLE_PATH`, `GOOGLE_AI_API_KEY(S)`, `RESUME_FILE_PATH`), `profile_store.py` (`ProfileStore` with dotted-path access and `to_js_dict()`).
- Key files: `src/core/config.py:1`, `src/core/profile_store.py:25`.

**`config/`:**
- Purpose: Q&A corpus storage.
- Contains: `qa_patterns.json` (v3.0: 67,022 groups, 224,791 variants, 27 categories) plus dated `.bak-*` backups.
- Key files: `config/qa_patterns.json`. Treat as read-only at runtime; modify only through a script in `scripts/`.

**`profiles/`:**
- Purpose: candidate data loaded at runtime.
- Contains: `resume.json` only. Gitignored, but the app degrades gracefully when missing (`SentinelAgent.__init__` catches `ProfileStore` errors at `src/sentinel/agent.py:309`).
- Key files: `profiles/resume.json`.

**`scripts/`:**
- Purpose: one-shot corpus migrations, audits, generators, and live end-to-end harnesses. Not imported by the runtime except `scripts/taxonomy_data.py`.
- Contains (24 files):
  - `apply_*` — apply audited fixes to `qa_patterns.json` (`apply_csv_pattern_fixes.py`, `apply_qa_audit_fixes_nov07.py`, `apply_audit_fixes_nov.py`, `apply_patterns_and_location_fixes_oct29.py`, `apply_csv_pattern_fixes_oct28.py`)
  - `repair_*` — structural/input-type/PII repairs (`repair_qa_patterns.py`, `repair_input_type_defaults.py`, `repair_pii_leaks.py`, `repair_pattern_overlap_edgecases.py`)
  - `audit_*` — overlap and input-type audits (`audit_pattern_overlaps.py`, `audit_qa_input_types.py`)
  - `generate_*` / `fix_*` / `import_*` / `analyze_*` — taxonomy expansion, overlap fixes, CSV import, error analysis
  - `probe_*` — read-only flow probes for Indeed
  - `test_live_*` / `run_live_*` — real-Chrome platform harnesses with screenshots
  - `taxonomy_data.py` — `TECHNOLOGIES` / `FEATURES` tables consumed by `agent.py` and the generator

**`tests/`:**
- Purpose: regression suite for corpus behavior and handler logic.
- Contains: 88 `test_*.py` modules. `conftest.py` provides session-scoped corpus fixtures (`real_patterns_data`, `real_pattern_matcher`), mock `page`/`context`/`browser` objects, and mock platform handlers.
- Key files: `tests/conftest.py`, `tests/integration/test_pattern_pipeline.py`, `tests/unit/sentinel/test_qa_csv_coverage.py`.

**`tasks/`:**
- Purpose: human-maintained notes from prior debugging sessions.
- Contains: `todo.md`, `lessons.md`. Not imported or executed.

**`.agents/`:**
- Purpose: artifacts from previous multi-agent runs (`BRIEFING.md`, `DISPATCH.md`, `plan.md`, `progress.md`).
- Contains: no runtime code; safe to ignore when navigating the app.

**`.planning/codebase/`:**
- Purpose: generated architecture/structure maps for planning agents.

**`live_test_output_instahyre/`, `live_test_output_naukri/`:**
- Purpose: screenshots captured by `scripts/test_live_*` harnesses. Generated, gitignored.

## Key File Locations

**Entry Points:**
- `src/sentinel/run.py:1113`: `if __name__ == "__main__": asyncio.run(main())` — primary bot runner.
- `src/sentinel/run.py:766`: `main()` — task table at `:770`, agent creation at `:856`, task loop at `:858`.
- `sentinel:20`: CLI launcher (`./sentinel stats|patterns|failures|learn|export`).
- `src/sentinel/cli.py:258`: `main()` argument parser for the CLI.
- `scripts/run_live_linkedin_test.py`: LinkedIn-only live harness with DOM/screenshot capture.
- `scripts/test_live_naukri_only.py`, `scripts/test_live_instahyre_only.py`, `scripts/test_live_hirist_only.py`, `scripts/test_live_indeed_only.py`, `scripts/test_live_both_tasks.py`: per-platform live harnesses.

**Configuration:**
- `src/core/config.py`: env loading and exported constants (reads `.env` if present).
- `pytest.ini`: test paths, asyncio auto mode, markers (`unit`, `integration`, `slow`).
- `requirements.txt`: `playwright>=1.60.0`, `aiohttp>=3.9.0`.
- `requirements-dev.txt`: pytest stack + coverage.
- `profiles/resume.json`: candidate profile consumed by `ProfileStore`.
- `config/qa_patterns.json`: Q&A corpus.
- `.env`: exists locally, gitignored. Never read or commit contents.
- `.vscode/settings.json`: only sets the Python env manager.

**Core Logic:**
- `src/sentinel/agent.py:181`: `SentinelAgent` class definition.
- `src/sentinel/agent.py:419`: `_inject_patterns_once()` — corpus → `window.__SENTINEL_*__`.
- `src/sentinel/agent.py:1152`: `_fuzzy_match_question()` — Python Q&A tiers.
- `src/sentinel/agent.py:3562`: `_log_qa_result()` — single CSV writer.
- `src/sentinel/agent.py:3624`: `_log_qa_entries()` — bulk/JS-payload CSV writer.
- `src/sentinel/agent.py:3761`: `_drain_js_qa_log()`.
- `src/sentinel/agent.py:4533`: `run()` — step loop and dispatch.
- `src/sentinel/agent.py:15421`: `_handle_scripted_fallback()` — universal page script.
- `src/sentinel/agent.py:26031`: `create_agent()` factory.
- `src/patterns/pattern_matcher.py:990`: `fuzzy_match()`; `:1325`: `create_matcher()`.
- `src/patterns/input_type_sanitizer.py:836`: `derive_value()`; `:1581`: `sanitize_answer()`.
- `src/patterns/input_aware_resolver.py:207`: `resolve()`.

**Testing:**
- `tests/conftest.py`: shared fixtures; loads the 77.8 MB corpus once per session.
- `tests/unit/qa/`: question/answer regression tests (the largest suite).
- `tests/unit/platforms/`: per-portal behavior tests.
- `tests/unit/patterns/`: matcher/loader/validator/resolver unit tests.
- `tests/integration/test_pattern_pipeline.py`: loader → matcher → validator integration.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (`question_fingerprint.py`, `input_aware_resolver.py`).
- Tests: `test_<subject>_<detail>.py`; Q&A audit regressions are date-stamped (`test_qa_csv_fixes_oct27.py`, `test_qa_audit_fixes.py`).
- Scripts: verb prefix — `apply_*`, `repair_*`, `audit_*`, `generate_*`, `probe_*`, `import_*`, `analyze_*`, `test_live_*`, `run_live_*`.
- Docs: uppercase root docs (`AGENTS.md`, `IMPLEMENTATION_SUMMARY.md`) and `UPPERCASE.md` under `.planning/codebase/`.
- JSON: lowercase with underscores (`qa_patterns.json`, `resume.json`).

**Classes:**
- PascalCase with role suffix: `SentinelAgent`, `PatternMatcher`, `PatternLoader`, `InputAwareResolver`, `EnhancedAnswerValidator`, `FingerprintMatcher`, `SuccessTracker`, `GemmaLLMClient`, `UIErrorDetector`, `RateLimiter`, `SessionManager`, `FormStateValidator`, `ProfileStore`, `Browser`.

**Functions/Methods:**
- `snake_case`; private methods prefixed `_`.
- Platform handlers: `_handle_<platform>_<task>` (`_handle_hirist_apply_task`, `_handle_indeed_apply_task`, `_handle_naukri_profile_update_task`).
- Platform utilities: `_<platform>_<verb>` (`_hirist_fill_questionnaire`, `_indeed_answer_questions`, `_naukri_answer_source`).
- Q&A helpers: `_fuzzy_match_question`, `_match_answer_to_options`, `_get_learned_answer`, `_validate_and_retry`.
- Logging helpers: `_log_<thing>` (`_log_qa_result`, `_log_qa_entries`, `_log_qa_payload`, `_log_naukri_chatbot_result`, `_log_question_detailed`).
- Public agent API: `run()`, `reset_per_task_state()`, `create_agent()`.

**Variables/Constants:**
- Module/class constants: `UPPER_SNAKE_CASE` (`MAX_STEPS_LINKEDIN`, `QA_RESULTS_COLUMNS`, `CANDIDATE_TOTAL_YEARS`, `SKILL_EXPERIENCE_YEARS`).
- Agent state fields: leading underscore + descriptive (`_naukri_no_progress_count`, `_linkedin_skipped_job_ids`).
- JSON/persisted keys: `snake_case` (`input_type_defaults`, `negative_patterns`, `requires_exact_match`).
- JS object keys: `camelCase` (`inputType`, `selectedOption`); `_log_qa_entries()` accepts both camelCase and snake_case and the short forms `t`/`s`.

**Return markers (JS → Python):**
- `UPPER_SNAKE_CASE`, prefixed by platform: `LINKEDIN_*` (16 unique), `NAUKRI_*` (18), `CHATBOT_*` (21), `INSTAHYRE_*` (24), plus generic `TASK_COMPLETE`, `SUCCESS`, `NO_ACTION`, `ERROR`.
- Optional detail after `:` and optional JSON after `|` (`LINKEDIN_FORM_STUCK: Validation errors`, `GENERIC_FORM_FILLED|[...]`).

**JS globals:**
- `window.__SENTINEL_<NAME>__`: `__SENTINEL_PATTERNS__`, `__SENTINEL_PATTERNS_WITH_DEFAULTS__`, `__SENTINEL_EXACT_MATCH_KEYS__`, `__SENTINEL_SYNONYMS__`, `__SENTINEL_STOPWORDS__`, `__SENTINEL_PROFILE__`, `__SENTINEL_SKILL_YEARS__`, `__SENTINEL_ZERO_SKILL_OVERRIDES__`, `__SENTINEL_GENERIC_SKILLS__`, `__SENTINEL_QA_LOG__`, `__SENTINEL_DEBUG__`, `__SENTINEL_ISVISIBLE__`, `__SENTINEL_IS_INTERSESSION__`, `__SENTINEL_INSTAHYRE_SKILLS__`, `__SENTINEL_IN_AUTOPILOT__`, `__skippedJobIds`, `__skippedJobTitles`.

**Pattern IDs and categories:**
- Pattern IDs: `snake_case`, descriptive, unique (`current_salary`, `springboot_experience`, `notice_period_in_months_exact`).
- Pattern strings: lowercase, no punctuation, multiple variants per group.
- Categories: 27 fixed labels (`skills`, `experience`, `salary`, `notice_period`, `compliance`, `personal_info`, `self_identification`, ...).

**Tests:**
- Classes: `Test<Subject>`; methods: `test_<behavior>` (e.g. `TestPatternMatcher::test_salary_question_matches`).
- Fixtures: `snake_case` (`real_patterns_data`, `mock_page`, `mock_platform_handlers`).

## Where to Add New Code

**New job platform (e.g. a sixth portal):**
- Handler: add `_handle_<platform>_apply_task()` and `_<platform>_*` helpers in `src/sentinel/agent.py`, near the existing blocks (`_handle_hirist_apply_task` at `:9731`, `_handle_indeed_apply_task` at `:8089`).
- Dispatch: add a URL/task-keyword branch in `SentinelAgent.run()` at `src/sentinel/agent.py:4639`–`4683`, and any marker handling in the ladder around `:6300`–`6900`.
- Platform detection: extend `_detect_platform()` (`:654`) and the JS `is<Platform>` checks inside `_handle_scripted_fallback` (`:17442`–`17443`).
- Task descriptor: add a `<PLATFORM>_JOB_APPLY_TASK` constant in `src/sentinel/prompts.py` (pattern of `HIRIST_JOB_APPLY_TASK` at `:408`).
- Runner registration: add a tuple to the `tasks` list in `src/sentinel/run.py:770`.
- Tests: add `tests/unit/platforms/test_<platform>_*.py`.
- Screenshots: follow the `live_test_output_<platform>/screenshots` convention and add it to `.gitignore`.

**New Q&A pattern (most common change):**
- Edit `config/qa_patterns.json` only. Required fields: `patterns`, `category`, `default`; recommended: `input_type_defaults`, `priority`, `negative_patterns`, `numeric_default`/`inr_default`/`lpa_default`.
- Validate JSON, then run `pytest tests/unit/qa/ -q`.
- Add a regression test in `tests/unit/qa/test_qa_<topic>.py` (date-stamped if it comes from a CSV audit batch).
- Do **not** retype the answer in `src/sentinel/agent.py` or in the JS literal unless the value must differ by platform; prefer `input_type_defaults` / `platform_overrides` / `__SENTINEL_PROFILE__`.

**New input-type or answer-derivation rule:**
- Primary: `src/patterns/input_type_sanitizer.py` (`detect_intent`, `derive_value`, `sanitize_answer`, `build_input_type_defaults`, `is_valid_value`).
- Add unit coverage in `tests/unit/qa/test_input_type_*.py` or `tests/unit/patterns/`.

**New option-matching behavior (radio/select/checkbox):**
- `src/patterns/input_aware_resolver.py` (`InputAwareResolver._match_to_options`, `OPTION_SYNONYMS`, `NumericRangeMatcher`).
- Tests: `tests/unit/patterns/test_input_aware_resolver.py`.

**New category validation or platform formatting:**
- Category rules: `src/patterns/answer_validator.py` (`_validate_*`, `_fix_answer`).
- Platform formatting: `src/patterns/enhanced_answer_validator.py` (`_check_platform_format`, `_apply_platform_format`).
- Tests: `tests/unit/patterns/test_answer_validator.py`.

**New question category or platform default:**
- `src/sentinel/question_classifier.py` (`QuestionCategory`, `PLATFORM_CONFIGS`, `QuestionClassifier.classify`, `get_answer`).
- `src/sentinel/question_fingerprint.py` for synonym/stop-word normalization and expected-format detection.

**New learned behavior / failure recovery:**
- `src/sentinel/self_healing.py` (`FailureLogger`, `LearningStore`, `RecoveryEngine`, `SelfHealingMatcher`).
- Detection side: `src/sentinel/ui_error_detector.py` (`ErrorType`, `ERROR_PATTERNS`, `UIErrorRecovery`).
- Wire-up point: `SentinelAgent._attempt_form_recovery()` at `src/sentinel/agent.py:3275`.

**New LLM behavior/prompt:**
- `src/sentinel/llm_client.py` (`GemmaLLMClient._build_prompt` at `:507`, `answer_question` at `:725`, model chain at `:27`).
- Candidate factsheet: `get_candidate_facts()` at `src/sentinel/llm_client.py:36`.
- Call sites: Instahyre `src/sentinel/agent.py:11373`, Indeed `:9443`, Hirist `:10834`.

**New CSV/audit output:**
- Write through `SentinelAgent._log_qa_result()` / `_log_qa_entries()` only (`src/sentinel/agent.py:3562`, `:3624`); never append to the CSV directly.
- Cover it with `tests/unit/sentinel/test_qa_csv_coverage.py` or a platform test.

**New live harness:**
- Add `scripts/test_live_<platform>_only.py` mirroring `scripts/test_live_instahyre_only.py`: insert repo root in `sys.path`, import `Browser`/`reset_shared_playwright` from `src.sentinel.run`, build `SentinelAgent`, navigate, call `agent.run(prompt)`, capture screenshots under `live_test_output_<platform>/`.

**New corpus maintenance script:**
- Add `scripts/<verb>_<subject>.py`, resolve `ROOT = Path(__file__).resolve().parents[1]`, load `config/qa_patterns.json`, write a `.bak-*` backup first, and re-run `pytest tests/unit/qa/`.

**Shared utilities:**
- Browser-adjacent helpers (human mouse/scroll/click, input resync): `src/sentinel/human_behavior.py`.
- Form snapshots: `src/sentinel/form_state_validator.py`.
- Pacing: `src/sentinel/rate_limiter.py`.
- Session health: `src/sentinel/session_manager.py`.
- Config/env: `src/core/config.py`.
- Profile access: `src/core/profile_store.py` (`get('personal.email')`).

## Special Directories

**`config/`:**
- Purpose: runtime corpus + backups.
- Generated: corpus is hand/script-maintained; backups are generated.
- Committed: `qa_patterns.json` yes; `*.bak-*` no (`.gitignore` has `config/*.bak-*`).

**`profiles/`:**
- Purpose: candidate identity.
- Generated: no.
- Committed: no (`profiles/` is gitignored); local copy required for full functionality.

**`live_test_output_instahyre/`, `live_test_output_naukri/`:**
- Purpose: screenshots produced by live harnesses.
- Generated: yes.
- Committed: no.

**`.venv/`:**
- Purpose: local Python 3.14 virtualenv.
- Generated: yes.
- Committed: no.

**`.agents/`, `.opencode/`, `.pytest_cache/`:**
- Purpose: tooling/agent-run artifacts.
- Generated: yes.
- Committed: `.agents` and `.opencode` are tracked; `.pytest_cache` is not.

**`~/Desktop/sentinel_errors/` (outside repo):**
- Purpose: runtime telemetry — `qa_results.csv`, `failure_log.jsonl`, `learned_patterns.json`, `metrics.jsonl`, `unknown_questions.log`, `all_questions.log`, screenshots.
- Generated: yes.
- Committed: no (outside the repository).

---

*Structure analysis: 2026-11-11*
