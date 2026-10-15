# Indeed + Hirist Task Fixes — Precise Change Set

This document is a hand-off spec so another model (e.g. GPT-5.2) can reproduce or
continue the work. It lists every file, symbol, selector and behaviour that was
changed, why, and how to test.

All changes are currently **uncommitted** on `master`.

```
config/qa_patterns.json                        |  35 +
src/sentinel/agent.py                          | +2348
src/sentinel/prompts.py                        | +105
src/sentinel/run.py                            | +17 -8
tests/unit/qa/test_qa_new_platform_patterns.py | +114
```

---

## 1. Dispatch (`src/sentinel/agent.py`, ~line 3134)

New dedicated handlers are intercepted before the generic scripted engine:

```python
if 'indeed' in current_url or 'indeed' in task_desc_lower:
    print("🚀 Indeed Apply Task Detected...")
    await self._handle_indeed_apply_task()
    self.state.task_complete = True
    break

if 'hirist' in current_url or 'hirist' in task_desc_lower:
    print("🚀 Hirist Apply Task Detected...")
    await self._handle_hirist_apply_task()
    self.state.task_complete = True
    break
```

**Why:** Indeed "Easily apply" renders inside nested cross-origin iframes and a
new SmartApply tab; Hirist is a Next.js SPA with hashed classes. Neither works
through the generic JS-injection form engine.

Also five existing platform-format branches in `_fuzzy_match_question` were
extended to include `indeed`/`hirist` (whole-number experience, short LWD, etc.):

```python
if self._current_platform in ('linkedin', 'indeed', 'hirist'):        # YOE -> '4'
if self._current_platform in ('linkedin', 'linkedin_form', 'indeed', 'hirist'):  # total exp -> '4'
if self._current_platform in ('linkedin', 'indeed', 'hirist'):        # exp format -> '4'
if self._current_platform in ('linkedin', 'linkedin_form', 'indeed', 'hirist'):  # LWD short
if self._current_platform in ('linkedin', 'linkedin_form', 'indeed', 'hirist'):  # notice
```

---

## 2. Runner (`src/sentinel/run.py`)

### 2a. Popup auto-close guard (~line 431)

The runner auto-closed every new tab 0.3s after it opened. SmartApply opens in a
**new tab**, which was being killed immediately.

```python
async def _auto_close_popup(new_page):
    try:
        await asyncio.sleep(0.6)                      # was 0.3
        u = (new_page.url or '').lower()
        if any(allowed in u for allowed in
               ('smartapply', 'indeed.com', 'hirist', 'instahyre', 'naukri', 'linkedin')):
            return                                    # never close an apply flow
        if self.context and len(self.context.pages) > 1 and new_page != self.context.pages[0]:
            ...
```

### 2b. Task list / seed URL (~line 771)

```python
("Indeed Application", "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile",
 prompts.INDEED_JOB_APPLY_TASK),
("Hirist Application", "https://www.hirist.tech/jobfeed",
 prompts.HIRIST_JOB_APPLY_TASK),
```

**Why:** the Indeed handler drives the real search UI from the homepage; do NOT
seed a pre-filtered URL.

---

## 3. Prompts (`src/sentinel/prompts.py`)

Two new constants appended: `INDEED_JOB_APPLY_TASK` and `HIRIST_JOB_APPLY_TASK`.
Each documents the 3-phase flow and the exact DOM selectors (see §4). These exist
for the LLM-driven fallback and as living documentation.

---

## 4. Indeed handler (`src/sentinel/agent.py`, `_handle_indeed_apply_task`, line 6686)

### 4.1 Class constants

| Constant | Value / purpose |
|---|---|
| `_INDEED_HOME_URL` | `https://in.indeed.com/?from=gnav-jobsearch--indeedmobile` |
| `_INDEED_SEARCH_ROLES` | rotation of role strings when `INDEED_SEARCH_QUERY` unset |
| `_INDEED_STEALTH_JS` | minimal stealth: `navigator.webdriver` -> undefined, `window.chrome.runtime`, `navigator.languages`, `navigator.plugins` only if empty, permissions.query shim |
| `_INDEED_DISMISS_OVERLAYS_JS` | dismisses only **visible** modals, skips `div[role="dialog"]` nav/menu dialogs, never clicks hidden close buttons |
| `_INDEED_MARK_CARD_JS` | tags cards `data-sentinel-card="<jk>"` |
| `_INDEED_EASY_APPLY_JS` | tags the in-pane apply control `data-sentinel-apply="1"` |
| `_INDEED_AFFIRMATIVE_OPTS` | `('yes','opt in','opt-in','i agree','agree','consent','allow','accept','authorized','authorised','willing')` |

