---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# Technology Stack

**Analysis Date:** 2026-11-11

## Languages

**Primary:**
- Python 3.14.4 (CPython, Homebrew `python@3.14`) - all application code in `src/sentinel/`, `src/patterns/`, `src/core/`, `scripts/`, and `tests/`
- Python modules are consumed as `src.<package>.<module>` imports; there is no installed package metadata, so the repo root is added to `sys.path` by launchers (`sentinel:11`, `src/sentinel/run.py:13`, `tests/conftest.py:14`)

**Secondary:**
- JavaScript (ES2020-era browser JS) - large embedded scripts inside `src/sentinel/agent.py` string literals, injected into pages with `page.evaluate()`. There are no standalone `.js` files and no Node.js build step. Examples: the LinkedIn `fuzzyMatch`/`KNOWN_PATTERNS` payload, `window.__SENTINEL_QA_LOG__`, Shadow DOM helpers, and Angular-scope manipulation for Instahyre.
- JSON - configuration and data: `config/qa_patterns.json` (Q&A corpus), `profiles/resume.json` (candidate profile), `~/Desktop/sentinel_errors/learned_patterns.json`, `pattern_stats.json`
- CSV / JSONL - local result and telemetry files written by `src/sentinel/agent.py` and `src/sentinel/self_healing.py`
- POSIX shell commands via `subprocess` - `pgrep` / `pkill` process management in `src/sentinel/run.py:654-842`

**Not used:** TypeScript, Node.js runtime, Go, Rust, Java, SQL, or any compiled native code in this repository.

## Runtime

**Environment:**
- CPython 3.14.4 virtual environment at `.venv/` (see `.venv/pyvenv.cfg`)
- Single-process `asyncio` event loop; Playwright's async API is the concurrency backbone
- macOS-first runtime. Chrome is launched from a hard-coded macOS path (`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`) in `src/sentinel/run.py:221`, `:360`, `:407`, `:825`
- System Google Chrome (stable channel), not Playwright's bundled Chromium. Launch mode is `chromium.launch_persistent_context(...)` with the user's Chrome profile copied to a temp directory (`src/sentinel/run.py:250-341`)
- Headless is hard-coded `False` for the normal run loop (`src/sentinel/run.py:894`, `:1030`); the `Browser` default is also `headless=False` (`src/sentinel/run.py:163`)

**Package Manager:**
- `pip` + `venv` (`.venv/`)
- Runtime constraints: `requirements.txt`
  - `playwright>=1.60.0`
  - `aiohttp>=3.9.0`
- Dev constraints: `requirements-dev.txt`
  - `pytest>=8.4.2`, `pytest-asyncio>=1.2.0`, `pytest-mock>=3.15.1`, `pytest-cov>=7.1.0`, `pytest-xdist>=3.6.0`, `coverage>=7.10.7`
- Lockfile: **missing**. There is no `poetry.lock`, `uv.lock`, `Pipfile.lock`, or pinned full freeze. Installed versions observed in `.venv`: `playwright 1.62.0`, `aiohttp 3.14.3`, `pytest 9.1.1`, `pytest-asyncio 1.4.0`, `pytest-mock 3.15.1`, `pytest-cov 7.1.0`, `pytest-xdist 3.8.0`, `coverage 7.15.4`
- No `pyproject.toml`, `setup.py`, or `setup.cfg`; the project is run from the checkout rather than installed

## Frameworks

