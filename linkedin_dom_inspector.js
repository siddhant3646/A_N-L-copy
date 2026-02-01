// LINKEDIN DOM INSPECTOR
// Run this in your browser console when on LinkedIn job search page

console.log('=== LINKEDIN DOM INSPECTION ===\n');

// 1. Find sidebar container
console.log('1. SIDEBAR SELECTORS:');
const sidebarSelectors = [
    '.jobs-search-results-list',
    '.scaffold-layout__list-container', 
    'ul.scaffold-layout__list-container',
    '.jobs-search-results-list__list',
    '[data-test-results-list]',
    '.jobs-search-two-pane__results-list',
    '[class*="jobs-search"][class*="list"]',
    '.scaffold-layout__list'
];

let foundSidebar = null;
for (const selector of sidebarSelectors) {
    const el = document.querySelector(selector);
    if (el) {
        console.log(`  ✓ ${selector} - FOUND`);
        foundSidebar = el;
    } else {
        console.log(`  ✗ ${selector} - not found`);
    }
}

// 2. Find job cards
console.log('\n2. JOB CARDS:');
if (foundSidebar) {
    const cards = foundSidebar.querySelectorAll('li, [data-job-id], [data-occludable-job-id]');
    console.log(`  Found ${cards.length} potential job cards in sidebar`);
    
    if (cards.length > 0) {
        const firstCard = cards[0];
        console.log('\n  First card details:');
        console.log(`    Tag: ${firstCard.tagName}`);
        console.log(`    class: ${firstCard.className}`);
        console.log(`    data-job-id: ${firstCard.getAttribute('data-job-id')}`);
        console.log(`    data-occludable-job-id: ${firstCard.getAttribute('data-occludable-job-id')}`);
    }
} else {
    // Try global search
    const globalCards = document.querySelectorAll('[data-job-id], [data-occludable-job-id]');
    console.log(`  Sidebar not found, but found ${globalCards.length} elements with job IDs globally`);
}

// 3. Find Easy Apply button
console.log('\n3. EASY APPLY BUTTON:');
const easyApplyBtn = document.querySelector('button.jobs-apply-button');
if (easyApplyBtn) {
    console.log('  ✓ Found .jobs-apply-button');
    console.log(`    Text: "${easyApplyBtn.innerText}"`);
} else {
    console.log('  ✗ .jobs-apply-button not found');
    
    // Try alternative selectors
    const altButtons = document.querySelectorAll('button');
    for (const btn of altButtons) {
        if (btn.innerText.toLowerCase().includes('easy apply')) {
            console.log(`  ✓ Found by text: ${btn.className}`);
            break;
        }
    }
}

// 4. Check for job details pane
console.log('\n4. JOB DETAILS PANE:');
const detailPane = document.querySelector('.jobs-search__job-details--container, .jobs-details');
console.log(detailPane ? '  ✓ Found' : '  ✗ Not found');

// 5. Current URL job ID
console.log('\n5. CURRENT URL:');
const urlParams = new URLSearchParams(window.location.search);
const currentJobId = urlParams.get('currentJobId');
console.log(`  currentJobId: ${currentJobId}`);

// 6. Check if current job is applied
console.log('\n6. APPLIED STATUS:');
const bodyText = document.body.innerText;
if (bodyText.includes('Applied')) {
    const match = bodyText.match(/Applied\s+(\d+\s+(?:seconds?|minutes?|hours?|days?)\s+ago)/i);
    if (match) {
        console.log(`  ✓ Job shows: "Applied ${match[1]}"`);
    } else {
        console.log('  ✓ Page contains "Applied" text');
    }
} else {
    console.log('  Not applied (no "Applied" text found)');
}

console.log('\n=== END INSPECTION ===');

// Return summary object for easy copying
{
    sidebar_found: !!foundSidebar,
    job_cards: foundSidebar ? foundSidebar.querySelectorAll('li').length : 0,
    easy_apply_found: !!document.querySelector('button.jobs-apply-button'),
    current_job_id: currentJobId,
    url: window.location.href
}
