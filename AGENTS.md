# AGENTS.md — Sentinel Project Context

## Project Overview

Sentinel is a job application automation bot that uses Playwright to fill forms on LinkedIn, Naukri, and Instahyre. It answers screening questions, handles Easy Apply flows, and manages post-application questionnaires. The system uses a multi-tier Q&A architecture: hardcoded interceptions in Python, JSON-based pattern matching, fingerprint normalization, and LLM-based answering (Gemma via Google AI Studio).

## How to Run

```bash
# Main automation (infinite loop cycling through 8 tasks)
python src/sentinel/run.py

# Tests
pytest                              # all tests
pytest tests/unit/qa/               # Q&A-specific tests
pytest --cov=src                    # with coverage
pytest -m "not slow"                # skip slow tests

# CLI utilities
./sentinel stats                    # application statistics
./sentinel patterns                 # pattern analysis
./sentinel failures                 # failure log review
./sentinel learn                    # trigger pattern learning
./sentinel export                   # export data

# Live testing
python scripts/run_live_linkedin_test.py
```

## Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| `CHROME_USER_DATA` | Chrome user data directory (logged-in profile) | `/Users/siddhant/Library/Application Support/Google/Chrome` |
| `CHROME_EXECUTABLE_PATH` | Chromium path (Linux/Raspberry Pi) | `/usr/bin/chromium-browser` |
| `GOOGLE_AI_API_KEY` | Google AI Studio API key for Gemma LLM | `AQ.Ab8...` |
| `RESUME_FILE_PATH` | Resume PDF path for LinkedIn Easy Apply | `/Users/siddhant/Desktop/Resume/SiddhantSinghResume2026.pdf` |

No `.env.example` exists; `.env` is gitignored.

## Architecture

### Two-Tier Q&A System

**Tier 1 (PHASE 1):** ~35 hardcoded keyword interceptions in `SentinelAgent._fuzzy_match_question()` returning fixed answers with 0.90-0.99 confidence.

**Tier 2:** `PatternMatcher` using `difflib.SequenceMatcher` against `qa_patterns.json` (v3.0, 11,576 pattern groups, threshold 0.65).

**Tier 3:** `QuestionClassifier` for smart category fallback (PHASE 3).

### Embedded JavaScript

LinkedIn and Naukri form filling use injected JavaScript via `page.evaluate()`. The JS `fuzzyMatch` function and `KNOWN_PATTERNS` object are embedded as large string literals inside `agent.py`. LinkedIn patterns are injected as `window.__SENTINEL_PATTERNS__`.

### Key Conventions

- `qa_patterns.json` is the single source of truth for Q&A patterns
- `input_type_defaults` in patterns map HTML input types to appropriate answer formats
- Platform detection via `self._current_platform` (Python) and `window.location.hostname` (JS)
- Dynamic placeholders: `__DYNAMIC_TODAY_US__`, `__DYNAMIC_TODAY_ISO__`, `__DYNAMIC_LWD__`

## Candidate Profile (Hardcoded Values)

| Field | Value |
|---|---|
| Name | Siddhant Singh |
| Email | siddhant3646@gmail.com |
| Phone | +91-7905828880 |
| Location | Bangalore, Karnataka, India |
| DOB | 17/12/2000 |
| Gender | Male |
| Nationality | Indian |
| Total Experience | 4.2 years (50 months) |
| Current Employer | Everbridge (Bangalore) |
| Designation | Software Engineer 2 (SDE-2) |
| Employment Type | Full-time (Permanent) |
| Current CTC | 23 LPA (23,00,000 INR) — 100% Fixed |
| Expected CTC | 30 LPA (30,00,000 INR) — 100% Fixed |
| Notice Period | 15 days (serving notice) |
| Work Authorization | Authorized to work in India, no sponsorship needed |
| LinkedIn | https://www.linkedin.com/in/siddhant-singh/ |
| GitHub | https://github.com/siddhant3646 |
| Portfolio | https://siddhant3646.github.io/Portfolio/ |
| Primary Stack | Java, Spring Boot, React, Node.js, Python, AWS, Kafka, PostgreSQL, MongoDB |
| Education | B.Tech in Computer Science |
| Willing to Relocate | Yes, 100% open |

