---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# External Integrations

**Analysis Date:** 2026-11-11

## APIs & External Services

**AI / LLM:**
- **Google AI Studio - Generative Language API (`v1beta`)** - answers open-ended questionnaire questions and transcribes Indeed reCAPTCHA audio challenges.
  - SDK/Client: custom `GemmaLLMClient` in `src/sentinel/llm_client.py` using `aiohttp` with a `urllib.request` fallback (`src/sentinel/llm_client.py:272-366`)
  - Base URL: `https://generativelanguage.googleapis.com/v1beta` (`src/sentinel/llm_client.py:213`)
  - Endpoints:
    - `GET /models?key=...` for model discovery, filtered to models supporting `generateContent` (`src/sentinel/llm_client.py:386`)
    - `POST /models/{model}:generateContent?key=...` for answers (`src/sentinel/llm_client.py:767`)
    - `POST /models/gemini-3.5-transcribe:generateContent?key=...` for audio transcription (`src/sentinel/llm_client.py:484`)
  - Auth: API key(s) passed as the `key` query parameter. Keys come from `GOOGLE_AI_API_KEYS` (comma-separated pool) and/or `GOOGLE_AI_API_KEY` (`src/core/config.py:22-42`).
  - Model preference order (discovery, `src/sentinel/llm_client.py:404-440`): `gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3-flash-preview`, other Gemini Flash models, `gemma-4-26b-a4b-it`, `gemma-4-31b-it`, then other Gemma models. Static fallback list at `src/sentinel/llm_client.py:27-34` also includes `gemma-3-27b-it`.
  - Request shape: `contents[0].parts[0].text` with `generationConfig` temperature `0.1`, `maxOutputTokens` `16000`, `topK` `20`, `topP` `0.8` (`src/sentinel/llm_client.py:744-756`)
  - Failure behavior: fail-open - returns `None` so pattern matching continues; rotates to the next API key on `429`, `403`, `5xx`, timeout, or exception, and advances to the next fallback model on `400`/`404` (`src/sentinel/llm_client.py:760-838`)
  - Call sites: Indeed questions `src/sentinel/agent.py:9443`; Hirist questionnaire `src/sentinel/agent.py:10834` and `:10961` (LLM budget of 12 in `_hirist_fill_questionnaire`, `src/sentinel/agent.py:10801`); Instahyre questionnaire `src/sentinel/agent.py:11373`; Indeed reCAPTCHA audio `src/sentinel/agent.py:8790`
  - Prompt context is built from a hard-coded candidate factsheet and system persona in `src/sentinel/llm_client.py:36-212` plus `get_candidate_facts()`; no external vector store or retrieval service is involved.

- **Google reCAPTCHA audio challenge (Indeed)** - when Indeed SmartApply presents a reCAPTCHA, `_indeed_solve_audio_challenge()` downloads the challenge audio URL from the page context and sends it to Gemini 3.5 Transcribe (`src/sentinel/agent.py:8742-8810`). This is an outbound browser/HTTP interaction with Google's reCAPTCHA service, not a configured API integration.
  - No reCAPTCHA API key or solver service is configured; the flow relies on the page-provided audio URL and the Google AI key.

**Job marketplaces (browser automation, no official/public API):**
- All platform integrations are UI-level interactions performed by Playwright against the live sites. There are no REST clients, OAuth apps, partner APIs, webhooks, or API credentials for these platforms.
- **LinkedIn** - job search and Easy Apply form filling.
  - URL used by the runner: `https://www.linkedin.com/jobs/search-results/...` (`src/sentinel/run.py:782`)
  - Handler: `_handle_scripted_fallback()` (`src/sentinel/agent.py:15421`), with injected JS patterns and `window.__SENTINEL_PATTERNS__`
  - Capabilities: Easy Apply modal traversal, Shadow DOM controls, radio/select/checkbox/text filling, resume PDF attachment, QA logging
  - Auth: existing LinkedIn session cookies in the Chrome profile
- **Naukri** - recommended jobs, profile updates, early-access jobs, and chatbot-style screening.
  - URLs: `https://www.naukri.com/mnjuser/recommendedjobs`, `https://www.naukri.com/mnjuser/profile?id=&altresid`, `https://www.naukri.com/mnjuser/recommended-earjobs` (`src/sentinel/run.py:781-788`)
  - Handlers: `_handle_chatbot_loop()` (`src/sentinel/agent.py:12356`) plus the scripted form fallback
  - Auth: existing Naukri session cookies in the Chrome profile
