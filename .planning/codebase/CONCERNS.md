---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# Codebase Concerns

**Analysis Date:** 2026-11-11

## Tech Debt

**`src/sentinel/agent.py` is a 26k-line monolith that is ~68% embedded JavaScript:**
- Issue: `agent.py` is 26,034 lines / 1.75 MB with 127 methods. Measured: 1.19 MB (68% of the file) sits inside 132 triple-quoted string literals that are JavaScript, not Python. The five largest methods are `_handle_scripted_fallback` (`agent.py:15421`, **10,614 lines**), `run` (`agent.py:4533`, 2,392 lines), `_handle_chatbot_loop` (`agent.py:12356`, 2,294 lines), `_fuzzy_match_question` (`agent.py:1152`, 1,967 lines), `_answer_instahyre_questionnaire` (`agent.py:11215`, 607 lines).
- Files: `src/sentinel/agent.py`
- Impact: no linter, type checker, or IDE navigation reaches the JS; a syntax error in one literal only surfaces at runtime inside `page.evaluate()`; diffs of a 10k-line method are unreviewable; every JS fix is a Python edit.
- Fix approach: extract the LinkedIn/Naukri scripts into `src/sentinel/scripts/*.js`, load with `Path.read_text()` at class init, keep the `window.__SENTINEL_*` injection contract. That alone removes ~1.1 MB of literals from `agent.py` and makes the JS testable with `node`.

**Answer logic is reimplemented five times, with different results per platform:**
- Issue: the same question can be answered by (1) ~35 hardcoded PHASE 0.1 intercepts plus 22 ordered PHASE 1 blocks in `_fuzzy_match_question` (`agent.py:1152`), (2) `PatternMatcher` (`src/patterns/pattern_matcher.py`), (3) `FingerprintMatcher` (`src/sentinel/question_fingerprint.py:865`), (4) `QuestionClassifier` (`src/sentinel/question_classifier.py`), and (5) two separate JavaScript `fuzzyMatch` implementations — `agent.py:12398` (Naukri chatbot) and `agent.py:15748` (LinkedIn form, 6-pass).
- Files: `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py`, `src/sentinel/question_fingerprint.py`, `src/sentinel/question_classifier.py`
- Impact: 361 `return ..., 0.9x` hardcoded confidences in `agent.py` alone. The Python path and the JS path disagree: `_fuzzy_match_question` calls `self._pattern_matcher.fuzzy_match(question)` with **no `input_type`** (`agent.py:3091`), while the JS path is input-type aware. A yes/no radio question handled on Naukri/Hirist/Instahyre gets the text answer; the same question on LinkedIn gets the radio answer.
- Fix approach: one resolution entrypoint that takes `(question, input_type, options)`, with platform rules as a post-processing table. `src/patterns/input_type_sanitizer.py` already contains the intended sanitisation; route every caller through it with an explicit `input_type`.

**`PatternMatcher._resolve_question_intent` is 823 lines with 111 `if/elif` branches:**
- Issue: `src/patterns/pattern_matcher.py:152-975` — 111 branches and 153 `return` statements encode question semantics as ordered regex checks. Ordering is load-bearing and undocumented outside code comments (e.g. yes/no proficiency must precede rating).
- Files: `src/patterns/pattern_matcher.py`
- Impact: adding a rule silently changes an earlier-matching rule's behaviour. This already happened: `pattern_matcher.py:404-406` now answers "Do you have experience in React?" with a 60-word sentence (see Known Bugs).
- Fix approach: split into named predicates (`is_yes_no_proficiency`, `is_rating`, `is_salary`…) each with its own unit test, driven by a declarative priority table instead of an if-chain.

**Candidate profile is copied into at least seven places; `ProfileStore` is effectively unused:**
- Issue: `src/patterns/input_type_sanitizer.py` declares `CURRENT_CTC_LPA = 23.0`, `EXPECTED_CTC_LPA = 30.0`, `NOTICE_PERIOD_DAYS = 15` (`src/patterns/input_type_sanitizer.py:34-47`) and calls itself the "single source of truth for derived fallbacks". The same values are re-declared in `src/sentinel/llm_client.py:36-200` (`get_candidate_facts()`), `src/sentinel/prompts.py:73-155`, `src/sentinel/agent.py` (hundreds of literals: "23 LPA" ×17, "30 LPA" ×12, "4.2 Years" ×11, "15 days" ×27, "Serving Notice" ×19), `src/sentinel/question_classifier.py`, `src/patterns/pattern_matcher.py`, and `config/qa_patterns.json`. `src/core/profile_store.py` — the intended authority — is consulted in only two places (`agent.py:310`, `agent.py:7849`) plus one JS injection (`agent.py:448`).
- Files: `src/core/profile_store.py`, `src/patterns/input_type_sanitizer.py`, `src/sentinel/llm_client.py`, `src/sentinel/prompts.py`, `src/sentinel/agent.py`, `config/qa_patterns.json`
- Impact: updating CTC/notice period requires edits in 7+ places; missing one produces contradictory answers within the same application. Worse, `profiles/` is gitignored, so a fresh clone silently falls back to the hardcoded values (`agent.py:308-314` logs a warning and sets `_profile_store = None`).
- Fix approach: make `ProfileStore` mandatory at startup (fail fast), render `get_candidate_facts()` and the JS profile from it, and delete the duplicate constants. Any remaining literal should be a `{{template}}` resolved at answer time.

