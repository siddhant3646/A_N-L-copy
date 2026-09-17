# Comprehensive Sentinel Q&A Audit Report: qa_results.csv Analysis

## Executive Summary
This report presents a rigorous, complete audit of all **1,275 logged entries** in `/Users/siddhant/Desktop/sentinel_errors/qa_results.csv` (generated during Sentinel automation runs across LinkedIn, Naukri, and Instahyre). The objective is to identify, classify, and systematically document every question answered incorrectly, with inappropriate fallbacks, with option/placeholder mismatches, or with excessive essay dumping.

### Key Audit Highlights
- **1,275 total logged rows** audited across **37 distinct job application URLs**.
- **171 unique question texts** cataloged and cross-referenced against the candidate profile (`AGENTS.md`) and `config/qa_patterns.json`.
- **29 distinct question discrepancies** identified, directly causing hundreds of misapplications and a catastrophic 118-iteration retry loop on a Freshworks LinkedIn job.
- **Root Causes Isolated**:
  1. **Textarea Essay Overwriting**: `src/sentinel/agent.py:10529-10532` unconditionally replaces valid concise answers (such as 'Yes' or '15') with a 508-character technical essay whenever `input.tagName === 'TEXTAREA'`.
  2. **Spanish Placeholder Trap**: In job `4440014488` (Freshworks), LinkedIn Easy Apply rendered Spanish placeholder options (`'Selecciona una opción'`). Sentinel selected the unselected placeholder 236 times (118 times for experience, 118 times for gender), resulting in validation errors and a 118-step submission loop generating 957 log entries.
  3. **Technology Experience Zeroing (R4 Violation)**: `config/qa_patterns.json` explicitly contains `dotnet_core_exp` with `default: 0` and `priority: 20`, causing questions on `.Net Core` and `.Netcore` to be answered with `0` instead of preserving candidate total experience (4.2 Years / 4).
  4. **Radio Range Matching Collapse**: Dropdown/radio matchers selected lowest experience brackets (`'0 - 6 months'`, `'0 - 2 yrs'`) for core tech skills (Java, React, Cloud, Microservices) where candidate has 4.2 years.
  5. **Affirmative Misclassification of Exclusion Questions**: Questions like 'Were you referred by an internal Xometry employee?', 'Have you been previously employed with Freshworks?', and 'Master of Business Administration' defaulted to 'yes'.
  6. **Capability Question Inversion**: 'Can you independently diagnose and solve technical problems?' was answered 'No'.
  7. **Entity & Profile Hallucinations**: 'Your title' was logged as 'Android Lead'; 'Company' was logged as 'DSC VIT Bhopal'; 'Github link' was populated with GitHub Pages portfolio URL.

---

## 1. High-Level Summary Statistics

### 1.1 Row Distribution by Platform
| Platform Label | Total Logged Rows | Distinct Questions | Distinct URLs | Percent of Total Rows |
|---|---|---|---|---|
| **linkedin** (submission payload logging) | 939 | 11 | 1 | 73.65% |
| **LinkedIn_Form** (step-by-step form filler) | 206 | 125 | 35 | 16.16% |
| **naukri** (chatbot & quick apply) | 126 | 44 | 1 | 9.88% |
| **instahyre** (questionnaire) | 4 | 2 | 1 | 0.31% |
| **TOTAL** | **1,275** | **171** | **37** | **100.00%** |

*Note on LinkedIn platforms*: `linkedin` rows represent bulk Q&A payloads dumped upon clicking Submit (lines 3670-3682 in `agent.py`), while `LinkedIn_Form` rows represent field-by-field filling during form navigation (lines 3724-3736).

### 1.2 Input Type Distribution
| Input Type | Total Rows Audited | Discrepancy Rows Detected | Primary Failure Mode |
|---|---|---|---|
| **text** | 852 | 13 | Technology zeroing, title/company mismatch, compound CTC failure |
| **select** (including custom variants) | 303 | 240 | Spanish placeholder selection (236 rows), Yes/No answering experience dropdowns |
| **button** | 81 | 0 | Accurately selected Bangalore/Hyderabad relocation chips |
| **radio** | 25 | 9 | Selected 0-6mo ranges, false affirmative referral/ex-employee answers |
| **textarea** | 12 | 7 | Generic 508-char technical essay dumped into Yes/No, salary, and NP fields |
| **checkbox** | 2 | 0 | Correctly checked compliance/relocation checkboxes |
| **TOTAL** | **1,275** | **269+** | *(Excluding duplicate loop repeats of valid fields in job 4440014488)* |