- **Instahyre** - matched opportunities, inbox questionnaires, and acknowledgement flows.
  - URLs: `https://www.instahyre.com/candidate/opportunities/?matching=true`, `https://www.instahyre.com/candidate/inbox/` (`src/sentinel/run.py:779-784`)
  - Handler: `_answer_instahyre_questionnaire()` (`src/sentinel/agent.py:11215`); Angular scope manipulation in injected JS
  - Auth: existing Instahyre session cookies in the Chrome profile
- **Hirist** - job feed and application questionnaires.
  - URLs: `https://www.hirist.tech/jobfeed` and category feeds such as `https://www.hirist.tech/k/java-jobs` (`src/sentinel/prompts.py:446-458`); overridable with `HIRIST_FEED_URL` and `HIRIST_FALLBACK_URLS` (`src/sentinel/agent.py:9747-9751`)
  - Handler: `_handle_hirist_apply_task()` (`src/sentinel/agent.py:9731`) and `_hirist_fill_questionnaire()` (`src/sentinel/agent.py:10798`)
  - Auth: existing Hirist session cookies in the Chrome profile
- **Indeed** - search, SmartApply, questionnaire answering, and reCAPTCHA handling.
  - Home/search URLs: `https://in.indeed.com/?from=gnav-jobsearch--indeedmobile` and configurable `INDEED_SEARCH_URL` / `INDEED_SEARCH_QUERY` / `INDEED_SEARCH_LOCATION` (`src/sentinel/agent.py:7814-7848`)
  - Handlers: `_indeed_run_apply_flow()` (`src/sentinel/agent.py:8898`), `_indeed_answer_questions()` (`src/sentinel/agent.py:9352`), `_indeed_solve_recaptcha()` (`src/sentinel/agent.py:8589`)
  - Status: the Indeed task is currently **commented out** of the default task list (`src/sentinel/run.py:776`); the implementation remains in `agent.py` and is exercised by live-test scripts in `scripts/`
  - Auth: existing Indeed session cookies in the Chrome profile

**Local CLI utilities:**
- The `./sentinel` launcher (`sentinel:1-22`) and `src/sentinel/cli.py` read/write local learning data only; they make no network calls.

## Data Storage

**Databases:**
- **None.** No SQL/NoSQL driver, ORM, schema, or migration tooling exists in `src/` or `requirements.txt`. Persistent state is JSON/JSONL/CSV on the local filesystem.

**File Storage:**
- Local filesystem only - no S3, GCS, Azure Blob, Supabase Storage, or database-backed storage.
- Primary runtime output directory: `~/Desktop/sentinel_errors/` (defined at `src/sentinel/agent.py:191-198`)

| Path | Written by | Purpose |
|---|---|---|
| `~/Desktop/sentinel_errors/qa_results.csv` | `SentinelAgent._log_qa_result()` / `_log_qa_entries()` (`src/sentinel/agent.py:3562`, `:3624`) | Consolidated audit of every answered/skipped/prefilled/rejected question across platforms |
| `~/Desktop/sentinel_errors/failure_log.jsonl` | `FailureLogger` (`src/sentinel/self_healing.py:75`) | Failure records with question, attempted answer, input type, platform, URL, error type, fingerprint |
| `~/Desktop/sentinel_errors/learned_patterns.json` | `LearningStore` (`src/sentinel/self_healing.py:152`) | Self-healing learned patterns and option mappings |
| `~/Desktop/sentinel_errors/pattern_stats.json` | `SuccessTracker` (`src/sentinel/question_fingerprint.py:521`) | Fingerprint success-rate statistics |
| `~/Desktop/sentinel_errors/metrics.jsonl` | `SentinelAgent.METRICS_LOG` (`src/sentinel/agent.py:194`) | Per-task metrics (applications, questions answered, errors, duration) |
| `~/Desktop/sentinel_errors/unknown_questions.log` | `SentinelAgent.UNKNOWN_QUESTIONS_LOG` (`src/sentinel/agent.py:192`) | Legacy unknown-question log |
| `~/Desktop/sentinel_errors/all_questions.log` | `SentinelAgent.ALL_QUESTIONS_LOG` (`src/sentinel/agent.py:193`) | Legacy all-questions log |
| `~/Desktop/sentinel_errors/*.png` | `UIErrorDetector` via `SCREENSHOT_DIR` (`src/sentinel/agent.py:191`, `:338`) | Debug screenshots on UI errors |
| `config/qa_patterns.json` | Human/script maintenance (`scripts/import_qa_results.py`, `scripts/repair_qa_patterns.py`) | 77.8 MB Q&A corpus, version 3.0, 67,022 groups, 224,791 variants |
| `profiles/resume.json` | Human-maintained, gitignored | Candidate profile consumed by `ProfileStore` (`src/core/profile_store.py:26-29`) and injected as `window.__SENTINEL_PROFILE__` |
| `live_test_output*/` | Live-test scripts (`scripts/run_live_linkedin_test.py`, `scripts/test_live_*`) | Screenshots and DOM snapshots from manual live runs; gitignored |

