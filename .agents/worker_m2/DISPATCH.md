## 2026-09-16T20:31:34Z

You are worker_m2.
Your working directory is: /Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/worker_m2

MANDATORY CONTEXT:
Read /Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/ORIGINAL_REQUEST.md before starting work.
Also read candidate ground truth in: /Users/siddhant/Desktop/Resume/MyModels/A_N&L/AGENTS.md
Read the CSV audit report in: /Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/spec_miner_csv/audit_report.md (specifically Section 2 Discrepancy Catalog, Section 3.3, 3.4, 3.5, 4.1, 4.2, Section 5.1).
Read the pattern schema and test suite notes in: /Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/explorer_patterns/handoff.md.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

EXCLUSIVE WRITE OWNERSHIP:
You have exclusive write ownership of:
- `config/qa_patterns.json`
- `src/sentinel/agent.py` (Phase 0.1 compliance intercepts, Phase 1 category matching, and platform-specific Q&A matching)

TASK: Milestone 2 — QA Pattern Implementation & Priority Calibration

1. CRITICAL TOOL RULE EXEMPTIONS (Requirement R4):
   - In `config/qa_patterns.json`: Locate `dotnet_core_exp` (around lines 2125-2135). It currently has `default: "0"` with priority 20. Update its default to `"4.2 Years"`, `numeric_default: "4.2"`, `platform_overrides: {"linkedin": "4"}`, and supply full `input_type_defaults` (`text`: `"4.2 Years"`, `select`: `"4.2 Years"`, `radio`: `"4.2"`, `number`: `"4.2"`, `textarea`: `"4.2 Years"`).
   - Add/verify `rel_exp_dotnetcore` with `"4.2 Years"` (LinkedIn: `"4"`).
   - Ensure Calypso, .NET/C#, and AEM backend questions strictly maintain candidate total experience (4.2 Years / 4) and are NEVER zeroed out.

