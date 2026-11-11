---
last_mapped_commit: eba6548b75949fbed92f35cb157b1eae759b3927
last_mapped_at: 2026-11-11
---
# Testing Patterns

**Analysis Date:** 2026-11-11

## Test Framework

**Runner:**
- `pytest` 9.1.1 installed (`.venv`, Python 3.14.4); floor `pytest>=8.4.2` in `requirements-dev.txt`.
- `pytest-asyncio` 1.4.0 with `asyncio_mode = auto` (`pytest.ini:14`).
- `pytest-mock>=3.15.1`, `pytest-cov>=7.1.0`, `pytest-xdist>=3.6.0`, `coverage>=7.10.7`.
- Class-based tests also use the stdlib `unittest` runner (`unittest.TestCase`, `unittest.IsolatedAsyncioTestCase`); pytest collects and runs them.
- Config: `pytest.ini` — `testpaths = tests`, `python_files = test_*.py`, `python_classes = Test*`, `python_functions = test_*`, `addopts = --tb=short --strict-markers`.

**Assertion Library:**
- Both styles are first-class: bare `assert` in pytest-style modules, and `self.assert*` in `unittest` classes. Match the file you extend.
- Negative assertions use `self.assertRaises(...)` / `pytest.raises(...)` (8 uses).

**Run Commands:**
```bash
pytest                                   # full suite (~5 min; 1,463 tests collected)
pytest tests/unit/qa/                    # Q&A matcher/CSV regressions
pytest tests/unit/qa/test_qa_csv_fixes_nov10.py -v
pytest tests/unit/patterns/ tests/unit/core/   # fast pure-logic suites
pytest -m "not slow"                     # skip the marked corpus-wide audit
pytest -m integration                    # only tests/integration
pytest --cov=src --cov-report=html:htmlcov --cov-report=xml   # opt-in coverage
pytest -n auto                           # xdist; CI only, slower locally (see pytest.ini:8)
```

**Prerequisites:**
- `node` on `PATH` (v25.2.1 in this environment). Five QA test modules shell out to `node -e` to execute the embedded LinkedIn JS extracted from `src/sentinel/agent.py`.
- `config/qa_patterns.json` (77.7 MB) must exist; suites skip when it is missing (`tests/integration/test_pattern_pipeline.py:25`, `tests/unit/patterns/test_pattern_matcher.py:253`).

## Test File Organization

**Location:**
- Separate tree, mirroring `src/` concerns rather than one-to-one modules:
  - `tests/unit/qa/` — 50 files: matcher behavior, pattern-corpus audits, QA CSV regressions.
  - `tests/unit/platforms/` — 21 files: LinkedIn/Naukri/Instahyre/Hirist/Indeed flow handlers.
  - `tests/unit/sentinel/` — 8 files: agent-wide concerns (QA CSV coverage, LLM client, session, safety modal, rate limits, pagination).
  - `tests/unit/patterns/` — 6 files: loader, matcher, validator, resolver, caching.
  - `tests/unit/core/` — 3 files: `config.py`, `profile_store.py`.
  - `tests/unit/browser/` — 2 files: human behavior.
  - `tests/integration/` — 1 file: `test_pattern_pipeline.py` (loader → matcher → validator against the real corpus).
- Root-level unit files: `tests/unit/test_infrastructure.py` (fixture smoke tests), `tests/unit/test_experience_radio_qa_enhancements.py`.

**Naming:**
- Files `test_<subject>.py`; dated regression files for QA audits (`test_qa_csv_fixes_oct03.py` … `test_qa_csv_fixes_nov10.py`, `test_qa_csv_audit_fixes_sept18.py`). Each file corresponds to one CSV audit batch and is never rewritten.
- Classes `Test<Subject><Behavior>`; methods describe the invariant (`test_repeat_fill_of_same_control_is_logged_once`, `test_naukri_chatbot_short_keys_are_mapped`).

**Structure:**
```
tests/
├── conftest.py                 # shared fixtures + automatic markers
├── __init__.py
├── unit/
│   ├── qa/                     # matcher + CSV regression suites (50 files)
│   ├── platforms/              # per-platform handler suites (21 files)
│   ├── sentinel/               # agent, LLM, session, safety (8 files)
│   ├── patterns/               # loader/matcher/validator/resolver (6 files)
│   ├── core/                   # config, profile store (3 files)
│   ├── browser/                # human behavior (2 files)
│   ├── test_infrastructure.py
│   └── test_experience_radio_qa_enhancements.py
└── integration/
    └── test_pattern_pipeline.py
```

