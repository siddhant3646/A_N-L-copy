// ============================================================
// LINKEDIN AUTOMATION - CLEAN REWRITE FOR 2025-2026
// Handles obfuscated classes and dynamic DOM structure
// ============================================================

(function() {
    'use strict';
    
    // Configuration
    const CONFIG = {
        maxRetries: 3,
        scrollAmount: 800,
        debug: true
    };
    
    // QA Patterns for question answering
    const QA_PATTERNS = {
        experience: {
            patterns: ['years of experience', 'months of experience', 'total experience', 'overall experience', 'year of exp', 'total exp', 'your total exp', 'what is your total exp', 'experience in your chosen engineering field', 'years of work experience do you have', 'work experience', 'exp in angular', 'exp in react', 'angular or react'],
            linkedin_default: '4',
            default: '4 Years'
        },
        current_salary: {
            patterns: ['current salary', 'what is your current salary', 'current ctc', 'current annual ctc', 'monthly salary', 'current ctc in lakhs', 'current ctc in lpa', 'current ctc [in lpa]', 'ctc in lacs per annum', 'cctc', 'what is your cctc', 'your cctc', 'your current ctc', 'what is your current ctc'],
            default: '15.3 LPA',
            numeric_default: '1530000',
            inr_default: '1530000'
        },
        expected_salary: {
            patterns: ['expected salary', 'what is your expected salary', 'expected ctc', 'expected annual ctc', 'expected ctc in lakhs', 'expected ctc in lpa', 'expected ctc [in lpa]', 'ectc', 'what is your ectc', 'your ectc', 'what is your current expected ctc', 'current expected ctc'],
            default: '24 LPA',
            numeric_default: '2400000',
            inr_default: '2400000'
        },
        notice_period: {
            patterns: ['notice period', 'serving notice', 'serving notice period', 'are you serving notice', 'currently serving notice', 'your np', 'what is your np', 'mention np'],
            default: 'Serving Notice Period',
            numeric_default: '30'
        },
        location_current: {
            patterns: ['current location', 'current city', 'currently located', 'where are you located', 'where do you stay', 'stay currently'],
            default: 'Noida'
        },
        location_preferred: {
            patterns: ['preferred location', 'preferred city', 'city preference', 'interview city'],
            default: 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune'
        },
        contact_phone: {
            patterns: ['phone number', 'mobile number', 'contact number'],
            default: '7905828880'
        },
        contact_email: {
            patterns: ['email address', 'email id'],
            default: 'siddhant3646@gmail.com'
        },
        skills_tech_stack: {
            patterns: ['tech stack', 'major tech stack', 'tech-stack', 'worked upon', 'technologies worked'],
            default: 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis'
        },
        skills_languages: {
            patterns: ['programming languages', 'which python libraries', 'python libraries', 'python packages'],
            default: 'Java, Python, JavaScript'
        },
        proficiency_rating: {
            patterns: ['rate proficiency', 'rate yourself', 'rate your proficiency', 'on a scale of 1-10', 'on a scale of 1 to 10', 'proficiency in'],
            default: '8'
        },
        willing_relocate: {
            patterns: ['willing to relocate', 'comfortable working in shift', 'shift timing', 'night shift', 'rotational shift', 'remote work', 'hybrid work', 'comfortable to work', 'settle in abroad', 'relocate'],
            default: 'Yes'
        },
        authorization: {
            patterns: ['work authorization', 'legally authorized', 'background check', 'drug test'],
            default: 'Yes'
        },
        visa_sponsorship: {
            patterns: ['visa sponsorship', 'require sponsorship', 'visa', 'bear expense', 'bear expenses', 'expenses and visa'],
            default: 'No'
        },
        education_degree: {
            patterns: ['degree', 'highest education', 'educational qualification', 'bachelor', 'educational and professional', 'all educational and professional'],
            default: 'B.Tech Computer Science',
            yes_no_default: 'Yes'
        },
        education_university: {
            patterns: ['college name', 'university', 'graduation year'],
            default: 'VIT Bhopal University'
        },
        education_cgpa: {
            patterns: ['cgpa', 'percentage'],
            default: '8.5'
        },
        personal_dob: {
            patterns: ['date of birth', 'dob', 'date of birth as per pan'],
            default: '17/12/2000'
        },
        personal_pan: {
            patterns: ['pan number', 'pan card number', 'pan card', 'mention your pan'],
            default: 'MTKPS1941P'
        },
        company_current: {
            patterns: ['current employer', 'current company', 'payroll company', 'current payroll company'],
            default: 'Fiserv'
        },
        interview_availability: {
            patterns: ['face to face interview', 'f2f interview', 'available for interview', 'interested for interview', 'virtual interview', 'telephonic interview', 'video interview'],
            default: 'Yes'
        },
        interview_slots: {
            patterns: ['tentative dates', 'time slots', 'interview slot', 'interview availability', 'weekday interview', 'dates and time slots'],
            default: 'Any slot available - flexible with dates and times on weekdays'
        },
        assessment_availability: {
            patterns: ['technical assessment', 'available to take a technical assessment', 'coding assessment', 'online assessment', 'available for assessment'],
            default: 'Yes'
        },
        contract_to_hire: {
            patterns: ['contract to hire', 'c2h position', 'interested in c2h'],
            default: 'Yes'
        },
        job_change_reason: {
            patterns: ['reason for job change', 'why job change', 'why are you looking', 'why switching', 'reason for leaving', 'reasons for your job change'],
            default: 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals'
        },
        preferred_role: {
            patterns: ['preferred position', 'frontend/backend', 'frontend or backend', 'preferred role', 'which role'],
            default: 'Backend'
        },
        referral: {
            patterns: ['referred for this position', 'referred by', 'employee referral', 'encouraged to apply'],
            default: 'No'
        },
        privacy_consent: {
            patterns: ['i consent', 'privacy notice', 'declare that you have read', 'agree to the privacy', 'read and agree', 'privacy policy agreement', 'consent to'],
            default: 'Yes'
        },
        english_level: {
            patterns: ['level of english', 'english level', 'english proficiency', 'proficiency in english', 'fluency in english', 'how fluent'],
            default: 'Professional proficiency'
        },
        experience_years_dropdown: {
            patterns: ['how many years of experience do you have', 'how many years of experience', 'years of experience do you have'],
            default: '3 to 6 years'
        },
        last_professional_experience: {
            patterns: ['what did you do during your last professional', 'last professional experience', 'during your last professional experience', 'last professinnal experience'],
            default: 'Full Stack Development using Java, Spring Boot, React, and AWS. Built scalable microservices, RESTful APIs, and responsive web applications. Led feature development, code reviews, and deployment pipelines.'
        },
        previous_relevant_experience: {
            patterns: ['specify previous experiences relevant', 'previous experiences relevant', 'relevant experiences for the position'],
            default: '3.8+ years as Full Stack Developer at Fiserv: Java/Spring Boot microservices, React frontends, AWS cloud infrastructure, CI/CD pipelines with Jenkins and GitHub Actions, PostgreSQL and MongoDB databases.'
        },
        why_join: {
            patterns: ['why would you like to join', 'why do you want to join', 'what makes you interested in joining'],
            default: 'I am excited about this opportunity as it aligns with my career goals and technical expertise. With 3.8+ years of full-stack development experience in Java, Spring Boot, React, and AWS, I am confident I can contribute meaningfully to the team and grow professionally.'
        },
        what_bring: {
            patterns: ['what could you bring', 'what can you bring', 'what value can you add', 'what do you bring'],
            default: 'I bring 3.8+ years of hands-on experience in full-stack development with Java, Spring Boot, React, and AWS. My strengths include building scalable microservices architectures, optimizing CI/CD pipelines, and delivering high-quality code through rigorous testing and code reviews.'
        }
    };
    
    // Helper: Match question text against QA patterns
    function matchQuestionToPattern(questionText) {
        const lowerText = questionText.toLowerCase();
        
        for (const [category, data] of Object.entries(QA_PATTERNS)) {
            for (const pattern of data.patterns) {
                if (lowerText.includes(pattern.toLowerCase())) {
                    console.log('Matched question to pattern:', category, '- Pattern:', pattern);
                    return { category, data };
                }
            }
        }
        
        return null;
    }
    
    // Helper: Get answer for a question based on patterns
    function getAnswerForQuestion(questionText, fieldType = 'text') {
        const match = matchQuestionToPattern(questionText);
        
        if (!match) {
            console.log('No pattern match found for question:', questionText);
            return null;
        }
        
        const { category, data } = match;
        
        // Special handling for LinkedIn experience (numeric only)
        if (category === 'experience') {
            return data.linkedin_default || '4';
        }
        
        // For CTC/salary fields, on LinkedIn we should always return INR value (1530000 or 2400000)
        if (category === 'current_salary' || category === 'expected_salary') {
            return data.inr_default; // Return INR numbers: 1530000 or 2400000
        }
        
        // For notice period fields, on LinkedIn return numeric value (30) for text inputs to avoid validation errors
        if (category === 'notice_period') {
            // For text/number inputs, return numeric value only
            if (fieldType === 'text' || fieldType === 'number') {
                return data.numeric_default || '30';
            }
            // For dropdowns/radios, return text value
            return data.default;
        }
        
        // For education documents question, return Yes for dropdown
        if (category === 'education_degree' && (fieldType === 'select' || fieldType === 'dropdown')) {
            return 'Yes';
        }
        
        // For other dropdowns/selects, return the default (usually Yes/No)
        if (fieldType === 'select' || fieldType === 'dropdown') {
            return data.default;
        }
        
        return data.default;
    }
    
    // Helper: Find elements by text content
    function findByText(selector, text, exact = false) {
        const elements = document.querySelectorAll(selector);
        const searchText = text.toLowerCase();
        return Array.from(elements).find(el => {
            const elText = el.innerText.toLowerCase();
            return exact ? elText === searchText : elText.includes(searchText);
        });
    }
    
    // Helper: Find Easy Apply button
    function findEasyApplyButton() {
        // Try by class first
        let btn = document.querySelector('button.jobs-apply-button');
        if (btn) return btn;
        
        // Fallback: search by text
        btn = findByText('button', 'easy apply');
        if (btn) return btn;
        
        // Fallback: search all buttons
        const buttons = document.querySelectorAll('button');
        for (const button of buttons) {
            const text = button.innerText.toLowerCase();
            if (text.includes('easy apply') || text.includes('apply')) {
                return button;
            }
        }
        return null;
    }
    
    // Helper: Query deep into shadow DOM and iframes
    function queryDeep(selector, root = document) {
        // First try normal query
        let result = root.querySelector(selector);
        if (result) return result;
        
        // Search in shadow DOM
        const allElements = root.querySelectorAll('*');
        for (const el of allElements) {
            if (el.shadowRoot) {
                result = queryDeep(selector, el.shadowRoot);
                if (result) return result;
            }
        }
        
        // Search in iframes
        const iframes = root.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                if (iframe.contentDocument) {
                    result = queryDeep(selector, iframe.contentDocument);
                    if (result) return result;
                }
            } catch (e) {
                // Cross-origin iframe, skip
            }
        }
        
        return null;
    }
    
    // Helper: Query all matching elements deep
    function queryAllDeep(selector, root = document) {
        const results = [];
        
        // Normal query
        results.push(...root.querySelectorAll(selector));
        
        // Shadow DOM
        const allElements = root.querySelectorAll('*');
        for (const el of allElements) {
            if (el.shadowRoot) {
                results.push(...queryAllDeep(selector, el.shadowRoot));
            }
        }
        
        // Iframes
        const iframes = root.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                if (iframe.contentDocument) {
                    results.push(...queryAllDeep(selector, iframe.contentDocument));
                }
            } catch (e) {
                // Cross-origin iframe, skip
            }
        }
        
        return results;
    }
    
    // Helper: Check if element is visible
    function isVisible(element) {
        if (!element) return false;
        // Relaxed visibility check - focus on basic display/visibility only
        const style = window.getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return false;
        }
        // Check dimensions
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }
    
    // Helper: Find the sidebar container (job list container)
    function findSidebar() {
        // Priority 1: Known stable selectors
        let sidebar = queryDeep('.scaffold-layout__list') || 
                      queryDeep('.jobs-search-results-list') ||
                      queryDeep('.jobs-search__left-rail');
        
        // Priority 2: Find by data attributes on a job card then walk UP
        // UPDATED: Use new LinkedIn selectors
        if (!sidebar) {
            const anyCard = queryDeep('[data-view-name="job-search-job-card"], [data-testid="job-card"], [data-occludable-job-id], [data-job-id]');
            if (anyCard) {
                let el = anyCard.parentElement;
                while (el && el !== document.body) {
                    const style = window.getComputedStyle(el);
                    if (el.scrollHeight > el.clientHeight + 20 &&
                        (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                        sidebar = el;
                        break;
                    }
                    el = el.parentElement;
                }
            }
        }
        
        // Priority 3: Geometry - any tall left-side scrollable div
        if (!sidebar) {
            const allDivs = Array.from(queryAllDeep('div'));
            for (const div of allDivs) {
                const rect = div.getBoundingClientRect();
                const style = window.getComputedStyle(div);
                if (rect.left < window.innerWidth / 2 && rect.width > 200 && rect.height > 400) {
                    if (div.scrollHeight > div.clientHeight + 20 &&
                        (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                        sidebar = div;
                        break;
                    }
                }
            }
        }
        
        return sidebar;
    }
    
    // Helper: Find job cards with multiple fallback strategies
    function findJobCards() {
        const sidebar = findSidebar();
        let jobCards = [];
        
        // STRATEGY 1: Data attributes (most reliable)
        // UPDATED: Primary selector is now data-view-name for modern LinkedIn UI
        const cardSelectors = [
            '[data-view-name="job-search-job-card"]',
            '[data-testid="job-card"]',
            '[data-occludable-job-id]',
            '[data-job-id]'
        ];
        
        for (const selector of cardSelectors) {
            if (sidebar) {
                const cards = Array.from(queryAllDeep(selector, sidebar));
                jobCards.push(...cards);
            } else {
                const cards = Array.from(queryAllDeep(selector));
                jobCards.push(...cards);
            }
        }
        
        // Remove duplicates
        jobCards = [...new Set(jobCards)];
        
        // STRATEGY 2: Find cards by searching for divs with role="button" that contain job links
        // This is common in the current LinkedIn UI
        if (jobCards.length === 0) {
            const container = sidebar || document;
            const allDivs = Array.from(container.querySelectorAll('div'));
            for (const div of allDivs) {
                // Check if it looks like a job card
                const hasJobLink = div.querySelector('a[href*="/jobs/view/"]') !== null ||
                                  div.querySelector('a[href*="currentJobId"]') !== null;
                const hasRoleButton = div.getAttribute('role') === 'button' || div.getAttribute('tabindex') === '0';
                const text = div.innerText || '';
                const hasContent = text.length > 50 && text.length < 800 && text.includes('\n');
                
                if (hasJobLink && hasContent) {
                    jobCards.push(div);
                }
            }
        }
        
        // STRATEGY 3: Link-based detection (backup)
        // Job cards contain links to /jobs/view/ URLs
        if (jobCards.length === 0) {
            const container = sidebar || document;
            const jobLinks = container.querySelectorAll('a[href*="/jobs/view/"]');
            for (const link of jobLinks) {
                // Find the parent container (could be li, div, or article)
                const card = link.closest('[data-view-name="job-search-job-card"]') ||
                            link.closest('[data-testid="job-card"]') ||
                            link.closest('[data-occludable-job-id]') || 
                            link.closest('[data-job-id]') ||
                            link.closest('li') ||
                            link.closest('div[class*="job-card"]') ||
                            link.closest('div[class*="search-result"]') ||
                            link.closest('div');
                if (card && !jobCards.includes(card)) {
                    jobCards.push(card);
                }
            }
        }
        
        // STRATEGY 4: List items with content heuristics
        // Look for list items in sidebar that have job-like content
        if (jobCards.length === 0) {
            const container = sidebar || document;
            const allLis = Array.from(container.querySelectorAll('li'));
            jobCards = allLis.filter(li => {
                const text = li.innerText || '';
                // Job cards typically have:
                // - Multiple lines (title, company, location)
                // - Reasonable text length (not too short, not too long)
                // - A job link
                const hasJobLink = li.querySelector('a[href*="/jobs/view/"]') !== null ||
                                  li.querySelector('a[href*="currentJobId"]') !== null;
                const hasMultipleLines = text.includes('\n');
                const reasonableLength = text.length > 30 && text.length < 800;
                
                return hasJobLink && hasMultipleLines && reasonableLength;
            });
        }
        
        // STRATEGY 5: Role-based detection
        // Look for div[role="listitem"] or div[role="button"] in sidebar
        if (jobCards.length === 0) {
            const container = sidebar || document;
            const roleElements = Array.from(container.querySelectorAll('div[role="listitem"], div[role="button"], article'));
            jobCards = roleElements.filter(el => {
                const text = el.innerText || '';
                // Must have multiple lines and reasonable length
                return text.includes('\n') && text.length > 30 && text.length < 800;
            });
        }
        
        // STRATEGY 6: Geometry-based detection (last resort)
        // Find clickable elements in the left sidebar that look like job cards
        if (jobCards.length === 0 && sidebar) {
            const sidebarRect = sidebar.getBoundingClientRect();
            const allClickables = Array.from(document.querySelectorAll('a, div[role="button"], li'));
            jobCards = allClickables.filter(el => {
                const rect = el.getBoundingClientRect();
                const text = el.innerText || '';
                // Must be inside sidebar, visible, and have job-like content
                const inSidebar = rect.left >= sidebarRect.left && rect.right <= sidebarRect.right;
                const hasContent = text.length > 30 && text.length < 800 && text.includes('\n');
                return inSidebar && isVisible(el) && hasContent;
            });
        }
        
        // Filter cards to ensure they're valid and visible
        return jobCards.filter(card => {
            // Must not be the currently active/selected card
            const isActive = card.classList.contains('jobs-search-results-list__list-item--active') ||
                            card.getAttribute('aria-current') === 'true' ||
                            card.getAttribute('aria-selected') === 'true' ||
                            card.getAttribute('data-view-name') === 'job-search-job-card-active';
            if (isActive) return false;
            
            // Must have some meaningful content
            const text = card.innerText || '';
            if (text.length < 20) return false;
            
            return true;
        });
    }
    
    // Helper: Get job ID from card
    function getJobIdFromCard(card) {
        // Try data attributes - UPDATED for modern LinkedIn UI
        let jobId = card.getAttribute('data-job-id') || 
                    card.getAttribute('data-occludable-job-id') ||
                    card.getAttribute('data-view-name');
        if (jobId) return jobId;
        
        // Try from link href
        const link = card.querySelector('a[href*="/jobs/view/"]') || 
                     card.querySelector('a[href*="currentJobId"]');
        if (link) {
            const href = link.getAttribute('href') || '';
            // Try multiple patterns
            const match1 = href.match(/currentJobId=(\d+)/);
            if (match1) return match1[1];
            const match2 = href.match(/\/view\/(\d+)/);
            if (match2) return match2[1];
        }
        
        return null;
    }
    
    // Helper: Check if job is applied
    function isJobApplied(card) {
        const text = card.innerText.toLowerCase();
        return text.includes('applied') || text.includes('see application');
    }
    
    // Helper: Check for modals
    function checkModals() {
        // Safety reminder modal
        const dialogs = document.querySelectorAll('[role="dialog"]');
        for (const dialog of dialogs) {
            const text = dialog.innerText.toLowerCase();
            
            if (text.includes('safety reminder')) {
                return { type: 'safety', element: dialog };
            }
            
            if (text.includes('application sent') || text.includes('application submitted')) {
                return { type: 'success', element: dialog };
            }
        }
        
        // Easy Apply form modal
        const formModal = document.querySelector('div.jobs-easy-apply-modal, div[data-test-modal="jobs-easy-apply-modal"]');
        if (formModal) {
            return { type: 'form', element: formModal };
        }
        
        return null;
    }
    
    
    // Main automation logic
    function runLinkedInAutomation() {
        console.log('=== LINKEDIN AUTOMATION STARTED ===');
        
        let modal;  // Declare once at function scope
        
        // First, check if there are visible autocomplete/dropdown options that need selection
        // Search in ENTIRE document since LinkedIn renders dropdowns in portals
        const allDropdownOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, [data-test-typeahead-item], .artdeco-typeahead__result, .jobs-typeahead__item, [class*="typeahead"]');
        console.log('Checking for dropdown options globally - found:', allDropdownOptions.length);
        
        for (const option of allDropdownOptions) {
            if (option.offsetParent !== null) {
                const text = option.innerText.toLowerCase().trim();
                if (text && !text.includes('select') && !text.includes('choose') && text.length > 2) {
                    console.log('FOUND VISIBLE DROPDOWN OPTION - Selecting:', text);
                    option.click();
                    return 'LINKEDIN_DROPDOWN_SELECTED:' + text;
                }
            }
        }
        
        const currentJobId = new URLSearchParams(window.location.search).get('currentJobId');
        console.log('Current Job ID:', currentJobId);
        
        // FIRST-PASS: Safety reminder modal intercept
        // Catches "Continue applying" button regardless of modal class structure
        {
            const allBtns = document.querySelectorAll('button, span[role="button"]');
            for (const btn of allBtns) {
                const txt = (btn.innerText || '').toLowerCase().trim();
                if (txt.includes('continue applying') && btn.offsetParent !== null) {
                    console.log('FIRST-PASS SAFETY INTERCEPT: Found "Continue applying" button, clicking...');
                    btn.click();
                    return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                }
            }
        }

        // Step 1: Handle modals (reuse modal variable)
        modal = checkModals();
        if (modal) {
            console.log('Modal detected:', modal.type);
            
            if (modal.type === 'safety') {
                // Click Continue button
                const buttons = modal.element.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.innerText.toLowerCase().includes('continue')) {
                        btn.click();
                        return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                    }
                }
                // Fallback: click last button
                if (buttons.length > 0) {
                    buttons[buttons.length - 1].click();
                    return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                }
            }
            
            if (modal.type === 'success') {
                // Close success modal
                const closeBtn = modal.element.querySelector('button');
                if (closeBtn) {
                    closeBtn.click();
                    return 'LINKEDIN_SUCCESS_MODAL_CLOSED';
                }
            }
            
            if (modal.type === 'form') {
                return handleApplicationForm(modal.element);
            }
        }
        
        // Step 2: Find job cards
        const jobCards = findJobCards();
        console.log('Found', jobCards.length, 'job cards');
        
        if (jobCards.length === 0) {
            console.log('No job cards found, scrolling...');
            window.scrollBy(0, CONFIG.scrollAmount);
            return 'LINKEDIN_SCROLLED: Looking for jobs';
        }
        
        // Step 3: Navigate to first job if none selected
        if (!currentJobId) {
            for (const card of jobCards) {
                if (!isJobApplied(card)) {
                    const link = card.querySelector('a');
                    if (link) {
                        console.log('Clicking first unapplied job');
                        link.click();
                        return 'LINKEDIN_FIRST_JOB_CLICKED';
                    }
                }
            }
        }
        
        // Step 4: Find current job card
        let currentCard = null;
        let currentIndex = -1;
        
        for (let i = 0; i < jobCards.length; i++) {
            const cardId = getJobIdFromCard(jobCards[i]);
            if (cardId === currentJobId) {
                currentCard = jobCards[i];
                currentIndex = i;
                break;
            }
        }
        
        if (!currentCard) {
            console.log('Current job card not found');
            return 'LINKEDIN_NO_CURRENT_CARD';
        }
        
        console.log('Current card index:', currentIndex);
        
        // Step 5: Check if current job is applied
        if (isJobApplied(currentCard)) {
            console.log('Current job is applied, finding next...');
            
            for (let i = currentIndex + 1; i < jobCards.length; i++) {
                if (!isJobApplied(jobCards[i])) {
                    const link = jobCards[i].querySelector('a');
                    if (link) {
                        link.click();
                        return 'LINKEDIN_NEXT_JOB_CLICKED';
                    }
                }
            }
            
            // No more jobs, scroll
            window.scrollBy(0, CONFIG.scrollAmount);
            return 'LINKEDIN_SCROLLED: Looking for more jobs';
        }
        
        // Step 6: Check for Easy Apply button
        const easyApplyBtn = findEasyApplyButton();
        if (!easyApplyBtn) {
            console.log('No Easy Apply button, skipping to next job');
            
            for (let i = currentIndex + 1; i < jobCards.length; i++) {
                if (!isJobApplied(jobCards[i])) {
                    const link = jobCards[i].querySelector('a');
                    if (link) {
                        link.click();
                        return 'LINKEDIN_NEXT_JOB_CLICKED';
                    }
                }
            }
            
            window.scrollBy(0, CONFIG.scrollAmount);
            return 'LINKEDIN_SCROLLED: Looking for more jobs';
        }
        
        // Step 7: Click Easy Apply
        console.log('Clicking Easy Apply button');
        easyApplyBtn.click();
        return 'LINKEDIN_EASY_APPLY_CLICKED';
    }
    
    // Get label text for an input element
    function getLabelForInput(input) {
        // Try to find associated label
        let label = null;
        
        // Method 1: Check for aria-labelledby
        const labelledBy = input.getAttribute('aria-labelledby');
        if (labelledBy) {
            const labelEl = document.getElementById(labelledBy);
            if (labelEl) return labelEl.innerText;
        }
        
        // Method 2: Check for aria-label
        const ariaLabel = input.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel;
        
        // Method 3: Check for id and find matching label
        const inputId = input.id;
        if (inputId) {
            label = document.querySelector(`label[for="${inputId}"]`);
            if (label) return label.innerText;
        }
        
        // Method 4: Look for label in parent elements (up to 5 levels)
        let parent = input.parentElement;
        for (let i = 0; i < 5 && parent; i++) {
            label = parent.querySelector('label');
            if (label) return label.innerText;
            parent = parent.parentElement;
        }
        
        // Method 5: Check previous sibling
        const prevSibling = input.previousElementSibling;
        if (prevSibling && prevSibling.tagName.toLowerCase() === 'label') {
            return prevSibling.innerText;
        }
        
        // Method 6: Look for label in previous siblings of parent containers (LinkedIn style)
        parent = input.parentElement;
        for (let i = 0; i < 3 && parent; i++) {
            // Check previous siblings of the parent
            let sibling = parent.previousElementSibling;
            while (sibling) {
                const labelInSibling = sibling.querySelector('label') || (sibling.tagName.toLowerCase() === 'label' ? sibling : null);
                if (labelInSibling) return labelInSibling.innerText;
                sibling = sibling.previousElementSibling;
            }
            parent = parent.parentElement;
        }
        
        // Method 7: Look for any text in form group container
        parent = input.closest('.jobs-easy-apply-form-section__question, [data-test-form-element], fieldset, .artdeco-form-field');
        if (parent) {
            const legend = parent.querySelector('legend, .artdeco-form-field__label');
            if (legend) return legend.innerText;
            // Get any text that's a direct label-like element
            const textElements = parent.querySelectorAll('span, div, p');
            for (const el of textElements) {
                const text = el.innerText.trim();
                if (text && text.length > 5 && text.length < 200 && !text.includes('Select an option')) {
                    return text;
                }
            }
        }
        
        return '';
    }
    
    // Handle application form
    function handleApplicationForm(modal) {
        console.log('Handling application form...');
        
        // Check for validation errors first
        const errorMessages = modal.querySelectorAll('.artdeco-inline-feedback__message, [data-test-form-element-error-message], .jobs-easy-apply-form-element__error-message');
        let hasErrors = false;
        let filledAny = false;
        
        for (const error of errorMessages) {
            if (error.offsetParent !== null && error.innerText.trim()) {
                console.log('Validation error found:', error.innerText);
                hasErrors = true;
            }
        }
        
        // Handle dropdown questions first
        const dropdowns = modal.querySelectorAll('select, [role="combobox"], .jobs-easy-apply-form-section__dropdown, [data-test-text-entity-list-form-select], .fb-dash-form-element__select-dropdown');
        console.log('Found', dropdowns.length, 'dropdowns');
        
        for (const dropdown of dropdowns) {
            // Check if dropdown needs to be filled
            const isEmpty = !dropdown.value || dropdown.value === '' || dropdown.innerText.toLowerCase().includes('select an option');
            
            if (isEmpty) {
                // Get label text to determine what to select
                const labelText = getLabelForInput(dropdown);
                console.log('Filling dropdown - Label detected:', JSON.stringify(labelText));
                console.log('Dropdown innerText preview:', dropdown.innerText.substring(0, 100));
                
                const lowerLabel = labelText.toLowerCase();
                
                // SPECIAL CASE: For "learn about" / "hear about" / "source" questions, select ANY first option
                const isLearnAboutQuestion = lowerLabel.includes('learn about') || 
                                            lowerLabel.includes('hear about') || 
                                            lowerLabel.includes('how did you') ||
                                            lowerLabel.includes('where did you') ||
                                            lowerLabel.includes('source') ||
                                            lowerLabel.includes('miratech');
                
                if (isLearnAboutQuestion) {
                    console.log('Learn about question detected - selecting first available option');
                    
                    // Click to open dropdown
                    dropdown.click();
                    
                    // Wait for options to appear and select first non-placeholder
                    setTimeout(() => {
                        const allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, .jobs-easy-apply-form-element__dropdown-option, li');
                        for (const option of allOptions) {
                            const text = option.innerText.trim().toLowerCase();
                            if (text && !text.includes('select') && !text.includes('choose') && text.length > 2) {
                                option.click();
                                console.log('Selected first option for learn about question:', option.innerText.trim());
                                filledAny = true;
                                break;
                            }
                        }
                    }, 300);
                    
                    return 'LINKEDIN_FORM_FILLING_DROPDOWN';
                }
                
                // Use QA patterns to determine the answer
                let selectValue = getAnswerForQuestion(labelText, 'select');
                
                // If no pattern match, use smart defaults based on keywords
                if (!selectValue) {
                    if (lowerLabel.includes('notice') || lowerLabel.includes('lwd')) {
                        // Don't select dropdown for notice period, we'll fill the text input
                        continue;
                    } else if (lowerLabel.includes('document') || lowerLabel.includes('certificate') || lowerLabel.includes('education')) {
                        selectValue = 'Yes';
                    } else {
                        // Default to Yes for unknown dropdowns
                        selectValue = 'Yes';
                    }
                }
                
                // For native select elements, set value directly
                if (dropdown.tagName.toLowerCase() === 'select' && selectValue) {
                    const options = dropdown.querySelectorAll('option');
                    for (const option of options) {
                        if (option.innerText.toLowerCase().includes(selectValue)) {
                            option.selected = true;
                            dropdown.value = option.value;
                            dropdown.dispatchEvent(new Event('change', { bubbles: true }));
                            console.log('Directly selected', selectValue, 'for native select');
                            filledAny = true;
                            break;
                        }
                    }
                } else {
                    // Click to open custom dropdown
                    dropdown.click();
                    
                    // Wait a moment for options to appear
                    setTimeout(() => {
                        if (selectValue) {
                            // Try to find and click specific option
                            const option = findByText('span, li, div[role="option"]', selectValue, true) ||
                                          findByText('span, li, div[role="option"]', selectValue);
                            
                            if (option) {
                                option.click();
                                console.log('Selected', selectValue, 'for dropdown');
                            }
                        } else {
                            // Fallback: try to select first non-placeholder option
                            const options = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, .jobs-easy-apply-form-element__dropdown-option');
                            for (const option of options) {
                                const text = option.innerText.toLowerCase();
                                if (text && !text.includes('select') && !text.includes('choose')) {
                                    option.click();
                                    console.log('Selected option:', text);
                                    break;
                                }
                            }
                        }
                    }, 200);
                    
                    // Return early to let dropdown settle
                    return 'LINKEDIN_FORM_FILLING_DROPDOWN';
                }
            }
        }
        
        // Handle text inputs (including autocomplete/combobox)
        const inputs = modal.querySelectorAll('input[type="text"], input[type="number"], input:not([type]), textarea');
        
        for (const input of inputs) {
            const placeholder = (input.placeholder || '').toLowerCase();
            const labelText = getLabelForInput(input);
            const lowerLabelText = labelText.toLowerCase();
            const combinedText = placeholder + ' ' + lowerLabelText;
            const inputValue = input.value || '';
            const isEmpty = !inputValue || inputValue.trim() === '';
            
            // Check if this is a location/city field that might need autocomplete selection
            const isLocationField = lowerLabelText.includes('location') || lowerLabelText.includes('city') || 
                                   placeholder.includes('location') || placeholder.includes('city');
            
            // Special handling for location fields: even if they have text, we need to check for dropdown
            if (isLocationField && !isEmpty) {
                console.log('Location field has text:', inputValue, '- checking if dropdown needs selection...');
                
                // Focus the field to trigger dropdown
                input.focus();
                input.dispatchEvent(new Event('focus', { bubbles: true }));
                input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
                
                // Return to let the dropdown appear, next iteration will select from it
                return 'LINKEDIN_LOCATION_TRIGGERED';
            }
            
            if (isEmpty) {
                console.log('Empty input found - Label:', JSON.stringify(labelText), '| Placeholder:', JSON.stringify(placeholder));
                console.log('Input element:', input.tagName, input.type, input.className.substring(0, 50));
                
                // Check if input expects numeric values only
                const isNumericInput = input.type === 'number' || 
                                      input.getAttribute('inputmode') === 'numeric' ||
                                      input.getAttribute('pattern')?.includes('\\d') ||
                                      input.className.toLowerCase().includes('number') ||
                                      input.className.toLowerCase().includes('decimal');
                
                // Use QA patterns to get the answer
                let fillValue = getAnswerForQuestion(labelText, 'text');
                
                // If no pattern match, use smart fallback based on keywords
                if (!fillValue) {
                    if (combinedText.includes('notice') || combinedText.includes('lwd') || combinedText.includes('join') || combinedText.includes('how soon')) {
                        fillValue = '30';
                        console.log('Fallback: Filling notice/join period with: 30');
                    } else if (combinedText.includes('phone') || combinedText.includes('mobile')) {
                        fillValue = '7905828880';
                        console.log('Fallback: Filling phone number');
                    } else if (combinedText.includes('email')) {
                        fillValue = 'siddhant3646@gmail.com';
                        console.log('Fallback: Filling email');
                    }
                } else {
                    console.log('Pattern matched! Filling with:', fillValue);
                }
                
                // If it's a numeric input, extract just the number from the answer
                if (fillValue && isNumericInput) {
                    const numericMatch = fillValue.match(/(\d+\.?\d*)/);
                    if (numericMatch) {
                        fillValue = numericMatch[1];
                        console.log('Extracted numeric value for number field:', fillValue);
                    }
                }
                
                if (fillValue) {
                    // Use property setter for React inputs
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    nativeInputValueSetter.call(input, fillValue);
                    
                    // Trigger events to open autocomplete if needed
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('focus', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
                    
                    filledAny = true;
                    console.log('Filled input successfully');
                    
                    // Check if this is a location/city field that might have autocomplete
                    if (isLocationField) {
                        console.log('Location field detected - waiting for autocomplete dropdown...');
                        
                        // Wait for dropdown to appear and select first option
                        setTimeout(() => {
                            // Look for dropdown options in the entire document (they might be in a portal)
                            const allOptions = document.querySelectorAll('[role="option"], .artdeco-typeahead__result, .jobs-typeahead__item, .artdeco-dropdown__item, li[class*="typeahead"], [data-test-typeahead-item]');
                            console.log('Found', allOptions.length, 'potential dropdown options in document');
                            
                            for (const option of allOptions) {
                                if (option.offsetParent !== null) {
                                    const text = option.innerText.trim();
                                    console.log('Dropdown option text:', text);
                                    // Click the first option that matches our filled value
                                    if (text && text.toLowerCase().includes(fillValue.toLowerCase())) {
                                        console.log('Clicking matching dropdown option:', text);
                                        option.click();
                                        return;
                                    }
                                }
                            }
                            
                            // If no matching option found, click the first non-placeholder option
                            for (const option of allOptions) {
                                if (option.offsetParent !== null) {
                                    const text = option.innerText.trim().toLowerCase();
                                    if (text && !text.includes('select') && !text.includes('choose') && text.length > 2) {
                                        console.log('Clicking first available dropdown option:', option.innerText.trim());
                                        option.click();
                                        return;
                                    }
                                }
                            }
                        }, 500); // Wait 500ms for dropdown to appear
                        
                        // Return and let the next iteration check if selection was successful
                        return 'LINKEDIN_LOCATION_FIELD_FILLED';
                    }
                }
            }
        }
        
        // Check for autocomplete/typeahead dropdown options that appeared after filling inputs
        // This handles location dropdowns and other autocomplete fields
        // Note: LinkedIn may render dropdowns in a portal outside the modal, so we search the entire document
        
        // First check inside the modal
        const typeaheadDropdown = modal.querySelector('[data-test-typeahead-results], .artdeco-typeahead__results-list, .jobs-typeahead__list');
        if (typeaheadDropdown) {
            const options = typeaheadDropdown.querySelectorAll('[role="option"], .artdeco-typeahead__result, .jobs-typeahead__item, li');
            console.log('Found typeahead dropdown in modal with', options.length, 'options');
            
            for (const option of options) {
                if (option.offsetParent !== null) {
                    const text = option.innerText.trim();
                    console.log('Typeahead option:', text);
                    // Click the first non-empty option
                    if (text && text.length > 0) {
                        console.log('Clicking typeahead option:', text);
                        option.click();
                        filledAny = true;
                        // Wait a moment for selection to register
                        return 'LINKEDIN_AUTOCOMPLETE_SELECTED';
                    }
                }
            }
        }
        
        // Also check for general autocomplete dropdowns - search in entire document since they might be in a portal
        let allOptions = modal.querySelectorAll('[role="option"], .artdeco-dropdown__item, [data-test-typeahead-item], .jobs-easy-apply-form-element__dropdown-option, .fb-dropdown__option');
        console.log('Found', allOptions.length, 'dropdown options in modal');
        
        // If none found in modal, search entire document (dropdowns may be rendered in a portal)
        if (allOptions.length === 0) {
            allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, [data-test-typeahead-item], .jobs-easy-apply-form-element__dropdown-option, .fb-dropdown__option, .artdeco-typeahead__result, li[class*="typeahead"], [data-test-typeahead-results] [role="option"]');
            console.log('Found', allOptions.length, 'dropdown options in entire document');
        }
        
        if (allOptions.length > 0) {
            for (const option of allOptions) {
                if (option.offsetParent !== null) {
                    const text = option.innerText.trim();
                    console.log('Dropdown option text:', text);
                    // Skip placeholder options
                    if (text && !text.toLowerCase().includes('select') && !text.toLowerCase().includes('choose') && text.length > 2) {
                        console.log('Selecting dropdown option:', text);
                        option.click();
                        return 'LINKEDIN_DROPDOWN_OPTION_SELECTED';
                    }
                }
            }
        }
        
        // Handle checkboxes (consent, privacy policy, etc.)
        // Search in modal first, then fall back to entire document
        let checkboxes = modal.querySelectorAll('input[type="checkbox"]');
        
        // Also try broader selectors in case checkboxes are in shadow DOM or different structure
        if (checkboxes.length === 0) {
            checkboxes = document.querySelectorAll('input[type="checkbox"]');
            console.log('No checkboxes in modal, searching entire document - found:', checkboxes.length);
        }
        
        // Further filter to only unchecked checkboxes that are visible
        checkboxes = Array.from(checkboxes).filter(cb => !cb.checked && cb.offsetParent !== null);
        
        console.log('Found', checkboxes.length, 'visible unchecked checkboxes');
        
        for (const checkbox of checkboxes) {
            // Check if already checked
            if (checkbox.checked) continue;
            
            // Get the question text from the checkbox or its label
            let questionText = getLabelForInput(checkbox) || checkbox.getAttribute('aria-label') || '';
            
            // If no label found, try to get text from nearby elements or parent containers
            if (!questionText) {
                // Look for text in parent fieldset or form section
                let parent = checkbox.closest('fieldset, .jobs-easy-apply-form-section__question, [data-test-form-element]');
                if (parent) {
                    questionText = parent.innerText.substring(0, 300);
                }
            }
            
            console.log('Checkbox question:', JSON.stringify(questionText));
            
            // Get answer from patterns
            const answer = getAnswerForQuestion(questionText, 'checkbox');
            
            // Check the checkbox if answer is Yes or if it's a privacy/consent checkbox
            const questionLower = questionText.toLowerCase();
            const isPrivacyOrConsent = questionLower.includes('privacy') || 
                                      questionLower.includes('consent') ||
                                      questionLower.includes('agree') ||
                                      questionLower.includes('declare') ||
                                      questionLower.includes('i consent');
            
            if (answer && answer.toLowerCase() === 'yes') {
                checkbox.click();
                console.log('Checked checkbox for:', questionText.substring(0, 50));
                filledAny = true;
            } else if (isPrivacyOrConsent) {
                // Default to checking privacy/consent checkboxes
                checkbox.click();
                console.log('Checked privacy/consent checkbox:', questionText.substring(0, 50));
                filledAny = true;
            } else {
                console.log('Skipping checkbox - not privacy/consent related:', questionText.substring(0, 50));
            }
        }
        
        // Handle radio buttons (Yes/No questions)
        const radioGroups = modal.querySelectorAll('fieldset, [role="radiogroup"], .jobs-easy-apply-form-section__question');
        console.log('Found', radioGroups.length, 'potential radio groups');
        
        for (const group of radioGroups) {
            const radios = group.querySelectorAll('input[type="radio"]');
            if (radios.length === 0) continue;
            
            // Check if any radio is already selected
            const isSelected = Array.from(radios).some(r => r.checked);
            if (isSelected) continue;
            
            // Get the question text from the group
            const questionText = getLabelForInput(group) || group.innerText.substring(0, 200);
            console.log('Radio group question:', JSON.stringify(questionText));
            
            // Get answer from patterns
            const answer = getAnswerForQuestion(questionText, 'radio');
            
            if (answer) {
                const answerLower = answer.toLowerCase();
                let selected = false;
                
                // Try to find and click the matching radio
                for (const radio of radios) {
                    const radioLabel = getLabelForInput(radio) || radio.value || '';
                    const radioText = radioLabel.toLowerCase();
                    
                    if (radioText.includes(answerLower) || 
                        (answerLower === 'yes' && radioText.includes('yes')) ||
                        (answerLower === 'no' && radioText.includes('no'))) {
                        radio.click();
                        console.log('Selected radio:', answer, 'for question:', questionText.substring(0, 50));
                        filledAny = true;
                        selected = true;
                        break;
                    }
                }
                
                // If no match found but we have a Yes/No answer, select first Yes or No option
                if (!selected && (answerLower === 'yes' || answerLower === 'no')) {
                    for (const radio of radios) {
                        const radioLabel = getLabelForInput(radio) || radio.value || '';
                        const radioText = radioLabel.toLowerCase();
                        
                        if ((answerLower === 'yes' && (radioText.includes('yes') || radio.value === 'true')) ||
                            (answerLower === 'no' && (radioText.includes('no') || radio.value === 'false'))) {
                            radio.click();
                            console.log('Selected radio (fallback):', answer, 'for question:', questionText.substring(0, 50));
                            filledAny = true;
                            break;
                        }
                    }
                }
            }
        }
        
        if (filledAny) {
            return 'LINKEDIN_FORM_FIELDS_FILLED';
        }
        
        // CRITICAL: Check for visible dropdown options BEFORE clicking Next
        // This prevents proceeding when a location or other autocomplete dropdown is open
        const visibleOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, [data-test-typeahead-item], .artdeco-typeahead__result, .jobs-typeahead__item');
        for (const option of visibleOptions) {
            if (option.offsetParent !== null) {
                const text = option.innerText.trim();
                if (text && text.length > 2 && !text.toLowerCase().includes('select')) {
                    console.log('WARNING: Dropdown option visible, NOT clicking Next:', text);
                    return 'LINKEDIN_WAITING_FOR_DROPDOWN_SELECTION';
                }
            }
        }
        
        // Also check for any open typeahead results containers
        const typeaheadContainers = document.querySelectorAll('[data-test-typeahead-results], .artdeco-typeahead__results-list, .jobs-typeahead__list');
        for (const container of typeaheadContainers) {
            if (container.offsetParent !== null && container.children.length > 0) {
                console.log('WARNING: Typeahead dropdown container is visible, NOT clicking Next');
                return 'LINKEDIN_WAITING_FOR_TYPEAHEAD';
            }
        }
        
        // Find next/submit button
        const nextBtn = findByText('button', 'continue to next step') || 
                       findByText('button', 'review your application') ||
                       findByText('button', 'submit application') ||
                       findByText('button', 'next') ||
                       modal.querySelector('button[aria-label="Continue to next step"], button[aria-label="Review your application"], button[aria-label="Submit application"]');
        
        if (!nextBtn) {
            return 'LINKEDIN_FORM_NO_BUTTON';
        }
        
        // Check if form still has validation errors after filling
        const remainingErrors = modal.querySelectorAll('.artdeco-inline-feedback__message, [data-test-form-element-error-message]');
        let errorCount = 0;
        let hasCheckboxError = false;
        for (const error of remainingErrors) {
            if (error.offsetParent !== null && error.innerText.trim()) {
                errorCount++;
                const errorText = error.innerText.toLowerCase();
                if (errorText.includes('checkbox') || errorText.includes('consent') || errorText.includes('agree') || errorText.includes('select')) {
                    hasCheckboxError = true;
                }
            }
        }
        
        // Fallback: If we have checkbox/consent validation errors, try to check ALL unchecked checkboxes
        if (hasCheckboxError && errorCount > 0) {
            console.log('Checkbox/consent validation error detected - attempting to check all unchecked checkboxes');
            const allCheckboxes = document.querySelectorAll('input[type="checkbox"]:not(:checked)');
            let checkedCount = 0;
            for (const cb of allCheckboxes) {
                if (cb.offsetParent !== null) {
                    cb.click();
                    checkedCount++;
                }
            }
            if (checkedCount > 0) {
                console.log('Checked', checkedCount, 'checkboxes as fallback');
                return 'LINKEDIN_CHECKBOXES_CHECKED_FALLBACK';
            }
        }
        
        if (errorCount > 0) {
            console.log('Validation errors remaining:', errorCount);
            return 'LINKEDIN_FORM_HAS_ERRORS';
        }
        
        // Click next/submit
        console.log('Clicking next/submit button');
        nextBtn.click();
        return 'LINKEDIN_FORM_SUBMITTED';
    }
    
    // Run automation
    return runLinkedInAutomation();
})();
