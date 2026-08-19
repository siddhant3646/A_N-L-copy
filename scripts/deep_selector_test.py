#!/usr/bin/env python3
"""
Deep Selector Test & Verification Script
Deeply tests interactive flows:
1. Naukri Job selection + Apply + Chatbot drawer detection
2. LinkedIn search page vs single job page + Auth inspection
3. Instahyre filter expansion + View » click + Apply modal inspection
4. Naukri Employment LWD dropdown data-ids inspection
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, stop_shared_playwright, cleanup_tmp_root


async def run_deep_tests():
    print("=" * 70)
    print("🔬 RUNNING DEEP SELECTOR INTERACTION TESTS")
    print("=" * 70)

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page()
    if not page:
        page = await browser.new_page()

    results = {}

    try:
        # -------------------------------------------------------------
        # TEST 1: Naukri Employment LWD Dropdowns exact data-ids
        # -------------------------------------------------------------
        print("\n" + "="*50)
        print("🔍 TEST 1: Inspecting Naukri Employment Dropdown Data-IDs")
        print("="*50)
        await page.goto("https://www.naukri.com/mnjuser/profile?id=&altresid", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Scroll to employment section to trigger lazyload
        await page.evaluate("""() => {
            const emp = document.querySelector('#lazyEmployment');
            if (emp) emp.scrollIntoView({block: 'center'});
        }""")
        await asyncio.sleep(2)

        emp_data = await page.evaluate("""() => {
            let empSection = document.querySelector('#lazyEmployment');
            if (!empSection) return { error: 'No lazyEmployment section' };
            const editIcon = empSection.querySelector('span.edit.icon, .edit.icon, [class*="edit"][class*="icon"]');
            if (!editIcon) return { error: 'No edit icon in employment section' };
            editIcon.click();
            return { clicked: true };
        }""")
        print(f"   Employment Edit Click: {emp_data}")
        await asyncio.sleep(3)

        # Inspect all options inside Year, Month, Day dropdowns
        dropdown_options = await page.evaluate("""() => {
            const result = {
                year_ids: [],
                month_ids: [],
                day_ids: [],
                dropdown_ids: []
            };

            document.querySelectorAll('a[data-id]').forEach(a => {
                const id = a.getAttribute('data-id');
                if (id.startsWith('lwdYear_')) result.year_ids.push({ id, text: a.innerText.trim() });
                else if (id.startsWith('lwdMonth_')) result.month_ids.push({ id, text: a.innerText.trim() });
                else if (id.startsWith('lwdDay_')) result.day_ids.push({ id, text: a.innerText.trim() });
            });

            document.querySelectorAll('[id*="lwd"], [id*="Lwd"]').forEach(el => {
                result.dropdown_ids.push({
                    id: el.id,
                    tagName: el.tagName,
                    className: el.className,
                    visible: el.offsetParent !== null
                });
            });

            return result;
        }""")
        print(f"   Dropdown elements found: {json.dumps(dropdown_options, indent=2)}")
        results["naukri_employment_dropdowns"] = dropdown_options

        # Close employment modal
        await page.evaluate("""() => {
            const closeBtn = document.querySelector('.modal-header .cross, .close, .cancelBtn');
            if (closeBtn) closeBtn.click();
            else document.body.click();
        }""")
        await asyncio.sleep(2)

        # -------------------------------------------------------------
        # TEST 2: Instahyre Search Filter & View » Modal
        # -------------------------------------------------------------
        print("\n" + "="*50)
        print("🔍 TEST 2: Inspecting Instahyre Filters & Apply Modal")
        print("="*50)
        await page.goto("https://www.instahyre.com/candidate/opportunities/?matching=true", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        instahyre_filters = await page.evaluate("""() => {
            const res = {};
            
            // Look for buttons/links that open filter settings
            const allButtons = Array.from(document.querySelectorAll('button, a, div[class*="filter"]'));
            res.possible_filter_toggles = allButtons
                .filter(el => (el.innerText || '').toLowerCase().includes('search') || (el.innerText || '').toLowerCase().includes('filter') || (el.id || '').includes('filter'))
                .map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    text: el.innerText.trim(),
                    visible: el.offsetParent !== null
                }));

            // Look for all input fields on the page
            res.all_inputs = Array.from(document.querySelectorAll('input')).map(inp => ({
                id: inp.id,
                name: inp.name,
                placeholder: inp.placeholder,
                className: inp.className,
                visible: inp.offsetParent !== null
            }));

            return res;
        }""")
        print(f"   Instahyre Filters: {json.dumps(instahyre_filters, indent=2)}")
        results["instahyre_filters"] = instahyre_filters

        # Test clicking "View »" on first job card
        print("   Testing click on first 'View »' button...")
        view_clicked = await page.evaluate("""() => {
            const btn = document.querySelector('button#interested-btn, button.button-interested.btn-success');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return { clicked: true, text: btn.innerText.trim() };
            }
            return { clicked: false };
        }""")
        print(f"   View Click Result: {view_clicked}")
        await asyncio.sleep(3)

        # Inspect job detail modal on Instahyre
        instahyre_modal_data = await page.evaluate("""() => {
            const modal = document.querySelector('.modal.in, .modal.show, div[id*="opportunity"], div.modal-dialog');
            const applyButtons = Array.from(document.querySelectorAll('button, a'))
                .filter(b => (b.innerText || '').trim().toLowerCase() === 'apply' || (b.className || '').includes('btn-primary'))
                .map(b => ({
                    tag: b.tagName,
                    id: b.id,
                    className: b.className,
                    text: b.innerText.trim(),
                    visible: b.offsetParent !== null
                }));

            return {
                modal_found: !!modal,
                modal_classes: modal ? modal.className : null,
                apply_buttons: applyButtons
            };
        }""")
        print(f"   Instahyre Modal Data: {json.dumps(instahyre_modal_data, indent=2)}")
        results["instahyre_modal"] = instahyre_modal_data

        # Close modal
        await page.evaluate("""() => {
            const closeBtn = document.querySelector('.modal.in .close, .modal.show .close, button.close, [data-dismiss="modal"]');
            if (closeBtn) closeBtn.click();
            else document.body.click();
        }""")
        await asyncio.sleep(2)

        # -------------------------------------------------------------
        # TEST 3: LinkedIn Profile & Auth Inspection
        # -------------------------------------------------------------
        print("\n" + "="*50)
        print("🔍 TEST 3: Inspecting LinkedIn Page & Auth State")
        print("="*50)
        await page.goto("https://www.linkedin.com/jobs/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        linkedin_data = await page.evaluate("""() => {
            return {
                url: window.location.href,
                title: document.title,
                cookies_count: document.cookie ? document.cookie.split(';').length : 0,
                has_nav: !!document.querySelector('nav, .global-nav'),
                has_me_icon: !!document.querySelector('.global-nav__me, .feed-identity-module'),
                body_text_snippet: document.body.innerText.substring(0, 300).replace(/\\n/g, ' '),
                sign_in_buttons: Array.from(document.querySelectorAll('a, button'))
                    .filter(b => (b.innerText || '').toLowerCase().includes('sign in') || (b.innerText || '').toLowerCase().includes('log in'))
                    .map(b => ({ tag: b.tagName, text: b.innerText.trim(), href: b.href || null }))
            };
        }""")
        print(f"   LinkedIn /jobs/ Status: {json.dumps(linkedin_data, indent=2)}")
        results["linkedin_status"] = linkedin_data

        # -------------------------------------------------------------
        # TEST 4: Naukri Recommended Jobs Checkbox Click & Apply State
        # -------------------------------------------------------------
        print("\n" + "="*50)
        print("🔍 TEST 4: Testing Naukri Checkbox Selection & Apply Button")
        print("="*50)
        await page.goto("https://www.naukri.com/mnjuser/recommendedjobs", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        naukri_action_test = await page.evaluate("""() => {
            const results = {};
            
            // Find checkboxes
            const cbContainers = document.querySelectorAll('.dspIB.saveJobContainer.tuple-check-box');
            results.checkbox_containers_count = cbContainers.length;

            if (cbContainers.length > 0) {
                const firstCb = cbContainers[0].querySelector('i');
                results.first_cb_found = !!firstCb;
                results.first_cb_class = firstCb ? firstCb.className : null;

                const applyBtnBefore = document.querySelector('.multi-apply-button');
                results.apply_btn_before = {
                    text: applyBtnBefore ? applyBtnBefore.innerText.trim() : null,
                    class: applyBtnBefore ? applyBtnBefore.className : null,
                    disabled: applyBtnBefore ? applyBtnBefore.disabled : null
                };

                // Simulate clicking the checkbox
                if (firstCb) {
                    firstCb.click();
                }

                const applyBtnAfter = document.querySelector('.multi-apply-button');
                results.apply_btn_after = {
                    text: applyBtnAfter ? applyBtnAfter.innerText.trim() : null,
                    class: applyBtnAfter ? applyBtnAfter.className : null,
                    disabled: applyBtnAfter ? applyBtnAfter.disabled : null
                };
            }

            return results;
        }""")
        print(f"   Naukri Checkbox Action Test: {json.dumps(naukri_action_test, indent=2)}")
        results["naukri_action_test"] = naukri_action_test

        # Save deep test results
        out_path = Path(__file__).parent.parent / "audit" / "deep_selector_test_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Saved deep test results to: {out_path}")

    finally:
        await browser.stop()
        await stop_shared_playwright()
        cleanup_tmp_root()
        print("✅ Deep test execution finished.")

if __name__ == "__main__":
    asyncio.run(run_deep_tests())