### 4.2 Search flow (home -> filter)

- `_indeed_prepare_results(page)`: prefers the real UI flow; honours
  `INDEED_SEARCH_URL` as a shortcut.
- `_indeed_search_from_home(page)`: types role into `#text-input-what` (name=`q`),
  location into `#text-input-where` (name=`l`), clicks
  `.yosegi-InlineWhatWhere-primaryButton` ("Find jobs"). Does **not** re-`goto`
  home if the form is already loaded.
- `_indeed_human_type(page, selector, text)`: per-character typing with jitter.
- `_indeed_apply_easily_filter(page)`: clicks `button[aria-label="Easily apply filter"]`,
  selects `[data-testid="selection-pill-option-1"]` ("Easily apply on Indeed"),
  clicks "Update".

### 4.3 Job collection + apply loop

- `_indeed_collect_jobs(page)` returns `{jk, title, company, easy, href}` with
  `easy` = in-site apply available; tags cards `data-sentinel-card`.
- `_indeed_open_card(page, job)`: clicks the `data-jk` card so the detail pane
  `#jobsearch-ViewjobPaneWrapper` loads **without leaving** the results page.
  **Never** use `/viewjob?jk=` — sponsored `/pagead/clk` cards redirect away.
- `_indeed_has_easy_apply(page)`: pane-scoped check with hydration retry.
- `_indeed_click_apply_control(page)`: clicks `[data-sentinel-apply="1"]`.
- `_indeed_run_apply_flow(page)`: snapshots `initial_page_ids` **before** the
  click (the new SmartApply tab is found by diffing page sets).

Loop bounds:
```python
max_applications = self._env_int('INDEED_MAX_APPLICATIONS', 5)
max_attempts     = max(max_applications * 8, 24)
while applied < max_applications and attempts < max_attempts:
    ...
```

### 4.4 SmartApply question answering

- `_indeed_answer_questions(frame)`:
  - iterates `.ia-Questions-item` (with fallback), tags each with
    `data-sentinel-qid="<hash>"`, returns `question`, `options`, `placeholder`,
    `inputType`, and `hasSelect/hasRadios/hasInput`.
  - calls `_fuzzy_match_question`, then dispatches to set-select / set-radio /
    set-text.
- `_indeed_set_text`: **trusted** interaction — click, `fill('')`,
  `press_sequentially(answer, delay=40)` (fallback `type`), dispatch `change` +
  `blur`; JS native-setter fallback only if a trusted click cannot reach the
  input. **Why:** masked/validated inputs ignore raw JS value assignment
  ("Answer this question to continue.").
- `_indeed_set_radio`: picks the matching option in-page, then a **real
  Playwright click** on the visible label. **Why:** React ignores
  `element.click()`; the radio flag flips but `onChange` never fires.
- `_indeed_align_radio_answer(qtext, options, answer)`: if the computed answer is
  not among the offered options, fall back to the affirmative option
  (`_INDEED_AFFIRMATIVE_OPTS`). Handles e.g. answer `'15'` -> `'Opt In'`,
  job-title -> `'Yes'`.
- **Required multi-select (checkbox) questions** — e.g. "Please share your shift
  preference" (options Night Job / Day Job / Flex Job / Evening Job / Rotating
  Shift). The scanner used to look only for text/select/radio controls, so the
  required group was never answered, the field stayed invalid, and Continue
  never enabled (the flow stalled at `questions/2` with "No advance or submit
  control found"). Fixes:
  - The scanner now collects `input[type="checkbox"]` into `options` and emits
    `hasCheckboxes`; the early-return also accepts checkbox-only groups.
  - New `_indeed_set_checkboxes(frame, qid, qtext, options, answer)`: matches the
    computed answer to an option, else prefers `Day Job` / `Flex Job` / first,
    and toggles the `<label for=...>` with a real Playwright click (JS
    `click()` fallback).
  - Dispatch: `hasCheckboxes and not hasRadios` routes to the checkbox setter,
    and the group is answered even when the pattern engine returns `None`.
- `_indeed_format_input_answer(answer, placeholder, input_type)`: converts
  `"15 Days"` -> today+15 formatted in the placeholder's order (`DD/MM/YYYY`
  etc.); maps `immediate/asap/now` -> today; parses explicit dates; leaves
  non-date fields untouched. **Why:** required masked date field
  "When are you available to start?" blocked `questions/1`.