## Platform-Specific Rules

### LinkedIn
- Experience answers as **whole numbers** (4, not 4.2)
- Salary as **raw INR** (2300000 / 3000000)
- Notice as **days** (15)
- Form filling via injected JS with 6-pass `fuzzyMatch`

### Naukri
- Experience as **"X Years"** (4.2 Years)
- Salary as **raw INR** (2300000 / 3000000)
- Chatbot-based Q&A flow with input-type-aware `fuzzyMatch`

### Instahyre
- LLM (Gemma) based answering for questionnaire
- CTC as **"23 LPA" / "30 LPA"**
- Angular scope manipulation for form interaction

---

## Q&A Matching Flow (Complete)

Entry point: `SentinelAgent._fuzzy_match_question()` at `agent.py:434`

```
PHASE 0: Skip Patterns (line 444)
  Detects skip/restart phrases → returns ('', 1.0)
  Keywords: 'skip this question', 'try again', 'restart conversation', etc.
  ↓
PHASE 0.1: Critical Compliance Intercepts (line 451)
  ~35 hardcoded compliance answers (confidence 0.95-0.98):
  - Conflict of interest → 'No'
  - Cooling period → 'No'
  - Non-compete → 'No'
  - Disciplinary → 'No'
  - Address → 'Bengaluru, Karnataka, India'
  - Scalable backend system → long technical answer
  - REST APIs in Spring Boot → long technical answer
  - Resume attachment → portfolio URL
  - Academic eligibility → 'Yes'
  - Shift flexibility → 'Yes'
  - Pronouns → 'He/Him/His'
  - Work authorization → 'Yes'/'No'
  - Ex-employee → 'Yes'/'No'
  - Relocation → 'Yes'
  ↓
PHASE 0.5: Fingerprint Matching (line 580)
  Uses FingerprintMatcher to normalize and match question variations.
  Resolves dynamic values via _resolve_dynamic().
  Validates answer format via detect_expected_format() + validate_answer().
  ↓
PHASE 0.6: Learned Pattern Matching (line 604)
  Checks self-healing patterns and pattern learner.
  Threshold: confidence >= 0.5
  ↓
PHASE 1: Keyword-based Priority Matching (line 613)
  Detects question categories via keyword analysis.
  Key detection variables:
  - is_salary_question, is_experience_question, is_notice_question
  - is_rating_question, is_yes_no_proficiency, is_project_count
  - is_tech_question, is_dsa_question, is_location_specific
  - is_total_exp_question, is_composite_hr, is_version_question
  - is_ecommerce_question, is_class_vs_functional, etc.

  Priority order within PHASE 1:
  1. Async/Celery/Background jobs (0.98)
  2. Company work history (0.98)
  3. Notice period for current company (0.99)
  4. Composite HR (CTC + NP) (0.98)
  5. NP abbreviation (0.98)
  6. LWD questions (0.98)
  7. Start date questions (0.99)
  8. Project count (0.98)
  9. Yes/No proficiency (0.98)          ← MUST be before rating questions
  10. E-commerce / BFSI / Kafka (0.98)
  11. System design / Microservices (0.98)
  12. Rating questions (0.95)
  13. Rating scale short (0.95)
  14. Position / DB / DSA (0.95)
  15. Tech stack / Technologies (0.95)
  16. Expertise / Class vs functional (0.95)
  17. Location specific (0.95)
  18. Salary questions (0.90-0.98)
  19. Total experience (0.95)
  20. Experience questions (0.95-0.98)
  21. Notice period (0.95-0.98)
  22. Location (0.95)
  ↓
PHASE 2: JSON Pattern Fuzzy Matching (line 1161)
  Uses PatternMatcher against qa_patterns.json.
  Validates answer via _validate_and_retry().
  ↓
PHASE 3: Smart Category Fallback (line 1176)
  Uses QuestionClassifier for intelligent defaults.
  Threshold: confidence >= 0.4
  ↓
FINAL: Return (None, best_score) (line 1194)
```

### JS-Side FuzzyMatch

