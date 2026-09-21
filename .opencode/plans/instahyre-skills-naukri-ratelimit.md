# Plan: Randomized Instahyre Skills + Naukri Rate-Limit Toast Fix

## Decisions (confirmed by user)
- Instahyre skills: random **8 languages + 7 tools** (15 total), drawn once per task run, stable for the whole task.
- `prompts.py`: update the two Instahyre skill lines for consistency.
- Naukri toast detection: **strict** — only trigger on a *visible* snackbar containing explicit error text (`error`, `limit`, `reached`, `something went wrong`, `processing`, `some error`).

---

## Issue 1 — Instahyre skills are hardcoded, no randomization

### Findings
- `const skillsToAdd = ['Java','JavaScript','TypeScript','SpringBoot','ReactJS','AWS','Git','OpenAI','LLMs','Claude','FastAPI','Machine Learning','Generative AI']` at `src/sentinel/agent.py:15995`, inside the single JS string of `_handle_scripted_fallback` (`agent.py:8941`).
- Both `INSTAHYRE_SEARCH_TASK` and `INSTAHYRE_INTERSESSION_TASK` share this handler, so one fix covers both.
- Selection must be **stable per task**: the handler runs every step (~1–2s). Re-shuffling each call would keep appending skills until the Selectize 15-item cap overflows.
- Reusable hooks: `reset_per_task_state()` (`agent.py:265`) and the window-global injection at `agent.py:8951` (`__SENTINEL_IS_INTERSESSION__`).

### Changes
1. **Class constants** near `agent.py:63`:
   - `INSTAHYRE_SKILL_LANGUAGES` = 35-item 8-pick pool.
   - `INSTAHYRE_SKILL_TOOLS` = 25-item 7-pick pool.
   - `INSTAHYRE_SKILL_LANGUAGES_COUNT = 8`, `INSTAHYRE_SKILL_TOOLS_COUNT = 7`.

   Languages pool: Java, JavaScript, HTML, CSS, ReactJS, NodeJS, Python, Spring,
   Spring Boot, Hibernate, Apache Spark, Apache Flink, Apache Kafka, Apache Storm,
   Apache Airflow, DBT, JUnit, System Design & patterns, Data Structures algorithms,
   Object-oriented, SOLID, CAP, AWS, GitLab, Azure, GCP, Cloud, RAG, LangChain,
   LlamaIndex, ChromaDB, YOLOv10, MediaPipe, Local LLMs (Gemma 3, Qwen, DeepSeek), Ollama.

   Tools pool: GIT, MySQL, NoSQL, Jira, Docker, Kubernetes, Splunk, Postman, Grafana,
   CICD, Confluence, Oracle SQL Developer, IntelliJ, Eclipse, Fortify, Microsoft Azure,
   Pivotal Cloud Foundry, Maven, Ant, Antigravity, Claude Code, Codex, Cursor, Kiro,
   Github Co-Pilot.

2. **`__init__`** (`agent.py:80`): add `self._instahyre_skills = None`.
3. **`reset_per_task_state()`** (`agent.py:265`): set `self._instahyre_skills = None` (fresh draw per task).
4. **New method `_get_instahyre_skills()`**:
   - Lazy: `random.sample(INSTAHYRE_SKILL_LANGUAGES, 8) + random.sample(INSTAHYRE_SKILL_TOOLS, 7)`.
   - Cache on `self._instahyre_skills`; return cached list if already set.
5. **Injection** in `_handle_scripted_fallback` next to `agent.py:8951`:
   - `window.__SENTINEL_INSTAHYRE_SKILLS__ = <json>` evaluated every call (survives navigation/reload).
6. **JS `agent.py:15995`**:
   ```js
   const skillsToAdd = (window.__SENTINEL_INSTAHYRE_SKILLS__ && window.__SENTINEL_INSTAHYRE_SKILLS__.length)
       ? window.__SENTINEL_INSTAHYRE_SKILLS__
       : ['Java','JavaScript','TypeScript','SpringBoot','ReactJS','AWS','Git','OpenAI','LLMs','Claude','FastAPI','Machine Learning','Generative AI'];
   ```