### 1.3 Error Count by Category
| Discrepancy Category | Unique Questions | Affected Logged Rows | Severity |
|---|---|---|---|
| **Option & Placeholder Mismatches** | 8 | 243 | CRITICAL (Causes form rejection & infinite loops) |
| **Textarea Essay Overwriting** | 6 | 7 | HIGH (Unprofessional submission, candidate disqualification) |
| **Candidate Profile & Fallback Failures** | 10 | 14 | HIGH (Incorrect PII, wrong credentials, false claims) |
| **Preserved Tool Rules / Tech Zeroing** | 2 | 2 | HIGH (Direct violation of Requirement R4) |
| **Platform CTC & Compound Field Nuances** | 3 | 5 | MEDIUM (Formatting inconsistency, missing component) |
| **TOTAL** | **29** | **271** | — |

---

## 2. Comprehensive Discrepancy Catalog

The following table catalogs every question in `qa_results.csv` exhibiting incorrect values, option mismatches, low confidence, or inappropriate fallbacks.

| # | Platform | Question Text (verbatim) | Input Type | Logged Answer & Conf | Failure Reason / Discrepancy | Expected Correct Answer | Recommended Pattern Key | Category | Priority |
|---|---|---|---|---|---|---|---|---|---|
| 1 | LinkedIn_Form | `This role requires you to be in Bengaluru. Are you okay with that?` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Yes/No location confirmation received 508-character technical essay due to `agent.py:10529` override. | `Yes` (or concise: "Yes, I am based in Bengaluru and available to work on-site.") | `role_location_bengaluru_textarea` | location | 18 |
| 2 | LinkedIn_Form | `We're incredibly fast-paced. We do whatever it takes to get things done. Would you be aligned with this aspect?` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Yes/No cultural alignment question received generic 508-character technical essay. | `Yes` (or concise: "Yes, I thrive in fast-paced, high-ownership environments.") | `work_culture_fast_paced_alignment` | behavioral | 18 |
| 3 | LinkedIn_Form | `What is your current compensation? Would be great if you can highlight your expected compensation as well.` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Combined compensation question received engineering summary instead of structured salary figures. | `Current CTC: 23 LPA, Expected CTC: 30 LPA (Fixed)` | `current_and_expected_ctc_textarea` | salary | 19 |
| 4 | LinkedIn_Form | `How quickly can you join us if shortlisted?` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Notice period question received engineering essay instead of notice duration. | `15 days (serving notice period)` | `joining_availability_textarea` | notice_period | 18 |
| 5 | LinkedIn_Form | `Have you been the main or only developer on a product that real users used? If yes, which one and what were you responsible for keeping running after launch?` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Specific product ownership question received generic resume blurb without answering the prompt. | `Yes, led backend engineering for critical services at Everbridge, managing microservices architecture and production reliability.` | `lead_developer_product_ownership` | technical | 16 |
| 6 | LinkedIn_Form | `Show a piece of UI you built from a design. How close did the final result come to the design, and how did you handle responsiveness?` | textarea | 4+ years of professional full-stack software engineering... [Keyword Match] | **Textarea Essay Dump**: Frontend design fidelity question received generic backend/fullstack essay. | `Built enterprise dashboards in React.js matching Figma specs with pixel-perfect responsive layouts using CSS flex/grid and Tailwind.` | `ui_design_fidelity_responsiveness` | technical | 16 |
| 7 | LinkedIn_Form | `Describe one product or feature you owned end to end, from idea to production. What was your specific role, and what did you decide yourself?` | textarea | `SDE-2 (Professional Software Developer)` [Keyword Match] | **Inappropriate Fallback**: 39-character job title dumped into complex open-ended product ownership question. | `Architected and deployed distributed notification pipelines at Everbridge using Spring Boot and Kafka, reducing latency by 40%.` | `product_feature_owned_end_to_end` | technical | 17 |
| 8 | LinkedIn_Form / linkedin | `Specify your relevant years of experience ` | select | `Selecciona una opción` [Keyword Match / form_filled] | **Option Mismatch (Placeholder)**: Selected Spanish placeholder 118 times, triggering submission failure and infinite form loop. | `3-6 years` (or `4 years` / `4`) | `select_relevant_years_experience` | experience | 18 |
| 9 | LinkedIn_Form / linkedin | `Gender ` | select-self-id / select | `Selecciona una opción` [Keyword Match / form_filled] | **Option Mismatch (Placeholder)**: Selected Spanish placeholder 118 times, preventing valid submission. | `Male` | `gender_self_id_spanish_resilient` | personal_info | 18 |
| 10 | LinkedIn_Form | `How many years of experience in Agentic AI?` | select | `Yes` [Keyword Match] | **Option Mismatch**: Years of experience dropdown answered with binary string 'Yes' instead of numeric experience range. | `1 year` (or `1-2 years` / `4`) | `exp_agentic_ai_years` | experience | 17 |
| 11 | LinkedIn_Form | `How many years of experience in Full Stack Development?` | select | `Yes` [Keyword Match] | **Option Mismatch**: Select dropdown for Full Stack experience answered with 'Yes' instead of experience duration. | `4 years` (or `3-5 years`) | `exp_full_stack_select` | experience | 18 |
| 12 | LinkedIn_Form | `How many years of experience in Azure, Docker, Kubernetes, and GitHub?` | select | `Yes` [Keyword Match] | **Option Mismatch**: Tool experience dropdown answered with 'Yes' instead of experience duration. | `4 years` (or `3-5 years`) | `exp_cloud_devops_select` | experience | 17 |
| 13 | naukri | `How many years of experience do you have in Microservices?` | radio | `0 - 6 months` [form_filled] | **Option Mismatch (Undervalued)**: Radio matcher selected entry-level option (0-6 mo) for core candidate competency (4.2 years). | `3 - 5 yrs` (or highest match <= 4.2 yrs) | `naukri_radio_microservices_exp` | experience | 18 |
| 14 | naukri | `How much experience you hold in Cloud?` | radio | `0 - 6 months` [form_filled] | **Option Mismatch (Undervalued)**: Radio matcher selected 0-6 months for AWS cloud skill where candidate has 4.2 years. | `3 - 5 yrs` (or `4.2 Years`) | `naukri_radio_cloud_exp` | experience | 18 |
| 15 | naukri | `How much experience you hold in IAM Roles and Python (Fast API)?` | radio | `0 - 6 months` [form_filled] | **Option Mismatch (Undervalued)**: Radio matcher selected lowest bracket for Python/IAM. | `3 - 5 yrs` (or `4.2 Years`) | `naukri_radio_python_iam_exp` | experience | 17 |
| 16 | naukri | `How much experience you hold in Java` | radio | `0 - 2 yrs` [form_filled] | **Option Mismatch (Undervalued)**: Candidate has 4.2 years in Java (primary stack); selected 0-2 yrs bracket instead of 4+ yrs. | `4 - 6 yrs` (or `3 - 5 yrs`) | `naukri_radio_java_exp` | experience | 19 |
| 17 | naukri | `How much experience you hold in React.Js?` | radio | `0 - 0.6 months` [form_filled] | **Option Mismatch (Undervalued)**: Candidate has 4.2 years in React.js; selected 0-0.6 months option. | `3 - 5 yrs` (or `4+ yrs`) | `naukri_radio_react_exp` | experience | 19 |
| 18 | naukri | `How many years of experience do you have in .Net Core?` | text | `0` [form_filled] | **Tool Rule Violation (R4)**: Zeroed out due to `dotnet_core_exp` pattern (priority 20). Must strictly preserve 4.2 Years. | `4.2 Years` | `dotnet_core_exp` (update default) | experience | 20 |
| 19 | naukri | `Rel Exp in .Netcore:` | text | `0` [form_filled] | **Tool Rule Violation (R4)**: Zeroed out to 0 instead of preserving candidate experience. | `4.2 Years` | `rel_exp_dotnetcore` | experience | 18 |
| 20 | LinkedIn_Form | `Can you independently diagnose and solve technical problems?` | select | `No` [Keyword Match] | **Capability Inversion**: SDE answered 'No' to core diagnostic capability, guaranteeing disqualification. | `Yes` | `diagnose_and_solve_problems` | skills | 19 |
| 21 | LinkedIn_Form | `Were you referred by an internal Xometry employee? 
Required` | radio | `yes` [Keyword Match] | **Erroneous Affirmative**: Cold applicant answered 'Yes', triggering invalid follow-up referee name. | `No` | `referred_by_internal_employee` | compliance | 20 |
| 22 | LinkedIn_Form | `If you answered yes to the last question, please provide the employee’s first and last name` | text | `Singh` [Keyword Match] | **Cascading Hallucination**: Answered with candidate last name because upstream referral was falsely affirmative. | `N/A` (or empty once upstream fixed) | `internal_referral_employee_name` | personal_info | 18 |
| 23 | LinkedIn_Form | `Have you been previously employed with Freshworks? 
Required` | radio | `yes` [Keyword Match] | **False Ex-Employee Claim**: Candidate never worked at Freshworks (currently at Everbridge). Should be 'No'. | `No` | `ex_employee_freshworks` | compliance | 19 |
| 24 | LinkedIn_Form | `Have you completed the following level of education: Master of Business Administration? 
Required` | radio | `yes` [Keyword Match] | **False Academic Credential**: Candidate holds B.Tech in CS; falsely claimed MBA degree. | `No` | `education_mba_degree` | education | 19 |
| 25 | LinkedIn_Form | `Please confirm the notice period(7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)? 2 or 3 months candidates can ignore this role?` | text | `4` [Keyword Match] | **Category Confusion**: Notice period answered with experience digits ('4') instead of candidate notice duration (15). | `15` | `confirm_notice_period_digits` | notice_period | 19 |
| 26 | LinkedIn_Form | `Rate your proficiency (1-5) in our core stack: React.js, Next.js, and React Native.` | text | `9` [Keyword Match] | **Rating Scale Overflow**: Scale 1-5 received '9' (matched generic 1-10 rating rule or DSA scale). | `5` (or `4`) | `rate_proficiency_scale_5_react` | skills | 19 |
| 27 | LinkedIn_Form | `Do you have hands-on experience with SQL, or are you familiar with SQL cpncepts?` | text | `4` [Keyword Match] | **Format Mismatch**: Yes/No question answered with numeric '4' due to keyword matching on 'SQL experience'. | `Yes` | `sql_hands_on_or_familiar_yn` | skills | 18 |
| 28 | LinkedIn_Form | `Github link` | text | `https://siddhant3646.github.io/Portfolio/` [Keyword Match] | **Entity Mapping Discrepancy**: GitHub profile link populated with GitHub Pages portfolio URL instead of GitHub repo profile. | `https://github.com/siddhant3646` | `github_profile_link` | personal_info | 19 |
| 29 | LinkedIn_Form | `Your title` | text | `Android Lead` [Keyword Match] | **Designation Hallucination**: Current title answered as 'Android Lead' instead of candidate role 'Software Engineer 2'. | `Software Engineer 2` (or `SDE-2`) | `current_job_title_exact` | personal_info | 19 |
| 30 | LinkedIn_Form | `Company` | text | `DSC VIT Bhopal` [Keyword Match] | **Employer Mismatch**: Answered college student club instead of current employer 'Everbridge'. | `Everbridge` | `current_company_name_exact` | personal_info | 19 |
| 31 | naukri | `CTC: Current & Expected?` | text | `3000000` [form_filled] | **Compound CTC Omission**: Question asks for Current & Expected; answered only expected salary (3000000), omitting Current (2300000). | `2300000 / 3000000` (or `23 LPA / 30 LPA`) | `ctc_current_and_expected_compound` | salary | 19 |
| 32 | instahyre | `What is your Expected CTC?` | text | `30` [pattern_fallback] | **Platform Format Inconsistency**: Instahyre requires '30 LPA' but received bare integer '30'. Fell back to pattern_fallback. | `30 LPA` | `instahyre_expected_ctc_lpa` | salary | 18 |

