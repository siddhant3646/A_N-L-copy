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
    
    // Handle application form
    function handleApplicationForm(modal) {
        console.log('Handling application form...');
        
        // Handle dropdown questions first
        const dropdowns = modal.querySelectorAll('select, [role="combobox"], .jobs-easy-apply-form-section__dropdown, [data-test-text-entity-list-form-select]');
        console.log('Found', dropdowns.length, 'dropdowns');
        
        for (const dropdown of dropdowns) {
            // Check if dropdown needs to be filled
            const isEmpty = !dropdown.value || dropdown.value === '' || dropdown.innerText.includes('Select an option');
            
            if (isEmpty) {
                console.log('Filling dropdown:', dropdown.innerText.substring(0, 50));
                
                // Click to open dropdown
                dropdown.click();
                
                // Wait a moment for options to appear
                setTimeout(() => {
                    // Try to find and click "Yes" option
                    const yesOption = findByText('span, li, div[role="option"]', 'yes', true) ||
                                     findByText('span, li, div[role="option"]', 'yes');
                    
                    if (yesOption) {
                        yesOption.click();
                        console.log('Selected Yes for dropdown');
                    } else {
                        // Fallback: try to select first non-placeholder option
                        const options = document.querySelectorAll('[role="option"], .artdeco-dropdown__item');
                        for (const option of options) {
                            const text = option.innerText.toLowerCase();
                            if (text && !text.includes('select')) {
                                option.click();
                                console.log('Selected option:', text);
                                break;
                            }
                        }
                    }
                }, 100);
                
                // Return early to let dropdown settle
                return 'LINKEDIN_FORM_FILLING_DROPDOWN';
            }
        }
        
        // Handle text inputs
        const inputs = modal.querySelectorAll('input[type="text"], input[type="number"], textarea');
        for (const input of inputs) {
            if (!input.value && input.placeholder) {
                const placeholder = input.placeholder.toLowerCase();
                console.log('Empty input found:', placeholder);
                
                // Smart filling based on placeholder keywords
                if (placeholder.includes('year') || placeholder.includes('experience')) {
                    input.value = '4';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    console.log('Filled with: 4 years');
                }
            }
        }
        
        // Find next/submit button
        const nextBtn = findByText('button', 'continue to next step') || 
                       findByText('button', 'review your application') ||
                       findByText('button', 'submit application');
        
        if (!nextBtn) {
            return 'LINKEDIN_FORM_NO_BUTTON';
        }
        
        // Check if form has validation errors
        const errorMessages = modal.querySelectorAll('.artdeco-inline-feedback__message, [data-test-form-element-error-message]');
        if (errorMessages.length > 0) {
            console.log('Validation errors found:', errorMessages.length);
            for (const error of errorMessages) {
                console.log('Error:', error.innerText);
            }
            return 'LINKEDIN_FORM_HAS_ERRORS';
        }
        
        // Click next/submit
        nextBtn.click();
        return 'LINKEDIN_FORM_SUBMITTED';
    }
    
    // Run automation
    return runLinkedInAutomation();
})();
