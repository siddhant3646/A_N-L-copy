# Handoff Report: Specification Mining & Q&A Audit of qa_results.csv

## 1. Observation
1. **Target Log Analyzed**: `/Users/siddhant/Desktop/sentinel_errors/qa_results.csv` (1,532,344 bytes).
   - Total parsed CSV rows: Exactly **1,275 rows** across 13 fields (`timestamp`, `platform`, `url`, `question`, `answer`, `input_type`, `options`, `selected_option`, `confidence`, `status`, `error_message`, `source`, `job_id_or_url`).
   - Distinct question texts: **171 unique questions** across **37 unique URLs/jobs**.
   - Platform counts: `linkedin` (939 rows), `LinkedIn_Form` (206 rows), `naukri` (126 rows), `instahyre` (4 rows).
   - Status counts: `submitted` (1,238 rows), `prefilled` (37 rows).

2. **Freshworks Form Loop & Placeholder Selection**:
   - URL: `https://www.linkedin.com/jobs/search-results/?currentJobId=4440014488...` accounts for **957 out of 1,275 rows (75.06% of the entire file)**.
   - For this single job, Sentinel attempted submission 118 times, logging repeated rows for `Specify your relevant years of experience` (118 times) and `Gender` (118 times) where `selected_option = 'Selecciona una opción'` (Spanish placeholder for 'Select an option').

3. **Textarea Essay Overwriting**:
   - Location confirmation: `This role requires you to be in Bengaluru. Are you okay with that?` (input_type: `textarea`) received the 508-character technical essay:
     *"4+ years of professional full-stack software engineering experience specializing in distributed systems, RESTful microservices, and modern web architectures..."*
   - Alignment confirmation: `We're incredibly fast-paced. We do whatever it takes to get things done. Would you be aligned with this aspect?` received the same 508-char essay.
   - Compensation: `What is your current compensation? Would be great if you can highlight your expected compensation as well.` received the same 508-char essay.
   - Notice period: `How quickly can you join us if shortlisted?` received the same 508-char essay.
   - Root code observation in `src/sentinel/agent.py`:
     Line 10529: `if (input.tagName === 'TEXTAREA' && (!answer || /^(\d+(\.\d+)?(\s*years?)?|yes|no)$/i.test(answer.trim()))) {`
     Line 10530: `    answer = '4+ years of professional full-stack software engineering experience specializing in distributed systems...';`

4. **Technology Experience Zeroing (Violation of Requirement R4)**:
   - Question `How many years of experience do you have in .Net Core?` on Naukri logged `answer: '0'` (confidence: `form_filled`).
   - Question `Rel Exp in .Netcore:` on Naukri logged `answer: '0'`.
   - Root code observation in `config/qa_patterns.json`:
     Lines 2125-2135: `"dotnet_core_exp": {"patterns": ["how many years of experience do you have in .net core?", ...], "category": "experience", "default": "0", "priority": 20}`
   - Requirement R4 in `ORIGINAL_REQUEST.md` explicitly requires: *"Strictly preserve candidate total experience (4.2 Years / 4) for Calypso, .NET/C#, and AEM backend questions without zeroing them out."*

5. **Option Mismatches in Radio & Select Groups**:
   - Naukri radio questions selected minimum brackets for core candidate skills (candidate has 4.2 years):
     - `How much experience you hold in Java` -> selected `0 - 2 yrs`
     - `How much experience you hold in React.Js?` -> selected `0 - 0.6 months`
     - `How much experience you hold in Cloud?` -> selected `0 - 6 months`
     - `How many years of experience do you have in Microservices?` -> selected `0 - 6 months`
   - Select dropdown questions asking for experience durations were answered with binary `'Yes'`:
     - `How many years of experience in Agentic AI?` -> `Yes`
     - `How many years of experience in Full Stack Development?` -> `Yes`
     - `How many years of experience in Azure, Docker, Kubernetes, and GitHub?` -> `Yes`

6. **Candidate Profile Violations & Fallback Inversions**:
   - Capability: `Can you independently diagnose and solve technical problems?` -> answered `No`.
   - Education: `Have you completed the following level of education: Master of Business Administration?` -> answered `yes` (Candidate has B.Tech in CS).
   - Referral: `Were you referred by an internal Xometry employee?` -> answered `yes`, prompting follow-up `please provide the employee’s first and last name` -> answered `Singh` (candidate last name).
   - Ex-employee: `Have you been previously employed with Freshworks?` -> answered `yes` (Candidate currently works at Everbridge).
   - Designation: `Your title` -> answered `Android Lead` instead of `Software Engineer 2`.
   - Company: `Company` -> answered `DSC VIT Bhopal` instead of `Everbridge`.
   - Portfolio vs GitHub: `Github link` -> answered `https://siddhant3646.github.io/Portfolio/` instead of `https://github.com/siddhant3646`.
   - Rating scale: `Rate your proficiency (1-5) in our core stack: React.js, Next.js, and React Native.` -> answered `9`.
   - Notice period: `Please confirm the notice period(7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)?...` -> answered `4` (years of experience).
   - Compound CTC: `CTC: Current & Expected?` on Naukri -> answered `3000000` (omitted Current CTC 2300000).
   - Instahyre Expected CTC: `What is your Expected CTC?` -> answered `30` instead of `30 LPA`.

