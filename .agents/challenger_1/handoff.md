# Challenger 1 Empirical Challenge & Verification Report — Milestone 4

**Verdict**: **REJECT**

---

## 1. Observation

### 1.1 Scope of Investigation
Challenger 1 conducted an adversarial stress test of Sentinel's Q&A engine, pattern database (`config/qa_patterns.json`), input-type guards, platform overrides, and Rule R4 invariants across `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py`, and `src/patterns/input_aware_resolver.py`.

A dedicated adversarial test module was created and executed in `tests/unit/qa/test_qa_adversarial_challenger.py` (31 passed in 83.28s).

---

### 1.2 Direct Observations & Confirmed Empirical Failures

#### Finding 1 (CRITICAL): LinkedIn Platform Override Leak via Phase 0.5 Fingerprint Bypass
- **File**: `src/sentinel/agent.py:757-775` (Phase 0.5 Fingerprint Matching) and `agent.py:1315-1316` (Platform-Specific Experience Format).
- **Verbatim Code at `agent.py:757-775`**:
  ```python
  if self._fingerprint_matcher:
      fp_match = self._fingerprint_matcher.match(question)
      if fp_match:
          answer, confidence = fp_match
          if self._pattern_matcher:
              answer = self._pattern_matcher._resolve_dynamic(answer)
              answer, confidence = self._pattern_matcher._resolve_question_intent(question, answer, confidence)
          # Validate answer format
          format_type = detect_expected_format(question)
          if format_type:
              is_valid, error_msg = validate_answer(answer, format_type)
              if not is_valid:
                  print(f"   ⚠️ Fingerprint match failed validation: {error_msg}")
              else:
                  print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
                  return answer, confidence
          else:
              print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
              return answer, confidence
  ```
- **Verbatim Code at `agent.py:1315-1316`**:
  ```python
  # Platform-specific experience format
  if self._current_platform == 'linkedin':
      return '4', 0.95
  ```
- **Empirical Execution**:
  ```python
  agent = SentinelAgent()
  agent._current_platform = "linkedin"
  ans, score = agent._fuzzy_match_question("years of experience")
  print(ans)  # Observed Output: '4.2 Years'
  ```
- **Specification Conflict**: `AGENTS.md` explicitly mandates:
  > *"LinkedIn: Experience answers as whole numbers (4, not 4.2)"*
- **Mechanism**: Standard questions (`"years of experience"`, `"how many years of experience do you have"`, `"specify your relevant years of experience"`) are stored in the fingerprint database with default answer `"4.2 Years"`. Because Phase 0.5 returns early at line 772 or 775 without platform normalization, line 1315 is dead code.
- **Worker Blindspot**: In `tests/unit/qa/test_qa_csv_audit_fixes.py:392-396`, Worker M3 only tested `"enter whole number years of experience"`, an artificial phrasing that evaded the fingerprint matcher and thus gave a false impression that LinkedIn integer formatting was functioning.

---

#### Finding 2 (HIGH): Radio Button Range Interval Collapse for Non-Standard Experience Phrasings
- **File**: `src/patterns/pattern_matcher.py:316-325, 335-339` and `src/patterns/input_aware_resolver.py:302-340`.
- **Verbatim Code at `pattern_matcher.py:316-339`**:
  ```python
  # 10. Detect if the question is asking for numeric years of experience
  is_num_years = bool(re.search(
      r'\b(how many years|how many yrs|how much experience|experience you hold|years of experience|yrs of experience|relevant years|total years|experience in years|how long have you|number of years|no\.?\s*of\s*years|years of exp)\b',
      ql
  ))

  # 11. Detect if the question is a Yes/No boolean question
  is_yes_no = bool(
      re.search(r'^(do you|have you|are you|can you|is it|did you|would you|will you|willing to|comfortable with|open to|do you have|have you worked|are you familiar|do you know)\b', ql) or
      re.search(r'\b(are you on notice|are you currently on notice|are you based in|are you located in|are you in|do you stay in)\b', ql) or
      (input_type in ('radio', 'checkbox') and not is_num_years)
  )
  ...
  if input_type in ('radio', 'checkbox'):
      if is_purely_numeric:
          num_m = re.search(r'\d+(\.\d+)?', al)
          val = float(num_m.group(0)) if num_m else 0.0
          return ('Yes' if val > 0 else 'No'), max(score, 0.95)
  ```