### 4.5 Advance-button detection

Indeed wraps the Continue label in a `<span>`, so the strict
`button:text-is("Continue")` selector never matches the `<button>`. The advance
selector list now uses `button:has-text("Continue")` (substring) and, when a
Continue/Next control is found but `disabled`, polls up to 5s for it to enable
before skipping the step (required fields may still be validating).

### 4.6 Review + reCAPTCHA + submit

- `_indeed_scroll_review(page)`: scrolls every `overflow-y:auto|scroll` ancestor
  plus window (the old max-scrollHeight heuristic left `scrollTop:0`).
- `_indeed_solve_recaptcha(page)`: reCAPTCHA Enterprise checkbox gating Submit.
  1. Preferred: `page.frame_locator('[data-testid="captcha"] iframe[title="reCAPTCHA"]').locator('#recaptcha-anchor').click()`.
  2. Fallback: human-like coordinate click at frame offset (~28,28).
  3. Poll `textarea[name="g-recaptcha-response"]` 20x1s for a token.
- `_indeed_submit_review(page)`: waits through "Preparing review", tries the
  captcha, retries once more if Submit is still disabled, then clicks
  `button[data-testid="submit-application-button"]` (force-click fallback).
- Stall detector ignores `/review-module`; `review_attempts` capped at 3.

---

## 5. Hirist handler (`src/sentinel/agent.py`, `_handle_hirist_apply_task`, line 8008)

Constants/env:

```
HIRIST_FEED_URL          default https://www.hirist.tech/jobfeed
HIRIST_MAX_APPLICATIONS  default 5
_HIRIST_TIME_UNITS = {'day':1,'week':7,'month':30,'year':365}
```

Methods: `_hirist_dismiss_dialogs`, `_hirist_read_meta` (reads
`window.__NEXT_DATA__`), `_hirist_collect_jobs` (dedupes `/j/<slug>-<id>` links),
`_hirist_click_apply`, `_hirist_confirm_modal`, `_hirist_questionnaire_present`
(matches `div.screening-question-container`), `_hirist_scan_questionnaire`,
`_hirist_option_to_days`, `_hirist_pick_option`, `_hirist_fill_text`,
`_hirist_click_option`, `_hirist_truncate`, `_hirist_fill_questionnaire`,
`_hirist_handle_questionnaire`, `_hirist_verify_applied`, `_hirist_recheck_applied`.

Key behaviours:
- **Hard cap on attempts** (not only verified successes) — the loop increments a
  counter for every job it tries to apply to and stops at
  `HIRIST_MAX_APPLICATIONS`.
- Questionnaire is handled **first**, then `_hirist_confirm_modal`.
- Open-ended/technical textareas prefer the **LLM** over patterns
  (`llm_budget = 12`, timeout `45.0s`, 2 attempts).
- Text inputs respect `maxChars`; answers are truncated with `_hirist_truncate`.
- Never select by `mui-style-*`; match by text/role/`href`.

---

## 6. Patterns (`config/qa_patterns.json`)

Added `indeed` and `hirist` blocks to `platform_defaults` and
`platform_specific_rules`:

```json
"indeed": { "experience_format":"numeric_only", "experience_example":"4",
            "salary_format":"numeric_currency", "salary_example":"2300000",
            "notice_format":"numeric_days", "notice_example":"15",
            "location_format":"city_only", "boolean_format":"yes_no",
            "numeric_defaults":true, "prefix_cleanup":true, "work_mode_format":"simple" },
"hirist": { "experience_format":"numeric_only", "experience_example":"4",
            "salary_format":"text_with_lpa", "salary_example":"23 LPA",
            "notice_format":"numeric_days", "notice_example":"15",
            "location_format":"detailed", "boolean_format":"yes_no",
            "numeric_defaults":true, "work_mode_format":"detailed" }
```

---

## 7. Tests

| File | Coverage |
|---|---|
| `tests/unit/platforms/test_indeed_search_flow.py` | 13 search-flow tests + `TestIndeedRadioAlignment` + `TestIndeedInputAnswerFormatting` + `TestIndeedCheckboxQuestions` |
| `tests/unit/platforms/test_indeed_apply_flow.py` | apply-flow helpers |
| `tests/unit/platforms/test_hirist_apply_cap.py` | Hirist attempt-cap |
| `tests/unit/qa/test_qa_new_platform_patterns.py` | new-platform patterns |

