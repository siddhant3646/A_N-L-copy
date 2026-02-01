"""
Prompts and Context for Sentinel Agent.
"""



COMMON_CONTEXT = """
SYSTEM INSTRUCTIONS:
1. **VISUAL FEEDBACK**: You will receive a static screenshot after every action.
2. **ACT IMMEDIATELY**: Do not wait for permission. Use tools now.
3. **CONTEXT**: Date: Jan 01, 2026. Joining: Jan 18, 2026.
4. **GOAL**: Complete the assigned task efficiently.
5. **VALIDATOR FEEDBACK**: If your action is VETOED, do NOT give up. Read the veto message, adjust your parameter (e.g., use `extract` instead of `click`), and try again.
6. **STRICT FOCUS**: You are only allowed to interact with the target portal (Naukri/LinkedIn). Ignore ALL external ads, blog links, or articles.
"""

NAUKRI_JOB_APPLY_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com/mnjuser/recommendedjobs immediately.

VERIFY you are on the site. If stuck on a generic landing page, refresh or re-navigate.

STRICT UI IDENTIFICATION:
1. CHECKBOXES: Locate the <div class="dspIB saveJobContainer tuple-check-box">. Click the <i> element inside that div.
2. APPLY BUTTON: Look for the container <span class="fright">. Inside it, find the button: <button class="multi-apply-button typ-16Bold "> (It often says "Apply 1 Job").
3. TARGET ROLES: "Java Developer", "FullStack Developer", "Full Stack Developer", "ReactJs Developer", "React Developer", "NodeJs", "NodeJs Developer", "React", "Java", "Full Stack", or "MERN".

ERROR HANDLING RULES (CRITICAL):
1. **IF VETOED (BLOCKED):**
   - **DO NOT NAVIGATE.** DO NOT REFRESH. DO NOT RESET.
   - A Veto is just a request for verification.
   - **ACTION:** Immediately use `find_text("Save")` or `extract` to find the correct element index again.
   - **THEN:** Click the NEW index returned by the tool.

2. **BLINDNESS RECOVERY:**
   - If `extract` returns empty or you can't see the element:
   - **ACTION:** `scroll(down=True, pages=0.5)` -> `wait(seconds=2)`.
   - **NEVER** scroll more than 1 page at a time.

CORE WORKFLOW (STRICT SEQUENCE):
1. SELECTION:
   - Identify the FIRST job card matching "TARGET ROLES".
   - **CRITICAL:** Verify the job card has a visible checkbox <i>. If NO checkbox (e.g. Saved job), SKIP it and find the next match.
   - Click the <i> checkbox for THAT ONE JOB ONLY.
   - **APPLY BAR:** If the blue "Apply" bar is not visible, `scroll(down=True, pages=0.5)` to find it.
   - CLICK the "Apply" button.

2. EXECUTION:
   - LOCATE the button using `button[class="multi-apply-button typ-16Bold"]` or text "Apply 1 Job".
   - CLICK the "Apply" button.
   - **IMMEDIATELY STOP** and scan for the "chatbot_DrawerContentWrapper" (the questionnaire modal).

3. MODAL HANDLING (STRICT):
   - **CRITICAL:** Do NOT try to find the container `chatbot_DrawerContentWrapper`.
   - **INSTEAD:** Immediately after clicking "Apply", look for **TEXT** on the screen.

   - **SCENARIO A (Diversity/Career Break):**
     - IF you see text "Are you on a career break?" or "companies value diversity":
     - **ACTION:** Click the "No" button immediately.
     - **WAIT:** 2 seconds for the next modal to load.

   - **SCENARIO B (Notice Period & LWD):**
     - IF asked "Are you serving notice period?" (Radio) -> **Select "Yes" or "Serving Notice Period"**.
     - IF asked "Select your Notice Period" (Dropdown) -> **Select "Serving Notice Period"**.
     - IF asked "Last Working Day" (Date) -> **Input "03/02/2026"**.

   - **SCENARIO C (Tech & Experience):**
     - **Universal Rule:** If asked about specific experience in [Tech Name] (e.g., "Experience in Java?", "Years in React?"):
       - IF Question is Yes/No -> **Click "Yes"**.
       - IF Question asks for Years/Number -> **Enter "3.5 Years"** (or just "3.5").
     - **Standard Fields:**
       - "Current Salary" -> "13.5" (or "13.5 LPA")
       - "Expected Salary" -> "20" (or "20 LPA")

   - **COMPLETION (The "Submit" Step):**
     - **Goal:** Click the button to close the modal.
     - **TRY 1 (Text Match):** Look for buttons with text: "Submit", "Save", "Send", "Apply", or "Update".
     - **TRY 2 (CSS Class):** If text fails, find and click the button with class `fright` or `primary-btn`.
     - **TRY 3 (Icon):** Look for a clickable element (often a blue button) at the bottom right.
     - **CRITICAL VERIFICATION:**
       - After clicking, execute: `wait(seconds=3)`.
       - Check if the modal text is GONE.
       - ONLY call `done` if the modal is truly gone.