---

## 3. Deep-Dive Root Cause Analysis

### 3.1 Textarea Essay Fallback (`src/sentinel/agent.py:10528-10532`)
In `agent.py`, lines 10528-10532 contain an aggressive textarea override intended to prevent single digits from appearing in descriptive textareas:
```javascript
// Textarea essay fallback (avoid single digits like 4.2 or 5 in descriptive textareas)
if (input.tagName === 'TEXTAREA' && (!answer || /^(\d+(\.\d+)?(\s*years?)?|yes|no)$/i.test(answer.trim()))) {
    answer = '4+ years of professional full-stack software engineering experience specializing in distributed systems...';
    window.__SENTINEL_DEBUG__&&console.log('Provided technical summary for textarea field:', labelText);
}
```
**Why this fails**:
- If a recruiter places a simple Yes/No question in a `<textarea>` (e.g. *"This role requires you to be in Bengaluru. Are you okay with that?"* or *"Would you be aligned with this aspect?"*), `fuzzyMatch` correctly resolves to `"Yes"`.
- But because `input.tagName === 'TEXTAREA'` and `answer` matches `/^(yes|no)$/i`, Sentinel erases `"Yes"` and replaces it with the 508-character engineering summary essay!
- Similarly, notice period (*"15"*) and compensation queries matching digits get erased and overwritten with the technical essay.

