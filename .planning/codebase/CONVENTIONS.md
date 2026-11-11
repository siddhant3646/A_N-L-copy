---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# Coding Conventions

**Analysis Date:** 2026-11-11

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` under `src/` — `pattern_matcher.py`, `input_aware_resolver.py`, `question_fingerprint.py`, `self_healing.py`.
- Tests: `test_<subject>.py`. QA regressions additionally encode the audit date: `tests/unit/qa/test_qa_csv_fixes_oct15.py`, `test_qa_csv_audit_fixes_sept22.py`, `test_qa_csv_fixes_nov10.py`.
- Scripts are verb-first: `scripts/apply_audit_fixes_nov.py`, `scripts/repair_pii_leaks.py`, `scripts/audit_pattern_overlaps.py`, `scripts/generate_50k_patterns.py`.
- Live/probe scripts are named for the platform: `scripts/test_live_instahyre_only.py`, `scripts/probe_indeed_apply_flow.py`, `scripts/run_live_linkedin_test.py`.
- Pattern IDs inside `config/qa_patterns.json` are `snake_case` and descriptive: `current_salary`, `experience_domain_specific`.

**Classes:**
- `PascalCase`, noun-first and role-suffixed: `SentinelAgent`, `PatternMatcher`, `PatternLoader`, `InputAwareResolver`, `QuestionClassifier`, `FingerprintMatcher`, `SelfHealingMatcher`, `SessionManager`, `RateLimiter`, `UIErrorDetector`, `GemmaLLMClient`, `ProfileStore`, `AnswerValidator`, `EnhancedAnswerValidator`.
- Test classes are `Test<Subject><Behavior>`: `TestPatternMatcherInit`, `TestQACSVFixesNov10`, `TestJSExperienceRanges`, `TestInstahyreGemmaAnswers`.
- Hand-rolled fakes are underscore-prefixed and singular: `_FakePage`, `_FakeFrame`, `_MockConsoleMsg` in `tests/unit/sentinel/test_qa_csv_coverage.py`.

**Functions and methods:**
- `snake_case` verbs; private methods use a single leading underscore (`_fuzzy_match_question`, `_log_qa_entries`, `_inject_patterns_once`).
- Domain prefixes group behavior on `SentinelAgent`:
  - `_handle_*` — platform flow drivers (`_handle_scripted_fallback`, `_handle_chatbot_loop`)
  - `_log_*` — persistence (`_log_qa_result`, `_log_naukri_chatbot_result`)
  - `_answer_*` — question answering (`_answer_instahyre_questionnaire`, `_answer_ctc_threshold_gate`)
  - `_hirist_*`, `_indeed_*`, `_instahyre_*`, `_naukri_*`, `_linkedin_*` — platform-scoped helpers
- Test helpers are underscore-prefixed inside the test class: `_fuzz_variants()`, `_pattern()`, `rows()`.

**Variables:**
- Agent mutable state is `self._<name>`: `self._page`, `self._current_platform`, `self._current_job_url`, `self._pattern_matcher`, `self._qa_logged_keys`.
- Matcher code and tests use terse locals: `q`, `ql` (question lower), `ans`, `score`, `opts`, `ans_norm`, `pid`, `pdata`.
- Module constants are `UPPER_SNAKE`: `FUZZY_MATCH_THRESHOLD`, `SALARY_KEYWORDS`, `CATEGORY_KEYWORDS`, `CORE_INPUT_TYPES`, `DEFAULT_GEMMA_MODELS` (`src/sentinel/agent.py:40`, `src/patterns/pattern_matcher.py:16`, `src/patterns/input_type_sanitizer.py:53`).
- Class constants are also `UPPER_SNAKE`: `SentinelAgent.MAX_STEPS_LINKEDIN`, `QA_RESULTS_COLUMNS`, `PatternMatcher.DEFAULT_THRESHOLD`, `RateLimiter.DEFAULT_DELAYS`.
- Environment variable constants mirror the env name exactly (`CHROME_USER_DATA`, `GOOGLE_AI_API_KEYS`, `RESUME_FILE_PATH`) in `src/core/config.py`.

**Types:**
- Enums are `PascalCase` with `UPPER_SNAKE` members: `QuestionCategory.SALARY`, `ErrorType.VALIDATION_ERROR`, `InputType.SELECT`. `ManagerIntent(str, Enum)` in `src/sentinel/schemas.py:5` is the JSON-serializable variant.
- Records are `@dataclass` classes with defaults: `FailureRecord`, `LearnedPattern`, `RecoveryResult` (`src/sentinel/self_healing.py`), `PlatformConfig` (`src/sentinel/question_classifier.py`), `ActionResult`, `SentinelState` (`src/sentinel/schemas.py`), `Option`, `MatchResult` (`src/patterns/input_aware_resolver.py`).
- Type hints use `typing.List/Dict/Optional/Tuple/Any` (114 `Optional[...]` usages), not builtin generics. `from __future__ import annotations` appears only in the newest modules (`src/patterns/input_type_sanitizer.py`, `tests/unit/qa/test_input_type_defaults_matrix.py`).

## Code Style

**Formatting:**
- No committed formatter or linter config (no `pyproject.toml`, `setup.cfg`, `ruff.toml`, `.flake8`, `.pre-commit-config.yaml`). `.ruff_cache/` in `.gitignore` shows Ruff is used ad hoc; no CI enforces anything.
- 4-space indentation; multi-line signatures align continuation arguments under the opening parenthesis and use trailing commas.
- Quote style is file-local and mixed: single quotes dominate `src/sentinel/agent.py` (~26k vs ~7.7k double) and `src/patterns/pattern_matcher.py`; double quotes dominate newer modules (`src/sentinel/rate_limiter.py`, `src/core/config.py`, `src/sentinel/question_classifier.py`). Match the file you are editing.
- Line length is not enforced. `src/sentinel/agent.py` has ~4,576 lines over 100 chars, mostly embedded JavaScript. Keep new Python near ≤100 columns.
- Embedded JS stays inline as triple-quoted f-strings inside `src/sentinel/agent.py`; there are no `.js` files in `src/`. When editing, preserve `{{` / `}}` escaping required by f-strings.
- Long modules use banner comments: `# ============...` in `tests/conftest.py`, `# ---------------------------------------------------------------------------` in `src/patterns/input_type_sanitizer.py`.
- Entry points start with `#!/usr/bin/env python3` (`sentinel`, `src/sentinel/cli.py`).