- **Empirical Execution**:
  ```python
  m = create_matcher("config/qa_patterns.json")
  resolver = InputAwareResolver()
  q = "Rel Exp in .Netcore:"
  ans, score = m.fuzzy_match(q, input_type="radio")
  print(ans)  # Output: 'Yes'

  options = [
      Option(value="0", label="0 - 2 yrs"),
      Option(value="1", label="2 - 4 yrs"),
      Option(value="2", label="4 - 6 yrs"),
      Option(value="3", label="6+ yrs")
  ]
  res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
  print(res.matched_option)  # Output: None (Failed to match any option)
  ```
- **Second Variant Execution (Collapsing to entry level)**:
  ```python
  options_months = [
      Option(value="0", label="0 - 6 months"),
      Option(value="1", label="1 - 3 yrs"),
      Option(value="2", label="3 - 5 yrs"),
      Option(value="3", label="5+ yrs")
  ]
  res2 = resolver.resolve(ans, InputType.RADIO, options=options_months, question=q)
  print(res2.matched_option.label)  # Output: '1 - 3 yrs' (Incorrect; candidate has 4.2 yrs -> should be '3 - 5 yrs')
  ```
- **Mechanism**: Worker M3 patched `is_num_years` to include `"how much experience"` and `"experience you hold"` for the 5 Naukri questions in `audit_report.md`. However, common phrasing variants like `"Rel Exp in .Netcore:"`, `"Calypso experience"`, `"AEM backend experience"`, or generic `"<tech> experience"` fail `is_num_years`. Under `input_type="radio"`, lines 325 and 339 coerce `"4.2"` into `"Yes"`. When `"Yes"` is passed to `InputAwareResolver`, range interval matching collapses completely.

---

#### Finding 3 (MEDIUM): Acronym-Only Pattern Omission for Adobe Experience Manager (AEM)
- **File**: `config/qa_patterns.json:aem_backend_experience`.
- **Verbatim Patterns in `config/qa_patterns.json`**:
  ```json
  "aem_backend_experience": {
    "patterns": [
      "how many years of experience do you have in aem backend?",
      "how many years of experience do you have in aem backend",
      "how many years of hands-on aem backend experience you have?",
      "how many years of hands-on aem backend experience you have",
      "aem backend experience",
      "hands-on aem backend experience"
    ],
    "category": "experience",
    "default": "4.2 Years",
    "numeric_default": "4.2",
    "priority": 16,
    "platform_overrides": { "linkedin": "4" }
  }
  ```
- **Empirical Execution**:
  ```python
  m = create_matcher("config/qa_patterns.json")
  q = "Adobe Experience Manager backend experience"
  ans, score = m.fuzzy_match(q, input_type="select")
  print(ans, score)  # Output: 'Yes', 0.85
  ```
- **Specification Conflict**: `ORIGINAL_REQUEST.md` Acceptance Criteria requires:
  > *"Every erroneous question identified from qa_results.csv resolves to its correct candidate value with confidence >= 0.90 in PatternMatcher and SentinelAgent._fuzzy_match_question."*
  > *"Questions regarding Calypso, .NET/C#, and AEM continue to return total candidate experience (4.2 Years / 4)."*
- **Mechanism**: The pattern group only specifies the acronym `"aem"`. When the recruiter spells out `"Adobe Experience Manager backend experience"`, `SequenceMatcher` fails to reach the 0.90 threshold, falling back to `tech_specific_experience` with confidence 0.85 and returning `"Yes"` instead of `"4.2 Years"`.

---

### 1.3 Positive Empirical Confirmations (Passed Tests)
Adversarial testing confirmed the following areas are robust:
1. **Rule R4 Zero/Empty Invariant**: Across 196 combinations of input types (`text`, `number`, `select`, `radio`, `textarea`) and platforms (`linkedin`, `naukri`, `instahyre`), queries for Calypso, .NET/C#, and AEM backend **NEVER** return `0`, `"0"`, `0.0`, `""`, or `None`.
2. **Textarea Intent Guards**: Yes/No questions (Bengaluru location, fast-paced alignment, shifts, non-compete), salary queries (Current/Expected), and notice period (15 days) submitted as `<textarea>` cleanly return concise answers and do **NOT** receive the 508-character technical architecture essay.
3. **Dropdown Multilingual Placeholder Filtering**: Native select and custom dropdown resolvers discard placeholder strings across Spanish (`"Selecciona una opción"`), Portuguese (`"Selecione uma opção"`), Italian (`"Seleziona un'opzione"`), German (`"Bitte auswählen"`), French (`"Sélectionnez une option"`), and bracketed/dashed markers (`"---"`, `"<Choose>"`).
4. **Schema Integrity**: `validate_patterns()` reports `0` errors on `config/qa_patterns.json` across 11,576 pattern groups and all 27 categories.