**`config/qa_patterns.json` is 74 MB of mostly machine-generated patterns with no schema:**
- Issue: 67,022 pattern groups / 224,791 variants, 74 MB on disk, ~368 MB parsed. 56,104 groups (84%) are combinatoric expansions of `scripts/taxonomy_data.py` × `scripts/generate_50k_patterns.py` (`exp_*` 11,910, `skill_*` 11,297, `rate_*` 10,967, `arch_*` 10,965, `test_*` 10,965). The distribution is pathological: 12,270 groups share the default `"4.2 Years"`, 10,969 share `"5"`, and 24,097 group defaults are long sentences starting with `"Yes,"`. `validate_patterns()` (`src/patterns/pattern_loader.py:75-114`) checks only presence of `patterns`, `category`, `default` — no types, no enum check, no duplicate detection.
- Files: `config/qa_patterns.json`, `src/patterns/pattern_loader.py:31-114`, `scripts/taxonomy_data.py`, `scripts/generate_50k_patterns.py`
- Impact: the 52k `skills` group dominates every fuzzy tier and steals matches (measured: "how do you approach performance tuning of a jvm in production at scale" → `"4+ years of professional full-stack software engineering experience…"`, confidence 0.98). Every edit rewrites a 74 MB blob in git. A malformed write is only caught at import by `json.JSONDecodeError`.
- Fix approach: split by category (`config/patterns/*.json`), keep generated combinatorics out of the hand-curated corpus (generate at runtime from taxonomy instead of storing), add a JSON Schema plus a `python -m scripts.validate_corpus` pre-commit step.

**Fourteen one-off mutation scripts rewrite the 74 MB corpus, most without atomic writes:**
- Issue: `scripts/apply_csv_pattern_fixes*.py`, `apply_audit_fixes_nov.py`, `apply_qa_audit_fixes_nov07.py`, `apply_patterns_and_location_fixes_oct29.py`, `audit_*.py`, `fix_*.py`, `repair_*.py` (25 files in `scripts/`). Only `repair_input_type_defaults.py`, `repair_pattern_overlap_edgecases.py`, `repair_qa_patterns.py` and `repair_pii_leaks.py` use a temp-file/backup pattern; the `apply_*` family does not.
- Files: `scripts/apply_*.py`, `scripts/audit_*.py`, `scripts/fix_pattern_overlaps.py`
- Impact: a crash mid-write truncates `config/qa_patterns.json`; one stale backup (`config/qa_patterns.json.bak-20261110-121219`, 74 MB) already sits in `config/`.
- Fix approach: consolidate into a single `scripts/corpus_cli.py` with `validate → backup → apply → re-validate` and a schema check in the loop.

**Production code imports a dev script:**
- Issue: `src/sentinel/agent.py:361` does `from scripts.taxonomy_data import TECHNOLOGIES, FEATURES` inside `_get_patterns_for_js()`. `scripts/` has no `__init__.py`, is not a package, and is not installed; it resolves only because `run.py:13` and `cli.py:26` mutate `sys.path`.
- Files: `src/sentinel/agent.py:361`, `scripts/taxonomy_data.py`, `src/sentinel/run.py:13`
- Impact: breaks when `agent.py` is imported from another working directory or installed as a package; silently swallowed by `except Exception: pass` at `agent.py:370`, which then injects **all** 67k patterns (157 MB payload) instead of skipping synthetic ones (11.4 MB).
- Fix approach: move `taxonomy_data` under `src/patterns/taxonomy.py`; the skip-set generation belongs with the corpus, not with runtime JS injection.

**All output paths are hardcoded to a macOS Desktop:**
- Issue: `agent.py:191-198` (`SCREENSHOT_DIR`, `UNKNOWN_QUESTIONS_LOG`, `ALL_QUESTIONS_LOG`, `METRICS_LOG`, `QA_RESULTS_CSV`), `src/sentinel/cli.py:35` (`Path.home()/"Desktop"/"sentinel_errors"`), `src/sentinel/self_healing.py:75`, `:152`, `:426-429`, `src/sentinel/question_fingerprint.py:521`. `src/sentinel/ui_error_detector.py:83` stores a literal unexpanded `"~/Desktop/sentinel_errors"` (and the attribute is never read — dead code).
- Files: `src/sentinel/agent.py:191-198`, `src/sentinel/cli.py:35`, `src/sentinel/self_healing.py:75`, `src/sentinel/question_fingerprint.py:521`, `src/sentinel/ui_error_detector.py:83`
- Impact: AGENTS.md documents a Raspberry Pi / Linux target, where `~/Desktop` does not exist. `_log_qa_result` would `os.makedirs("~/Desktop/...")` into `$HOME` and silently fail through its `except Exception` (`agent.py:3615-3616`), losing the audit trail that the whole Q&A pipeline is validated against.
- Fix approach: one `SENTINEL_DATA_DIR` env var (default `~/.local/state/sentinel`), resolved once in `src/core/config.py`; `tests/unit/sentinel/test_qa_csv_coverage.py` already monkeypatches `SCREENSHOT_DIR`, so the seam exists.