### 3.2 Spanish Placeholder Trap & The 118-Attempt Loop (Job 4440014488)
In LinkedIn job `4440014488` (Freshworks SDE role), the page contained Spanish localized form labels/placeholders:
- `Specify your relevant years of experience` had dropdown options including `Selecciona una opción` (Select an option) and `3-6 years`.
- `Gender` had `Selecciona una opción` and `Male`.
- In `agent.py` select handler, `fuzzyMatch` or option extraction failed to recognize `Selecciona una opción` as an unselected prompt placeholder. Sentinel selected or kept the placeholder option.
- When Sentinel clicked "Submit", LinkedIn's HTML5 / Angular form validation halted the submit with an error.
- Sentinel's loop retry mechanism re-attempted the form 118 times, re-logging every field on the step (RSU, CTC, nationality, motivation, etc.) 118 times before timing out.
- **Resolution**: Dropdown handlers must explicitly filter out placeholder strings across all languages (`select an option`, `selecciona una opción`, `choose`, `select...`) and enforce selecting a valid option.

### 3.3 Technology Experience Zeroing (Violation of Requirement R4)
In `config/qa_patterns.json`, lines 2125-2135:
```json
"dotnet_core_exp": {
  "patterns": [
    "how many years of experience do you have in .net core?",
    "how many years of experience do you have in .net core",
    "how many years of experience do you have in dotnet core"
  ],
  "category": "experience",
  "default": "0",
  "priority": 20
}
```
- Because `dotnet_core_exp` has priority **20** and `default: "0"`, it overrode the candidate's general experience rule and answered `0` on Naukri.
- Furthermore, `Rel Exp in .Netcore:` was also zeroed out.
- **Requirement R4 Mandate**: "Strictly preserve candidate total experience (4.2 Years / 4) for Calypso, .NET/C#, and AEM backend questions without zeroing them out."
- **Resolution**: `dotnet_core_exp` default must be set to `4.2 Years` (with `4` for LinkedIn whole number rules), `rel_exp_dotnetcore` added with 4.2 Years, and AEM backend experience added to ensure zeroing never occurs.