## Import Organization

**Order (observed consistently):**
1. Standard library (`asyncio`, `csv`, `json`, `os`, `re`, `inspect`, `datetime`, `difflib`).
2. Blank line, then third-party (`playwright.async_api`), with `try/except ImportError` for optional deps — see `aiohttp` in `src/sentinel/llm_client.py:17`.
3. Blank line, then local absolute imports `from src.core.config import ...`, `from src.patterns.pattern_matcher import create_matcher`.
4. Inside `src/patterns/`, relative imports are used: `from .pattern_loader import PatternLoader` (`src/patterns/pattern_matcher.py:7`).

**Path Aliases:**
- None. Imports are absolute `src.*`. Root scripts and several tests bootstrap with `sys.path.insert(0, os.path.abspath(...))`; `tests/conftest.py:14` does this for the whole pytest session, so new tests do not need their own path shim.

## Error Handling

**Strategy:** fail-open automation. A failed step must never abort the run; only configuration/loading errors raise.

**Patterns:**
- Custom exceptions for data/config problems: `PatternLoadError`, `PatternValidationError` (`src/patterns/pattern_loader.py:21-28`), `ProfileStoreError` (`src/core/profile_store.py`). They carry the offending path or JSON message.
- Matchers return sentinels instead of raising: `(None, confidence)` from `PatternMatcher.fuzzy_match`, `None` from `GemmaLLMClient.answer_question` when unconfigured, `{"healthy": False, "reason": ..., "crashes": n}` from `SessionManager.check_health` (`src/sentinel/session_manager.py:38`).
- Agent flow methods return uppercase string states: `"SUCCESS"`, `"NO_ACTION"`, `"ERROR"`, `"NO_PAGE"`, `"NAV_ERROR"`, `"LINKEDIN_FORM_STUCK"`.
- Broad `except Exception` is the norm (352 occurrences); it is deliberate around page interaction and file I/O. Six bare `except:` remain — do not add more.
- Any persistence call wraps I/O in `try/except` and prints a warning rather than propagating (`_log_qa_result` at `src/sentinel/agent.py:3562`).
- `raise` is rare (10 occurrences) and limited to loader/validator boundaries.