**Config loading is a hand-rolled `.env` parser with machine-specific defaults:**
- Issue: `src/core/config.py:3-13` splits on the first `=`, strips quotes, and ignores `export ` prefixes, inline comments, and multi-line values. Defaults are absolute paths to the author's machine: `/Users/siddhant/Library/Application Support/Google/Chrome` (`config.py:16`), `/Applications/Google Chrome.app/...` (`config.py:17`), `/Users/siddhant/Desktop/Resume/SiddhantSinghResume2026.pdf` (`config.py:45`, repeated at `agent.py:247`). There is no `.env.example`.
- Files: `src/core/config.py`, `src/sentinel/agent.py:247`
- Impact: values with `#` or spaces are silently truncated; a key written as `export KEY=...` is dropped and the LLM silently disables itself; on Linux the browser launch fails with a confusing missing-binary error.
- Fix approach: use `python-dotenv`, require the four variables with explicit errors, and check in `.env.example` with variable names only.

**No CI, no packaging, no lockfile:**
- Issue: no `.github/`, `.gitlab-ci.yml`, `pyproject.toml`, `setup.py`, `Makefile`, or `tox.ini`. `requirements.txt` contains four `>=` constraints and no lock; `requirements-dev.txt` adds test tooling. `./sentinel` claims `pip install -e .` in its docstring but there is nothing to install.
- Files: `requirements.txt`, `requirements-dev.txt`, `sentinel`, `pytest.ini`
- Impact: the test suite is currently **red** (3 failures) and nobody is notified; dependency drift is unchecked; the tool can only be run from the repo root.
- Fix approach: add a GitHub Actions job (`pytest -m "not slow"`, coverage floor for `src/patterns`), a `pyproject.toml` with a console-script entry point, and pin exact versions.

**Logging is `print()` with emoji:**
- Issue: 498 `print(` calls in `src/sentinel/agent.py`, 247 containing ⚠️/✅/❌. Exactly one `logging.getLogger` in the whole `src/` tree (`src/sentinel/llm_client.py:24`).
- Files: `src/sentinel/agent.py`, all of `src/sentinel/`
- Impact: no levels, no timestamps, no rotation, no way to filter; the infinite loop's stdout is the only record and it is not captured anywhere durable.
- Fix approach: module-level `logging` with a rotating file handler under `SENTINEL_DATA_DIR`; keep the emoji output only behind `SENTINEL_CONSOLE=1`.

**Docs and line anchors have drifted by thousands of lines:**
- Issue: AGENTS.md cites `_fuzzy_match_question` at `agent.py:434` (actual 1152), `_log_qa_result` at 3441 (actual 3562), `_handle_scripted_fallback` at 8362 (actual 15421), `_answer_instahyre_questionnaire` at 5303 (actual 11215), `_handle_chatbot_loop` at 6410 (actual 12356), `_hirist_fill_questionnaire` at 10298 (actual 10798). `INDEED_HIRIST_FIXES.md:7` states "All changes are currently uncommitted on `master`". `IMPLEMENTATION_SUMMARY.md` describes a two-tier system that is now five-tier.
- Files: `AGENTS.md`, `IMPLEMENTATION_SUMMARY.md`, `INDEED_HIRIST_FIXES.md`
- Impact: a mapper/agent following AGENTS.md navigates to the wrong place every time; the pitfall list remains accurate while the anchors do not.
- Fix approach: reference symbols (`SentinelAgent._log_qa_result`) not line numbers; regenerate the file map as part of the release checklist.

**Committed process scaffolding and stale artifacts:**
- Issue: `.agents/` is tracked with 99 files / 4,704 lines of agent briefs and handoffs (`.agents/orchestrator_1/plan.md`, `.agents/auditor_1/handoff.md`, …), `.opencode/plans/` holds two draft plans, and two Naukri screenshots are tracked (`live_test_output_naukri/screenshots/20261030_142746_initial_load.png`, `20261030_142816_final_state.png`) despite `live_test_output_naukri/` being in `.gitignore:38`.
- Files: `.agents/**`, `.opencode/plans/**`, `live_test_output_naukri/screenshots/*.png`
- Impact: 552 KB of transient working notes in the source tree; screenshots of a logged-in job board are permanently in history.
- Fix approach: `git rm -r --cached .agents .opencode/plans live_test_output_naukri`, add to `.gitignore`, keep handoffs in an untracked scratch dir.

## Known Bugs

**The test suite is red at HEAD (3 failures, 1,460 passing):**
- Symptoms / reproductions:
  - `tests/unit/test_experience_radio_qa_enhancements.py::TestExperienceRadioAndQAEnhancements::test_skill_intent_resolution` — `fuzzy_match("Do you have experience in React?")` returns `"Yes, extensive hands-on experience in production environments."` instead of `"Yes"`. Reproduced for React, Angular, Spring Boot, Docker, AWS, Kafka, Python, Java.
  - `tests/unit/qa/test_qa_updates.py::TestNewPatternsReliability::test_azure_experience` — `"Do you have azure cloud experience? if yes how many years?"` returns the same sentence instead of `"4"`.
  - `tests/unit/qa/test_qa_csv_fixes_oct27.py::TestQACSVFixesOct27::test_experience_req_4_to_9_years` — `"• 4-9 years of experience in full stack, frontend, or backend software development."` returns the tech-stack list (`"Java, Spring Boot, Node.js, …"`) instead of `"Yes"`.
