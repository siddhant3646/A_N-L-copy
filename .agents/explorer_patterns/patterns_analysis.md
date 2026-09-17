# QA Pattern Structures, Intercepts, Tool Rule Exemptions, and Test Suite Analysis

**Date**: 2026-09-15  
**Investigator**: Explorer Subagent (`explorer_patterns`)  
**Target Repository**: Sentinel Job Application Automation Bot  

---

## Executive Summary

This investigation analyzed the multi-tier Q&A answering architecture of Sentinel across `config/qa_patterns.json`, `src/sentinel/agent.py`, `src/patterns/pattern_matcher.py`, `src/patterns/pattern_loader.py`, and `tests/unit/qa/`.

Key findings include:
1. **Tool Rule Exemptions (Calypso, .NET/C#, AEM)**: Total experience (4.2 Years / 4) is strictly preserved across all three evaluation paths:
   - Python `SentinelAgent._fuzzy_match_question`: Phase 1 `is_asking_quantity` intercepts experience questions and delegates to `self._pattern_matcher.fuzzy_match("years of experience")` or platform default (`'4'` for LinkedIn, `'4.2 Years'` for others).
   - Python `PatternMatcher`: `niche_non_resume_skills` (priority 15, matching "calypso"), `dotnet_experience` (priority 12, matching ".net" / "c#"), and `tech_specific_experience` (priority 11, matching "backend experience") resolve directly in Tier 1 substring/exact matching without touching zero-default patterns.
   - JS-side form filling: Naukri's `fuzzyMatch` has an explicit pre-check forcing experience patterns for questions with `/how many years|years of exp|years of experience|total years/`, while LinkedIn's 6-pass `fuzzyMatch` has Pass 5 and Pass 6 type fallbacks returning `yearsDefault` (`'4'` on LinkedIn, `'4 Years'` on Naukri).
2. **`qa_patterns.json` Schema (v3.0)**: Contains 11,643 pattern groups. Every pattern group requires `patterns` (list), `category` (string), `default` (string), `priority` (integer 2-20), and `input_type_defaults` (object).
3. **`agent.py` Intercepts**: Phase 0.1 houses ~35 compliance and intent intercepts (confidence 0.95-0.98), while Phase 1 executes 22 prioritized categories before fuzzy matching.
4. **Test Suite Status**: 12 test files containing 314 tests in `tests/unit/qa/` passing with 100% success rate (314 passed in 191s). Gaps exist in comprehensive coverage for textarea input-type guards, edge-case platform overrides, and negative pattern collisions.

---

## 1. Tool Rule Exemptions & Total Experience Preservation

### 1.1 Candidate Profile Baselines
- **Total Experience**: 4.2 years (50 months)
- **LinkedIn Format**: Whole numbers (`4`)
- **Naukri Format**: `"4.2 Years"` / `"4.2"`
- **Instahyre Format**: `"4.2 Years"` / `"4.2"`

### 1.2 Processing of Calypso, .NET/C#, and AEM

| Question Target | `config/qa_patterns.json` Pattern ID | Priority | Match Tier in `PatternMatcher` | Answer (PM) | Answer (Agent) |
|---|---|---|---|---|---|
| **Calypso** ("How many years of experience do you have in Calypso?") | `niche_non_resume_skills` | 15 | Tier 1 (Exact match) | `4.2 Years` (conf 0.98) | `4.2 Years` (conf 1.0 via Fingerprint) |
| **.NET / C#** ("How much hands-on experience do you have with .NET and C# development?") | `dotnet_experience` | 12 | Tier 1 (Word-boundary substring `.net`) | `4.2 Years` (conf 0.98) | `4.2 Years` (conf 0.95 via Phase 1 `is_experience_question`) |
| **AEM** ("How many years of hands-on AEM backend experience you have?") | `tech_specific_experience` | 11 | Tier 1 (Word-boundary substring `backend experience`) | `4.2` (conf 0.98) | `4.2 Years` (conf 0.98 via Phase 1 `is_experience_question`) |

### 1.3 Total Experience Fallback Mechanics
1. **In `src/sentinel/agent.py` (Phase 1, lines 1149-1223)**:
   - `is_asking_quantity` checks for phrases like `how many years`, `years of experience`, `total experience`, `total years`, `how much experience`, `relevant experience`, or pairs of `experience`/`exp` + `years`/`yrs`/`months`.
   - When detected (and not salary/rating/tech list):
     - LinkedIn: Returns `'4'` (confidence 0.95).
     - Non-LinkedIn: Queries `self._pattern_matcher.fuzzy_match("years of experience")`, falling back to `'4 Years'` (confidence 0.95).
2. **In `src/patterns/pattern_matcher.py` (`_resolve_question_intent`, lines 286-304)**:
   - `is_num_years` regex matches quantity requests:
     `r'\b(how many years|how many yrs|years of experience|yrs of experience|relevant years|total years|experience in years|how long have you|number of years|no\.?\s*of\s*years|years of exp)\b'`
   - If an matched answer is non-numeric or boolean (`'Yes'`, `'True'`, `'1'`), it auto-corrects to `'4.2 Years'` with confidence 0.95.
3. **Zero-Default Safeguards**:
   - Only 21 pattern groups in `qa_patterns.json` have a `"0"` or `"0 Years"` default (e.g. `skill_cad_fusion`, `skill_saviynt`, `skill_sitecore`, `additional_months`, `dependents_count`).
   - Calypso, .NET, C#, and AEM are explicitly excluded from zero-default patterns.
   - Any new pattern added for niche tools must explicitly set `"default": "4.2 Years"` (or `"4"` for LinkedIn) and priority >= 11 to avoid fallthrough to Tier 2 fuzzy collisions.

---

## 2. `config/qa_patterns.json` Architecture

### 2.1 Schema Requirements (v3.0)
The root JSON object strictly conforms to:
```json
{
  "version": "3.0",
  "description": "...",
  "platform_defaults": {
    "naukri": { ... },
    "linkedin": { ... },
    "instahyre": { ... }
  },
  "platform_specific_rules": {
    "naukri": { ... },
    "linkedin": { ... },
    "instahyre": { ... }
  },
  "patterns": {
    "<pattern_id>": {
      "patterns": ["question variant 1", "question variant 2"],
      "category": "skills",
      "default": "4.2 Years",
      "priority": 12,
      "input_type_defaults": {
        "text": "4.2 Years",
        "number": "4",
        "radio": "Yes",
        "select": "Yes",
        "textarea": "4.2 Years",
        "checkbox": "Yes"
      },
      "negative_patterns": ["salary", "ctc"],
      "platform_overrides": { "linkedin": "4" },
      "requires_exact_match": false,
      "sensitive": false
    }
  },
  "categories": { ... },
  "learning": { ... }
}
```

### 2.2 Field Definitions & Rules
1. **`patterns` (list of strings, required)**:
   - Must be lowercased, stripped of trailing punctuation.
   - Minimum 1 pattern string per group.
2. **`category` (string, required)**:
   - One of 17 defined categories (`skills`, `experience`, `preference`, `soft_skills`, `yes_no`, `personal_info`, `education`, `availability`, `salary`, `location`, `compliance`, `notice_period`, `employment`, `work_authorization`, `self_identification`, `technical_screening`, `work_mode`).
3. **`default` (string, required)**:
   - Non-empty baseline answer.
4. **`priority` (integer 2-20, required)**:
   - Tier 1 and Tier 2 use `priority` to break ties among competing patterns.
   - Priority 14: Deep technical concepts & framework implementations (6,798 groups).
   - Priority 15: Niche skills / non-resume explicit intercepts (1,124 groups).
   - Priority 12-13: Frameworks & languages (.NET, Java, Spring Boot).
   - Priority 6-10: Standard HR parameters (salary, notice period, location).
   - Priority 2-5: Generic fallback phrases.
5. **`input_type_defaults` (dict, required)**:
   - Maps HTML input tags to contextual representations.
   - Supported keys: `text`, `textarea`, `radio`, `select`, `checkbox`, `number`, `date`, `tel`, `text_inr`, `text_lpa`, `select-aggressive`, `select-education`, `select-location`.
   - **Textarea Guard Rule**: Questions expecting simple confirmation or quantitative data (e.g. Yes/No, Salary, Notice Period, Location) MUST NOT have long essay strings in their `textarea` key.
6. **`negative_patterns` (list of strings, optional)**:
   - If any substring in `negative_patterns` appears in the incoming question text, `_passes_negative` returns `False`, eliminating false-positive matches (1,060 pattern groups use this).

### 2.3 Validation Scripts
- `src/patterns/pattern_loader.py:validate_patterns(patterns)`: Checks that top-level `'patterns'` exists, each group is a dict, and required fields (`patterns`, `category`, `default`) are present and non-empty.
- `scripts/repair_qa_patterns.py validate`: Confirms 0 schema errors and tracks duplicate triggers across pattern groups.

---

## 3. `src/sentinel/agent.py` Intercepts & JS-Side Logic

### 3.1 Python Phase Flow in `_fuzzy_match_question`
1. **PHASE 0: Skip Patterns (lines 447-452)**
   - Returns `('', 1.0)` for chatbot commands like "skip this question", "try again".
2. **PHASE 0.1: Critical Compliance & Specific Intent Intercepts (lines 454-675)**
   - Intercepts ~35 high-stakes questions returning fixed answers with confidence 0.95-0.98.
   - Examples: AI coding tools (`Yes`), conflict of interest (`No`), moonlighting (`No`), payslip availability (`Yes, all documents available`), counter offers (`No`), cooling period (`No`), criminal record (`No`), visa sponsorship (`No`), ex-employee (`No` except Everbridge/Fiserv).
3. **PHASE 0.5: Fingerprint Matching (lines 677-699)**
   - Normalized bag-of-words lookup via `FingerprintMatcher`.
4. **PHASE 0.6: Learned Pattern Matching (lines 701-707)**
   - Self-healing lookup from `~/Desktop/sentinel_errors/failure_log.jsonl`.
5. **PHASE 1: Keyword-based Priority Matching (lines 710-1268)**
   - 22 prioritized categories:
     1. Async/Celery/Background jobs
     2. Company work history (Everbridge/Fiserv vs other companies)
     3. Notice period for current company in days (`15`, 0.99)
     4. Composite HR (CTC + ECTC + NP)
     5. NP abbreviation
     6. LWD date calculation (today + 15 days)
     7. Desired start date (today + 15 days)
     8. Project count (`5`, 0.98)
     9. Yes/No proficiency (`Yes`, 0.98) — strictly precedes rating checks
     10. E-commerce / BFSI / Kafka / On-call
     11. System design architecture essay
     12. Rating questions (`9`, 0.95)
     13. Short rating scale 1-5 (`4`, 0.95)
     14. Preferred position (`Backend`, 0.95)
     15. Tech stack & Python libraries
     16. Technologies worked & expertise level
     17. Location & relocation checks
     18. Salary questions (monthly, LPA, ECTC, CCTC)
     19. Experience questions (`is_experience_question` -> 4 / 4.2 Years)
     20. Notice period (`15 days`)
     21. Location (`Bangalore`)
6. **PHASE 2: JSON Pattern Fuzzy Matching (lines 1270-1283)**
   - Invokes `self._pattern_matcher.fuzzy_match(question)`.
7. **PHASE 3: Smart Category Fallback (lines 1285-1302)**
   - Uses `QuestionClassifier` for category-level defaults (threshold >= 0.4).

### 3.2 Injected JavaScript Handlers
- **Naukri Chatbot (`_handle_chatbot_loop`, line 6632)**:
  - Detects input types (text, radio, select, number).
  - Explicit pre-check intercepts `/how many years|years of exp|years of experience|total years/` and routes to `expKeys` to enforce total experience answers.
- **LinkedIn Form (`_handle_scripted_fallback`, line 8884)**:
  - 6-pass fuzzy matching:
    - Pass 1: Exact match
    - Pass 2: Substring match with anti-collision and negative pattern filtering
    - Pass 3: All-words containment match
    - Pass 4: Keyword overlap (threshold >= 0.3)
    - Pass 5: Smart type-based defaults (RSU, 12th board, company, experience, notice)
    - Pass 6: Post-match platform overrides (ensures numeric experience on LinkedIn host)

---

## 4. Test Suite Assessment (`tests/unit/qa/`)

### 4.1 Test Inventory (314 Tests across 12 Files)
1. `test_fixed_qa_results.py` (7 tests): Verifies specific historical regression fixes.
2. `test_fuzzy_coverage_expansion.py` (43 tests): Broad regex and keyword fuzzy matching coverage.
3. `test_input_type_awareness.py` (6 tests): Input-type-aware defaults and textarea behavior.
4. `test_known_qa_reliability.py` (105 tests): Comprehensive assertion suite on standard QA groups.
5. `test_qa_audit_fixes.py` (37 tests): Audit fixes for compensation, relocation, and compliance.
6. `test_qa_aug25_fixes.py` (12 tests): August 25 release regression assertions.
7. `test_qa_aug27_fixes.py` (13 tests): Niche skills (Calypso, Camunda, Incorta, Snowflake), childhood question.
8. `test_qa_aug29_fixes.py` (5 tests): Notice period and relocation refinements.
9. `test_qa_new_platform_patterns.py` (31 tests): Multi-platform question normalization.
10. `test_qa_sept14_fixes.py` (13 tests): September 14 compliance intercepts, counter offers, contract types, Calypso/.NET/AEM experience preservation.
11. `test_qa_sept15_fixes.py` (7 tests): Experience range resolving, multilingual gender, select placeholders.
12. `test_qa_updates.py` (35 tests): LeetCode, AWS, GCP, Redis, PF history, and general pattern tests.

### 4.2 Test Coverage Gaps & Edge Cases
1. **Textarea Inappropriate Essay Blurbs**: Simple Yes/No or relocation questions presented inside `<textarea>` elements often match patterns whose `textarea` input-type default is populated with a 500-word engineering blurb. Tests in `test_input_type_awareness.py` do not systematically check relocation, notice period, and salary textarea inputs.
2. **AEM Phrasing Variants**: `test_qa_sept14_fixes.py` tests `"How many years of hands-on AEM backend experience you have?"`, which matched because of `"backend experience"`. Questions like `"Years of experience in Adobe Experience Manager (AEM)"` or `"How much AEM experience do you have?"` need explicit test cases to guarantee they never return 0.
3. **Negative Pattern Collisions**: Niche skill questions combined with salary or notice keywords (e.g. "Expected salary for Calypso engineer") must verify that salary patterns win over niche skill patterns.
4. **Format Invariant Verification**: Verifying that `PatternMatcher.fuzzy_match` and `SentinelAgent._fuzzy_match_question` both return confidence >= 0.90 for all audited CSV failure patterns.

---

## 5. Implementation Blueprint for Downstream Agents

### 5.1 Pattern Additions in `config/qa_patterns.json`
- Ensure any new pattern has:
  - Explicit snake_case ID.
  - Priority calibrated between 8 and 15 (15 for niche skills, 11-12 for specific frameworks, 8-10 for HR).
  - Clean `input_type_defaults` where `textarea` reflects concise answers for Yes/No, Location, Salary, and Notice Period questions.
  - Required `negative_patterns` to prevent stealing generic experience or salary questions.

### 5.2 Intercept Guard Expansion in `src/sentinel/agent.py`
- In Phase 0.1, add any new strict compliance or organizational questions discovered in the CSV audit.
- In Phase 1, ensure `is_asking_quantity` continues to protect Calypso, .NET, C#, and AEM questions.

### 5.3 Textarea Guard in `src/patterns/pattern_matcher.py`
- In `_resolve_question_intent`, enforce that if `input_type == 'textarea'` and the question is categorized under `yes_no`, `salary`, `notice_period`, or `location`, long essay defaults are truncated or mapped to their concise string equivalents.

### 5.4 Test Suite Additions in `tests/unit/qa/`
- Create a dedicated unit test file `tests/unit/qa/test_qa_csv_audit_fixes.py` covering:
  - All questions extracted from the 1,275-row audit log.
  - Verification that Calypso, .NET, and AEM questions return 4.2 Years / 4 with confidence >= 0.90.
  - Verification that textarea inputs for Yes/No, location, notice, and salary receive concise answers.
  - Execution via `./.venv/bin/pytest tests/unit/qa/ -q`.
