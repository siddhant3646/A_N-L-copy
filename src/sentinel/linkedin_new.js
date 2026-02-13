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
            patterns: ['years of experience', 'months of experience', 'total experience', 'overall experience', 'year of exp', 'total exp', 'your total exp', 'what is your total exp', 'experience in your chosen engineering field', 'years of work experience do you have', 'work experience'],
            linkedin_default: '4',
            default: '3.8 Years'
        },
        current_salary: {
            patterns: ['current salary', 'what is your current salary', 'current ctc', 'current annual ctc', 'monthly salary', 'current ctc in lakhs', 'current ctc in lpa', 'current ctc [in lpa]', 'ctc in lacs per annum', 'cctc', 'what is your cctc', 'your cctc', 'your current ctc', 'what is your current ctc'],
            default: '13.5 LPA',
            numeric_default: '13.5',
            inr_default: '1350000'
        },
        expected_salary: {
            patterns: ['expected salary', 'what is your expected salary', 'expected ctc', 'expected annual ctc', 'expected ctc in lakhs', 'expected ctc in lpa', 'expected ctc [in lpa]', 'ectc', 'what is your ectc', 'your ectc', 'what is your current expected ctc', 'current expected ctc'],
            default: '20 LPA',
            numeric_default: '20',
            inr_default: '2000000'
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
        
        // For CTC/salary fields, on LinkedIn we should always return numeric inr value
        if (category === 'current_salary' || category === 'expected_salary') {
            return data.inr_default; // Always return full numeric value (1350000 or 2000000)
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
    
    // Helper: Find job cards
    function findJobCards() {
        const cards = [];
        
        // Method 1: Look for links with currentJobId
        const jobLinks = document.querySelectorAll('a[href*="currentJobId"]');
        for (const link of jobLinks) {
            const card = link.closest('li') || link.closest('div');
            if (card && !cards.includes(card)) {
                cards.push(card);
            }
        }
        
        // Method 2: Look for list items with job-related content
        if (cards.length === 0) {
            const allLis = document.querySelectorAll('li');
            for (const li of allLis) {
                const text = li.innerText.toLowerCase();
                const hasJobLink = li.querySelector('a[href*="jobs"]') !== null;
                const hasCompany = text.includes('company') || text.includes('inc') || text.includes('corp');
                const hasLocation = text.includes('india') || text.includes('bangalore') || text.includes('mumbai') || text.includes('delhi');
                
                if (hasJobLink && (hasCompany || hasLocation) && li.innerText.length > 50) {
                    cards.push(li);
                }
            }
        }
        
        return cards;
    }
    
    // Helper: Get job ID from card
    function getJobIdFromCard(card) {
        // Try data attributes
        let jobId = card.getAttribute('data-job-id') || card.getAttribute('data-occludable-job-id');
        if (jobId) return jobId;
        
        // Try from link href
        const link = card.querySelector('a[href*="currentJobId"]');
        if (link) {
            const href = link.getAttribute('href');
            const match = href.match(/currentJobId=(\d+)/);
            if (match) return match[1];
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
        
        const currentJobId = new URLSearchParams(window.location.search).get('currentJobId');
        console.log('Current Job ID:', currentJobId);
        
        // Step 1: Handle modals first
        const modal = checkModals();
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
                
                // Use QA patterns to determine the answer
                let selectValue = getAnswerForQuestion(labelText, 'select');
                
                // If no pattern match, use smart defaults based on keywords
                if (!selectValue) {
                    const lowerLabel = labelText.toLowerCase();
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
        
        // Handle text inputs
        const inputs = modal.querySelectorAll('input[type="text"], input[type="number"], input:not([type]), textarea');
        
        for (const input of inputs) {
            if (!input.value || input.value.trim() === '') {
                const placeholder = (input.placeholder || '').toLowerCase();
                const labelText = getLabelForInput(input);
                const lowerLabelText = labelText.toLowerCase();
                const combinedText = placeholder + ' ' + lowerLabelText;
                
                console.log('Empty input found - Label:', JSON.stringify(labelText), '| Placeholder:', JSON.stringify(placeholder));
                console.log('Input element:', input.tagName, input.type, input.className.substring(0, 50));
                
                // Use QA patterns to get the answer
                let fillValue = getAnswerForQuestion(labelText, 'text');
                
                // If no pattern match, use smart fallback based on keywords
                if (!fillValue) {
                    if (combinedText.includes('notice') || combinedText.includes('lwd')) {
                        fillValue = '30';
                        console.log('Fallback: Filling notice period with: 30 days');
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
                
                if (fillValue) {
                    // Use property setter for React inputs
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    nativeInputValueSetter.call(input, fillValue);
                    
                    // Trigger events
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('blur', { bubbles: true }));
                    
                    filledAny = true;
                    console.log('Filled input successfully');
                }
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
        for (const error of remainingErrors) {
            if (error.offsetParent !== null && error.innerText.trim()) {
                errorCount++;
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