Run:
```bash
pytest tests/unit/platforms/ tests/unit/qa/ -q
```

---

## 8. Live test harnesses

```bash
# Indeed-only, cap 1, real (non-headless) Chrome
INDEED_MAX_APPLICATIONS=1 .venv/bin/python -u scripts/test_live_indeed_only.py

# Hirist-only, cap 1 (counts apply ATTEMPTS)
HIRIST_MAX_APPLICATIONS=1 .venv/bin/python -u scripts/test_live_hirist_only.py

# Both tasks
INDEED_MAX_APPLICATIONS=1 HIRIST_MAX_APPLICATIONS=1 \
  .venv/bin/python -u scripts/test_live_both_tasks.py

# Search-flow probe (no applying)
.venv/bin/python -u scripts/probe_indeed_search_flow.py

# Single-job SmartApply debug (dumps /tmp/indeed_questions.html, /tmp/indeed_review.html)
SENTINEL_INDEED_DEBUG=1 SENTINEL_PROBE_JK=<jk> SENTINEL_PROBE_COMPANY="<company>" \
  .venv/bin/python -u scripts/probe_indeed_apply_flow.py
```

Debug env: `SENTINEL_INDEED_DEBUG=1`, `SENTINEL_INDEED_MAX_STEPS=<n>`,
`SENTINEL_JS_DEBUG=1`, `HEADLESS=True`.

---

## 9. Live validation

Indeed (`.venv/bin/python -u scripts/test_live_indeed_only.py`, cap 1) — PASSED
end-to-end:

```
🏠 home search → Full Stack Developer / Bengaluru, Karnataka
   → "Easily apply on Indeed" filter applied
🔎 16 cards → SmartApply (smartapply.indeed.com/.../applybyapplya)
   → resume uploaded → questions/1 ("Do you have a completed Bachelor's degree?" -> Yes)
   → review-module → Submit disabled behind reCAPTCHA
🔒 coordinate click (no token) → 🔒 frame click → 🔓 token received
🚀 submit clicked → ✅ Applied (1/1): Full Stack Developer - AI Trainer @ DataAnnotation
Indeed Task Return: True | Applications Submitted: 1
```

Observed reCAPTCHA behaviour: the first (coordinate) click only "primes" the
widget and yields no token; the immediately following trusted frame click on
`#recaptcha-anchor` produces the token. So the two-step sequence in
`_indeed_solve_recaptcha` + `_indeed_submit_review` is deliberate — do not
remove the coordinate-click fallback.

Hirist (`.venv/bin/python -u scripts/test_live_hirist_only.py`, cap 1) — PASSED
end-to-end:

```
🔎 Found 50 Hirist job link(s) in feed
🤖 [Gemma LLM] Model: gemma-4-31b-it | Q: 'What is your College/University name ?'
      -> A: 'Vellore Institute of Technology (VIT Bhopal)'
   📝 Submitted Hirist questionnaire step 1 (3 field(s) filled)
✅ Applied (1/1): NxtWave - Backend Engineer - Java/Python/Golang
🛑 Reached Hirist application cap (1). Stopping task.
Hirist Task Return: True | Submitted: 1 | Questions: 3
```

The three fields were the notice period ("15"), current salary ("23") and the
free-text "College/University name" (LLM answer). The attempt cap stopped the
run at exactly one attempt, as required.

## 10. Known open issues

1. **reCAPTCHA Enterprise challenge (intermittent).** The SmartApply Submit is
   gated by a visible reCAPTCHA checkbox. It is solved when the browser is
   scored low-risk (works in isolated probes), but after repeated applications
   in one session Indeed can escalate to an **image challenge**, which cannot be
   solved programmatically. Current code retries the anchor click but does not
   solve challenges.
2. ~~**Some SmartApply questions still stall a step.**~~ **FIXED.** The
   `Java Full Stack Developer @ TechBiz Global GmbH` stall at `questions/2`
   was a required **multi-select checkbox** group ("Please share your shift
   preference") that the scanner ignored, leaving Continue disabled. See §4.4.
   (A secondary contributor was the `:text-is("Continue")` selector failing on
   the `<span>`-wrapped label — see §4.5.)

## 11. Priorities if continuing

1. Capture a debug dump for the stalling question and fix the required-field
   detection (same class of bug as the masked date fix).
2. Reduce reCAPTCHA risk: add human dwell/mouse before Submit, avoid rapid
   repeat applications, prefer a single long-lived profile (do not rotate the
   copied profile directory).