DETAILS TO USE:
- Resume: Use my uploaded resume.
- Expected Salary: 20 LPA | Current Salary: 13.5 LPA
- Notice Period: "Serving Notice Period" (Always select this radio button/option).
- Last Working Day (LWD): "Feb 3, 2026" (Format as required: 03/02/2026).
- Experience: 3.5 Years (42 months total). ALWAYS ENTER "3.5 Years" in experience fields.
- Location: Noida. Preferred: Mumbai, Delhi/NCR, Bangalore, Hyderabad, Remote, Pune, Noida, Gurgaon.
- Relocation: Yes. | Immediate Joiner: Yes.
- Completed B.Tech in CSE from VIT Bhopal in year 2018, CGPA: 8.5 and if asked in percentage then it is 85%
- Completed HSC/10th in year 2016, CGPA: 8.8 and if asked in percentage then it is 88%
- Completed SSC/12th in year 2018, Percentage was 70%.
- Resident/Citizen of India.
- I am not interested in any visa or sponsorship.
- I am interested in any relocation.
"""

LINKEDIN_JOB_APPLY_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.linkedin.com/jobs/search-results/?f_AL=true&f_TPR=r18000&keywords=%22hiring%22%20AND%20(%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22)%20AND%20India&f_CS=G,H,I immediately.

GOAL: Click 'Easy Apply' and submit applications.

DETAILS TO USE:
- Email: siddhant3646@gmail.com
- Mobile: 7905828880
- Phone Code: India (+91)
- Skills: Java, JavaScript, HTML, CSS, ReactJS, NodeJS, Python, Spring Boot, Hibernate, AWS, SQL, Docker, Kubernetes.
- Expected Salary: 20,00,000
- Current Salary: 13,50,000
- Notice Period: 30 days (Serving Notice). LWD: Feb 03, 2026.
- Experience: 4 Years.
- Location: Current: Noida. Preferred: Mumbai, Delhi/NCR, Bangalore, Hyderabad, Remote, Pune, Noida, Gurgaon.
- Relocation: Yes.
- Immediate Joiner: Yes. Can join by Feb 03, 2026.
- Completed B.Tech in CSE from VIT Bhopal in year 2018, CGPA: 8.5 and if asked in percentage then it is 85%
- Completed HSC/10th in year 2016, CGPA: 8.8 and if asked in percentage then it is 88%
- Completed SSC/12th in year 2018, Percentage was 70%.
- Resident/Citizen of India
- I am not interested in any visa or sponsorship.
- I am interested in any relocation.

ACTION PLAN:
1. Navigate to the URL.
2. CLICK the first job card in the left list.
3. CLICK 'Easy Apply'. Use these specific selectors:
   - ID: `#jobs-apply-button-id`
   - Class: `.jobs-apply-button`
   - Aria Label: `button[aria-label*="Easy Apply"]`
   - Text: "Easy Apply" inside a button.
4. Handle form questions with above data.
5. SUBMIT application.
START NOW using the navigation tool.
""" 

NAUKRI_PROFILE_UPDATE_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com immediately.
GO TO: "View and Update Profile" (Top Right Menu).

GOAL: Update 'Resume Headline'.
1. Locate 'Resume Headline' section.
2. REMOVE the fullstop at the very end of the text. Save.
3. ADD the fullstop back at the end. Save again.

Verify the change. START NOW.
"""

# Condensed version for smaller models - used by the scripted fallback
NAUKRI_TASK_CONTEXT = """
TASK: Apply to the first matching job on Naukri.

CRITICAL SEQUENCE (MUST FOLLOW IN ORDER):
1. CHECKBOX FIRST: You MUST click the checkbox for a job BEFORE clicking Apply. The Apply button is DISABLED until a job is selected.
2. VERIFY SELECTION: Look for a checked/selected checkbox icon before proceeding.
3. APPLY: Only after checkbox is clicked, click the "Apply" button (.multi-apply-button).
4. MODAL: Handle the chatbot questionnaire using these rules:
   - Career Break/Diversity -> Click "No"
   - Notice Period -> Select "Serving Notice Period" or "Yes"
   - LWD -> Enter "03/02/2026"
   - Tech Experience (Yes/No) -> Click "Yes"
   - Tech Experience (Years) -> Enter "3.5 Years"
   - Current Salary -> "13.5 LPA"
   - Expected Salary -> "20 LPA"
   - Location -> "Noida"
   - Relocation -> "Yes"
5. DONE: When modal closes or "Application Submitted" appears, task complete.

RULES:
- NEVER click Apply button without first selecting a job checkbox.
- Target roles: Java, React, Full Stack, Node, MERN.
- If chatbot overlay is visible, focus on answering the questions.
"""

NAUKRI_PROFILE_UPDATE_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com/mnjuser/profile?id=&altresid immediately.

GOAL: Update 'Resume Headline' to trigger profile refresh.

WORKFLOW:
1. Locate 'Resume Headline' section (div#lazyResumeHead)
2. Click the pencil/edit icon (span.edit.icon)
3. In the textarea, REMOVE the fullstop at the very end
4. Click Save
5. Wait 2 seconds
6. Click the pencil/edit icon again
7. ADD the fullstop back at the end
8. Click Save again
9. Task Complete
"""