### 3.4 Radio Button Numeric Range Matching Collapse
In Naukri chatbot applications, questions like `How much experience you hold in Java` presented radio options such as `["0 - 2 yrs", "2 - 4 yrs", "4 - 6 yrs", "6+ yrs"]`.
- Sentinel matched `0 - 2 yrs` instead of the appropriate 4.2-year bracket (`4 - 6 yrs`).
- Similarly, for Cloud, Microservices, and React.js, Sentinel selected `0 - 6 months` or `0 - 0.6 months`.
- **Resolution**: `NumericRangeMatcher` in `input_aware_resolver.py` and the chatbot JS radio selector in `agent.py` must accurately compute candidate years (4.2) against range boundaries `[min, max]` and select the interval containing 4.2 (i.e. 4 - 6 yrs or 3 - 5 yrs).

### 3.5 Capability & Diagnostic Inversion
Question: `Can you independently diagnose and solve technical problems?`
- Answered: `No`
- Cause: `agent.py` Phase 0.1 compliance or negative indicator regex erroneously flagged words like `problems` or `diagnose` as negative compliance items (like disciplinary/criminal/conflict checks) or matched a negative default.
- **Resolution**: Independent problem solving and troubleshooting are essential positive engineering competencies. They must have dedicated high-priority positive intercepts returning `Yes`.