---

## 2. Logic Chain
1. *From Observation 1 & 2*: 957 out of 1,275 rows in `qa_results.csv` are duplicates generated by a single LinkedIn job application (`currentJobId=4440014488`). The root cause was that `Specify your relevant years of experience` and `Gender` had Spanish prompt options (`Selecciona una opción`). Because Sentinel's select option extractor did not recognize foreign-language placeholders as invalid, it selected the placeholder. LinkedIn's client-side validation failed form submission, causing Sentinel's 118-iteration watchdog loop to re-attempt and re-log all fields on the step.
2. *From Observation 3*: Textareas for Yes/No questions (e.g. Bangalore location, fast-paced culture) and compensation/notice period questions received a 508-character technical essay because line 10529 in `agent.py` explicitly executes a regex check: `(!answer || /^(\d+(\.\d+)?(\s*years?)?|yes|no)$/i.test(answer.trim()))`. When an answer is concise ('Yes', '15', etc.), this condition evaluates to true and unconditionally clobbers `answer` with the static engineering blurb.
3. *From Observation 4*: In `config/qa_patterns.json`, `dotnet_core_exp` was assigned priority 20 and `default: 0`. In `PatternMatcher.fuzzy_match()`, priority 20 overrides lower-priority generic experience rules (priority 3), returning 0. This directly contradicts Requirement R4 of `ORIGINAL_REQUEST.md`.
4. *From Observation 5*: In radio button range parsing, option labels like `"0 - 2 yrs"` were matched because the range matcher matched the lowest index or sub-string containing 0 rather than performing numerical boundary checking (`min <= 4.2 <= max`). Similarly, select dropdowns for experience matched generic affirmative patterns (`'Yes'`) when the dropdown actually expected an experience bracket.
5. *From Observation 6*: Questions containing words like 'diagnose' or 'solve problems' hit negative compliance fallbacks; referral and ex-employee questions fell through to broad affirmative defaults ('yes'); and candidate profile keys (Title, Company, GitHub) mapped to wrong profile attributes or fallbacks.

---

## 3. Caveats
1. **No Source Code Modifications Made**: Per the Spec Miner scope boundaries, all source files in `src/`, `config/`, and `tests/` remain completely untouched. Implementation belongs to downstream engineering agents.
2. **Live Browser Environment**: Certain runtime behaviors (e.g. LinkedIn XHR typeahead for city auto-complete and Spanish language selection) reflect the specific state of the DOM during that recorded execution. Future forms may present options in other languages unless generic placeholder detection is implemented.
3. **No failure_log.jsonl Found**: In `/Users/siddhant/Desktop/sentinel_errors/`, only `qa_results.csv` was present. The failure JSONL was either cleaned up or not configured for this specific run session.

---

## 4. Conclusion
A total of **29 unique question discrepancies** were discovered across 171 unique questions, affecting **271+ logged rows** (and triggering a 944-row submission retry loop).
To achieve 100% compliance with `ORIGINAL_REQUEST.md`:
1. **Pattern Engineering**: Update `dotnet_core_exp` from `0` to `4.2 Years` (with `4` for LinkedIn and numeric defaults) and add patterns for `rel_exp_dotnetcore`, `aem_backend_experience`, `diagnose_and_solve_problems`, `education_mba_degree` (No), `confirm_notice_period_digits` (15), `rate_proficiency_scale_5` (5), and `ctc_current_and_expected_compound`.
2. **Textarea Guard Fix**: Refactor `agent.py:10528-10532` so that concise answers for Yes/No, location, compensation, and notice period are preserved and not overwritten with technical essays.
3. **Dropdown & Radio Range Calibration**: Filter out placeholder options (including `Selecciona una opción`) and ensure `NumericRangeMatcher` correctly maps 4.2 years to appropriate option intervals.

---

## 5. Verification Method
1. **Audit Report Inspection**:
   - Inspect `/Users/siddhant/Desktop/Resume/MyModels/A_N&L/.agents/spec_miner_csv/audit_report.md` to review the full 32-row discrepancy table and summary statistics.
2. **Independent CSV Row Count & Question Count Verification**:
   ```bash
   python3 -c "
   import csv
   with open('/Users/siddhant/Desktop/sentinel_errors/qa_results.csv') as f:
       rows = list(csv.DictReader(f))
   print(f'Total rows: {len(rows)}')
   print(f'Unique questions: {len(set(r["question"].strip() for r in rows))}')
   "
   ```
   *Expected output*: Total rows: 1275, Unique questions: 171.
3. **Verification of Zeroed .Net Pattern**:
   ```bash
   python3 -c "
   import json
   with open('config/qa_patterns.json') as f:
       p = json.load(f)['patterns']['dotnet_core_exp']
   print(p['default'], p['priority'])
   "
   ```
   *Expected output*: 0 20 (proves why .Net Core was zeroed out).
4. **Verification of Textarea Essay Override**:
   ```bash
   sed -n '10528,10533p' src/sentinel/agent.py
   ```
   *Expected output*: Regex checking `input.tagName === 'TEXTAREA'` and replacing with 508-char essay.