#### Naukri Chatbot (agent.py:6451-6508, called at 6771)
1. Pre-check: Detects "how many years of experience" to force experience pattern
2. Pattern matching: Sorts by key length (descending), exact match → substring → normalized match with collision detection
3. Post-match: Yes/No override, numeric exclusion, negative indicators check

#### LinkedIn Form (agent.py:8617-8825, called at multiple locations)
6-pass matching:
| Pass | Lines | Description |
|---|---|---|
| 1 | 8628-8632 | Exact match (highest priority) |
| 2 | 8634-8656 | Substring match with anti-collision |
| 3 | 8658-8680 | Contains-words match (all significant words) |
| 4 | 8682-8700 | Keyword overlap (threshold 0.3) |
| 5 | 8702-8778 | Smart type-based defaults (safety net) |
| 6 | 8780-8822 | Platform-specific overrides (post-match disambiguation) |

---

## Platform Internals

### LinkedIn Form Filling (`_handle_scripted_fallback`, line 8362)

1. **Pattern Injection**: `_inject_patterns_once()` (line 220) injects `KNOWN_PATTERNS` as `window.__SENTINEL_PATTERNS__` via `page.evaluate()`
2. **Form Detection**: Detects Easy Apply modal, iterates through form sections
3. **Input Handling**:
   - **Radio buttons**: Matches label text against patterns, selects best match
   - **Checkboxes**: Clicks if answer is affirmative ("Yes", "True")
   - **Select dropdowns**: Matches option text against patterns, handles numeric ranges
   - **Text/Textarea**: Fills with pattern-matched answer
   - **Number inputs**: Extracts numeric value from answer
4. **6-Pass FuzzyMatch**: Each question goes through 6 matching passes (see above)
5. **Platform Overrides**: LinkedIn-specific answer transformations (whole number experience, raw INR salary)

### Naukri Chatbot (`_handle_chatbot_loop`, line 6410)

1. **Chatbot Detection**: Waits for `chatbot_DrawerContentWrapper` to appear
2. **Question Extraction**: Reads question text from chatbot DOM
3. **Input-Type-Aware fuzzyMatch**: Detects input type (radio/select/text/number) before matching
4. **Answer Injection**: Fills answer into chatbot input field
5. **Iteration**: Loops through all chatbot questions until completion
6. **Post-Apply Navigation**: Handles post-apply redirect to recommended jobs
7. **Platform Overrides**: Naukri-specific formatting ("4.2 Years", raw INR)

### Instahyre (`_answer_instahyre_questionnaire`, line 5303)

1. **Angular Scope Manipulation**: Accesses Angular scope to read/write form data
2. **LLM Integration**: Uses Gemma (via `llm_client.py`) for open-ended questions
3. **Questionnaire Flow**: Iterates through Instahyre questionnaire sections
4. **Acknowledgment Flow**: Handles terms/conditions checkboxes
5. **Submission**: Submits completed questionnaire

---

## qa_patterns.json Schema

**File:** `config/qa_patterns.json` (3.6 MB, 231,361 lines, 11,576 pattern groups)

### Top-Level Structure

```json
{
  "version": "3.0",
  "description": "...",
  "platform_defaults": { "naukri": {...}, "linkedin": {...}, "instahyre": {...} },
  "platform_specific_rules": { "naukri": {...}, "linkedin": {...}, "instahyre": {...} },
  "patterns": { ... },
  "categories": { ... },
  "learning": { "enabled": true, "auto_learn_threshold": 0.8, ... }
}
```

### Pattern Entry Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `patterns` | `string[]` | Yes | Question text variants (lowercased) for fuzzy matching |
| `category` | `string` | Yes | Classification label (see categories below) |
| `default` | `string` | Yes | Default answer (static or dynamic placeholder) |
| `input_type_defaults` | `object` | No | Maps HTML input types → appropriate answer formats |
| `priority` | `number` | No | Match priority (higher = matched first, range 2-20) |
| `negative_patterns` | `string[]` | No | Substrings that disqualify this pattern from matching |
| `requires_exact_match` | `boolean` | No | No fuzzy matching allowed (21 entries, PII/sensitive) |
| `requires_context` | `boolean` | No | Needs platform context to resolve (2 entries) |
| `sensitive` | `boolean` | No | Contains PII (phone, email, DOB, PAN, passport) |
| `numeric_default` | `string` | No | Numeric-only version of default (e.g., "23" for salary) |
| `inr_default` | `string` | No | Raw INR value (e.g., "3000000") |
| `lpa_default` | `string` | No | LPA value (e.g., "30") |
| `dynamic_answer` | `boolean` | No | Answer computed at runtime |
| `format` | `string` | No | Expected answer format (e.g., "mm/dd/yyyy") |
| `platform_overrides` | `object` | No | Per-platform answer overrides |
| `note` | `string` | No | Human-readable documentation |