---

## 4. Standard Specification Miner Findings

### 4.1 Features Discovered
| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|---|---|---|---|---|---|---|
| 1 | Textarea Guard | Input-Aware Textarea Routing | Directs textarea questions to concise answers for Yes/No, Location, Salary, Notice Period rather than default essay | Form question string, `input_type='textarea'` | Concise string (e.g. "Yes", "15 days") | Defaults to 508-char essay if regex matches single word | `agent.py:10529` & CSV audit |
| 2 | Preserved Tool Rules | Calypso Experience | Preserves candidate total experience for Calypso queries | Calypso experience question | `4.2 Years` (Naukri) / `4` (LinkedIn) | Never 0 | `qa_patterns.json` & R4 spec |
| 3 | Preserved Tool Rules | .NET / C# Experience | Preserves candidate total experience for .NET Core / C# queries | .NET Core, .Netcore, C# questions | `4.2 Years` (Naukri) / `4` (LinkedIn) | Was returning 0 due to `dotnet_core_exp` priority 20 | CSV rows 61, 132 & `qa_patterns.json` |
| 4 | Preserved Tool Rules | AEM Experience | Preserves candidate total experience for Adobe Experience Manager backend queries | AEM backend questions | `4.2 Years` (Naukri) / `4` (LinkedIn) | Unhandled if missing from JSON | ORIGINAL_REQUEST.md R4 |
| 5 | Form Filling | Multi-Language Dropdown Disambiguation | Prevents selecting placeholder options like 'Selecciona una opción' or 'Select an option' | `<select>` DOM options | Non-placeholder matching option | Selected placeholder 118 times causing retry loop | Job 4440014488 in CSV |
| 6 | Form Filling | Radio Numeric Range Matching | Matches 4.2 years into bracketed radio intervals (e.g. '3-5 years', '4-6 years') | Array of range labels, candidate experience (4.2) | Best matching range option | Selected lowest option '0-6 months' / '0-2 yrs' | Naukri radio rows in CSV |
| 7 | Profile Mapping | Accurate Job Title Resolution | Maps title questions strictly to 'Software Engineer 2' (SDE-2) | 'Your title', 'Designation' | `Software Engineer 2` | Returned 'Android Lead' | Row 260 in CSV |
| 8 | Profile Mapping | Current Employer Resolution | Maps company questions to 'Everbridge' | 'Company', 'Current employer' | `Everbridge` | Returned 'DSC VIT Bhopal' | Row 261 in CSV |
| 9 | Profile Mapping | GitHub Repo URL Resolution | Maps GitHub questions to candidate GitHub profile | 'Github link', 'GitHub profile' | `https://github.com/siddhant3646` | Returned GitHub Pages portfolio link | Row 262 in CSV |
| 10 | Compliance | Referral Negative Intercept | Answers 'No' to internal employee referral without valid referee | 'Were you referred by an internal employee' | `No` | Returned 'yes' and asked for referee name | Row 147 in CSV |
| 11 | Compliance | Ex-Employee Negative Intercept | Answers 'No' to having previously worked at applying company | 'Have you been previously employed with Freshworks' | `No` | Returned 'yes' | Row 53 in CSV |
| 12 | Education | Negative Degree Intercept | Answers 'No' to unearned degrees (MBA, PhD) while preserving B.Tech in CS | 'Master of Business Administration' | `No` | Returned 'yes' | Row 55 in CSV |
| 13 | Rating Scale | Bounded Scale Normalization | Normalizes 1-5 rating questions to max 5 (instead of 9 or 10) | 'Rate your proficiency (1-5)...' | `4` or `5` | Returned '9' (out of scale) | Row 130 in CSV |
| 14 | Compensation | Compound CTC Splitting | Answers both current and expected CTC when combined in one field | 'CTC: Current & Expected?' | `2300000 / 3000000` | Returned only expected (3000000) | Row 17 in CSV |
| 15 | Platform Rules | Instahyre LPA Format | Ensures Instahyre salary questions include 'LPA' suffix | 'What is your Expected CTC?' on Instahyre | `30 LPA` | Returned bare '30' | Rows 150-151 in CSV |