- Root cause: `src/patterns/pattern_matcher.py:404-406` — after the exact-match tier resolves `tech_specific_experience` (default `4.2`), the intent resolver rewrites it for non-radio controls to a fixed 60-word sentence. This is the same code path the AGENTS.md pitfall #9 fix introduced.
- Files: `src/patterns/pattern_matcher.py:395-406`, `config/qa_patterns.json` (`tech_specific_experience`)
- Trigger: any "Do you have … experience?" phrasing on a text control, or any call without `input_type` (which is every Python-side call).
- Workaround: pass `input_type="radio"`/`"checkbox"` — but `_fuzzy_match_question` never does.

**Confidence scores are meaningless for match quality:**
- Symptoms: `_tier1_match` returns `0.98` whenever `AnswerValidator.validate()` accepts the answer, regardless of how little of the question matched (`pattern_matcher.py:1039-1043`, `:1077-1081`). Reproduced:
  - `"how do you approach performance tuning of a jvm in production at scale"` → `"4+ years of professional full-stack software engineering experience…"`, conf `0.98`
  - `"what would you do if a customer escalation arrives mid sprint"` → `"Yes, worked in Agile/Scrum environments for 3+ years"`, conf `0.98`
- Files: `src/patterns/pattern_matcher.py:1019-1081`
- Trigger: any question sharing a single keyword with a broad substring pattern.
- Workaround: none at runtime; `_resolve_question_intent` is the only guard and it misses these phrasings.

**LLM answers are stamped with confidence 0.95 unconditionally:**
- Symptoms: `agent.py:10965` sets `answer, conf = llm_ans, 0.95` regardless of model agreement, finish reason, or length. `qa_results.csv` therefore records a hallucination exactly like a deterministic pattern hit.
- Files: `src/sentinel/agent.py:10965`, `src/sentinel/agent.py:3562`
- Trigger: any Hirist/Instahyre/Indeed textarea where the pattern confidence is `< 0.65` or the prompt looks like an essay.
- Workaround: query the CSV by `source='llm_gemma'` rather than by confidence.

**CSV dedupe silently drops legitimate duplicate controls:**
- Symptoms: `_log_qa_entries` builds `dedupe_key = (question[:160].lower(), answer[:160].lower(), input_type, status)` (`agent.py:3672-3673`) and skips the row if seen. Two identical labels in one application (common on LinkedIn multi-skill sections) produce a single CSV row.
- Files: `src/sentinel/agent.py:3624-3693`
- Trigger: repeated identical question text within one `_current_job_url`.
- Workaround: none; the dropped control is invisible after the fact.

**INR normalisation concatenates unrelated digit groups:**
- Symptoms: `_validate_and_retry` does `fixed_answer = ''.join(re.findall(r'\d+', answer.replace(',', '')))` for `salary_inr` (`agent.py:3171`). `"23 LPA (2.3M)"` becomes `"2323"`; `"CTC 23,00,000 + 1,00,000 bonus"` becomes `"2300000100000"`.
- Files: `src/sentinel/agent.py:3119-3200`
- Trigger: any answer containing more than one numeric token on an INR-formatted field.
- Workaround: none.

**Task dispatch is substring matching on the prompt text:**
- Symptoms: routing checks like `'inbox' in task_desc_lower or 'inbox' in current_url` (`agent.py:4639-4648`), `'profile' in current_url and 'employment' in task_desc_lower` (`agent.py:4672`), `'early access' in task_desc_lower` (`agent.py:4679`). A new prompt that mentions "inbox" or "profile" anywhere is routed to the wrong handler.
- Files: `src/sentinel/agent.py:4639-4683`, `src/sentinel/agent.py:6330-6346` (duplicated dispatch block)
- Trigger: editing any string in `src/sentinel/prompts.py`.
- Workaround: none; add keywords only and hope for no collision.

**Rendered JS failures are swallowed:**
- Symptoms: 391 `except` clauses in `src/`, **162 of which are body-`pass`**; plus 6 bare `except:` (`run.py:271`, `agent.py:635`, `:685`, `:3198`, `:4992`, `:6354`). Page-provided scripts return `NO_ACTION`/`SCRIPT_ERROR` strings, and a thrown selector error is indistinguishable from "nothing to do".
- Files: `src/sentinel/agent.py`, `src/sentinel/run.py`
- Trigger: any site DOM change.
- Workaround: `SENTINEL_JS_DEBUG=1` surfaces page-side logs only.

## Security Considerations