## Logging

**Framework:** `print()` for application output (650 calls), stdlib `logging` only in `src/sentinel/llm_client.py` (`logger = logging.getLogger(__name__)`).

**Patterns:**
- Emoji-prefixed console lines: `✅` success, `⚠️` warning/failure, `📝` persisted record, `🖥️ JS:` browser console, `🛡️` runner banner. Example: `print(f"   ✅ Successfully injected healed value '{healed_value}'")` (`src/sentinel/agent.py:3465`).
- Browser console noise is filtered in `_log_js_msg` before printing; tests assert that CORS/CSP/font warnings are dropped (`tests/unit/platforms/test_hirist_qa_logging_and_console_filtering.py`).
- Durable artifacts live under `~/Desktop/sentinel_errors/` (`SentinelAgent.SCREENSHOT_DIR`, `src/sentinel/agent.py:191`): `qa_results.csv`, `failure_log.jsonl`, `metrics.jsonl`, `unknown_questions.log`, `learned_patterns.json`, `pattern_stats.json`.
- **QA CSV contract:** `SentinelAgent.QA_RESULTS_COLUMNS` (`src/sentinel/agent.py:198`) defines the 13 columns `timestamp, platform, url, question, answer, input_type, options, selected_option, confidence, status, error_message, source, job_id_or_url`.
  - `_log_qa_result()` is the single writer; `log_qa_result` is the public alias. Never open the CSV directly.
  - Statuses in use: `submitted`, `validation_error`, `unknown`, `skipped`, `prefilled`, `recovered`.
  - Sources in use: `pattern_match`, `pattern_fallback`, `llm_gemma`, `js_form_fill`, `profile_prefilled`, `resync_retype`, `naukri_chatbot_fuzzy`, `self_healing`, `unmatched`, `unknown`.
  - `_log_qa_entries()` dedupes per application (keyed on `_current_job_url`) and maps blank answers to `status='unknown'`; `_log_qa_payload()` parses page-side `MARKER|JSON` results; `_drain_js_qa_log()` reads/clears `window.__SENTINEL_QA_LOG__`.

## Comments

**When to Comment:**
- Comments explain *why*, usually with measured justification. Example in `src/patterns/pattern_loader.py:38`: memoization because "the corpus is a 68 MB file and tests construct many matchers per session".
- Ordering and collision hazards are documented at the code site: `src/sentinel/agent.py:43` explains why module-level keyword constants replaced duplicated literals; `AGENTS.md` documents the yes/no-before-rating ordering rule.
- Inline JS comments use `//` inside the f-string literals.
- No `TODO`/`FIXME`/`HACK` markers exist in `src/` (the only `XXX` is a phone regex in `src/sentinel/question_fingerprint.py:669`).

**JSDoc/TSDoc:**
- Python docstrings, Google style with `Args:` / `Returns:` / `Raises:` for public APIs (`PatternLoader.load`, `FailureLogger.log_failure`, `GemmaLLMClient` methods).
- Module docstrings start with a one-line summary, then a bullet list of responsibilities (`src/sentinel/self_healing.py`, `src/sentinel/question_classifier.py`, `src/patterns/__init__.py`).
- Long internal methods document behavior and side effects, e.g. `_log_qa_entries` docstring explains the page mirror and dedupe rule (`src/sentinel/agent.py:3624`).

## Function Design

**Size:** No enforced limit. Helpers are small and single-purpose; some agent methods are very large (`_fuzzy_match_question` in `src/sentinel/agent.py:1152` spans ~1,900 lines, `_handle_scripted_fallback` similar). New logic should be added as `_answer_*` / `_resolve_*` / `_format_*` helpers rather than growing those methods.

**Parameters:** Explicit, typed, keyword-friendly. Logging APIs are called with keyword arguments (`_log_qa_result(question=..., answer=..., status=...)`) so new columns do not break call sites.