## Test Structure

**Suite Organization — class style (dominant in `tests/unit/qa/` and `tests/unit/platforms/`):**
```python
import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import create_matcher

class TestQACSVFixesNov10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SentinelAgent()
        cls.matcher = cls.agent._pattern_matcher

    def test_preferred_location_misspelling(self):
        q = "PREFERRRED LOCATION"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.65)
        self.assertIn("Bangalore", ans)
```

**Suite Organization — pytest style (`tests/unit/patterns/`, `tests/unit/core/`, `tests/integration/`):**
```python
import pytest
from src.patterns.pattern_matcher import PatternMatcher

class TestPatternMatcherInit:
    def test_init_with_default_threshold(self, sample_qa_patterns):
        matcher = PatternMatcher({"patterns": sample_qa_patterns})
        assert matcher.threshold == PatternMatcher.DEFAULT_THRESHOLD
```

**Patterns:**
- `setUpClass` builds one `SentinelAgent()` and/or `create_matcher("config/qa_patterns.json")` per class — construction is cheap because `PatternMatcher` shares its index bundle (`src/patterns/pattern_matcher.py:49`) and `load_patterns` memoizes by mtime/size (`src/patterns/pattern_loader.py:38`).
- `setUp` per test creates temp output and redirects persistence:
```python
self.tmp = tempfile.TemporaryDirectory()
self.addCleanup(self.tmp.cleanup)
self.agent.SCREENSHOT_DIR = self.tmp.name
self.agent.QA_RESULTS_CSV = os.path.join(self.tmp.name, "qa_results.csv")
```
- Teardown via `addCleanup`, `TemporaryDirectory`, or `asyncTearDown` (`tests/unit/sentinel/test_llm_client.py:14`).
- Assertions mix numeric thresholds with content checks: `self.assertGreaterEqual(score, 0.95)` plus `self.assertIn("Spring Boot:", ans)`.

## Mocking

**Framework:** `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`, `patch.object`), plus `monkeypatch` for environment variables.

**Patterns:**
```python
# Async Playwright page driven by a scripted list of evaluate() results
mock_page = AsyncMock()
mock_page.evaluate = AsyncMock(side_effect=[
    True,                       # wait_for_questions
    [{"index": 0, "question": "...", "inputType": "radio", "options": ["Yes", "No"]}],
    "CLICKED_RADIO",            # fill_result
    "SUBMIT_CLICKED",           # submit
    True,                       # confirmation
])

# Typed LLM double
mock_llm = MagicMock(spec=GemmaLLMClient)
mock_llm.answer_question = AsyncMock(return_value="Yes")

with tempfile.TemporaryDirectory() as tmp_dir:
    test_csv = os.path.join(tmp_dir, "qa_results.csv")
    with patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
         patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir), \
         patch.object(self.agent, "_get_llm_client", return_value=mock_llm), \
         patch("asyncio.sleep", AsyncMock()):
        await self.agent._answer_instahyre_questionnaire(mock_page, url)
```
(`tests/unit/platforms/test_instahyre_gemma_answers.py`)

- Method doubling on the agent uses `patch.object(SentinelAgent, "_handle_linkedin_resume_upload", new=AsyncMock())` — see `tests/unit/sentinel/test_qa_csv_coverage.py:192`.
- Call capture uses `side_effect=lambda **kw: calls.append(kw)` and `MagicMock` assertions (`self.agent.log_qa_result.assert_called_once()`, `.call_args[1]`).
- Hand-written fakes replace Playwright when `evaluate()` dispatch matters: `_FakePage` answers only the QA-drain script (`"window[globalName]" in script`) and returns `"NO_ACTION"` otherwise (`tests/unit/sentinel/test_qa_csv_coverage.py:26`).

**What to Mock:**
- Playwright `page`/`frame` objects, locators, `page.evaluate`, `page.title`, mouse.
- The LLM client (`MagicMock(spec=GemmaLLMClient)`) and `_get_llm_client`.
- `asyncio.sleep` for speed (`@pytest.fixture mock_sleep`, `patch("asyncio.sleep", AsyncMock())`).
- Output paths (`QA_RESULTS_CSV`, `SCREENSHOT_DIR`) and env vars (`monkeypatch.setenv`, autouse `mock_env_vars` in `tests/conftest.py:293`).
- Downstream agent methods when testing a single handler (`_fuzzy_match_question`, `_hirist_click_option`, `_indeed_set_text`, etc.).