**Core:**
- Playwright Python (async API) `1.62.0` (minimum `1.60.0`) - browser automation, persistent Chrome context, CDP calls, page/context routing, request interception. Entry points: `src/sentinel/run.py:127-151`, `src/sentinel/agent.py`
- `asyncio` (stdlib) - task loop, browser lifecycle, rate limiting, retries (`src/sentinel/run.py:766`, `src/sentinel/agent.py:4533`)
- `aiohttp` `3.14.3` (minimum `3.9.0`) - async HTTP for Google AI Studio calls, with a `urllib.request` fallback when `aiohttp` is unavailable (`src/sentinel/llm_client.py:272-366`)
- Custom Q&A engine (no third-party framework):
  - `PatternMatcher` with `difflib.SequenceMatcher` and category indexes (`src/patterns/pattern_matcher.py`)
  - `QuestionClassifier` (`src/sentinel/question_classifier.py`)
  - `FingerprintMatcher` / `SuccessTracker` (`src/sentinel/question_fingerprint.py`)
  - `InputAwareResolver` (`src/patterns/input_aware_resolver.py`)
  - `AnswerValidator` / `EnhancedAnswerValidator` (`src/patterns/answer_validator.py`, `src/patterns/enhanced_answer_validator.py`)
  - Embedded JS matching in `src/sentinel/agent.py`
- No web framework, ORM, database driver, task queue, LangChain/LlamaIndex, or agent framework. Task execution is 100% scripted (`SentinelAgent.run()` docstring at `src/sentinel/agent.py:4534`); the LLM is only used for questionnaire answering and captcha audio transcription.

**Testing:**
- `pytest` `9.1.1` - runner (`pytest.ini`)
- `pytest-asyncio` `1.4.0` - `asyncio_mode = auto` (`pytest.ini:14`)
- `pytest-mock` `3.15.1` - mocking
- `pytest-cov` `7.1.0` + `coverage` `7.15.4` - optional coverage
- `pytest-xdist` `3.8.0` - optional parallel runs (not the default, per `pytest.ini` comments)
- `unittest.mock` (`AsyncMock`, `MagicMock`) for browser fixtures (`tests/conftest.py:9`)

**Build/Dev:**
- No build system, bundler, transpiler, or generated-code step
- `pytest.ini` - test discovery, markers (`unit`, `integration`, `slow`), `--tb=short`, `--strict-markers`
- `.vscode/settings.json` - only Python environment manager setting
- Linting/formatting: **not configured** (no `.eslintrc`, `.prettierrc`, `ruff.toml`, `setup.cfg`, or `pyproject.toml`; `.ruff_cache/` is gitignored but `ruff` is not installed)

## Key Dependencies

**Critical:**
- `playwright` `1.62.0` - drives Chrome for LinkedIn, Naukri, Instahyre, Hirist, and Indeed. Without it the application cannot run.
- `aiohttp` `3.14.3` - Google AI Studio HTTP client; `src/sentinel/llm_client.py:17-20` treats it as optional and falls back to `urllib`
- Google Chrome stable - the actual browser binary; the Playwright-bundled Chromium is bypassed via `executable_path`

**Infrastructure:**
- `greenlet` / `pyee` - transitive Playwright dependencies (visible in `.venv`)
- `aiohappyeyeballs`, `aiosignal`, `frozenlist`, `multidict`, `yarl`, `propcache`, `attrs` - transitive `aiohttp` stack
- `typing_extensions` - transitive dependency
- No `python-dotenv`; `.env` parsing is implemented in `src/core/config.py:3-13`
- No `requests`, `httpx`, `boto3`, `supabase`, `redis`, `psycopg`, `pymongo`, or other service SDKs

**Notable stdlib modules:**
- `argparse` (`src/sentinel/cli.py`), `csv` and `json` (QA/result logging), `difflib` (fuzzy matching), `hashlib` (fingerprints), `subprocess` (Chrome process control), `tempfile`/`shutil` (profile mirroring and temp cleanup), `urllib.request` (HTTP fallback), `dataclasses`, `logging`, `pathlib`

## Configuration

