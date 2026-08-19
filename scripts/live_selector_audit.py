#!/usr/bin/env python3
"""
Live Selector Audit Script
Opens the browser using the exact same Browser/Profile configuration as Sentinel,
navigates through all 7 tasks, extracts elements, and verifies selectors against live DOM.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, get_shared_playwright, reset_shared_playwright, stop_shared_playwright, cleanup_tmp_root
from src.sentinel import prompts

TASKS = [
    {
        "id": 1,
        "name": "Naukri Application",
        "url": "https://www.naukri.com/mnjuser/recommendedjobs",
        "prompt": prompts.NAUKRI_JOB_APPLY_TASK,
        "platform": "naukri",
        "category": "recommendedjobs",
    },
    {
        "id": 2,
        "name": "LinkedIn Application",
        "url": "https://www.linkedin.com/jobs/search-results/?currentJobId=4325424519&keywords=%22hiring%22%20AND%20%28%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22%29%20AND%20India&origin=JOB_SEARCH_PAGE_JOB_FILTER&referralSearchId=Qwth1ndwtouG0vtFGj%2Bpsg%3D%3D&geoId=102713980&distance=0.0&f_TPR=r86400&f_AL=true",
        "prompt": prompts.LINKEDIN_JOB_APPLY_TASK,
        "platform": "linkedin",
        "category": "jobs_search",
    },
    {
        "id": 3,
        "name": "Instahyre Search",
        "url": "https://www.instahyre.com/candidate/opportunities/?matching=true",
        "prompt": prompts.INSTAHYRE_SEARCH_TASK,
        "platform": "instahyre",
        "category": "opportunities",
    },
    {
        "id": 4,
        "name": "Naukri Employment LWD +15",
        "url": "https://www.naukri.com/mnjuser/profile?id=&altresid",
        "prompt": prompts.NAUKRI_EMPLOYMENT_LWD_15_TASK,
        "platform": "naukri",
        "category": "profile_employment",
    },
    {
        "id": 5,
        "name": "Naukri Employment LWD +14",
        "url": "https://www.naukri.com/mnjuser/profile?id=&altresid",
        "prompt": prompts.NAUKRI_EMPLOYMENT_LWD_14_TASK,
        "platform": "naukri",
        "category": "profile_employment",
    },
    {
        "id": 6,
        "name": "Naukri Profile Update",
        "url": "https://www.naukri.com/mnjuser/profile?id=&altresid",
        "prompt": prompts.NAUKRI_PROFILE_UPDATE_TASK,
        "platform": "naukri",
        "category": "profile_headline",
    },
    {
        "id": 7,
        "name": "Naukri Early Access",
        "url": "https://www.naukri.com/mnjuser/recommended-earjobs",
        "prompt": prompts.NAUKRI_EARLY_ACCESS_TASK,
        "platform": "naukri",
        "category": "recommended_earjobs",
    },
]


async def inspect_page_selectors(page, task_info):
    """Inspect and test all selectors relevant to the current task on the live page."""
    task_cat = task_info["category"]
    task_name = task_info["name"]
    print(f"\n🔍 [AUDIT] Running DOM Selector Inspection for: {task_name}")

    audit_results = {
        "task_id": task_info["id"],
        "task_name": task_name,
        "url": page.url,
        "title": await page.title(),
        "timestamp": datetime.now().isoformat(),
        "selectors": {},
        "summary": {}
    }

    if task_cat == "recommendedjobs":
        js_inspection = """() => {
            const results = {};
            
            // 1. Job card/container selectors
            const cardSelectors = [
                'article.jobTuple',
                '.dspIB.saveJobContainer.tuple-check-box',
                'div.tuple-check-box',
                'div.srp-jobtuple-wrapper',
                'div.cust-job-tuple',
                'div.tuple',
                '[data-job-id]',
                '.job-card',
                '.tuple-wrapper',
                'div.list > article',
                'div.styles_tuple-wrapper__',
                'div[class*="styles_tuple-wrapper"]',
                'div[class*="tuple"]',
                'div[class*="jobTuple"]'
            ];
            results.cards = {};
            cardSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.cards[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    sample_tag: els[0] ? els[0].tagName : null,
                    sample_class: els[0] ? els[0].className : null,
                    sample_text: els[0] ? els[0].innerText.substring(0, 80).replace(/\\n/g, ' ') : null
                };
            });

            // 2. Checkbox selectors
            const checkboxSelectors = [
                '.dspIB.saveJobContainer.tuple-check-box',
                'div.tuple-check-box i',
                '.tuple-check-box i.ico-checkbox',
                'i.ico-checkbox',
                'i.naukicon-checkbox',
                '.saveJobContainer i',
                'i[class*="checkbox"]',
                'div[class*="checkbox"]',
                'i.ni-icon',
                'i[class*="ico"]',
                '.tuple-check-box'
            ];
            results.checkboxes = {};
            checkboxSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.checkboxes[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    sample_class: els[0] ? els[0].className : null,
                    sample_parent_class: (els[0] && els[0].parentElement) ? els[0].parentElement.className : null
                };
            });

            // 3. Apply Button Selectors
            const applySelectors = [
                'button.multi-apply-button',
                'button.multi-apply-button.typ-16Bold',
                '.multi-apply-button',
                'span.fright button',
                'button.apply-button',
                'button[class*="multi-apply"]',
                'button[class*="apply"]',
                '.apply-bar',
                'div[class*="apply-bar"]',
                'div[class*="apply"]'
            ];
            results.apply_buttons = {};
            applySelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.apply_buttons[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    text: els[0] ? els[0].innerText.trim() : null,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // 4. Chatbot drawer selectors
            const chatbotSelectors = [
                '.chatbot_DrawerContentWrapper',
                '#chatbot_DrawerContentWrapper',
                '.chatbot_drawer',
                '[class*="DrawerContentWrapper"]',
                'div.chatbot_drawer',
                'div[class*="chatbot"]',
                'div[class*="drawer"]',
                'div[class*="chat-drawer"]',
                'div[class*="Drawer"]'
            ];
            results.chatbot_drawer = {};
            chatbotSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.chatbot_drawer[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // 5. Total job cards overview
            const allTuples = document.querySelectorAll('article, div[class*="tuple"], div[class*="job-card"]');
            results.page_tuples_detected = allTuples.length;
            
            // Check if user is logged in
            results.is_logged_in = !document.querySelector('a[href*="login"]') && !!document.querySelector('a[href*="profile"], div[class*="nI-gNb-drawer"], div.nI-gNb-header');

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    elif task_cat == "jobs_search":
        js_inspection = """() => {
            const results = {};
            
            // 1. Job search card selectors
            const cardSelectors = [
                '.scaffold-layout__list',
                '.scaffold-layout__list-container',
                'li.scaffold-layout__list-item',
                '[data-occludable-job-id]',
                'div[data-job-id]',
                '.jobs-search-results-list',
                '.job-card-container',
                '.jobs-search-results__list-item',
                'div[data-view-name="job-search-job-card"]'
            ];
            results.job_cards = {};
            cardSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.job_cards[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    sample_class: els[0] ? els[0].className : null,
                    sample_attr: els[0] ? (els[0].getAttribute('data-job-id') || els[0].getAttribute('data-occludable-job-id') || els[0].getAttribute('data-view-name')) : null
                };
            });

            // 2. Easy Apply button selectors
            const applySelectors = [
                '#jobs-apply-button-id',
                'button.jobs-apply-button',
                'button[aria-label*="Easy Apply"]',
                'button.jobs-apply-button--top-card',
                'div.jobs-apply-button--top-card button',
                '.jobs-apply-button'
            ];
            results.easy_apply_buttons = {};
            applySelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.easy_apply_buttons[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    text: els[0] ? els[0].innerText.trim() : null,
                    aria_label: els[0] ? els[0].getAttribute('aria-label') : null,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // 3. Modal selectors
            const modalSelectors = [
                'div.jobs-easy-apply-modal',
                '.artdeco-modal',
                'div[data-test-modal]',
                '.artdeco-modal__content'
            ];
            results.modals = {};
            modalSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.modals[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false
                };
            });

            results.is_logged_in = !document.querySelector('a[href*="login"]') && !!document.querySelector('.global-nav__me, .feed-identity-module, nav.global-nav');

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    elif task_cat == "opportunities":
        js_inspection = """() => {
            const results = {};
            
            // 1. Filter toggle selectors
            const filterToggleSelectors = [
                '#filter-toggle',
                '.filter-toggle',
                'button#filter-toggle',
                'div.filter-toggle',
                'a[data-target="#filter-modal"]',
                '.search-filter-container',
                'button.btn-show-results'
            ];
            results.filter_toggles = {};
            filterToggleSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.filter_toggles[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    text: els[0] ? els[0].innerText.trim() : null
                };
            });

            // 2. Filter input selectors
            const inputSelectors = [
                'input#years',
                '#years',
                'input#location-selectized',
                '#location-selectized',
                'input#skills-selectized',
                '#skills-selectized',
                'input#job-functions-selectized',
                '#job-functions-selectized',
                'button#show-results',
                '#show-results',
                '.btn-show-results'
            ];
            results.filter_inputs = {};
            inputSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.filter_inputs[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    id: els[0] ? els[0].id : null,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // 3. Job card view / apply selectors
            const jobSelectors = [
                'button#interested-btn',
                'button.button-interested.btn-success',
                'a.btn-interested',
                'button.btn-interested',
                '.opportunity-card',
                'button.btn-primary.new-btn',
                'button.btn-lg.btn-primary',
                'button#apply-btn'
            ];
            results.job_actions = {};
            jobSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.job_actions[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    text: els[0] ? els[0].innerText.trim() : null
                };
            });

            results.is_logged_in = !document.querySelector('a[href*="login"]') && !!document.querySelector('nav, .navbar, .candidate-profile');

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    elif task_cat == "profile_employment":
        js_inspection = """() => {
            const results = {};
            
            // 1. Employment section
            const sectionSelectors = [
                '#lazyEmployment',
                '[data-plugin="lazyload"][id*="Employment"]',
                '.employment-section',
                'div.widgetContainer'
            ];
            results.employment_section = {};
            sectionSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.employment_section[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false
                };
            });

            // Find employment container and edit icon
            let empSection = document.querySelector('#lazyEmployment');
            if (!empSection) {
                empSection = document.querySelector('[data-plugin="lazyload"][id*="Employment"]');
            }
            if (!empSection) {
                const headings = document.querySelectorAll('h2, h3, .widgetHead');
                for (let h of headings) {
                    if (h.innerText && h.innerText.trim() === 'Employment') {
                        empSection = h.closest('.widgetContainer, [class*="widget"], .card, section');
                        break;
                    }
                }
            }

            results.emp_section_found = !!empSection;

            const editSelectors = [
                'span.edit.icon',
                '.edit.icon',
                '[class*="edit"][class*="icon"]',
                'span[class*="edit"]',
                '.editIcon'
            ];
            results.edit_icons = {};
            editSelectors.forEach(sel => {
                const els = empSection ? empSection.querySelectorAll(sel) : document.querySelectorAll(sel);
                results.edit_icons[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // Check dropdown selectors
            const dropdownSelectors = [
                '#lwdYearFor',
                '#lwdMonthFor',
                '#lwdDayFor',
                '.dropdownList',
                '#submitEmployment',
                'button.btn-dark-ot'
            ];
            results.dropdown_and_save = {};
            dropdownSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.dropdown_and_save[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false
                };
            });

            results.is_logged_in = !document.querySelector('a[href*="login"]') && !!document.querySelector('a[href*="profile"], div.nI-gNb-header, div.profile-section, .user-name');

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    elif task_cat == "profile_headline":
        js_inspection = """() => {
            const results = {};
            
            // 1. Headline section
            const sectionSelectors = [
                '#lazyResumeHead',
                '.resumeHeadline',
                'div[data-plugin="lazyload"][id*="ResumeHead"]',
                'div.resume-headline-section'
            ];
            results.headline_section = {};
            sectionSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.headline_section[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false
                };
            });

            const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
            results.headline_section_found = !!headlineSection;

            // 2. Edit icon
            const editSelectors = [
                'span.edit.icon',
                'span.icon.edit',
                '[class*="edit"][class*="icon"]',
                'span[class*="edit"]'
            ];
            results.edit_icons = {};
            editSelectors.forEach(sel => {
                const els = headlineSection ? headlineSection.querySelectorAll(sel) : document.querySelectorAll(sel);
                results.edit_icons[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    sample_class: els[0] ? els[0].className : null
                };
            });

            // 3. Textarea and save button
            const formSelectors = [
                '#resumeHeadline',
                'textarea[id="resumeHeadline"]',
                '.form-actions button.btn-dark-ot',
                '.action.s12 button.btn-dark-ot',
                'button.btn-dark-ot[type="submit"]',
                'button[type="submit"]'
            ];
            results.form_elements = {};
            formSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.form_elements[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    sample_val_length: els[0] && els[0].value ? els[0].value.length : null
                };
            });

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    elif task_cat == "recommended_earjobs":
        js_inspection = """() => {
            const results = {};
            
            // 1. Early Access container
            const containerSelectors = [
                'section.lp__left-section-container',
                'div.recommended-jobs-container',
                'div.tuple-wrapper',
                'div.row7',
                'div.tf__content'
            ];
            results.containers = {};
            containerSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.containers[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false
                };
            });

            // 2. Share interest button
            const specificBtn = "body > main > div > div > div > section.lp__left-section-container > div > div:nth-child(1) > div > div.row7 > div > div.tf__content > button";
            const shareBtnSelectors = [
                specificBtn,
                'div.tf__content button',
                'button.tf__content',
                'button.share-interest-btn',
                'button:has-text("Share interest")'
            ];
            results.share_buttons = {};
            shareBtnSelectors.forEach(sel => {
                try {
                    const els = document.querySelectorAll(sel);
                    results.share_buttons[sel] = {
                        count: els.length,
                        found: els.length > 0,
                        visible: els[0] ? (els[0].offsetParent !== null) : false,
                        text: els[0] ? els[0].innerText.trim() : null
                    };
                } catch(e) {
                    results.share_buttons[sel] = { error: e.message };
                }
            });

            // Check all buttons for text match
            const allBtns = Array.from(document.querySelectorAll('button'));
            const matchedBtns = allBtns.filter(b => (b.innerText || '').toLowerCase().includes('share interest'));
            results.share_interest_text_matches = {
                count: matchedBtns.length,
                visible_count: matchedBtns.filter(b => b.offsetParent !== null).length,
                classes: matchedBtns.map(b => b.className)
            };

            // 3. Success status header
            const statusSelectors = [
                '.apply-status-header.green .apply-message',
                '.apply-status-header .apply-message',
                '.apply-status-header'
            ];
            results.status_messages = {};
            statusSelectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                results.status_messages[sel] = {
                    count: els.length,
                    found: els.length > 0,
                    visible: els[0] ? (els[0].offsetParent !== null) : false,
                    text: els[0] ? els[0].innerText.trim() : null
                };
            });

            return results;
        }"""
        audit_results["selectors"] = await page.evaluate(js_inspection)

    return audit_results


