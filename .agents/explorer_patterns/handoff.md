# Handoff Report: QA Pattern Structures, Intercepts, Tool Rule Exemptions, and Test Suite

**Author**: Explorer Subagent (`explorer_patterns`)  
**Working Directory**: `/Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/explorer_patterns`  
**Date**: 2026-09-15  

---

## 1. Observation

1. **Test Suite Status**:
   - Command: `./.venv/bin/pytest tests/unit/qa/ -q`
   - Result: `314 passed in 191.12s (0:03:11)` across 12 test files.
   - Files: `test_fixed_qa_results.py`, `test_fuzzy_coverage_expansion.py`, `test_input_type_awareness.py`, `test_known_qa_reliability.py`, `test_qa_audit_fixes.py`, `test_qa_aug25_fixes.py`, `test_qa_aug27_fixes.py`, `test_qa_aug29_fixes.py`, `test_qa_new_platform_patterns.py`, `test_qa_sept14_fixes.py`, `test_qa_sept15_fixes.py`, `test_qa_updates.py`.

2. **Tool Rule Exemptions (Calypso, .NET/C#, AEM)**:
   - In `tests/unit/qa/test_qa_sept14_fixes.py` (lines 129-142):
     ```python
     def test_excluded_questions_maintain_total_experience(self):
         # 13, 14, 15 must NOT be 0 (retains candidate total experience)
         questions = [
             "How many years of experience do you have in Calypso?",
             "How much hands-on experience do you have with .NET and C# development?",
             "How many years of hands-on AEM backend experience you have?",
         ]
         for q in questions:
             agent_ans, _ = self.agent._fuzzy_match_question(q)
             pm_ans, _ = self.pattern_matcher.fuzzy_match(q)
             self.assertNotEqual(agent_ans, "0", f"Should not be 0 for: {q}")
             self.assertNotEqual(pm_ans, "0", f"Should not be 0 for: {q}")
             self.assertTrue("4" in agent_ans, f"Expected 4+ years for: {q}")
     ```
   - In `config/qa_patterns.json`:
     - Pattern `niche_non_resume_skills` (line 85824, priority 15, default `"4.2 Years"`) matches `"how many years of experience do you have in calypso"` exactly.
     - Pattern `dotnet_experience` (priority 12, default `"4.2 Years"`, platform override `linkedin: "4"`) matches `.net` and `c#`.
     - Pattern `tech_specific_experience` (priority 11, default `"4.2"`) matches `backend experience`.
   - Execution verification:
     - Calypso: `pm.fuzzy_match` -> `('4.2 Years', 0.98)`; `agent._fuzzy_match_question` -> `('4.2 Years', 1.0)`.
     - .NET/C#: `pm.fuzzy_match` -> `('4.2 Years', 0.98)`; `agent._fuzzy_match_question` -> `('4.2 Years', 0.95)`.
     - AEM: `pm.fuzzy_match` -> `('4.2', 0.98)`; `agent._fuzzy_match_question` -> `('4.2 Years', 0.98)`.

3. **`config/qa_patterns.json` Schema**:
   - Root keys: `['version', 'description', 'platform_defaults', 'platform_specific_rules', 'patterns', 'categories', 'learning']`.
   - 11,643 pattern groups; 56,526 pattern strings.
   - `python scripts/repair_qa_patterns.py validate` returned `schema errors: 0`.
   - `pattern_loader.validate_patterns()` returned `0` errors.
   - Every pattern group requires: `patterns` (list), `category` (string), `default` (string), `priority` (int 1-20), `input_type_defaults` (dict with `text`, `select`, `radio`, `textarea`, `checkbox`).

4. **`src/sentinel/agent.py` Architecture**:
   - Phase 0 (lines 447-452): Skips restart/skip conversation patterns.
   - Phase 0.1 (lines 454-675): ~35 compliance and intent intercepts (e.g. AI tools, conflict of interest, moonlighting, payslips, counter offers, cooling period).
   - Phase 1 (lines 710-1268): 22 prioritized categories. Lines 1149-1223 define `is_asking_quantity` and `is_experience_question` returning `4` (LinkedIn) or querying `self._pattern_matcher.fuzzy_match("years of experience")` (`4.2 Years` / `4 Years`).
   - Naukri Chatbot JS (lines 6632-6689): `isYearsOfExpQuestion` regex pre-check enforces `expKeys` returning total experience.
   - LinkedIn Form JS (lines 8884-9112): Pass 5/6 fallback enforces `yearsDefault` (`'4'` on LinkedIn host, `'4 Years'` on Naukri).

---

## 2. Logic Chain

1. **Exemption Preservation Logic**:
   - Premise: User requirement R4 mandates candidate total experience (4.2 Years / 4) must be strictly preserved for Calypso, .NET/C#, and AEM backend questions without zeroing them out.
   - Observation 2 demonstrates that in `config/qa_patterns.json`, `niche_non_resume_skills` (priority 15) and `dotnet_experience` (priority 12) have default `"4.2 Years"` with priority above generic fallbacks.
   - Observation 2 demonstrates that in `SentinelAgent._fuzzy_match_question` (lines 1149-1223), questions with `how many years` or `years of experience` trigger `is_experience_question`, returning the candidate's total experience (`'4'` or `'4.2 Years'`).
   - Deductive Step: Neither `PatternMatcher` nor `SentinelAgent` allows these questions to fall through to zero-default patterns. Downstream pattern additions must maintain this priority ordering and must never introduce a zero-default pattern matching Calypso, .NET/C#, or AEM.

2. **Textarea Safety Guard Logic**:
   - Premise: Requirement R2 identifies that simple Yes/No questions, compensation questions, and notice period questions inappropriately receive a 500-word engineering summary when rendered in HTML `<textarea>`.
   - Observation 4 shows that pattern entries in `qa_patterns.json` contain an `input_type_defaults` dictionary with a `textarea` key. In `src/patterns/pattern_matcher.py:306-328` and `_resolve_question_intent`, boolean questions are checked for radio/checkbox, but `textarea` is not explicitly guarded against technical essay fallback for simple questions.
   - Deductive Step: To fulfill R2, `PatternMatcher._resolve_question_intent` and `config/qa_patterns.json` must sanitize `textarea` defaults for `yes_no`, `location`, `salary`, and `notice_period` categories to return concise strings rather than technical blurbs.

3. **Schema Integrity Logic**:
   - Premise: Requirement R3 mandates `config/qa_patterns.json` remain strictly valid JSON conforming to v3.0 schema.
   - Observation 3 shows `validate_patterns` in `pattern_loader.py` checks `patterns`, `category`, and `default`. In addition, `input_type_defaults` and `priority` are universally present across all 11,643 existing groups.
   - Deductive Step: Any newly added pattern must supply all 5 core fields (`patterns`, `category`, `default`, `priority`, `input_type_defaults`) to prevent schema regression.

---

## 3. Caveats

1. **Instahyre Flow**: Instahyre form filling relies predominantly on LLM prompt-driven answering (`llm_client.py` using Gemma) and Angular scope manipulation rather than injected JS `fuzzyMatch`. Python-side `SentinelAgent._fuzzy_match_question` provides fallback values.
2. **CSV Log Dynamic Content**: The 1,275-row CSV log at `~/Desktop/sentinel_errors/qa_results.csv` is actively mined by `spec_miner_csv`. The exact questions to be added to `qa_patterns.json` will come from the miner's output; this investigation establishes the structural rules and priority scale those additions must obey.
3. **Duplicate Triggers in `repair_qa_patterns.py`**: Running `repair_qa_patterns.py validate` noted 106 existing duplicate triggers across different pattern groups. While schema errors were 0, new pattern strings should avoid collision with existing high-priority keys.

---

## 4. Conclusion

1. The candidate's total experience (4.2 Years / 4) is solidly defended across Python intercepts, JSON patterns, and JS form fillers for Calypso, .NET/C#, and AEM.
2. Adding new patterns to `config/qa_patterns.json` requires:
   - v3.0 schema compliance (required keys: `patterns`, `category`, `default`, `priority` [2-20], and `input_type_defaults` with `text`, `select`, `radio`, `textarea`, `checkbox`).
   - Clean `input_type_defaults.textarea` values that return concise strings for Yes/No, Salary, Notice Period, and Location questions.
3. Adding intercept guards to `src/sentinel/agent.py` should follow Phase 0.1 for compliance/legal yes/no questions and Phase 1 for technical/intent disambiguation.
4. Downstream test expansion should create a new dedicated test file (e.g. `tests/unit/qa/test_qa_csv_audit_fixes.py`) targeting the mined CSV questions to verify 100% pass rate without regressing the existing 314 tests.

---

## 5. Verification Method

To independently reproduce and verify this investigation:

1. **Run full existing QA test suite**:
   ```bash
   ./.venv/bin/pytest tests/unit/qa/ -q
   ```
   *Expected*: 314 passed, 0 failed.

2. **Verify Calypso, .NET, and AEM experience preservation**:
   ```bash
   ./.venv/bin/python -c "
   from src.patterns.pattern_loader import load_patterns
   from src.patterns.pattern_matcher import PatternMatcher
   from src.sentinel.agent import SentinelAgent

   patterns = load_patterns('config/qa_patterns.json')
   pm = PatternMatcher(patterns)
   agent = SentinelAgent()

   for q in [
       'How many years of experience do you have in Calypso?',
       'How much hands-on experience do you have with .NET and C# development?',
       'How many years of hands-on AEM backend experience you have?'
   ]:
       pm_ans, pm_conf = pm.fuzzy_match(q)
       agent_ans, agent_conf = agent._fuzzy_match_question(q)
       assert pm_ans not in ('0', '0 Years', None), f'PM zeroed: {q}'
       assert agent_ans not in ('0', '0 Years', None), f'Agent zeroed: {q}'
       assert '4' in pm_ans and '4' in agent_ans, f'Not 4+: {q}'
       print(f'PASS: {q} -> PM: {pm_ans}, Agent: {agent_ans}')
   "
   ```

3. **Verify `config/qa_patterns.json` schema validation**:
   ```bash
   ./.venv/bin/python -c "
   from src.patterns.pattern_loader import load_patterns, validate_patterns
   patterns = load_patterns('config/qa_patterns.json')
   errs = validate_patterns(patterns)
   assert len(errs) == 0, f'Schema errors: {errs}'
   print('PASS: qa_patterns.json schema is 100% valid')
   "
   ```