**Chrome session data is committed to git and reachable from `origin/main`:**
- Risk: `p/Default/Cookies`, `p/Default/History`, `p/Default/Default/Cookies`, `p/Default/Login Data` and ~3,075 objects under `p/` are in the history (commits `c5981c0`, `e45f5e0` and earlier are ancestors of `origin/main`). Cookies for LinkedIn/Naukri/Instahyre are session credentials — anyone with repo access can replay them. The remote is `https://github.com/siddhant3646/A_N-L-copy.git`.
- Files: `p/**` (deleted in `e45f5e0`, still in history), `.gitignore:6-8`
- Current mitigation: `p/` and `profiles/` are now ignored (`e45f5e0` "exclude Chrome profile directory from git").
- Recommendations: treat all platform sessions as compromised — log out everywhere and rotate passwords; run `git filter-repo --path p/ --invert-paths` and force-push; verify the GitHub repo visibility; enable secret scanning.

**A committed `.env` is still reachable through a leftover filter-branch backup ref:**
- Risk: the root commit `ba51a76` ("first commit") added `.env` (9 lines) and is not in `main`, but it is reachable via `refs/original/refs/heads/main` — the backup ref `git filter-branch` leaves behind. A `git push --all` or `git push --mirror` re-publishes the API key. Five additional commits match `AIza`-prefixed key material in a history-wide pickaxe search.
- Files: `refs/original/refs/heads/main` → `ba51a76`; `.gitignore:87`
- Current mitigation: `.env` is untracked and ignored in the working tree; the file exists locally with mode `0644` (world-readable).
- Recommendations: `git update-ref -d refs/original/refs/heads/main`, expire reflogs, `git gc --prune=now`; **rotate the Google AI key**; `chmod 600 .env`.

**The Google AI key is sent in a URL query string and partially echoed in logs:**
- Risk: `src/sentinel/llm_client.py:386`, `:484`, `:767` build `...?key={active_key}`. Query strings land in proxy logs, `aiohttp` debug logs, and crash reports. `rotate_to_next_key` prints the last six characters of both keys (`llm_client.py:252`).
- Files: `src/sentinel/llm_client.py:241-252, 386, 484, 767`
- Current mitigation: none.
- Recommendations: send `x-goog-api-key` as a header; log a key fingerprint (first 4 + last 4 of a hash), never key material.

**Full candidate PII is sent to Google on every LLM call and is hardcoded in tracked files:**
- Risk: `get_candidate_facts()` (`src/sentinel/llm_client.py:36-200`) embeds name, email, phone, city, CTC, CGPA, and a passport-availability statement, and `_build_prompt` (`llm_client.py:507-535`) prepends the whole factsheet to **every** question. The same data is hardcoded in `src/sentinel/prompts.py:108-109`, `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py`, `src/sentinel/question_classifier.py`, `src/patterns/input_type_sanitizer.py:34-47`, and `config/qa_patterns.json` (20 email, 51 phone, 10 DOB occurrences). Tests hardcode it too (email in 6 files, phone in 18), as does `.agents/auditor_1/handoff.md` and `AGENTS.md:84-104`.
- Files: `src/sentinel/llm_client.py:36-200`, `src/sentinel/prompts.py:108-109`, `config/qa_patterns.json`, `AGENTS.md:82-104`, `.agents/auditor_1/handoff.md`
- Current mitigation: 44 patterns are flagged `"sensitive": true` and 65 have `"requires_exact_match": true`; `scripts/repair_pii_leaks.py` exists to rewrite PII that leaked into derived `number`/`tel` defaults (its docstring names `aadhaar_number`, `personal_aadhaar_number`, `personal_emergency_contact`, `ref_reference_phone`).
- Recommendations: send a redacted factsheet (no email/phone/IDs) and let the model answer structurally; move all PII into `profiles/resume.json`; add a pre-commit grep for the email/phone; scrub `config/qa_patterns.json` and `AGENTS.md`.

**Process-level kills reach beyond this app:**
- Risk: `run.py:842` runs `pkill -f 'Google Chrome.*--enable-automation'`, killing every Chrome automation session on the machine, and `run.py:654-690` `pgrep`/`SIGKILL`s by path substring. `agent.py:8713` shells out to `afplay /System/Library/Sounds/Glass.aiff`, which does not exist off macOS.
- Files: `src/sentinel/run.py:619-690, 842`, `src/sentinel/agent.py:8713`
- Current mitigation: PID-marker scoping for the profile dir, best-effort `try/except`.
- Recommendations: track the spawned PID from Playwright and terminate only that process tree; gate the sound on `sys.platform == "darwin"`.

**Automation targets are ToS-restricted:**
- Risk: LinkedIn, Naukri, Instahyre and Hirist all prohibit automated form submission. Account restriction is the likely failure mode, and the code deliberately mimics human behaviour (`src/sentinel/human_behavior.py`, `src/sentinel/rate_limiter.py`) to avoid detection.
- Files: `src/sentinel/human_behavior.py`, `src/sentinel/rate_limiter.py`, `src/sentinel/agent.py`
- Recommendations: treat as accepted risk, cap daily volume, and keep a manual-review queue; do not increase concurrency.

## Performance Bottlenecks