async def run_live_test_suite():
    """Run all 7 tasks using the seeded profile and inspect live DOM elements."""
    print("=" * 70)
    print("🛡️  STARTING SENTINEL LIVE BROWSER TEST & SELECTOR AUDIT")
    print(f"📁 Seeded Profile: {CHROME_USER_DATA}")
    print("=" * 70)

    # Initialize Browser instance with the seeded Chrome profile
    browser = Browser(
        headless=False,
        user_data_dir=CHROME_USER_DATA
    )

    all_audits = []

    try:
        print("\n🚀 Starting Browser...")
        await browser.start()

        page = await browser.get_current_page()
        if not page:
            page = await browser.new_page()

        print("✅ Browser started successfully with seeded profile!")

        for task in TASKS:
            task_id = task["id"]
            task_name = task["name"]
            task_url = task["url"]

            print(f"\n{'#'*60}")
            print(f"🎯 TASK {task_id}/7: {task_name}")
            print(f"🔗 URL: {task_url}")
            print(f"{'#'*60}")

            try:
                print(f"⏳ Navigating to {task_url}...")
                await page.goto(task_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(6)  # Allow dynamic JS content, lazyload, and hydration to settle

                # Handle interactive modal testing if applicable
                if task["category"] == "profile_employment":
                    # Let's also test opening the employment modal dynamically to inspect dropdown selectors inside modal
                    print("   🔍 Testing Employment modal expansion...")
                    modal_opened = await page.evaluate("""() => {
                        let empSection = document.querySelector('#lazyEmployment');
                        if (!empSection) {
                            empSection = document.querySelector('[data-plugin="lazyload"][id*="Employment"]');
                        }
                        if (!empSection) {
                            const headings = document.querySelectorAll('h2, h3, .widgetHead');
                            for (let h of headings) {
                                if (h.innerText && h.innerText.trim() === 'Employment') {
                                    empSection = h.closest('.widgetContainer, [class*="widget"], .card, section');
                                    break;
                                }
                            }
                        }
                        if (empSection) {
                            const editIcon = empSection.querySelector('span.edit.icon, .edit.icon, [class*="edit"][class*="icon"]');
                            if (editIcon) {
                                editIcon.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if modal_opened:
                        print("   ✅ Employment edit clicked, waiting 3s for modal...")
                        await asyncio.sleep(3)
                        # Inspect inside the open modal
                        dropdown_audit = await page.evaluate("""() => {
                            const y = document.querySelector('#lwdYearFor');
                            const m = document.querySelector('#lwdMonthFor');
                            const d = document.querySelector('#lwdDayFor');
                            const s = document.querySelector('#submitEmployment, button[type="submit"], button.btn-dark-ot');
                            
                            // Check data-ids in DOM
                            const yearAnchors = document.querySelectorAll('a[data-id^="lwdYear_"]');
                            const monthAnchors = document.querySelectorAll('a[data-id^="lwdMonth_"]');
                            const dayAnchors = document.querySelectorAll('a[data-id^="lwdDay_"]');

                            return {
                                year_dropdown_visible: y ? y.offsetParent !== null : false,
                                month_dropdown_visible: m ? m.offsetParent !== null : false,
                                day_dropdown_visible: d ? d.offsetParent !== null : false,
                                save_btn_visible: s ? s.offsetParent !== null : false,
                                save_btn_text: s ? s.innerText.trim() : null,
                                year_anchors_count: yearAnchors.length,
                                month_anchors_count: monthAnchors.length,
                                day_anchors_count: dayAnchors.length,
                                sample_month_data_ids: Array.from(monthAnchors).slice(0, 4).map(a => a.getAttribute('data-id')),
                                sample_day_data_ids: Array.from(dayAnchors).slice(0, 4).map(a => a.getAttribute('data-id'))
                            };
                        }""")
                        print(f"   📋 Modal Dropdowns Data: {json.dumps(dropdown_audit, indent=2)}")
                        # Close modal by clicking outside/cancel
                        await page.evaluate("""() => {
                            const cancelBtn = document.querySelector('.modal-header .cross, .close, button.cancelBtn, .cancelBtn');
                            if (cancelBtn) cancelBtn.click();
                            else document.body.click();
                        }""")
                        await asyncio.sleep(1)

                elif task["category"] == "profile_headline":
                    print("   🔍 Testing Resume Headline modal expansion...")
                    headline_modal_opened = await page.evaluate("""() => {
                        const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
                        if (headlineSection) {
                            const editIcon = headlineSection.querySelector('span.edit.icon, span.icon.edit, [class*="edit"][class*="icon"]');
                            if (editIcon) {
                                editIcon.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if headline_modal_opened:
                        print("   ✅ Resume Headline edit clicked, waiting 3s for modal...")
                        await asyncio.sleep(3)
                        headline_modal_audit = await page.evaluate("""() => {
                            const textarea = document.querySelector('#resumeHeadline, textarea[id="resumeHeadline"]');
                            const saveBtn = document.querySelector('.form-actions button.btn-dark-ot, .action.s12 button.btn-dark-ot, button.btn-dark-ot[type="submit"], button[type="submit"]');
                            return {
                                textarea_found: !!textarea,
                                textarea_visible: textarea ? textarea.offsetParent !== null : false,
                                current_headline: textarea ? textarea.value : null,
                                save_btn_found: !!saveBtn,
                                save_btn_visible: saveBtn ? saveBtn.offsetParent !== null : false,
                                save_btn_class: saveBtn ? saveBtn.className : null
                            };
                        }""")
                        print(f"   📋 Resume Headline Modal Data: {json.dumps(headline_modal_audit, indent=2)}")
                        # Close modal
                        await page.evaluate("""() => {
                            const cancelBtn = document.querySelector('.modal-header .cross, .close, button.cancelBtn, .cancelBtn, .cancel-btn');
                            if (cancelBtn) cancelBtn.click();
                            else document.body.click();
                        }""")
                        await asyncio.sleep(1)

                # Inspect DOM selectors for this page
                task_audit = await inspect_page_selectors(page, task)
                all_audits.append(task_audit)
                print(f"📊 Audit Result for {task_name}:\n{json.dumps(task_audit['selectors'], indent=2)}")

            except Exception as e:
                print(f"❌ Error during task {task_name}: {e}")
                all_audits.append({
                    "task_id": task_id,
                    "task_name": task_name,
                    "url": task_url,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })

            await asyncio.sleep(3)

        # Save comprehensive results to audit JSON file
        out_path = Path(__file__).parent.parent / "audit" / "live_selector_audit_results.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(all_audits, f, indent=2)
        print(f"\n💾 Saved detailed audit results to: {out_path}")

    finally:
        print("\n🔒 Closing browser session...")
        await browser.stop()
        await stop_shared_playwright()
        cleanup_tmp_root()
        print("✅ Live test suite complete.")

if __name__ == "__main__":
    asyncio.run(run_live_test_suite())