### 4.2 Edge Cases Discovered
| # | Feature | Input | Observed Behavior | Required Behavior |
|---|---|---|---|---|
| 1 | Textarea Answering | `This role requires you to be in Bengaluru. Are you okay with that?` (textarea) | Replaced "Yes" with 508-char technical summary | Return concise affirmative "Yes" or "Yes, based in Bengaluru" |
| 2 | Dropdown Selection | `Specify your relevant years of experience` in Spanish locale | Selected first option `Selecciona una opción` | Skip placeholder options; select `3-6 years` |
| 3 | Dropdown Selection | `Gender` in Spanish locale | Selected first option `Selecciona una opción` | Skip placeholder options; select `Male` |
| 4 | Radio Selection | `How much experience you hold in Java` with options `["0 - 2 yrs", "2 - 4 yrs", "4 - 6 yrs"]`. | Selected `0 - 2 yrs` | Compare 4.2 against `[4, 6]` and select `4 - 6 yrs` |
| 5 | Tech Experience | `How many years of experience do you have in .Net Core?` | Returned `0` via `dotnet_core_exp` priority 20 | Return candidate experience `4.2 Years` (Naukri) / `4` (LinkedIn) |
| 6 | Rating Field | `Rate your proficiency (1-5) in our core stack: React.js, Next.js...` | Returned `9` | Respect (1-5) scale upper bound; return `5` |
| 7 | Notice Period | `Please confirm the notice period(7 days, 15 days, 30, 60 or 90 days Just put 2 digit number)?...` | Returned `4` (years of experience) | Extract notice period intent; return `15` |
| 8 | Technical Screening | `Can you independently diagnose and solve technical problems?` | Returned `No` | Return affirmative `Yes` |
| 9 | Referral Checking | `Were you referred by an internal Xometry employee?` | Returned `yes`, causing subsequent question `provide employee's first and last name` -> `Singh` | Return `No`, terminating referral branch |
| 10 | Compound CTC | `CTC: Current & Expected?` (single text input) | Returned `3000000` | Return composite string `2300000 / 3000000` |

---

## 5. Summary Recommendations for Downstream Agents

1. **For Pattern Engineer (`explorer_patterns`)**:
   - Update `dotnet_core_exp` in `config/qa_patterns.json` from `default: 0` to `default: 4.2 Years` (with `4` for LinkedIn and numeric defaults).
   - Add dedicated patterns for:
     - `rel_exp_dotnetcore` -> `4.2 Years` / `4`
     - `aem_backend_experience` -> `4.2 Years` / `4`
     - `diagnose_and_solve_problems` -> `Yes` (priority 19)
     - `referred_by_internal_employee` (ensure priority 20 overrides affirmative defaults)
     - `education_mba_degree` -> `No` (priority 19)
     - `current_and_expected_ctc_compound` -> `2300000 / 3000000` (priority 19)
     - `rate_proficiency_scale_5` -> `5` (priority 19)
     - `confirm_notice_period_digits` -> `15` (priority 19)

2. **For Textarea & Input Guard Engineer (`explorer_textarea` & Agent refactor)**:
   - In `src/sentinel/agent.py:10528-10532`, dismantle the unconditional regex replacement that overwrites `yes`, `no`, or numeric answers with the 508-char technical essay.
   - Implement intelligent textarea classification:
     - If question is Yes/No (location, travel, alignment) -> retain concise affirmative answer.
     - If question is Compensation / Notice Period -> retain concise salary/notice figures.
     - Only inject technical essay when the textarea explicitly requests candidate overview, cover letter, why hire you, or background summary.

3. **For Dropdown & Form Handler Optimization**:
   - Update select dropdown matching in `src/sentinel/agent.py` to ignore localized placeholder options (`'selecciona una opción'`, `'select an option'`, etc.).
   - Prevent infinite 118-step retry loops on LinkedIn form submission by improving stuck-modal detection and preventing repeated submissions of rejected placeholder values.
   - Calibrate `NumericRangeMatcher` to correctly map 4.2 years to matching range brackets for radio button groups.