---

## 2. Logic Chain

1. **Step 1 (From Observation 1.2 Finding 1)**: `AGENTS.md` establishes candidate rule: LinkedIn experience must be formatted as integers (`"4"`). `SentinelAgent` has explicit code at line 1315 to enforce this. However, Phase 0.5 (lines 758-775) executes *before* line 1315 and returns early whenever a question matches the fingerprint cache.
2. **Step 2**: Because standard questions like `"years of experience"` match in the fingerprint cache, Phase 0.5 returns `"4.2 Years"` with confidence 1.00 directly to callers on LinkedIn, completely disabling the platform override. This directly violates the platform-specific formatting rules.
3. **Step 3 (From Observation 1.2 Finding 2)**: Requirement R4 and `audit_report.md` Section 3.4 require experience queries to resolve properly to candidate experience ranges in radio button groups without collapsing to entry-level brackets (`0 - 6 months` or `0 - 2 yrs`).
4. **Step 4**: Worker M3 patched `is_num_years` for only two phrasings (`how much experience` and `experience you hold`). Questions phrased as `"Rel Exp in .Netcore:"`, `"Calypso experience"`, or `"<tech> experience"` fail `is_num_years` and are coerced by lines 335-339 into `"Yes"`.
5. **Step 5**: When `"Yes"` is fed into `InputAwareResolver`, range interval options like `['0 - 2 yrs', '2 - 4 yrs', '4 - 6 yrs', '6+ yrs']` fail to resolve (`None`), while options like `['0 - 6 months', '1 - 3 yrs', '3 - 5 yrs', '5+ yrs']` incorrectly match `1 - 3 yrs` (undervaluing the candidate from 4.2 yrs to entry-level). This recreates the exact regression documented in the audit.
6. **Step 6 (From Observation 1.2 Finding 3)**: Requirement R4 mandates candidate experience for AEM backend queries with confidence >= 0.90. Omitting `"adobe experience manager"` from `aem_backend_experience` causes full-name queries to drop to 0.85 confidence and select fields to return `"Yes"` rather than candidate experience.
7. **Conclusion from Logic Chain**: While base fixes for textarea and base pattern schema are sound, the presence of platform override leaks on LinkedIn, radio range resolution collapse on non-standard phrasing variants, and AEM full-name omission prevents full approval.

---

## 3. Caveats

- **Live Browser Form Interaction**: Tests were executed at the Python unit and integration level (`PatternMatcher`, `SentinelAgent`, `InputAwareResolver`, `OptionExtractor`). Live browser DOM evaluation (`scripts/run_live_linkedin_test.py`) was not executed as live credentials and network sessions are outside Milestone 4 unit challenge scope.
- **Review-Only Constraint**: In strict adherence to Challenger role instructions (*"Review-only — do NOT modify implementation code. Report any failures as findings — do NOT fix them yourself"*), no fixes were applied to `agent.py`, `pattern_matcher.py`, or `config/qa_patterns.json`. All fixes must be implemented by the appropriate worker.

---

## 4. Conclusion

**Verdict: REJECT**

The Q&A engine and patterns cannot be approved in their current state due to 3 reproducible empirical bugs:
1. **Critical**: LinkedIn experience questions return `"4.2 Years"` instead of `"4"` in `SentinelAgent._fuzzy_match_question()` due to Phase 0.5 fingerprint early return bypass.
2. **High**: Radio button range matching collapses (returning `None` or entry-level `1 - 3 yrs`) for experience questions phrased without `"how many years"` or `"how much experience"` (e.g., `"Rel Exp in .Netcore:"`).
3. **Medium**: `"Adobe Experience Manager backend experience"` drops confidence to 0.85 and returns `"Yes"` for select fields due to missing full-name pattern variants in `config/qa_patterns.json`.