**Return Values:**
- Matchers: `Tuple[Optional[str], float]` (answer, confidence).
- Predicates: `bool` with names like `_is_intersession_task`, `_detect_negation`, `_is_skill_years_question`.
- Automation handlers: uppercase status strings.
- Stateless helpers are `@staticmethod` / `@classmethod` (`_has_leadership_context`, `_format_skill_years`, `_skill_display_name`, `AnswerValidator.validate`).

## Module Design

**Exports:** Package `__init__.py` files re-export explicit names with `__all__` (`src/patterns/__init__.py`, `src/sentinel/__init__.py`). Import from the package root when a public API exists; import the concrete module for internals (`from src.patterns.pattern_matcher import create_matcher`).

**Barrel Files:** Only the two `__init__.py` barrels above; `src/core/__init__.py` is empty by design.

**Layering:**
- `src/core/` — configuration and profile loading (`config.py`, `profile_store.py`), no browser or matching logic.
- `src/patterns/` — corpus loading, matching, validation, sanitization. Must not import `src.sentinel`.
- `src/sentinel/` — agent, platform flows, LLM, recovery, CLI, runner. Imports both lower layers.

**Single sources of truth:**
- Q&A behavior lives in `config/qa_patterns.json`; Python only implements logic that needs context. JS mirrors must be updated in `KNOWN_PATTERNS` inside `src/sentinel/agent.py` when LinkedIn/Naukri page scripts must answer the question.
- Candidate facts live in `profiles/resume.json` (gitignored, loaded by `ProfileStore`). Fallback constants are duplicated in `src/patterns/input_type_sanitizer.py:36-51` and `src/sentinel/llm_client.py:get_candidate_facts()` — update all three together.

## Configuration Conventions

- `src/core/config.py` parses `.env` manually with stdlib (no `python-dotenv`) and exports module-level constants with macOS-local defaults.
- `.env` exists at the repo root, is gitignored, and must never be read into documentation or logs. Variable names used by the code: `CHROME_USER_DATA`, `CHROME_EXECUTABLE_PATH`, `GOOGLE_AI_API_KEY`, `GOOGLE_AI_API_KEYS`, `RESUME_FILE_PATH`, plus runtime flags `SENTINEL_JS_DEBUG`, `SENTINEL_INDEED_DEBUG`, `INSTAHYRE_MAX_APPLICATIONS`, `INDEED_SEARCH_URL`, `INDEED_SEARCH_QUERY`, `INDEED_SEARCH_LOCATION`.
- `profiles/` is gitignored; `profiles/resume.json` is the runtime profile.

## Commit Conventions

From `AGENTS.md` and `git log`:
- Imperative mood is dominant: `Add unit tests for QA pattern fixes from CSV audits in October 2023`, `Fix qa_results.csv misanswers: day-count LWD, PM/EM/leadership zero-years`.
- Conventional Commits appear for scoped fixes: `fix(qa): ...`, `fix(linkedin): ...`, `feat: ...`, `chore: ...`.
- Multi-part summaries are joined with semicolons/dashes; no ticket or issue references.
- Single branch: `main` (remote `origin`), no feature branches.

## Prescriptive Rules for New Code

1. Put new Q&A behavior in `config/qa_patterns.json` first (patterns, category, default, `input_type_defaults`, `negative_patterns`). Add Python only for context-dependent logic.
2. Mirror any new JS-answerable pattern in the embedded `KNOWN_PATTERNS` literal in `src/sentinel/agent.py`.
3. Every new fill/skip/reject path must call `_log_qa_result()` (or `_log_qa_entries()` for a JS payload). This is the audit contract enforced by tests.
4. Use `queryDeep` / `queryAllDeep` for LinkedIn Shadow DOM; never `data-view-name` as a unique identifier.
5. Apply template/dynamic-value post-processing on every early-return path (see the `{{TECH_EXP_YEARS}}` leak lesson in `AGENTS.md`).
6. Platform formatting is decided from `self._current_platform`: LinkedIn/Indeed/Hirist use whole-number experience and raw INR; Naukri uses `"4.2 Years"`; Instahyre uses LPA strings.
7. Add tests to `tests/unit/qa/` for matcher behavior and `tests/unit/platforms/` for platform handlers; never write to `~/Desktop/sentinel_errors` in tests.

---

*Convention analysis: 2026-11-11*