- Resume uploads read a local PDF from `RESUME_FILE_PATH` (`src/sentinel/agent.py:249`, `:9240`); nothing is uploaded to a Sentinel-controlled server.

**Caching:**
- None external. Only in-process caches:
  - `_LOAD_CACHE` keyed by file path + `(mtime_ns, size)` in `src/patterns/pattern_loader.py:28-71`
  - `PatternMatcher._INDEX_CACHE` keyed by `id(patterns)` with a 3-entry limit in `src/patterns/pattern_matcher.py:57-85`
  - Session-scoped pytest fixtures in `tests/conftest.py:21-34`
- No Redis, Memcached, CDN cache, or browser cache dependency. Chrome caches are explicitly excluded when copying the profile (`src/sentinel/run.py:287-296`).

## Authentication & Identity

**Auth Provider:**
- **None for the application itself.** There is no login system, user table, OAuth/OIDC flow, JWT issuance, or identity provider.
- Platform identity is inherited from the operator's existing Google Chrome profile. `Browser.start()` mirrors `CHROME_USER_DATA/Default` plus `Local State` into a temp profile and launches `launch_persistent_context` so existing session cookies are reused (`src/sentinel/run.py:250-341`).
  - Implementation detail: caches, lock files, and crash-restore state are excluded/reset; stale `Singleton*`/`lock` files are removed before launch.
  - No credential entry or 2FA handling is implemented.
- Google AI Studio access uses API keys in the query string (`GOOGLE_AI_API_KEYS` / `GOOGLE_AI_API_KEY`), not OAuth.
- Indeed reCAPTCHA is handled opportunistically by the page/browser and the audio-transcription flow; no solver account or token service is configured.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, Rollbar, DataDog, New Relic, OpenTelemetry, or equivalent SDK is installed or configured.

**Logs:**
- Console output via `print()` throughout `src/sentinel/run.py` and `src/sentinel/agent.py` (task progress, route-blocking stats, LLM model/latency lines).
- Python `logging` is used only in `src/sentinel/llm_client.py` (`logger = logging.getLogger(__name__)`); no handlers, formatters, or log-level configuration are defined.
- Browser console messages are forwarded to stdout with noise filters (`_log_js_msg`, `src/sentinel/agent.py:4452-4508`).
- Persistent local logs: `qa_results.csv`, `metrics.jsonl`, `failure_log.jsonl`, `learned_patterns.json`, `pattern_stats.json`, and debug screenshots under `~/Desktop/sentinel_errors/`.
- No log rotation, retention policy, or remote shipping.

## CI/CD & Deployment

**Hosting:**
- Local macOS workstation running an infinite loop (`src/sentinel/run.py:766`), not a hosted service.

**CI Pipeline:**
- None. No `.github/workflows`, `.gitlab-ci.yml`, Jenkinsfile, CircleCI, or equivalent config was found.

**Deployment:**
- None. No Dockerfile, docker-compose file, Makefile, Procfile, systemd unit, or release pipeline. Execution is manual:
  - `python src/sentinel/run.py`
  - `./sentinel <command>`
  - `python scripts/run_live_linkedin_test.py`

## Environment Configuration