# Task runs second: Sets LWD to System Date + 30 days
NAUKRI_EMPLOYMENT_LWD_30_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com/mnjuser/profile?id=&altresid immediately.

GOAL: Update 'Expected Last Working Day' in the Employment section to System Date + 30 days.

WORKFLOW:
1. Locate Employment section on the profile page
2. Click the pencil/edit icon next to your current employment (Software Engineer 2 at Fiserv)
3. Wait for the Employment modal to open
4. Scroll down to find "Expected last working day" dropdowns
5. Set the Year, Month, and Day dropdowns to: System Date + 30 days
6. Click Save button
7. Task Complete

DOM Selectors:
- Year dropdown: #lwdYearFor
- Month dropdown: #lwdMonthFor
- Day dropdown: #lwdDayFor
"""

# Task runs first: Sets LWD to System Date + 31 days
NAUKRI_EMPLOYMENT_LWD_31_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com/mnjuser/profile?id=&altresid immediately.

GOAL: Update 'Expected Last Working Day' in the Employment section to System Date + 31 days.

WORKFLOW:
1. Locate Employment section on the profile page
2. Click the pencil/edit icon next to your current employment (Software Engineer 2 at Fiserv)
3. Wait for the Employment modal to open
4. Scroll down to find "Expected last working day" dropdowns
5. Set the Year, Month, and Day dropdowns to: System Date + 31 days
6. Click Save button
7. Task Complete

DOM Selectors:
- Year dropdown: #lwdYearFor
- Month dropdown: #lwdMonthFor
- Day dropdown: #lwdDayFor
"""

NAUKRI_EARLY_ACCESS_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.naukri.com/mnjuser/recommended-earjobs immediately.

GOAL: Click 'Share interest' on Early Access job cards.

WORKFLOW:
1. Navigate to the Early Access Roles page
2. Find job cards with "Share interest" buttons
3. Click "Share interest" on the first available job
4. Verify success: Look for "Interest shared successfully!" message
5. Task Complete

DOM Selectors:
- Share Interest Button: button.tf__content button, button:has-text("Share interest")
- Success Message: .apply-status-header.green .apply-message
"""

INSTAHYRE_SEARCH_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.instahyre.com/candidate/opportunities/?matching=true immediately.

GOAL: Configure job search filters on Instahyre and apply to 5 jobs.

PHASE 1 - CONFIGURE SEARCH:
1. Click "Search other jobs" dropdown to expand the filter panel
2. Set Experience: 4 years
3. Set Location: Anywhere in India
4. Add Skills (one by one): Java, JavaScript, HTML, CSS, SpringBoot, ReactJS, AWS
5. Add Job Functions: Backend Development, Frontend Development, Full-Stack Development
6. Click "Show results" button after all configuration is complete

PHASE 2 - APPLY TO JOBS (Loop 5 times):
1. On results page, click "View »" button on a job card
2. Wait for job modal to open
3. Click "Apply" button in the modal
4. Wait for confirmation, close modal if needed
5. Repeat for next job until 5 applications completed

TASK COMPLETE: After 5 applications submitted.

DOM Selectors:
- Search Other Jobs Dropdown: Text "Search other jobs" or .filter-toggle
- Skills Input: input#skills-selectized
- Job Functions Input: input#job-functions-selectized
- Experience Input: input#years
- Location Input: input#location-selectized
- Show Results Button: button#show-results
- View Button: button#interested-btn, button.button-interested.btn-success
- Apply Button: button.btn-primary.new-btn, button.btn-lg.btn-primary
"""

# Intersession task - runs during wait period between cycles (20 jobs)
INSTAHYRE_INTERSESSION_TASK = COMMON_CONTEXT + """
NAVIGATE to https://www.instahyre.com/candidate/opportunities/?matching=true immediately.

GOAL: Apply to 20 jobs on Instahyre during the intersession period.

PHASE 1 - QUICK FILTER SETUP (Skip if already configured):
1. If filters are already set, skip to Phase 2
2. Otherwise: Set Experience: 4 years, Location: Anywhere in India
3. Add Skills: Java, JavaScript, SpringBoot, ReactJS
4. Add Job Functions: Backend Development, Frontend Development
5. Click "Show results"

PHASE 2 - APPLY TO 20 JOBS (High Volume Session):
1. On results page, click "View »" button on a job card
2. Wait for job modal to open
3. Click "Apply" button in the modal
4. Wait for confirmation, close modal if needed
5. Repeat until 20 applications completed

TASK COMPLETE: After 20 applications submitted.

DOM Selectors:
- View Button: button#interested-btn, button.button-interested.btn-success
- Apply Button: button.btn-primary.new-btn, button.btn-lg.btn-primary
"""