### Input Type Keys (13 total)

`text`, `textarea`, `radio`, `select`, `checkbox`, `number`, `date`, `tel`, `text_inr`, `text_lpa`, `select-aggressive`, `select-education`, `select-location`

### All 27 Categories

| Category | Count | Smart Fallback |
|---|---|---|
| `skills` | 8,403 | Yes |
| `experience` | 1,317 | Yes (context required) |
| `preference` | 510 | Yes |
| `soft_skills` | 306 | Yes |
| `yes_no` | 217 | Yes (default: "Yes") |
| `personal_info` | 143 | No (exact match) |
| `education` | 138 | Yes |
| `availability` | 130 | Yes |
| `salary` | 89 | Yes |
| `location` | 71 | Yes |
| `compliance` | 66 | No |
| `notice_period` | 44 | Yes |
| `employment` | 38 | Yes |
| `work_authorization` | 34 | No |
| `self_identification` | 20 | No (exact match) |
| `technical_screening` | 14 | Yes |
| `work_mode` | 9 | Yes (default: "Yes") |
| `screening` | 9 | Yes |
| `behavioral` | 5 | Yes |
| `technical` | 6 | Yes |
| `compensation` | 1 | Yes |
| `data_consent` | 1 | Yes |
| `leadership` | 1 | Yes |
| `personal` | 1 | No |
| `role` | 1 | Yes |
| `skip` | 1 | Yes |
| `work` | 1 | Yes |

### Dynamic Placeholders

| Placeholder | Meaning |
|---|---|
| `__DYNAMIC_TODAY_US__` | Today's date in US format (MM/DD/YYYY) |
| `__DYNAMIC_TODAY_ISO__` | Today's date in ISO format |
| `__DYNAMIC_LWD__` | Last Working Day (today + 15 days) |

### Example Entries

**Minimal:**
```json
"some_pattern": {
  "patterns": ["question text variant"],
  "category": "skills",
  "default": "Yes"
}
```

**Full:**
```json
"current_salary": {
  "patterns": ["ctc", "gross current salary"],
  "category": "salary",
  "default": "23 LPA",
  "numeric_default": "23",
  "priority": 7,
  "negative_patterns": ["expected ctc", "expected salary"],
  "input_type_defaults": {
    "radio": "23",
    "select": "23 LPA",
    "text": "23 LPA",
    "number": "23",
    "text_inr": "2300000",
    "textarea": "23 LPA",
    "checkbox": "Yes"
  }
}
```

---

## How to Add QA Patterns

**When to add:** When a question is answered incorrectly (found in `qa_results.csv` or failure log).

### Step-by-Step Process

1. **Identify the question** from `qa_results.csv` or failure log
2. **Create a unique pattern ID** (snake_case, descriptive)
3. **Add question variants** to `patterns` array (lowercased, multiple phrasings)
4. **Set category** (one of 27 categories)
5. **Set default answer** (platform-appropriate format)
6. **Add `input_type_defaults`** for different form controls
7. **Set priority** (2-20, higher = matched first)
8. **Add `negative_patterns`** if needed (to prevent over-matching)
9. **Validate JSON** before committing

### Naming Conventions

- Pattern IDs: `snake_case`, descriptive (e.g., `current_salary`, `experience_domain_specific`)
- Patterns array: lowercase, no punctuation, multiple variants
- Categories: use existing categories when possible

### Priority Guidelines

| Priority | Use Case |
|---|---|
| 2-5 | Generic/broad patterns (experience, location) |
| 6-10 | Standard patterns (salary, notice period) |
| 11-15 | Specific technical patterns |
| 16-20 | Highly specific/technical explanations |

### Field Usage Guide