**Required env vars:**
- `CHROME_USER_DATA` - path to the logged-in Chrome profile. Strongly required for any authenticated platform flow; defaults to the macOS Chrome profile path.
- `RESUME_FILE_PATH` - path to the resume PDF used by upload flows; defaults to a local desktop path.
- `GOOGLE_AI_API_KEY` **or** `GOOGLE_AI_API_KEYS` - Google AI Studio key(s). Technically optional because the LLM fails open, but required for LLM questionnaire answers and reCAPTCHA audio transcription.

**Optional runtime env vars:**
- Browser/debug: `SENTINEL_JS_DEBUG`, `SENTINEL_INDEED_DEBUG`
- Instahyre: `INSTAHYRE_MAX_APPLICATIONS`
- Indeed: `INDEED_HOME_URL`, `INDEED_SEARCH_URL`, `INDEED_SEARCH_QUERY`, `INDEED_SEARCH_LOCATION`, `INDEED_MAX_APPLICATIONS`
- Hirist: `HIRIST_FEED_URL`, `HIRIST_FALLBACK_URLS`, `HIRIST_MAX_APPLICATIONS`
- Probe scripts: `SENTINEL_PROBE_JK`, `SENTINEL_PROBE_COMPANY`

**Secrets location:**
- `.env` at the repo root, gitignored (`.gitignore` "Secrets / local env"), parsed by `src/core/config.py:3-13`. No `.env.example` or secret template is committed.
- Google AI keys live in `.env` (or the process environment).
- Platform credentials are not stored by the project; they live in the external Chrome profile directory referenced by `CHROME_USER_DATA`.
- `profiles/resume.json` contains candidate PII and is gitignored via `profiles/`.

## Webhooks & Callbacks

**Incoming:**
- None. No HTTP server, route handler, or webhook endpoint is exposed.

**Outgoing:**
- None. No webhook registration, callback URL, or event delivery integration.
- Browser-level event hooks are internal to the process, not network callbacks:
  - `context.route("**/*", ...)` for resource blocking (`src/sentinel/run.py:563`)
  - `context.on("page", ...)` to auto-close popups (`src/sentinel/run.py:446`)
  - `page.on("console", ...)` for console forwarding (`src/sentinel/agent.py:4560`)

## Rate Limits & Quotas

- **Google AI Studio:** key rotation on `429`/`403`, per-model fallback chain, 60 s generation timeout, 120 s `aiohttp` session timeout, and fail-open to deterministic patterns (`src/sentinel/llm_client.py:760-838`).
- **Job platforms:** application-level pacing in `src/sentinel/rate_limiter.py` - minimum delays Naukri `1.5 s`, LinkedIn `2.0 s`, Instahyre `1.5 s`, default `1.0 s`, with 0-0.3 s jitter and exponential backoff capped at `60 s`.
- **Run loop:** LinkedIn/Naukri rate-limit timestamps skip subsequent tasks until expiry (`src/sentinel/run.py:869-887`); a 10 s cooldown and Playwright pipe reset occur between tasks (`src/sentinel/run.py:984-991`).
- **Application caps:** `INSTAHYRE_MAX_APPLICATIONS`, `INDEED_MAX_APPLICATIONS`, and `HIRIST_MAX_APPLICATIONS` bound per-run application volume.

## Integration Data Flows

1. **Questionnaire answering (all platforms):** injected JS or a platform handler extracts the question/options from the live DOM -> Python `_fuzzy_match_question()` / `PatternMatcher` resolves a deterministic answer -> optional `GemmaLLMClient.answer_question()` fallback for unresolved or essay questions -> the chosen control is filled and a row is written to `qa_results.csv` (`src/sentinel/agent.py:3562-3694`).
2. **Resume attachment:** LinkedIn/Indeed upload flows read the PDF from `RESUME_FILE_PATH` and attach it through the page's file input (`src/sentinel/agent.py:9240`).
3. **Indeed reCAPTCHA:** audio challenge URL is fetched with the shared `aiohttp` session -> audio bytes are base64-encoded into a Gemini request -> transcript is typed into `#audio-response` (`src/sentinel/agent.py:8742-8810`).
4. **Learning loop:** failures are appended to `failure_log.jsonl`; `./sentinel learn` and `scripts/import_qa_results.py` promote recurring failures into `learned_patterns.json` or `config/qa_patterns.json`.

---

*Integration audit: 2026-11-11*