7. **`prompts.py`**: update Instahyre skill lines `240` and `277` to describe the random 8-language + 7-tool, runtime-injected selection. Line `111` (LinkedIn) stays untouched.

### Notes / risks
- Free-text skills (e.g. "Local LLMs (Gemma 3, Qwen, DeepSeek)", "System Design & patterns") go through Selectize `createItem`, same as today's "LLMs"/"Generative AI".
- Existing `existingSkills` dedupe + fixed 15-item set keeps the loop idempotent: once all present, `addedCount == 0`.

---

## Issue 2 — Naukri rate-limit toast never caught

### Findings (root causes)
1. **Primary:** every snackbar visibility gate uses `el.offsetParent !== null`
   (`agent.py:5193, 5205, 7164, 7172, 7216, 7221, 7435, 15684, 15694, 15727, 15737`).
   `offsetParent` is `null` for `position: fixed` elements — Naukri's
   `div.ss-snackbar.ss-snackbar-error` is a fixed toast, so every check silently
   returns null/false. The code already works around this for the chat layer via
   `getBoundingClientRect` (`agent.py:7206`), but not for snackbars.
2. **Timing:** the common `NAUKRI_APPLY_CLICKED` branch (`agent.py:4754`) does not poll
   after the click; it sleeps 1.5–2.5s, optionally native re-clicks, then
   `_handle_chatbot_loop` polls only `attempts=1` after another 2–3.5s sleep. The async
   toast can vanish/navigate first. The poll at `agent.py:4697` is under
   `CHECKBOX_CLICKED`, which the fallback never returns (dead path).
3. **Synchronous in-JS checks** run in the same tick as `.click()`, so they can never
   see the async toast.
4. `agent.py:14569` checks presence with **no** visibility gate → can false-positive on
   a stale hidden snackbar.

### Changes
1. **Shared visibility helper** injected in `_inject_patterns_once`'s `init_script`
   (`agent.py:249-257`):
   ```js
   window.__SENTINEL_ISVISIBLE__ = (el) => {
       if (!el) return false;
       if (el.offsetParent !== null) return true;
       const r = el.getBoundingClientRect();
       if (r.width === 0 && r.height === 0) return false;
       const cs = getComputedStyle(el);
       if (cs.display === 'none' || cs.visibility === 'hidden') return false;
       if (parseFloat(cs.opacity || '1') === 0) return false;
       return true;
   };
   ```
2. **Replace every snackbar `offsetParent !== null` gate** with
   `window.__SENTINEL_ISVISIBLE__(el)` at the lines listed above; also visibility-gate
   the `14569` check.
3. **Strict text gate** (unchanged set): `error` / `limit` / `reached` /
   `something went wrong` / `processing` / `some error`.
4. **Immediate poll** in the `APPLY_CLICKED` branch (`agent.py:4754`):
   `await self._poll_naukri_error_snackbar(attempts=5, interval=0.8)` right after the
   click, before the sleep; on hit set `self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)`,
   `self.state.task_complete = True`, break.
5. Chatbot-loop early poll (`agent.py:6914`) becomes effective with the fixed visibility check.

---

## Tests
- `tests/unit/platforms/test_instahyre_random_skills.py`:
  - 15 unique skills; exactly 8 from languages pool, 7 from tools pool.
  - Stable across repeated `_get_instahyre_skills()` calls within a task.
  - Changes after `reset_per_task_state()`.
  - Injected `__SENTINEL_INSTAHYRE_SKILLS__` payload verified via mocked page.
- `tests/unit/sentinel/test_naukri_rate_limit.py`:
  - Mocked `page.evaluate` returning `NAUKRI_RATE_LIMITED...` → sets flag + completes.
  - Returning `''` → does not set flag.
  - Fixed-position visibility validated via an `integration`-marked `page.set_content` test.
- Run: `pytest tests/unit/platforms tests/unit/sentinel -q` then `pytest -m "not slow"`.

---

## Working-tree note
Pre-existing unrelated uncommitted edits exist in `src/sentinel/agent.py`,
`config/qa_patterns.json`, `src/sentinel/question_fingerprint.py`. Leave them untouched.