| Field | When to Use |
|---|---|
| `requires_exact_match: true` | PII, sensitive data, self-identification (prevents fuzzy matching) |
| `sensitive: true` | Phone, email, DOB, PAN, passport (controls logging/redaction) |
| `negative_patterns` | Broad patterns that could steal matches (e.g., "experience" excluding "java experience") |
| `platform_overrides` | When answer differs by platform |
| `dynamic_answer: true` | When answer is computed at runtime (dates) |
| `numeric_default` | When form expects pure number (e.g., "23" for salary) |
| `inr_default` | Raw INR value (e.g., "2300000") |
| `lpa_default` | LPA value (e.g., "23") |

### Complete Example

```json
"java_spring_boot_experience": {
  "patterns": [
    "experience in java spring boot",
    "java spring boot experience",
    "how many years of java spring boot",
    "years of experience in java spring boot"
  ],
  "category": "experience",
  "default": "4.2 Years",
  "priority": 12,
  "negative_patterns": [
    "salary",
    "notice period"
  ],
  "input_type_defaults": {
    "radio": "4.2",
    "select": "4.2 Years",
    "text": "4.2 Years",
    "number": "4.2",
    "textarea": "4.2 Years of experience in Java Spring Boot",
    "checkbox": "Yes"
  }
}
```

### Testing After Adding

```bash
pytest tests/unit/qa/ -v
```

Add a test in `tests/unit/qa/test_qa_*.py` if the pattern is critical.

---

## File-by-File Guide

### Core Application

| File | Lines | Purpose |
|---|---|---|
| `src/sentinel/agent.py` | ~15,500 | Core `SentinelAgent` class. Contains Python-side Q&A logic (`_fuzzy_match_question`), embedded JS for LinkedIn/Naukri form filling, platform-specific handlers, form section processing, Shadow DOM traversal |
| `src/sentinel/run.py` | ~1,080 | Main runner. `Browser` class manages Chrome lifecycle. Infinite loop cycles through 8 tasks: Naukri apply, LinkedIn Easy Apply, Instahyre tasks. Handles temp directory management, Chrome temp cleanup, profile copying |
| `src/sentinel/prompts.py` | ~360 | Task prompts and system instructions for LLM-guided tasks. Contains `COMMON_CONTEXT`, `NAUKRI_JOB_APPLY_TASK`, `LINKEDIN_EASY_APPLY_TASK`, `INSTAHYRE_*` task definitions |

### Q&A & Pattern Matching