**Agent construction loads and indexes 368 MB of JSON:**
- Problem: `SentinelAgent.__init__` calls `create_matcher()` (parses 74 MB, builds a 67k index: measured 0.23 s parse + 1.64 s index) and then `FingerprintMatcher.build_from_patterns()` over all 224k variants (1.5 s, 207k fingerprints). Measured resident memory after both indexes: **660 MB**.
- Files: `src/sentinel/agent.py:293-305`, `src/patterns/pattern_loader.py:27-72`, `src/patterns/pattern_matcher.py:46-75`, `src/sentinel/question_fingerprint.py:973-996`
- Cause: every layer keeps its own full copy of the corpus (raw dict, normalized pattern cache, owner index, fingerprint cache, exact-question cache).
- Improvement path: one shared index built once per process; precompute a serialized index (msgpack/`sqlite`) at build time instead of re-normalising 224k strings on startup.

**An 11.4 MB JSON payload is injected into every page:**
- Problem: `_inject_patterns_once` (`agent.py:419-500+`) serialises `compact_groups` and evaluates it as a single JS expression. Measured with synthetic patterns excluded: 12,196 groups → **11.4 MB** of JSON (all 67k groups would be 157 MB).
- Files: `src/sentinel/agent.py:419-500`, `src/sentinel/agent.py:341-417`
- Cause: the corpus is shipped to the browser verbatim on every context.
- Improvement path: ship only the ~12k hand-curated groups (already the intent) and gzip/base64 the payload; or answer in Python and send one answer per field.

**Unanswered questions cost 0.2 s + 0.2 s in linear scans:**
- Problem: `PatternMatcher._tier3_match` loops all 224k normalised patterns with `SequenceMatcher` (`pattern_matcher.py:1125-1159`, measured 0.20 s per miss), and `FingerprintMatcher.match` scans 207k fingerprints (`question_fingerprint.py:938-971`, measured 0.18 s per miss). Both run before the LLM is consulted.
- Files: `src/patterns/pattern_matcher.py:1125-1159`, `src/sentinel/question_fingerprint.py:921-971`
- Cause: no inverted index for tier 3 and no index at all for the fingerprint matcher.
- Improvement path: bucket fingerprints by first token / length, and cap tier 3 to the detected categories.

**The CSV is opened and closed once per row:**
- Problem: `_log_qa_result` does `open(..., "a")` + `csv.DictWriter` per answer (`agent.py:3607-3613`), plus `os.makedirs` and `os.path.exists` per call.
- Files: `src/sentinel/agent.py:3562-3620`
- Improvement path: keep one handle per task and flush on task end; the file has no rotation and grows unbounded across an infinite loop.

**`get_all_matches` is O(224k) `SequenceMatcher` calls per question** (`pattern_matcher.py:1248-1291`) — diagnostic/test-only today, but any future "show me alternatives" UI would inherit it.

**Repository bloat slows every git operation:**
- Problem: `.git` is **476 MB**, pack 415 MB, driven by 74 MB corpus revisions; a `git log -p` on `config/qa_patterns.json` is effectively unusable.
- Files: `config/qa_patterns.json`
- Improvement path: `git filter-repo` to drop historical corpus blobs, then store the corpus via Git LFS or generate it.

## Fragile Areas

**`_handle_scripted_fallback` and its page-side protocol:**
- Files: `src/sentinel/agent.py:15421-26034`
- Why fragile: 10,614 lines emitted as one `page.evaluate` string; results travel by three channels (`formResults`/`genericResults` return values, a `MARKER|JSON` string, and `window.__SENTINEL_QA_LOG__` drained separately). `attachQaLog` only wraps two arrays (`agent.py:17604`, `:25765`) while 79 `Results.push(` calls exist — any array created later loses its mirror. Early returns (`LINKEDIN_FORM_STUCK`, `LINKEDIN_INVALID_CARD_REMOVED`) bypass the return-channel entirely.
- Safe modification: keep the drain call (`agent.py:26020`) before every early return; add a test that asserts every `Results =` in the JS is wrapped.
- Test coverage: none executes this JS; tests call `inspect.getsource` and `assertIn` on selectors (e.g. `tests/unit/platforms/test_linkedin_stuck_modal.py:53-61`).