**Environment:**
- Root `.env` file is loaded at import time by a custom stdlib parser in `src/core/config.py:3-13`. `.env` exists locally and is gitignored (`.gitignore` "Secrets / local env"); no `.env.example` exists.
- Variable names read by code (values intentionally not reproduced):
  - `CHROME_USER_DATA` - Chrome profile directory; default `/Users/siddhant/Library/Application Support/Google/Chrome` (`src/core/config.py:16`)
  - `CHROME_EXECUTABLE_PATH` - declared and tested, but **not wired into `Browser.start()`**, which hard-codes the macOS Chrome path (`src/sentinel/run.py:221`)
  - `GOOGLE_AI_API_KEY` - single Google AI Studio key (`src/core/config.py:30`)
  - `GOOGLE_AI_API_KEYS` - comma-separated key pool; combined with `GOOGLE_AI_API_KEY` and de-duplicated (`src/core/config.py:22-41`)
  - `RESUME_FILE_PATH` - local resume PDF used for LinkedIn/Indeed uploads; default `/Users/siddhant/Desktop/Resume/SiddhantSinghResume2026.pdf` (`src/core/config.py:45`, `src/sentinel/agent.py:249`)
- Optional runtime knobs read directly from environment:
  - `SENTINEL_JS_DEBUG` - enables JS-side debug output (`src/sentinel/agent.py:455`)
  - `INSTAHYRE_MAX_APPLICATIONS` (`src/sentinel/agent.py:6729`)
  - `INDEED_SEARCH_URL`, `INDEED_SEARCH_QUERY`, `INDEED_SEARCH_LOCATION`, `INDEED_HOME_URL`, `INDEED_MAX_APPLICATIONS`, `SENTINEL_INDEED_DEBUG` (`src/sentinel/agent.py:7814-8997`)
  - `HIRIST_FEED_URL`, `HIRIST_FALLBACK_URLS`, `HIRIST_MAX_APPLICATIONS` (`src/sentinel/agent.py:9747-9751`)
  - `SENTINEL_PROBE_JK`, `SENTINEL_PROBE_COMPANY` (probe scripts in `scripts/`)
- There is no `HEADLESS` environment read despite the AGENTS.md example; headless mode is a constructor argument only.

**Build:**
- No build config. Runtime configuration is:
  - `config/qa_patterns.json` - 77,795,113 bytes (~77.8 MB) JSON corpus, schema `version: "3.0"`, **67,022 pattern groups**, **224,791 question variants**, **27 categories**. The loader memoizes by `(mtime_ns, size)` in `src/patterns/pattern_loader.py:28-71`.
  - `profiles/resume.json` - candidate profile with `personal`, `employment`, `work_experience`, `education`, `skills`, `projects`, `leadership_and_activities`, `preferences`, `cover_letter`, `resume_pdf_path`, `cover_letter_pdf_path` (gitignored via `profiles/`)
  - `pytest.ini` - test configuration
- `config/qa_patterns.json.bak-*` backups exist locally and are gitignored (`config/*.bak-*`)

## Platform Requirements

**Development:**
- macOS (hard-coded Chrome path, `pgrep`/`pkill`, macOS GPU/display workarounds in `src/sentinel/run.py:80-120`)
- Google Chrome stable installed at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- Python 3.14 with `.venv` activated; `pip install -r requirements.txt -r requirements-dev.txt`
- A Chrome profile already logged into LinkedIn, Naukri, Instahyre, Hirist, and/or Indeed; `CHROME_USER_DATA` must point at it
- Resume PDF present at `RESUME_FILE_PATH` for upload flows
- Optional Google AI Studio API key(s) for LLM fallback and captcha audio transcription; without keys the LLM client fails open
- `chmod +x sentinel` to use the `./sentinel` CLI launcher

**Production:**
- Intended deployment is a personal workstation/desktop running the infinite loop in `src/sentinel/run.py`, not a container, serverless function, or cloud service
- No Dockerfile, Procfile, systemd unit, or deployment manifest exists
- Linux/Raspberry Pi operation is only partially supported: `CHROME_EXECUTABLE_PATH` exists in config but `Browser.start()` ignores it and hard-codes the macOS path (`src/sentinel/run.py:221`)
- Persistent local disk required for `~/Desktop/sentinel_errors/` (QA CSV, failure log, learned patterns, screenshots)

---

*Stack analysis: 2026-11-11*