| File | Lines | Purpose |
|---|---|---|
| `config/qa_patterns.json` | ~231,000 | Single source of truth for Q&A. 11,576 pattern groups across 27 categories. See schema section above |
| `src/patterns/pattern_matcher.py` | ~583 | `PatternMatcher` class. Uses `difflib.SequenceMatcher` for fuzzy matching (threshold 0.65). Builds category index, handles normalization (C++ → cpp, C# → csharp), resolves dynamic values, validates answers |
| `src/patterns/pattern_loader.py` | ~343 | `load_patterns()` and `validate_patterns()`. Loads JSON, validates structure, provides utilities for accessing patterns |
| `src/patterns/input_aware_resolver.py` | ~400 | `InputAwareResolver` class. Matches answers to available form options considering input type. `NumericRangeMatcher` handles range options like "3-5 years". Fuzzy matching of answer text to option labels |
| `src/patterns/answer_validator.py` | ~170 | `AnswerValidator` class. Category-specific validation (salary must have number, experience must have number, notice period ≤ 12 months, location can't be just a number). `fix()` method auto-corrects invalid answers |

### Candidate Profile & Config

| File | Lines | Purpose |
|---|---|---|
| `src/core/config.py` | 24 | Loads `.env` file (stdlib, no python-dotenv). Exports `CHROME_USER_DATA`, `CHROME_EXECUTABLE_PATH`, `GOOGLE_AI_API_KEY`, `RESUME_FILE_PATH` |
| `src/core/profile_store.py` | 88 | `ProfileStore` class. Loads `profiles/resume.json`, validates required keys (name, email, phone). Dotted-path accessor (`get('personal.email')`). `to_js_dict()` exports profile for JS injection |
| `profiles/resume.json` | — | Candidate profile data (gitignored). Source of truth for personal info |

### Intelligence & Learning

| File | Lines | Purpose |
|---|---|---|
| `src/sentinel/self_healing.py` | ~471 | `FailureLogger`, `LearnedPattern`, `RecoveryResult`. Logs failures to `~/Desktop/sentinel_errors/failure_log.jsonl`. Persistent learning from corrections. Recovery strategies (try alternatives, suggest corrections) |
| `src/sentinel/question_classifier.py` | ~823 | `QuestionClassifier` class. Smart categorization using keyword/regex patterns. Platform-specific defaults. `QuestionCategory` enum (SALARY, EXPERIENCE, NOTICE_PERIOD, etc.). `InputType` enum |
| `src/sentinel/question_fingerprint.py` | ~929 | `FingerprintMatcher` class. Normalizes questions to fingerprints (removes stop words, applies synonym map). Success rate tracking. Validation rules for expected formats |
| `src/sentinel/llm_client.py` | ~496 | Google AI Studio Gemma LLM client. Async, fail-open question answering. Dynamic model discovery, fallback chains (`gemma-3-27b-it` → `gemma-2-27b-it` → ...). Retries with capped exponential backoff. `get_candidate_facts()` builds candidate factsheet for LLM prompting |

### Browser & Session Management

| File | Lines | Purpose |
|---|---|---|
| `src/sentinel/session_manager.py` | ~103 | `SessionManager` class. Tracks session health (page crashes, navigation drift, timeouts). Recovery strategies: reload, re-navigate, graceful shutdown. Max 3 crashes before giving up |
| `src/sentinel/ui_error_detector.py` | ~723 | `UIErrorDetector` class. Detects validation errors, modal messages, form issues on LinkedIn/Naukri/Instahyre. `ErrorType` enum (VALIDATION_ERROR, INPUT_MISMATCH, STATE_DESYNC, etc.). Integrates with SelfHealingMatcher for automatic retry |
| `src/sentinel/rate_limiter.py` | 78 | `RateLimiter` class. Per-platform adaptive delays (Naukri: 1.5s, LinkedIn: 2.0s, Instahyre: 1.5s). Exponential backoff on errors (capped at 60s). Jitter to mimic human pacing |
| `src/sentinel/human_behavior.py` | ~396 | Human-like mouse movements (bezier curves), scrolling, clicking with natural delays. `human_mouse_move()`, `human_scroll()`, `human_click()`. Tracks mouse position via `window.lastMouseX/Y` |

### Scripts

| File | Purpose |
|---|---|
| `scripts/import_qa_results.py` | Imports QA results from CSV into qa_patterns.json |
| `scripts/repair_qa_patterns.py` | Repairs/validates qa_patterns.json structure |
| `scripts/run_live_linkedin_test.py` | Runs live LinkedIn form-filling test |

### Tests

| Directory | Purpose |
|---|---|
| `tests/unit/qa/` | Q&A-specific unit tests |
| `tests/unit/` | All other unit tests |
| `tests/integration/` | Integration tests |
| `tests/test_input_type_awareness.py` | 13 tests for input-type-aware answer generation |

Test configuration: `pytest.ini` (asyncio auto mode), markers: `unit`, `integration`, `slow`.

---

## Debugging Guide

### Analyzing qa_results.csv

The file `~/Desktop/sentinel_errors/qa_results.csv` logs every answered question:

```bash
# Find incorrectly answered questions
grep "incorrect\|wrong\|mismatch" ~/Desktop/sentinel_errors/qa_results.csv

# Find questions that fell through to LLM (low confidence)
grep "0\.[0-4]" ~/Desktop/sentinel_errors/qa_results.csv
```

### Common Error Patterns

| Symptom | Cause | Fix |
|---|---|---|
| Experience question returns "9" | Yes/No proficiency question matched rating check | Ensure `is_yes_no_proficiency` check is BEFORE `is_rating_question` in PHASE 1 |
| CTC question returns only expected | Compound CTC pattern missing from JS `salaryKeys` | Add compound pattern (e.g., "current & expected ctc") to both LinkedIn JS and Naukri Python handlers |
| Experience question returns "5" | `project_count` or `rating_scale_dsa` pattern matched | Add `negative_patterns` like "years of experience", "how many years" to those patterns |
| LinkedIn form skips a field | Shadow DOM not traversed | Use `queryDeep`/`queryAllDeep` for Shadow DOM penetration |
| Naukri chatbot stuck | Modal not detected | Check for `chatbot_DrawerContentWrapper` class |
| Template leak (`{{TECH_EXP_YEARS}}`) | Fingerprint match returned early before post-processing | Always apply post-processing on early-return paths |

### Environment Variables for Debugging

| Variable | Purpose |
|---|---|
| `SENTINEL_JS_DEBUG=1` | Enable JS-side debug logging in injected scripts |
| `HEADLESS=True` | Run Chrome in headless mode (for CI/Raspberry Pi) |

### Failure Log

`~/Desktop/sentinel_errors/failure_log.jsonl` — JSONL file with full failure context:
```json
{
  "timestamp": "2026-03-02T10:30:00",
  "question": "How many years of Java experience?",
  "attempted_answer": "9",
  "input_type": "radio",
  "options": ["Yes", "No"],
  "platform": "linkedin",
  "url": "https://www.linkedin.com/jobs/...",
  "error_type": "input_mismatch",
  "fingerprint": "a1b2c3d4e5f6g7h8"
}
```

---

## Git & Workflow

### Commit Conventions

Mixed style (no strict enforcement):
- **Imperative mood** (dominant): "Add unit tests for QA updates", "Refactor Instahyre task prompts"
- **Conventional Commits** (some): `feat:`, `fix:`, `refactor:` prefixes
- Multi-part messages separated by semicolons
- No issue/ticket references

### Branch Strategy

Single-branch development on `master` (local) / `main` (remote). No feature branches.

### Key Lessons Learned

1. **Template resolution at EVERY return path** — `{{TECH_EXP_YEARS}}` leaked because fingerprint matching returned early before post-processing. Always apply post-processing on early-return paths.
2. **Never use `data-view-name` as unique identifier** — identical across all cards. Only use truly unique attributes (numeric IDs, href paths).
3. **Adding parent elements as card selectors creates hidden duplicates** — `li` + inner `div` both matched, causing 50 elements for 25 cards. Target the element carrying data attributes, not its parent wrapper.
4. **`querySelector` on `queryAllDeep` results may miss nested elements** — Shadow DOM traversal cards may not find children with regular `querySelector`. Use `.closest('li')?.querySelector(...)` as fallback.

---

## Common Pitfalls (Critical)

1. **Yes/No proficiency before rating** — "Strong proficiency in Java?" must answer "Yes", not "9". The `is_yes_no_proficiency` check MUST come before `is_rating_question` in PHASE 1.

2. **Compound CTC patterns** — "current and expected CTC" must return both values (`"Current: 2300000, Expected: 3000000"`), not just expected. Add compound patterns to both LinkedIn JS `salaryKeys` and Naukri Python salary handler.

3. **Negative patterns on broad matchers** — `project_count` and `rating_scale_dsa` must have `negative_patterns` like `"years of experience"`, `"how many years"` to prevent them from stealing experience questions.

4. **Platform-specific formatting** — LinkedIn wants whole numbers (4), Naukri wants decimals (4.2 Years), Instahyre wants LPA strings (23 LPA). Always check `self._current_platform`.

5. **JS-side patterns must stay in sync** — When adding patterns to Python-side `qa_patterns.json`, also add corresponding patterns to the embedded JS `KNOWN_PATTERNS` in `agent.py` for LinkedIn and Naukri.

6. **Dynamic placeholders** — Use `__DYNAMIC_TODAY_US__`, `__DYNAMIC_TODAY_ISO__`, `__DYNAMIC_LWD__` for date fields. These are resolved at runtime by `_resolve_dynamic()`.

7. **Shadow DOM** — LinkedIn uses Shadow DOM extensively. Always use `queryDeep`/`queryAllDeep` instead of regular `querySelector`/`querySelectorAll`.

8. **React state desync** — After filling a field, the React state may not update. Use the "Backspace & Retype" recovery protocol from `human_behavior.py` with native value setter + manual event dispatch.