2. Implement Pattern Definitions in `config/qa_patterns.json` for all 29 Discrepancies from `audit_report.md`:
   Ensure all new pattern entries conform to v3.0 schema:
   - `patterns`: list of lowercased question strings
   - `category`: one of the 27 valid categories (`skills`, `experience`, `preference`, `soft_skills`, `yes_no`, `personal_info`, `education`, `availability`, `salary`, `location`, `compliance`, `notice_period`, `employment`, `work_authorization`, `self_identification`, `technical_screening`, `work_mode`, `screening`, `behavioral`, `technical`, etc.)
   - `default`: candidate ground truth answer
   - `priority`: integer (18-20 for critical compliance/PII, 10-17 for tech/experience)
   - `input_type_defaults`: dictionary with `text`, `select`, `radio`, `textarea`, `checkbox` (and `number` where appropriate)
   - `negative_patterns` where appropriate to prevent collision.

   Specific patterns to add or update:
   - `referred_by_internal_employee`: "were you referred by an internal employee", "were you referred by an internal xometry employee", etc. -> default "No", priority 20, category "compliance"
   - `internal_referral_employee_name`: "if you answered yes to the last question, please provide the employee's first and last name", etc. -> default "N/A", priority 18, category "personal_info"
   - `ex_employee_freshworks` / ex-employee: "have you been previously employed with freshworks", "have you been previously employed with", etc. -> default "No", priority 19, category "compliance"
   - `education_mba_degree`: "have you completed the following level of education: master of business administration", "master of business administration", "mba degree", "phd degree" -> default "No", priority 19, category "education"
   - `diagnose_and_solve_problems`: "can you independently diagnose and solve technical problems", "independently diagnose and solve" -> default "Yes", priority 19, category "skills"
   - `current_job_title_exact`: "your title", "current job title", "designation" -> default "Software Engineer 2", priority 19, category "personal_info"
   - `current_company_name_exact`: "company", "current company", "current employer" -> default "Everbridge", priority 19, category "personal_info"
   - `github_profile_link`: "github link", "github profile", "github url" -> default "https://github.com/siddhant3646", priority 19, category "personal_info" (ensure it is NOT the portfolio URL)
   - `rate_proficiency_scale_5`: "rate your proficiency (1-5)", etc. -> default "5", priority 19, category "skills"
   - `confirm_notice_period_digits`: "please confirm the notice period(7 days, 15 days, 30, 60 or 90 days just put 2 digit number)", etc. -> default "15", priority 19, category "notice_period"
   - `ctc_current_and_expected_compound`: "ctc: current & expected?", "current and expected ctc", "current & expected ctc" -> default "2300000 / 3000000", input_type_defaults text_inr: "2300000 / 3000000", text_lpa: "23 LPA / 30 LPA", priority 19, category "salary"
   - `instahyre_expected_ctc_lpa`: "what is your expected ctc" -> default "30 LPA", platform_overrides: {"instahyre": "30 LPA"}, category "salary", priority 18
   - Select dropdown experience questions: "how many years of experience in agentic ai" -> default "1 year" (select: "1 year", radio: "1"), "how many years of experience in full stack development" -> default "4 years" (select: "4 years", radio: "4"), "how many years of experience in azure, docker, kubernetes, and github" -> default "4 years" (select: "4 years", radio: "4"). Ensure select dropdowns do NOT return "Yes".
   - Textarea questions:
     * "this role requires you to be in bengaluru. are you okay with that?" -> default "Yes", textarea: "Yes, I am based in Bengaluru and available to work on-site."
     * "would you be aligned with this aspect?" -> default "Yes", textarea: "Yes, I thrive in fast-paced, high-ownership environments."
     * "what is your current compensation? would be great if you can highlight your expected compensation as well" -> default "Current CTC: 23 LPA, Expected CTC: 30 LPA (Fixed)"
     * "how quickly can you join us if shortlisted?" -> default "15 days", textarea: "15 days (serving notice period)"
     * "have you been the main or only developer on a product that real users used..." -> engineering ownership response based on Everbridge SDE-2 experience.
     * "show a piece of ui you built from a design..." -> React UI responsive design response.
     * "describe one product or feature you owned end to end..." -> Everbridge distributed notification / microservices response.

3. Implement Corresponding Intercepts in `src/sentinel/agent.py`:
   - In Phase 0.1 (compliance intercepts):
     * Add deterministic checks for internal employee referral (`'No'`), ex-employee (`'No'`), unearned degrees like MBA/PhD (`'No'`), and independent problem solving / diagnosis (`'Yes'`).
   - In Phase 1:
     * Add checks for notice period 2-digit confirmation returning `'15'`, rating scale 1-5 returning `'5'`, GitHub profile link returning `'https://github.com/siddhant3646'`, job title returning `'Software Engineer 2'`, current company returning `'Everbridge'`, and compound CTC returning `'2300000 / 3000000'` (or raw INR formatted).

4. Automated Validation:
   - Validate JSON syntax and schema:
     `./.venv/bin/python -c "from src.patterns.pattern_loader import load_patterns, validate_patterns; p = load_patterns('config/qa_patterns.json'); errs = validate_patterns(p); assert len(errs) == 0, f'Errors: {errs}'; print('SCHEMA VALID')"`
   - Validate Calypso, .NET/C#, and AEM experience preservation:
     Check that none return 0 and all return 4+ years.
   - Run pytest suite:
     `./.venv/bin/pytest tests/unit/qa/ -q`
     Ensure 100% pass rate.

5. Document results in `handoff.md` and `progress.md` in `/Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/worker_m2/`.
   Then notify orchestrator via `send_message`.

## 2026-09-16T21:00:16Z
**Context**: Milestone 2 execution status check.
**Content**: Checking in on progress for test verification and handoff report creation. Are the test commands completed?
**Action**: Please report your current status or provide your handoff.md when ready.