**What NOT to Mock:**
- The pattern corpus and `PatternMatcher` for QA regression tests — those tests exist to validate real `config/qa_patterns.json` behavior.
- `SentinelAgent()` construction; tests instantiate it directly without a browser.
- Pure helpers (`AnswerValidator`, `input_type_sanitizer`, `FingerprintMatcher`); call them for real.

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**
- `real_patterns_data`, `real_pattern_matcher` — session-scoped real corpus, built once.
- `mock_page`, `mock_context`, `mock_browser` — pre-wired async Playwright doubles.
- `mock_platform_handlers`, `mock_linkedin_handler`, `mock_naukri_handler` — async handler doubles with `detect_login_required`, `handle_task`, `get_selectors`.
- `sample_qa_patterns`, `sample_questions`, `sample_agent_state` — small in-memory corpora/state.
- `temp_directory`, `temp_profile_dir`, `temp_qa_patterns_file` — temp filesystem with cleanup.
- `mock_config`, `mock_datetime`, `mock_sleep`.
- Autouse `mock_env_vars` sets `CHROME_USER_DATA` and `CHROME_EXECUTABLE_PATH` for every test.

**Test Data:**
```python
@pytest.fixture
def sample_qa_patterns():
    return {
        "salary": {"patterns": ["current salary", "what is your ctc"],
                   "category": "salary", "default": "13.5 LPA", "numeric_default": "13.5"},
        "last_working_date": {"patterns": ["what is your lwd"],
                              "category": "notice_period", "default": "__DYNAMIC_LWD__",
                              "input_type_defaults": {"text": "__DYNAMIC_LWD__", "date": "__DYNAMIC_LWD__"},
                              "priority": 13},
    }
```

**Location:**
- Fixtures live only in `tests/conftest.py`; module-local fixtures are defined in the test file (`small_corpus` in `tests/unit/patterns/test_pattern_load_caching.py:19`, `qa_config` in `tests/unit/qa/test_input_type_defaults_matrix.py:40`).
- JS payload shapes are inlined per test (dicts with `question`/`q`, `answer`/`a`, `inputType`/`t`, `selectedOption`/`s`).

## Coverage

**Requirements:** None enforced. No `.coveragerc`, no `--cov-fail-under`.

**View Coverage:**
```bash
pytest --cov=src --cov-report=html:htmlcov --cov-report=xml
```
Coverage is opt-in to keep the default run fast (`pytest.ini:6-10`).

**Behavioral coverage that *is* enforced by tests:**
- Every fill/skip/reject path must emit a QA CSV row: `tests/unit/sentinel/test_qa_csv_coverage.py` (payload, drain, dedupe, job attribution, chatbot markers, Indeed scanning), `tests/unit/platforms/test_hirist_qa_logging_and_console_filtering.py`, `tests/unit/platforms/test_instahyre_gemma_answers.py`.
- Corpus-wide input-type completeness: `tests/unit/qa/test_input_type_defaults_matrix.py` audits every pattern in `config/qa_patterns.json` so no pattern ships an unusable value for a supported control.
- Cache invariants: `tests/unit/patterns/test_pattern_load_caching.py` guards the 68 MB corpus load/index caches (if they regress, suite runtime jumps from minutes to tens of minutes).

## Test Types

**Unit Tests:**
- Scope: single class or handler; no network, no browser launch, no real LLM.
- Approach: construct `SentinelAgent()` / `PatternMatcher` directly; call private methods; mock Playwright and persistence.
- Marker: applied automatically to everything under `tests/unit/` by `pytest_collection_modifyitems` (`tests/conftest.py:322`); 21 tests also carry an explicit `@pytest.mark.unit`.

**Integration Tests:**
- Scope: `tests/integration/test_pattern_pipeline.py` — `PatternLoader` → `PatternMatcher` → `AnswerValidator` over the real `config/qa_patterns.json`.
- Approach: skips when the corpus is absent; asserts structural invariants (non-empty `patterns` arrays, valid defaults for core categories, at least 300 groups).

