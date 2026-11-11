---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
<!-- refreshed: 2026-11-11 -->
# Architecture

**Analysis Date:** 2026-11-11

## System Overview

Sentinel is a script-driven job-application bot. A single long-lived `SentinelAgent` is reused across tasks; each task gets a fresh persistent Chrome context built from the user's real Chrome profile. Navigation and form filling are deterministic Playwright code and injected JavaScript. An LLM is used only for questionnaire answers: Instahyre asks Gemma for every question and prefers its answer, while Indeed/Hirist call Gemma only when pattern resolution fails.

```text
┌───────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION                                                        │
│  `src/sentinel/run.py`  (main loop, task table, Browser lifecycle)    │
│  `sentinel` -> `src/sentinel/cli.py`  (learning/analytics CLI)        │
└───────────────────────────────┬───────────────────────────────────────┘
                                │  one agent.run(prompt) per task
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│  AGENT CONTROL PLANE — `src/sentinel/agent.py` (26,034 lines)         │
│  `SentinelAgent.run()` step loop + URL/task dispatch + marker parsing │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┬──────┐ │
│  │ LinkedIn     │ Naukri       │ Instahyre    │ Hirist       │Indeed│ │
│  │ JS + handlers│ chatbot JS   │ Angular scope│ DOM handlers │iframe│ │
│  └──────────────┴──────────────┴──────────────┴──────────────┴──────┘ │
└──────────┬───────────────────────────────────┬───────────────────────┘
           │ page.evaluate(js)                 │ _fuzzy_match_question()
           ▼                                   ▼
┌──────────────────────────────┐   ┌───────────────────────────────────┐
│  PAGE-SIDE ENGINE            │   │  ANSWER RESOLUTION (Python)       │
│  `window.__SENTINEL_*__`     │   │  `src/patterns/*`                 │
│  fuzzyMatch (6-pass)         │   │   PatternMatcher 3 tiers          │
│  fills controls, queues CSV  │   │   InputAwareResolver              │
│  returns `MARKER|JSON`       │   │   input_type_sanitizer            │
└──────────┬───────────────────┘   │  `src/sentinel/question_*.py`     │
           │                       │  GemmaLLMClient (fallback)        │
           └───────────┬───────────┴───────────────────────────────────┘
                       ▼
┌───────────────────────────────────────────────────────────────────────┐
│  EXTERNAL / PERSISTENT                                                │
│  Chrome via Playwright (persistent profile copy)                      │
│  LinkedIn · Naukri · Instahyre · Hirist · Indeed                      │
│  Google AI Studio (Gemma)  |  `config/qa_patterns.json` (77.8 MB)     │
│  `profiles/resume.json`    |  `~/Desktop/sentinel_errors/*`           │
└───────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `main()` | Warms Playwright, registers task table, loops cycles, launches one `Browser` per task, reuses one `SentinelAgent`, runs Instahyre "intersession" passes between cycles | `src/sentinel/run.py:766` |
| `Browser` | Persistent-context Chrome lifecycle: profile mirror, lock cleanup, launch retries, popup auto-close, PID-based force kill, temp sweep | `src/sentinel/run.py:162` |
| `SentinelAgent` | Owns per-task state, dispatch, platform handlers, Q&A Python tiers, CSV audit writers, metrics | `src/sentinel/agent.py:181` |
| `SentinelAgent.run()` | Step loop (max 120), rate-limit/session/login guards, task routing, marker-string handling, metrics save | `src/sentinel/agent.py:4533` |
| `_handle_scripted_fallback()` | Injects corpus into page, evaluates the 10.6k-line universal JS function, drains page-side QA log | `src/sentinel/agent.py:15421` |
| `_handle_chatbot_loop()` | Naukri chatbot state machine: 30 iterations of JS question extraction/answer, completion detection | `src/sentinel/agent.py:12356` |
| `_answer_instahyre_questionnaire()` | Reads Angular scope questions, answers via patterns then Gemma, writes Angular model + DOM, submits | `src/sentinel/agent.py:11215` |
| `_handle_hirist_apply_task()` | Hirist next-gen job feed apply flow, experience filters, questionnaire | `src/sentinel/agent.py:9731` |
| `_handle_indeed_apply_task()` | Indeed SmartApply inside nested iframes, reCAPTCHA handling, question filling | `src/sentinel/agent.py:8089` |
| `_handle_instahyre_inbox_task()` | Instahyre recruiter-inbox conversations + questionnaire invitations | `src/sentinel/agent.py:7125` |
| `PatternMatcher` | 3-tier corpus matching (exact/word-boundary → category fuzzy → global fuzzy), dynamic placeholder resolution, intent overrides | `src/patterns/pattern_matcher.py:36` |
| `PatternLoader` / `load_patterns` | Memoized JSON load/validation of the 77.8 MB corpus | `src/patterns/pattern_loader.py:31` |
| `input_type_sanitizer` | Single deterministic place for control-safe answers: `derive_value`, `sanitize_answer`, `build_input_type_defaults`, stale-date repair, PII detection | `src/patterns/input_type_sanitizer.py` |
| `InputAwareResolver` | Maps a canonical answer onto available radio/select/checkbox options, including numeric ranges | `src/patterns/input_aware_resolver.py:134` |
| `AnswerValidator` / `EnhancedAnswerValidator` | Category validation and platform-format correction | `src/patterns/answer_validator.py:5`, `src/patterns/enhanced_answer_validator.py:16` |
| `FingerprintMatcher` / `SuccessTracker` | Normalizes questions to fingerprints, caches matches, tracks per-answer success rates | `src/sentinel/question_fingerprint.py:865`, `:503` |
| `QuestionClassifier` | Keyword/regex category classification + platform defaults (PHASE 3 fallback) | `src/sentinel/question_classifier.py:342` |
| `SelfHealingMatcher` | Failure log (`failure_log.jsonl`), learned patterns (`learned_patterns.json`), option mappings, recovery engine | `src/sentinel/self_healing.py:419` |
| `GemmaLLMClient` | Google AI Studio Gemma answer generation with key rotation, model discovery, fallback chain | `src/sentinel/llm_client.py:210` |
| `UIErrorDetector` | Platform-specific validation-error detection and suggested recovery | `src/sentinel/ui_error_detector.py:50` |
| `RateLimiter` / `SessionManager` / `FormStateValidator` | Adaptive pacing, crash/timeout recovery, pre/post form snapshots | `src/sentinel/rate_limiter.py:14`, `src/sentinel/session_manager.py:13`, `src/sentinel/form_state_validator.py:13` |
| `ProfileStore` | Loads/validates `profiles/resume.json`, dotted-path access, JS export | `src/core/profile_store.py:25` |
| `prompts.py` | Task descriptors whose keywords drive routing, plus candidate facts text used as reference material | `src/sentinel/prompts.py` |

## Pattern Overview

**Overall:** Layered scripted automation with a page-side script engine, a shared multi-tier answer resolver, and a stringly-typed status protocol between JavaScript and Python.

**Key Characteristics:**
- **No LLM in the navigation loop.** `SentinelAgent.run()` is explicitly `100% SCRIPTED (No LLM)` (`src/sentinel/agent.py:4534`). Prompts in `src/sentinel/prompts.py` act as task identifiers and routing keywords; the actual actions are Playwright code and injected JS.
- **One agent, many browsers.** `main()` creates one `SentinelAgent` (`src/sentinel/run.py:856`) and calls `reset_per_task_state()` before every task (`:902`); pattern indexes, fingerprint cache and learned patterns survive across tasks. A new `Browser` is created per task.
- **One universal page script.** `_handle_scripted_fallback` evaluates a single ~10.6k-line JS function that branches on `window.location.hostname` / `document.title` into LinkedIn, Naukri and Instahyre sections (`src/sentinel/agent.py:15477`–`26030`).
- **Data-driven Q&A.** `config/qa_patterns.json` (v3.0; 67,022 pattern groups, 224,791 variants, 27 categories) is injected into the page as `window.__SENTINEL_PATTERNS__` / `__SENTINEL_PATTERNS_WITH_DEFAULTS__` (`src/sentinel/agent.py:419`), so JS and Python answer from the same corpus.
- **Conservative fallback ordering.** Python resolution goes skip → hard gates/intercepts → fingerprint → learned → keyword priority → JSON fuzzy → classifier, with each tier returning a confidence score.
- **Audit trail is part of the contract.** Every answered/skipped/rejected control must produce a row in `~/Desktop/sentinel_errors/qa_results.csv` through `_log_qa_result()` / `_log_qa_entries()` (`src/sentinel/agent.py:3562`, `:3624`).

## Layers

**Orchestration layer:**
- Purpose: process lifecycle, task scheduling, Chrome/profile management, cycle pacing, rate-limit carry-over
- Location: `src/sentinel/run.py`, `src/sentinel/cli.py`, `sentinel`
- Contains: `Browser`, temp-dir/profile mirror, Playwright singleton, task table, intersession loop, CLI subcommands
- Depends on: `src/core/config.py`, `src/sentinel/agent.py`, `src/sentinel/prompts.py`
- Used by: `python src/sentinel/run.py`, live harness scripts

**Agent control layer:**
- Purpose: per-task state machine and platform dispatch
- Location: `src/sentinel/agent.py`
- Contains: `SentinelAgent.run()`, URL/task dispatch, marker parsing, metrics, login/health guards, CSV writers, self-healing hooks
- Depends on: every other `src/` module
- Used by: `run.py`, scripts

**Page automation layer:**
- Purpose: interact with portal DOM/React/Angular
- Location: embedded JS inside `src/sentinel/agent.py` (`_handle_scripted_fallback`, `_handle_chatbot_loop`, `_answer_instahyre_questionnaire`, Hirist/Indeed handlers) and `src/sentinel/human_behavior.py`
- Contains: 6-pass `fuzzyMatch`, Shadow DOM `queryDeep`/`queryAllDeep`, React native-setter retyping, Angular `$scope` reads/writes, iframe traversal
- Depends on: `window.__SENTINEL_*__` globals, Playwright `page.evaluate` / `frame.evaluate`
- Used by: agent control layer

**Answer resolution layer:**
- Purpose: turn a question into a control-safe answer
- Location: `src/patterns/`, `src/sentinel/question_classifier.py`, `src/sentinel/question_fingerprint.py`, `src/sentinel/llm_client.py`
- Contains: corpus loader, matcher tiers, sanitizer, option resolver, validators, classifier, LLM fallback
- Depends on: `config/qa_patterns.json`, `profiles/resume.json`, Google AI Studio
- Used by: `SentinelAgent._fuzzy_match_question()` (`src/sentinel/agent.py:1152`), `_match_answer_to_options()` (`:3222`), `_validate_and_retry()` (`:3119`), and platform handlers

**Resilience & telemetry layer:**
- Purpose: keep long-running sessions alive and learn from failures
- Location: `src/sentinel/self_healing.py`, `ui_error_detector.py`, `session_manager.py`, `rate_limiter.py`, `form_state_validator.py`
- Contains: failure log, learned patterns, recovery engine, error classifiers, crash counters, jitter/backoff
- Depends on: `~/Desktop/sentinel_errors/`
- Used by: agent loop (`_attempt_form_recovery` at `src/sentinel/agent.py:3275`) and handlers

**Configuration/data layer:**
- Purpose: environment, candidate identity, answer corpus
- Location: `src/core/config.py`, `src/core/profile_store.py`, `profiles/resume.json`, `config/qa_patterns.json`
- Contains: env parsing (stdlib, no python-dotenv), profile validation, JSON corpus
- Depends on: `.env` (present, gitignored), filesystem
- Used by: every layer

## Data Flow

### Primary Task Path

1. `main()` starts a shared Playwright instance and warms the Chrome pipe (`src/sentinel/run.py:766`, `:797`).
2. It iterates the task table (`src/sentinel/run.py:770`; nine active entries — Hirist, Instahyre Inbox, Naukri, LinkedIn, Instahyre Search, LWD +15, LWD +14, Naukri Profile Update, Naukri Early Access; the Indeed entry is commented out).
3. For each task: `Browser.start()` mirrors `$CHROME_USER_DATA/Default` into one shared temp profile, patches crash-restore prefs, kills stale Chrome by PID marker, and launches `launch_persistent_context` with retries (`src/sentinel/run.py:212`).
4. `agent.reset_per_task_state()` clears page refs, counters, metrics and rate-limit flags (`src/sentinel/agent.py:503`), then `agent.run(task_description=prompt)` is called (`src/sentinel/run.py:944`).
5. `run()` enters a 120-step loop (`src/sentinel/agent.py:4582`): rate limiter → session health → LinkedIn/Naukri rate-limit guard → memory cleanup → page health → login check → dialog dismissal → random human behavior.
6. Dedicated workflows are dispatched first by URL/task keywords: Instahyre inbox/questionnaire, Indeed, Hirist, Naukri profile/LWD/early-access (`src/sentinel/agent.py:4640`–`4682`). Otherwise `_handle_scripted_fallback()` runs.
7. The returned marker string drives post-processing in `run()`: `TASK_COMPLETE`, `SUCCESS`, `NAUKRI_*`, `LINKEDIN_*`, `CHATBOT_*`, `INSTAHYRE_*`, `ERROR`, etc. Metrics are updated and `_save_metrics()` writes JSONL (`src/sentinel/agent.py:3880`, `:6917`).
8. `Browser.stop()` closes pages/context, force-kills leftover Chrome, sweeps temp; `run.py` resets the Playwright pipe and waits 10s before the next task (`src/sentinel/run.py:692`).

### Python Q&A Resolution Path (`_fuzzy_match_question`)

Entry: `src/sentinel/agent.py:1152`. Platform is refreshed from the current URL at `:1155`.

1. **PHASE 0 — skip patterns** (`:1165`): returns `('', 1.0)` for "skip this question", "try again", etc.
2. **PHASE 0.05 — skill/eligibility gates** (`:1172`): 0–5 rating scale, CTC threshold gate, experience threshold gate, zero-skill role/domain overrides, per-skill years map (`SKILL_EXPERIENCE_YEARS`, `ZERO_EXPERIENCE_OVERRIDES` at `src/sentinel/agent.py:63`–`180`).
3. **PHASE 0.1 — compliance and intent intercepts** (`:1239`): a long ladder of hardcoded answers (conflict of interest, notice/LWD, relocation, work authorization, domain-specific essays, pronouns, etc.) with 0.95–0.99 confidence.
4. **PHASE 0.5 — fingerprint match** (`:2259`): `FingerprintMatcher.match()`; resolves dynamic placeholders and intent, applies LinkedIn whole-number experience normalization, validates against `detect_expected_format()` / `validate_answer()`.
5. **PHASE 0.6 — learned patterns** (`:2285`): `SelfHealingMatcher.get_learned_answer()`, requires confidence ≥ 0.5.
6. **PHASE 1 — keyword priority matching** (`:2294`): detects salary/experience/notice/location/rating/project-count/tech/DSA/etc. categories, then applies a fixed priority ladder.
7. **PHASE 2 — JSON corpus** (`:3085`): `PatternMatcher.fuzzy_match(question)` with threshold `0.65`, then `_validate_and_retry()`.
8. **PHASE 3 — classifier fallback** (`:3100`): `QuestionClassifier.classify()` + `get_answer()` when confidence ≥ 0.4.
9. Returns `(None, best_score)` when nothing matches.

Answers are then adapted for the control: `_format_answer_for_field()` (`:594`) coerces numeric and yes/no values, `_match_answer_to_options()` (`:3222` → `InputAwareResolver`) picks from available options, and platform formatting is applied by `EnhancedAnswerValidator._apply_platform_format()` (`src/patterns/enhanced_answer_validator.py:109`) plus host-specific JS overrides.

### Page-Side Form-Filling Path (LinkedIn / Naukri / Instahyre search)

1. `_handle_scripted_fallback()` injects the corpus once per page (`_inject_patterns_once`, `src/sentinel/agent.py:419`). It builds `compact_groups` from `PatternMatcher.patterns` while skipping synthetic taxonomy IDs derived from `scripts/taxonomy_data.py` (`:341`–`417`), then sets globals:
   `__SENTINEL_PATTERNS__`, `__SENTINEL_PATTERNS_WITH_DEFAULTS__`, `__SENTINEL_EXACT_MATCH_KEYS__`, `__SENTINEL_SYNONYMS__`, `__SENTINEL_STOPWORDS__`, `__SENTINEL_PROFILE__`, `__SENTINEL_SKILL_YEARS__`, `__SENTINEL_ZERO_SKILL_OVERRIDES__`, `__SENTINEL_GENERIC_SKILLS__`, `__SENTINEL_DEBUG__`, `__SENTINEL_ISVISIBLE__`.
2. The universal JS function reads those globals, applies host-specific overrides (LinkedIn salary/experience normalization at `:15500`+, Naukri/Instahyre logic), and walks radios, checkboxes, selects, text inputs and textareas. Shadow DOM helpers `queryDeep`/`queryAllDeep` are used for LinkedIn.
3. Every filled control is pushed into a local `formResults` / `genericResults` array; `attachQaLog()` mirrors each push into `window.__SENTINEL_QA_LOG__` (see `:15483`).
4. The function returns a marker such as `LINKEDIN_FORM_STEP_CONTINUED|[...]`, `GENERIC_FORM_FILLED|[...]`, `INSTAHYRE_*`, or `NO_ACTION`. The `\x08` → `\\b` replacement protects regex word boundaries from Python escape handling (`src/sentinel/agent.py:26009`).
5. Python evaluates the script at `:26012`, then drains `window.__SENTINEL_QA_LOG__` (`_drain_js_qa_log`, `:3761`) and parses the `MARKER|JSON` payload (`_log_qa_payload`, `:3694`). Both funnel into `_log_qa_entries()` → `qa_results.csv`.

### Naukri Chatbot Path

1. `run()` sees `CHATBOT_DETECTED` (or `CHECKBOX_CLICKED`/`APPLY_CLICKED` variants) for `naukri.com` and calls `_handle_chatbot_loop()` (`src/sentinel/agent.py:6579`).
2. The loop runs up to 30 iterations. Each iteration evaluates a dedicated async JS block that detects the chat input type (select/radio/checkbox/date/button/text) and runs an input-type-aware `fuzzyMatch` (`:12398`).
3. JS returns `CHATBOT_COMPLETE`, `CHATBOT_WAITING`, `CHATBOT_SKIPPED_QUESTION: ...`, `CHATBOT_SUBMISSION_ERROR: ...`, or a `MARKER|JSON` answer payload.
4. `_log_naukri_chatbot_result()` (`:3720`) writes the row; `_resolve_naukri_completion()` (`:6925`) reconciles the "X out of Y" count and returns `CHATBOT_COMPLETE: n/5` or `CHATBOT_NO_PROGRESS: n/5`.
5. `_handle_naukri_post_apply()` (`:12235`) controls batching, no-progress guards and navigation back to recommended jobs.

### Instahyre Questionnaire Path

1. `_handle_instahyre_inbox_task()` (`:7125`) opens inbox conversations/questionnaires and delegates to `_answer_instahyre_questionnaire()` (`:11215`).
2. The handler reads questions from the Angular scope (`window.angular.element(...).scope().questionnaire.questions`) with a DOM fallback, including type, min/max and choice options.
3. For each question: `_fuzzy_match_question()` produces a pattern answer; a Gemma call (`GemmaLLMClient.answer_question`, timeout 15s) is attempted and wins when it returns text (`source="llm_gemma"`); otherwise the pattern/fallback answer is used (`:11373`).
4. The answer is written back into the Angular scope model and DOM, then submission is triggered through the Angular controller. `_send_instahyre_ack()` (`:11822`) handles acknowledgement messages.
5. Every answer is logged with its real `input_type` via `_log_qa_result()`.

### Hirist / Indeed Paths

- **Hirist:** `_handle_hirist_apply_task()` (`:9731`) navigates the Next.js job feed, applies experience filters, opens apply modals, scans the questionnaire (`_hirist_scan_questionnaire`, `:10344`), fills controls (`_hirist_fill_questionnaire`, `:10798`) and logs each attempt, including `validation_error` rows. `_hirist_recheck_applied()` (`:11200`) verifies the final state.
- **Indeed:** `_handle_indeed_apply_task()` (`:8089`) drives search UI + "Easily apply" filter, opens cards, and runs `_indeed_run_apply_flow()` (`:8898`) inside the SmartApply iframe. `_indeed_answer_questions()` (`:9352`) scans `.ia-Questions-item`, answers from patterns then Gemma, and sets text/radio/checkbox/select via `_indeed_set_*` helpers (`:9514`–`9728`). reCAPTCHA/audio challenge handling lives at `:8589`/`:8742`.

### State Management

- **Python per-task state:** `SentinelState` (`src/sentinel/schemas.py`) holds `step_count`, `task_complete`, `errors`; `SentinelAgent.metrics` is a dict reset per task; counters such as `_naukri_no_progress_count`, `_linkedin_stuck_count`, `_instahyre_wait_count` gate loops.
- **Cross-task state:** pattern indexes (`PatternMatcher._INDEX_CACHE`), corpus load cache (`pattern_loader._LOAD_CACHE`), `FingerprintMatcher`, `SuccessTracker`, `SelfHealingMatcher` learned patterns.
- **Page-side state:** `window.__SENTINEL_QA_LOG__` (CSV queue), `window.__skippedJobIds` / `__skippedJobTitles` (job de-dupe), `sessionStorage` keys such as `naukri_total_applied` and `instahyre_*` flags.
- **Filesystem state:** `qa_results.csv`, `failure_log.jsonl`, `learned_patterns.json`, `metrics.jsonl`, `unknown_questions.log`, `all_questions.log`, screenshots — all under `~/Desktop/sentinel_errors/` (`src/sentinel/agent.py:191`–`198`, `src/sentinel/self_healing.py:75`, `:152`).

## Key Abstractions

**`PatternMatcher` (corpus engine):**
- Purpose: answer arbitrary question text from the JSON corpus
- Examples: `src/patterns/pattern_matcher.py:36`; created via `create_matcher()` (`:1325`), used by `SentinelAgent` and scripts
- Pattern: tiered retrieval — exact normalized match → word-boundary substring → category-scoped fuzzy (`SequenceMatcher`) → global fuzzy, with priority tie-breaks, negative patterns and `requires_exact_match` protection

**`QuestionIntent` / `derive_value` (control-safe derivation):**
- Purpose: convert a canonical answer into the value an HTML control can accept
- Examples: `detect_intent()` (`src/patterns/input_type_sanitizer.py:640`), `derive_value()` (`:836`), `sanitize_answer()` (`:1581`), `build_input_type_defaults()` (`:1704`)
- Pattern: deterministic rule table over question text + category + default, with candidate constants as fallbacks

**`InputAwareResolver` / `InputType`:**
- Purpose: choose the option label that best represents an answer
- Examples: `src/patterns/input_aware_resolver.py:134`; `NumericRangeMatcher` (`:55`) for "3-5 years" option sets
- Pattern: synonym groups + numeric/range matching + fuzzy label similarity, returning `MatchResult` with `match_type`/confidence

**`FingerprintMatcher` / `SuccessTracker`:**
- Purpose: collapse question paraphrases into a stable key and learn which answers succeed
- Examples: `src/sentinel/question_fingerprint.py:865`, `:503`
- Pattern: stop-word removal + synonym normalization + SHA-1 fingerprint; JSON persistence of attempt stats

**`SelfHealingMatcher`:**
- Purpose: turn failures/manual corrections into reusable learned patterns
- Examples: `src/sentinel/self_healing.py:419`; `FailureLogger` (`:70`), `LearningStore` (`:147`), `RecoveryEngine` (`:262`)
- Pattern: append-only failure JSONL + mutable learned-pattern JSON + option-mapping store

**`GemmaLLMClient`:**
- Purpose: answer open-ended questions that patterns cannot cover
- Examples: `src/sentinel/llm_client.py:210`; called from Instahyre (`src/sentinel/agent.py:11373`) and Indeed (`:9443`)
- Pattern: multi-key rotation, model discovery (`verify_and_select_model`, `:367`), fallback chain, capped exponential backoff, `_match_chosen_option()` to snap free text onto available options

**Status markers (`MARKER|JSON`):**
- Purpose: the only return channel from page scripts to Python
- Examples: `LINKEDIN_FORM_STUCK`, `LINKEDIN_SUCCESS_MODAL_CLOSED`, `NAUKRI_RATE_LIMITED`, `CHATBOT_COMPLETE: 3/5`, `INSTAHYRE_ADDED_SKILLS: 15 skills added`, `GENERIC_FORM_FILLED|[...]`
- Pattern: upper-snake marker, optional `:` detail, optional `|` JSON payload; Python dispatches by substring/prefix checks in `run()`

**`window.__SENTINEL_*__` globals:**
- Purpose: carry corpus, profile, skill maps and JS↔Python queues across `page.evaluate` calls
- Examples: injection at `src/sentinel/agent.py:419`–`500`; consumption in JS at `:15477`+
- Pattern: write once per page, read from any injected function; `__SENTINEL_QA_LOG__` is drained and cleared each step

## Entry Points

**`python src/sentinel/run.py`:**
- Location: `src/sentinel/run.py:1113` (`asyncio.run(main())`)
- Triggers: manual/daemon invocation
- Responsibilities: infinite cycle of nine tasks + Instahyre intersession passes; process-level temp/Playwright cleanup via `atexit`

**`./sentinel <subcommand>`:**
- Location: `sentinel:20` → `src/sentinel/cli.py:258`
- Triggers: operator commands
- Responsibilities: `stats`, `patterns`, `failures`, `learn`, `export` over the self-healing store

**Live harnesses:**
- Location: `scripts/run_live_linkedin_test.py`, `scripts/test_live_{linkedin,both_tasks,naukri,instahyre,hirist,indeed}_*.py`
- Triggers: `python scripts/...`
- Responsibilities: single-platform real-Chrome runs with screenshots/DOM capture under `live_test_output*/`

**Tests:**
- Location: `tests/` (88 `test_*.py` modules)
- Triggers: `pytest`
- Responsibilities: pattern-corpus regressions, platform handler behavior with mocked Playwright pages, core config/profile tests, one integration pipeline test

## Architectural Constraints

- **Concurrency:** single-threaded `asyncio` event loop. All Playwright operations are async; LLM HTTP calls use `urllib` inside `asyncio.to_thread` (`src/sentinel/llm_client.py:303`, `:348`). No worker pool for portal automation.
- **Global mutable state:** `_shared_playwright`, `_shared_tmp_root`, `_shared_profile_dir`, `_browser_counter` (`src/sentinel/run.py:17`–`31`); `PatternMatcher._INDEX_CACHE` (`src/patterns/pattern_matcher.py:45`); `pattern_loader._LOAD_CACHE` (`src/patterns/pattern_loader.py:29`). The process assumes a single agent/browser at a time.
- **One agent per process:** `create_agent()` is called once (`src/sentinel/run.py:856`). Per-task isolation is by `reset_per_task_state()`, not by re-instantiation; any new mutable field must be reset there.
- **macOS/Chrome coupling:** `Browser.start()` hardcodes `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` (`src/sentinel/run.py:219`) and force-kills processes with `pgrep -f sentinel_profile_<pid>` (`:662`). `CHROME_EXECUTABLE_PATH` from `src/core/config.py` is not used by `run.py`.
- **Profile mirror cost:** each task wipes and re-copies the Chrome `Default` profile (minus caches) into one shared temp dir (`src/sentinel/run.py:270`–`318`). Startup is I/O-heavy and blocking inside the async function.
- **CDP payload limit:** `_get_patterns_for_js()` deliberately excludes synthetic taxonomy cohorts generated from `scripts.taxonomy_data.py` (`src/sentinel/agent.py:355`–`369`) to keep the injected arrays within Chrome DevTools limits.
- **Stringly-typed protocol:** ~79 platform-prefixed markers (`LINKEDIN_*`, `NAUKRI_*`, `CHATBOT_*`, `INSTAHYRE_*`) plus generic status words — 157 distinct uppercase return strings in total — are interpreted in `run()`; adding a new state requires editing both the JS literal and the Python dispatch ladder.
- **JS/Python duplication:** skill-year maps, zero-experience overrides, salary normalization and fuzzy-match logic exist in Python (`src/sentinel/agent.py:63`+) and again inside the JS literals (`:12398`, `:15748`). They must be edited together.
- **Corpus is committed and large:** `config/qa_patterns.json` is 77.8 MB and read at agent construction; `load_patterns`/`_INDEX_CACHE` make this ~0.2 s per process but memory-heavy.
- **Chrome-only:** no Firefox/WebKit support; selectors assume Chromium DOM/CDP behavior.
- **No packaging:** import works only from the repo root; every entry point injects the repo root into `sys.path` (`src/sentinel/run.py:13`, `sentinel:14`, `tests/conftest.py:14`).

## Anti-Patterns

### God class and god methods

**What happens:** `SentinelAgent` is a 26,034-line class. `_handle_scripted_fallback` spans ~10,600 lines (`src/sentinel/agent.py:15421`–`26030`), `run()` ~2,390 lines (`:4533`–`6923`), `_fuzzy_match_question` ~1,970 lines (`:1152`–`3117`), `_handle_chatbot_loop` ~2,290 lines (`:12356`–`14649`).
**Why it's wrong:** any change risks unrelated platforms; review, merge conflicts and test isolation are hard; IDE navigation and static analysis are ineffective.
**Do this instead:** when touching a platform, extract its block into a small helper/module under `src/sentinel/` (e.g. `naukri_chatbot.py`) and keep `agent.py` as the dispatcher. New code should follow the smaller modules (`src/sentinel/rate_limiter.py`, `src/sentinel/session_manager.py`) rather than adding another thousand-line method.

### Stringly-typed control flow

**What happens:** JS returns markers like `SUCCESS`, `LINKEDIN_FORM_STUCK: ...`, `CHATBOT_COMPLETE: 3/5`, and Python branches on `in result` / `startswith` in a long if-ladder (`src/sentinel/agent.py:4745`–`6900`).
**Why it's wrong:** substring collisions are real — the code needs an explicit `ERROR`/`ERROR:` check before the `SUCCESS` check (`:4745`) to avoid a failure message containing "SUCCESS" being treated as success; ordering is load-bearing and undocumented.
**Do this instead:** return structured payloads (e.g. JSON `{status, platform, detail}`) or at minimum define marker constants in one module and dispatch with exact prefix matching, not `in`.

### Triplicated answer sources

**What happens:** the same facts live in `config/qa_patterns.json`, in Python constants (`SKILL_EXPERIENCE_YEARS`, `CANDIDATE_TOTAL_YEARS`, `ZERO_EXPERIENCE_OVERRIDES` at `src/sentinel/agent.py:63`–`180`), and in JS overrides inside the injected literal (LinkedIn salary/experience rewrite at `src/sentinel/agent.py:15500`+, Naukri pre-checks at `:12398`+). The sanitizer also owns its own constants (`CURRENT_CTC_LPA`, `NOTICE_PERIOD_DAYS`, etc. at `src/patterns/input_type_sanitizer.py:34`–`55`).
**Why it's wrong:** fixing one layer silently diverges from the others; AGENTS.md's sync warnings exist because this has already caused wrong answers.
**Do this instead:** treat `config/qa_patterns.json` as the single source of truth, and when a value must be known in JS, inject it from Python (as `__SENTINEL_PROFILE__` / `__SENTINEL_SKILL_YEARS__` already do) rather than retyping it.

### Production code importing a maintenance script

**What happens:** `SentinelAgent._get_patterns_for_js()` imports `scripts.taxonomy_data` (`src/sentinel/agent.py:361`).
**Why it's wrong:** the runtime package depends on an uninstalled top-level `scripts/` directory; any packaging or path change breaks pattern injection, and the dependency is invisible in `requirements`.
**Do this instead:** move `TECHNOLOGIES`/`FEATURES` into `src/patterns/taxonomy.py` (or generate a small committed manifest) and have both the agent and the generator import from `src`.

### Bare `except:` in control flow

**What happens:** `_detect_platform()` wraps its whole body in `try: ... except: pass` (`src/sentinel/agent.py:654`–`687`). Bare `except:` also appears in answer normalization (`:635`), date fixing (`:3198`), button clicking (`:4992`), Naukri result parsing (`:6354`), and profile lock cleanup (`src/sentinel/run.py:271`).
**Why it's wrong:** bare `except:` catches `KeyboardInterrupt`, `asyncio.CancelledError` and `SystemExit`, so Ctrl+C and task cancellation can be swallowed; real bugs become silent.
**Do this instead:** catch `Exception` (never bare) and log the failure, as the newer handlers do.

### Blocking I/O inside async handlers

**What happens:** CSV append (`src/sentinel/agent.py:3608`), JSON dumps of the pattern payload (`:443`), profile mirroring (`src/sentinel/run.py:270`+) and `subprocess.run`/`pgrep` calls (`src/sentinel/run.py:618`–`688`) run directly on the event loop.
**Why it's wrong:** each call stalls Playwright's protocol handling and page timers, which can trigger the "stuck modal"/timeout paths the code then tries to recover from.
**Do this instead:** keep per-row CSV writes buffered and flush off-loop (`asyncio.to_thread`), and reuse the existing async patterns rather than adding synchronous work to `run()`.

## Error Handling

**Strategy:** layered containment — page-side guards, marker-based error states, Python recovery components, and a final per-task try/except that skips the task instead of killing the process.

**Patterns:**
- **Marker errors:** `ERROR`/`ERROR: ...` results are counted; 10 consecutive script errors stop the task (`src/sentinel/agent.py:4745`–`4763`).
- **Rate limits:** LinkedIn → 3-hour pause, Naukri → 9-hour pause, stored on the agent and honored at the outer loop (`src/sentinel/agent.py:4794`–`4802`, `src/sentinel/run.py:946`–`953`).
- **Self-healing:** `_attempt_form_recovery()` (`:3275`) queries `UIErrorDetector`, consults `SelfHealingMatcher`, fixes the value with `EnhancedAnswerValidator`, retries the field and records success/failure.
- **Session health:** `SessionManager.check_health()`/`recover()` reload/re-navigate after crashes, with a max-crash stop (`src/sentinel/session_manager.py`).
- **Task-level containment:** `main()` catches navigation and runtime errors per task, skips the task, and continues the cycle (`src/sentinel/run.py:961`–`979`); Chrome launch failures raise `RuntimeError` and are treated as skippable.
- **Telemetry:** failures append to `~/Desktop/sentinel_errors/failure_log.jsonl`; unknown questions to `unknown_questions.log`; validation rejections to `qa_results.csv` with `status='validation_error'`.

## Cross-Cutting Concerns

**Logging:** `print()` with emoji prefixes is the primary log. Browser console messages are attached via `page.on("console", self._log_js_msg)` (`src/sentinel/agent.py:4560`) and filtered for noisy site output (`:4452`). `SENTINEL_JS_DEBUG=1` enables `window.__SENTINEL_DEBUG__` logs (`:455`).

**Validation:** three layers — `PatternMatcher` intent resolution and negative patterns, `AnswerValidator`/`EnhancedAnswerValidator` category + platform checks, and `input_type_sanitizer.is_valid_value`/`sanitize_answer` for control compatibility. `_validate_and_retry()` repairs numeric/salary/yes-no formats.

**Authentication:** none in code. Sentinel relies on the logged-in Chrome profile copied from `CHROME_USER_DATA`; `_check_login_state()` pauses and prompts the operator if a login wall appears (`src/sentinel/agent.py:3962`).

**Platform detection:** `_detect_platform()` from the page URL (`:654`), explicit `_current_platform` overrides in handlers (`:7145`, `:8108`, `:9743`), and `window.location.hostname` inside JS (`:15500`). All three must agree for correct formatting.

**Memory management:** `_maybe_cleanup_memory()` clears the DevTools console every 50 steps (`:3947`); `run.py` resets the Playwright pipe and sweeps Chrome temp after every task (`src/sentinel/run.py:980`–`988`).

---

*Architecture analysis: 2026-11-11*