**LinkedIn/Naukri DOM selectors:**
- Files: `src/sentinel/agent.py` (170 `page.evaluate` calls, hundreds of literal selectors), e.g. `chatbot_DrawerContentWrapper`, `.artdeco-modal`, `.jobs-easy-apply-form-section__question`
- Why fragile: any class rename by the platform breaks a step silently (`except: pass`), and Shadow DOM requires `queryDeep`/`queryAllDeep` which `querySelector` cannot follow (AGENTS.md lesson #4).
- Safe modification: add new selectors alongside old ones; never replace a selector without a live run.
- Test coverage: mocked `page.evaluate` only.

**Hardcoded job-search URLs:**
- Files: `src/sentinel/run.py:770-788` (notably the LinkedIn URL at `run.py:782`, which embeds `currentJobId=4475096962` and a `referralSearchId=fh2mUpxEErxKDOF…` tracking token)
- Why fragile: stale job IDs and referral tokens expire; the URL is the task's entry point, so a dead link fails navigation and skips the task.
- Safe modification: keep search filters in a config constant, drop `currentJobId`/`referralSearchId`.

**Manual state-reset contract:**
- Files: `src/sentinel/agent.py:503-545` (`reset_per_task_state`)
- Why fragile: it must list every mutable attribute set in `__init__` (`agent.py:236-330`); 40+ attributes, no test asserts parity. A newly added counter that is not reset leaks across the 8-task cycle (this is exactly the `_injected_contexts` bug the docstring describes).
- Safe modification: group per-task state in a dataclass and replace the instance wholesale.

**Corpus caching returns shared mutable objects:**
- Files: `src/patterns/pattern_loader.py:27-72` (`_LOAD_CACHE`), `src/patterns/pattern_matcher.py:46-75` (`_INDEX_CACHE`, limit 3)
- Why fragile: `load_patterns` returns the *same dict* to every caller and only documents "treat as read-only"; one `update_patterns()` or in-place edit mutates every matcher in the process. `_INDEX_CACHE` holds strong references to up to three corpora — worst case 3 × 368 MB.
- Safe modification: never mutate the loaded dict; use `update_patterns()` which rebuilds indexes.

**`_fuzzy_match_question` ordering constraints:**
- Files: `src/sentinel/agent.py:1152-3119` (yes/no proficiency at `:2650` and again at `:2711`, rating at `:2718`, salary at `:2882`, experience at `:2968`)
- Why fragile: the yes/no branch is duplicated, and the ordering rule ("yes/no before rating") is enforced only by position. Any refactor that sorts branches breaks production behaviour with no test naming the rule.
- Safe modification: add a regression test per priority pair before touching the order; the existing `tests/unit/qa/` suite is the only guard.

**`except Exception: pass` on the recovery paths:**
- Files: 162 sites across `src/`, concentrated in `agent.py`
- Why fragile: recovery is best-effort on top of best-effort; when a form is stuck there is no record of which step failed, only the final `LINKEDIN_FORM_STUCK`.

## Scaling Limits

**Page payload:**
- Current capacity: an 11.4 MB JSON payload per page context, re-injected on every navigation; multiple navigations per task.
- Limit: Chrome CDP message limits and page heap; `_maybe_cleanup_memory` (`agent.py:3947-3958`) only calls `console.clear()`, so page memory is reclaimed solely by the between-task `browser.stop()`.
- Scaling path: shrink the payload (curated-only groups) or move matching back to Python.

**Run duration / state growth:**
- Current capacity: 8 tasks per cycle (`run.py:770-788`), 120 steps per task (`agent.py:187-189`), 15-20 min cooldown per cycle (`run.py:997`), unlimited cycles.
- Limit: `_linkedin_skipped_job_ids`, `_linkedin_skipped_job_titles`, `_processed_questionnaires`, `_qa_logged_keys` grow within a task; `SuccessTracker` is capped at 20,000 entries (`question_fingerprint.py:508-513`) with FIFO pruning; `qa_results.csv` has no rotation.
- Scaling path: persist skipped IDs with a TTL, rotate the CSV daily, and add a max-cycle/max-duration guard to the loop.

**Memory:**
- Current capacity: 660 MB of indexes plus a Playwright/Chrome process per task (`run.py:893-899` creates a fresh `Browser` per task).
- Limit: a Raspberry Pi (documented target) has 2-8 GB total; 660 MB of Python indexes plus Chrome will not fit comfortably.
- Scaling path: build the index once and share it across the process (already attempted via `_INDEX_CACHE`), or move matching to a small SQLite FTS index.

**Git:**
- Current capacity: 476 MB `.git`, 415 MB pack, 15,405 objects.
- Limit: cloning takes minutes; every corpus edit adds ~74 MB (compressed less, but still large).
- Scaling path: LFS or a generated corpus.

## Dependencies at Risk

**Playwright (`>=1.60.0`, unpinned):**
- Risk: the entire product is selector-coupled to three websites; a Playwright minor bump changes waiting semantics, and a site redesign breaks selectors.
- Impact: all form filling stops.
- Migration plan: pin an exact version and add a smoke test that launches Chromium against a fixture page.

**Google AI Studio models (`DEFAULT_GEMMA_MODELS`, `llm_client.py:27-34`):**
- Risk: the fallback chain lists models that do not appear to exist (`gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it`) alongside real ones (`gemma-3-27b-it`). Every nonexistent model costs a 404 round-trip before failover; `verify_and_select_model` (`llm_client.py:367`) can also pin a bad name.
- Impact: slow, quota-burning LLM paths that silently degrade to pattern answers.
- Migration plan: discover models at startup and build the chain from `models.list` only; delete the hardcoded list.

**`aiohttp` (optional import):**
- Risk: `llm_client.py:17-20` degrades to `urllib` in a thread when `aiohttp` is missing; the fallback path (`llm_client.py:303-350`) has different timeout/error semantics.
- Impact: two code paths for the same HTTP call; only one is exercised in CI.
- Migration plan: make `aiohttp` a hard requirement (it already is in `requirements.txt`).

**No lockfile / `>=` constraints:**
- Risk: `requirements.txt` has four `>=` pins and `requirements-dev.txt` five; a fresh install can pull a breaking major.
- Impact: "works on my machine" between the dev Mac and the Pi.
- Migration plan: `pip-compile` to a `requirements.lock`.

**`node` is an undeclared test dependency:**
- Risk: `tests/unit/qa/test_js_experience_ranges.py:56` shells out to `node -e` with no `shutil.which` guard.
- Impact: suite errors on any machine without Node, which is not documented in `requirements-dev.txt` or AGENTS.md.
- Migration plan: `pytest.importorskip`/`pytest.mark.skipif(shutil.which("node") is None)`.

## Missing Critical Features

**No CI or coverage gate:**
- Problem: nothing runs the suite automatically; it is red today.
- Blocks: safe refactors of `pattern_matcher.py` and `agent.py`; any regression that only the tests would catch.

**No pattern provenance in the audit trail:**
- Problem: `QA_RESULTS_COLUMNS` (`agent.py:199-204`) records `confidence` and `source` but not the matched `pattern_id`, the tier, or the question category. `match_with_details` (`pattern_matcher.py:1239-1247`) also omits the id.
- Blocks: root-causing a wrong answer from `qa_results.csv` alone — you must re-run the matcher and hope the corpus hasn't changed.

**No corpus schema or migration tooling:**
- Problem: `validate_patterns` checks three keys; there is no schema version bump path beyond the `"version": "3.0"` string.
- Blocks: safe bulk edits; any script can write a pattern with `default: null`.

**No dry-run / offline mode:**
- Problem: verifying a pattern change requires a live logged-in browser (`scripts/run_live_*_only.py`).
- Blocks: testing a fix without risking a real application.

**No single-instance lock:**
- Problem: two `python src/sentinel/run.py` processes share the same Chrome profile and append to the same CSV with no locking (`agent.py:3607-3613`).
- Blocks: reliable concurrent use; risks CSV interleaving and profile corruption.

**No `.env.example` and no secrets management:**
- Problem: the four required variables are documented only in AGENTS.md; a fresh clone cannot start without guessing.
- Blocks: onboarding, and any move to a second machine.

## Test Coverage Gaps

Measured at HEAD with `.venv/bin/python -m pytest --cov=src` (235 s, 1,460 passed / 3 failed):

```
TOTAL                       11507   5687    51%
src/sentinel/agent.py        6054   3491    42%
src/sentinel/run.py           666    618     7%
src/sentinel/cli.py           152    152     0%
src/patterns/enhanced_answer_validator.py 111  89   20%
src/sentinel/self_healing.py  240    167    30%
src/sentinel/question_classifier.py 273 162   41%
src/sentinel/ui_error_detector.py 236 134    43%
src/patterns/pattern_matcher.py 793   112    86%
src/patterns/input_type_sanitizer.py 1183 300  75%
```

**The 10,614-line embedded JavaScript is effectively untested:**
- What's not tested: every `page.evaluate` body — LinkedIn form filling, Naukri chatbot, Instahyre ack, Hirist questionnaire selectors.
- Files: `src/sentinel/agent.py:12356-26034`
- Risk: a selector or JS syntax error is discovered only during a live run, on a real application.
- Priority: High.

**`run.py` (the process supervisor) is 7% covered:**
- What's not tested: the infinite loop, temp-dir GC, Chrome sweep, `pkill` logic, per-task browser restart, rate-limit deferral.
- Files: `src/sentinel/run.py:213-1117`
- Risk: a regression here strands or duplicates browser processes and silently skips tasks.
- Priority: High.

**`src/sentinel/cli.py` is 0% covered** — `./sentinel stats|patterns|failures|learn|export` (AGENTS.md "How to Run") is never executed by a test.
- Files: `src/sentinel/cli.py`
- Priority: Medium.

**Ordering rules inside `_fuzzy_match_question` have no dedicated test:**
- What's not tested: the PHASE 1 priority order itself (yes/no before rating, salary before experience, notice before location). The existing QA tests assert individual answers, not the relative ordering.
- Files: `src/sentinel/agent.py:1152-3119`
- Risk: a reorder silently flips answers in production; this is the exact class of bug AGENTS.md pitfall #1 describes.
- Priority: High.

**The Python and JS paths are never compared:**
- What's not tested: that `agent._fuzzy_match_question(q)` and the injected JS `fuzzyMatch(q)` return the same answer for the same input and control type.
- Files: `src/sentinel/agent.py:1152`, `src/sentinel/agent.py:12398`, `:15748`
- Risk: platform-dependent answer drift is invisible until it reaches a form (already observed: `input_type` is dropped at `agent.py:3091`).
- Priority: High.

**Tests encode the current profile values and will all break on a profile change:**
- What's not tested / at risk: `"4.2 Years"` appears in 64 test files, `"2300000"` in 40, the phone number in 18, the email in 6.
- Files: `tests/unit/qa/**`, `tests/unit/platforms/**`
- Risk: the candidate is serving notice with an LWD computed from "today + 15 days"; updating CTC or notice period after joining a new role breaks dozens of assertions at once, and the failures will look like logic bugs.
- Priority: Medium (plan the change; move expected values to `tests/conftest.py` fixtures derived from `ProfileStore`).

**Test organisation obscures what is covered:**
- What's not tested: unclear — 31 of 51 files in `tests/unit/qa/` are named by fix date (`test_qa_csv_fixes_oct27.py`, `test_qa_aug25_fixes.py`, …), so coverage is organised by incident rather than behaviour.
- Files: `tests/unit/qa/`
- Risk: nobody can tell whether a given rule is still guarded; duplicates accumulate.
- Priority: Medium.

---

*Concerns audit: 2026-11-11*