**E2E Tests:**
- Not part of pytest. Live browser runs are standalone scripts: `scripts/run_live_linkedin_test.py`, `scripts/test_live_naukri_only.py`, `scripts/test_live_instahyre_only.py`, `scripts/test_live_hirist_only.py`, `scripts/test_live_indeed_only.py`, `scripts/test_live_both_tasks.py`. They drive real Chrome profiles and write screenshots under `live_test_output_*/` (gitignored).

## Common Patterns

**Async Testing:**
```python
# pytest-asyncio auto mode
@pytest.mark.asyncio
async def test_session_manager_recover_prioritizes_expected_url():
    sm = SessionManager()
    mock_page = MagicMock()
    mock_page.reload = AsyncMock()
    await sm.recover(mock_page, expected_url="https://www.naukri.com/recommendedjobs")
    mock_page.reload.assert_awaited_once()
```
```python
# unittest async class
class TestInstahyreGemmaAnswers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
```
```python
# sync test driving one async method
written = asyncio.run(self.agent._drain_js_qa_log(platform="linkedin"))
```
- `asyncio_mode = auto` means `async def test_*` runs without a marker, though several tests still carry `@pytest.mark.asyncio` (47 uses).

**CSV Assertion Pattern:**
```python
def rows(self):
    with open(self.agent.QA_RESULTS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

self.assertEqual(rows[0]["status"], "submitted")
self.assertEqual([r["status"] for r in rows], ["submitted", "validation_error"])
```

**Static Source Assertions:**
```python
source = inspect.getsource(SentinelAgent._handle_scripted_fallback)
self.assertIn("const attachQaLog = (arr) => {", source)
self.assertIn("await self._drain_js_qa_log(", source)
```
Used to lock the page-side mirror and drain call in place (`tests/unit/sentinel/test_qa_csv_coverage.py:180`).

**Embedded JS Execution:**
```python
tree = ast.parse(open("src/sentinel/agent.py").read())
js_code = next(n.value.value for n in ast.walk(tree)
               if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "js_code")
proc = subprocess.run(["node", "-e", script], input=js_code, capture_output=True, text=True)
self.assertEqual(proc.returncode, 0, proc.stderr)
```
`tests/unit/qa/test_js_experience_ranges.py:12` loads the JS literal with `ast`, then evaluates extracted functions in Node to assert range matching (`4.2` → `"4-6 years"`). Same approach in `test_preferred_work_location.py`, `test_qa_csv_fixes_oct15.py`, `test_qa_sept15_fixes.py`, `test_safety_modal.py`.

**Fuzzing Pattern:**
`tests/unit/qa/test_qa_adversarial_challenger.py` generates variants (upper/lower, padded whitespace, punctuation, stripped punctuation) and asserts the same answer/score bounds hold for each.

**Parameterization:**
```python
@pytest.mark.parametrize("question,default,category", [
    ("what is your current ctc", "23 LPA", "salary"),
    ("how many years of java experience", "4.2 Years", "experience"),
])
def test_every_core_input_type_is_populated(question, default, category):
```
(`tests/unit/qa/test_input_type_defaults_matrix.py:47`)

**Skip Pattern:**
`pytest.skip("qa_patterns.json not found")` / `self.skipTest(...)` when the corpus is absent. Only one test is marked `@pytest.mark.slow` (`test_input_type_defaults_matrix.py:258`).

## Guidance for New Tests

- Matcher/pattern behavior → `tests/unit/qa/`; use the real corpus through `SentinelAgent()._pattern_matcher` or `create_matcher("config/qa_patterns.json")`, and assert `(answer, score)` pairs.
- Platform handlers → `tests/unit/platforms/test_<platform>_<behavior>.py`; drive the handler with `AsyncMock`, patch persistence to a temp dir, assert CSV rows and return values.
- CSV contract changes → extend `tests/unit/sentinel/test_qa_csv_coverage.py`; add one case per producer shape (Python, LinkedIn JS payload, Naukri chatbot marker).
- New dated regression file only for a new audit batch (`test_qa_csv_fixes_<mon><dd>.py`); otherwise append to the matching existing suite.
- Never let a test touch `~/Desktop/sentinel_errors`, launch Chrome, call Google AI Studio, or depend on `node` unless the test is explicitly about embedded JS.
- Keep assertions on behavior and audit output, not on internal cache fields, except in `test_pattern_load_caching.py` where the cache is the subject.

---

*Testing analysis: 2026-11-11*