### Required Remediations Before Approval:
1. **Fix LinkedIn Platform Override in `src/sentinel/agent.py:772`**:
   Before returning early from Phase 0.5, apply platform-specific formatting:
   ```python
   if self._current_platform in ('linkedin', 'linkedin_form'):
       # If answer is experience years (e.g. '4.2 Years'), normalize to '4'
       if re.search(r'\b\d+(\.\d+)?\s*years?\b', answer, re.I) or 'experience' in question.lower():
           num_m = re.search(r'\d+', answer)
           if num_m:
               answer = num_m.group(0)
   ```
2. **Fix `is_num_years` in `src/patterns/pattern_matcher.py:317`**:
   Expand `is_num_years` regex to include:
   ```python
   r'\b(how many years|how many yrs|how much experience|experience you hold|years of experience|yrs of experience|relevant years|total years|experience in years|how long have you|number of years|no\.?\s*of\s*years|years of exp|rel exp|relevant exp|backend experience|exp in|experience in)\b'
   ```
   Or verify if the matched pattern category is `"experience"` before coercing to boolean `"Yes"`.
3. **Update `aem_backend_experience` in `config/qa_patterns.json`**:
   Add the following variants to `patterns`:
   - `"adobe experience manager backend experience"`
   - `"adobe experience manager experience"`
   - `"how many years of experience do you have in adobe experience manager backend"`
   - `"years of experience in adobe experience manager"`

---

## 5. Verification Method

To independently reproduce the findings and verify the failures:

1. **Run the Adversarial Challenger Test Suite**:
   ```bash
   ./.venv/bin/pytest tests/unit/qa/test_qa_adversarial_challenger.py -v
   ```
   *Expected output*: 31 passed in ~83s (reproducing Bug 1, Bug 2, and Bug 3 in dedicated test cases).

2. **Direct Reproduction Script for Bug 1 (LinkedIn Platform Leak)**:
   ```bash
   ./.venv/bin/python -c "
   from src.sentinel.agent import SentinelAgent
   agent = SentinelAgent()
   agent._current_platform = 'linkedin'
   ans, score = agent._fuzzy_match_question('years of experience')
   print(f'LinkedIn experience result: {ans!r}')
   assert ans == '4', f'BUG: expected 4, got {ans}'
   "
   ```
   *Fails with*: `AssertionError: BUG: expected 4, got 4.2 Years`

3. **Direct Reproduction Script for Bug 2 (Radio Range Collapse)**:
   ```bash
   ./.venv/bin/python -c "
   from src.patterns.pattern_matcher import create_matcher
   from src.patterns.input_aware_resolver import InputAwareResolver, InputType, Option
   m = create_matcher('config/qa_patterns.json')
   resolver = InputAwareResolver()
   q = 'Rel Exp in .Netcore:'
   ans, score = m.fuzzy_match(q, input_type='radio')
   options = [
       Option(value='0', label='0 - 2 yrs'),
       Option(value='1', label='2 - 4 yrs'),
       Option(value='2', label='4 - 6 yrs'),
       Option(value='3', label='6+ yrs')
   ]
   res = resolver.resolve(ans, InputType.RADIO, options=options, question=q)
   print(f'Rel Exp resolution: {res.matched_option}')
   assert res.matched_option is not None, 'BUG: resolution failed completely (None)'
   assert res.matched_option.label == '4 - 6 yrs', f'BUG: wrong interval {res.matched_option.label}'
   "
   ```
   *Fails with*: `AssertionError: BUG: resolution failed completely (None)`

4. **Direct Reproduction Script for Bug 3 (AEM Acronym-Only Omission)**:
   ```bash
   ./.venv/bin/python -c "
   from src.patterns.pattern_matcher import create_matcher
   m = create_matcher('config/qa_patterns.json')
   q = 'Adobe Experience Manager backend experience'
   ans, score = m.fuzzy_match(q, input_type='select')
   print(f'AEM full name select: ans={ans!r}, score={score}')
   assert score >= 0.90, f'BUG: confidence {score} < 0.90'
   assert ans in ['4.2 Years', '4'], f'BUG: wrong answer {ans}'
   "
   ```
   *Fails with*: `AssertionError: BUG: confidence 0.85 < 0.90`
