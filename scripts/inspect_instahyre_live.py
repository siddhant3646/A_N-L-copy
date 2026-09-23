import asyncio
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright, stop_shared_playwright, cleanup_tmp_root
from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts

OUTPUT_DIR = Path("live_test_output/instahyre")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

INSTAHYRE_URL = "https://www.instahyre.com/candidate/opportunities/?matching=true"


async def analyze_page_elements(page):
    """Deeply inspect and extract all elements on the Instahyre page."""
    analysis = await page.evaluate("""() => {
        const result = {
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            angularDetected: !!window.angular,
            jqueryDetected: !!window.$,
            searchBar: {},
            filters: {
                companySize: [],
                locations: [],
                jobFunctions: [],
                experience: [],
                allCheckboxes: [],
                allSelects: []
            },
            tabs: [],
            actionButtons: [],
            jobCards: [],
            modals: [],
            emptyState: {}
        };

        // 1. Search Bar Inputs & Elements
        const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
        result.searchBar.inputs = inputs.map(i => ({
            id: i.id,
            name: i.name,
            type: i.type,
            placeholder: i.placeholder,
            className: i.className,
            value: i.value,
            offsetParent: !!i.offsetParent,
            ngModel: i.getAttribute('ng-model'),
            ngClick: i.getAttribute('ng-click')
        }));

        // Selectize instances
        result.searchBar.selectizeControls = Array.from(document.querySelectorAll('.selectize-control')).map(sc => {
            const input = sc.querySelector('input');
            const items = Array.from(sc.querySelectorAll('.item')).map(it => (it.innerText || '').replace(/×/g, '').trim());
            return {
                inputId: input ? input.id : null,
                inputPlaceholder: input ? input.placeholder : null,
                selectedItems: items,
                className: sc.className
            };
        });

        // 2. Filters Sidebar
        const labels = Array.from(document.querySelectorAll('label, .ui-checkbox, [class*="checkbox"]'));
        result.filters.allCheckboxes = labels.map(l => {
            const input = l.querySelector('input[type="checkbox"]');
            return {
                text: (l.innerText || l.textContent || '').trim().replace(/\\s+/g, ' '),
                className: l.className,
                hasInput: !!input,
                isChecked: input ? input.checked : null,
                ngClick: (input ? input.getAttribute('ng-click') : null) || l.getAttribute('ng-click'),
                ngModel: (input ? input.getAttribute('ng-model') : null) || l.getAttribute('ng-model')
            };
        }).filter(l => l.text.length > 0 && l.text.length < 100);

        // Selects
        result.filters.allSelects = Array.from(document.querySelectorAll('select')).map(s => ({
            id: s.id,
            name: s.name,
            className: s.className,
            options: Array.from(s.options).map(o => ({ text: o.text.trim(), value: o.value, selected: o.selected })),
            ngModel: s.getAttribute('ng-model')
        }));

        // 3. Tabs
        const tabs = Array.from(document.querySelectorAll('.nav-tabs li, [role="tab"], .tab, [class*="tab"]'));
        result.tabs = tabs.map(t => ({
            text: (t.innerText || t.textContent || '').trim().replace(/\\s+/g, ' '),
            className: t.className,
            active: t.classList.contains('active') || t.getAttribute('aria-selected') === 'true'
        })).filter(t => t.text.length > 0 && t.text.length < 50);

        // 4. Action Buttons
        const buttons = Array.from(document.querySelectorAll('button, a.btn, input[type="button"], input[type="submit"]'));
        result.actionButtons = buttons.map(b => ({
            tag: b.tagName,
            text: (b.innerText || b.textContent || b.value || '').trim().replace(/\\s+/g, ' '),
            id: b.id,
            className: b.className,
            ngClick: b.getAttribute('ng-click'),
            type: b.type,
            isVisible: !!b.offsetParent,
            disabled: b.disabled
        })).filter(b => b.text.length > 0 && b.text.length < 80);

        // 5. Job Cards
        const cardEls = Array.from(document.querySelectorAll('.job-card, [class*="opportunity-card"], [class*="job-listing"], .employer-row, .opportunity-card'));
        result.jobCards = cardEls.map((c, idx) => {
            const title = c.querySelector('h3, h4, .job-title, [class*="title"]');
            const company = c.querySelector('.company-name, .employer-name, [class*="company"]');
            const btns = Array.from(c.querySelectorAll('button, a.btn')).map(b => ({
                text: (b.innerText || b.textContent || '').trim().replace(/\\s+/g, ' '),
                className: b.className,
                ngClick: b.getAttribute('ng-click')
            }));
            return {
                index: idx,
                title: title ? title.innerText.trim() : null,
                company: company ? company.innerText.trim() : null,
                buttons: btns
            };
        });

        // 6. Modals
        const modalEls = Array.from(document.querySelectorAll('.modal, [class*="modal"], [role="dialog"], .dialog'));
        result.modals = modalEls.map(m => ({
            id: m.id,
            className: m.className,
            role: m.getAttribute('role'),
            isOpen: m.classList.contains('in') || m.classList.contains('show') || (m.style && m.style.display === 'block'),
            hasBackdrop: !!document.querySelector('.modal-backdrop'),
            buttons: Array.from(m.querySelectorAll('button')).map(b => (b.innerText || b.textContent || '').trim())
        }));

        // 7. Empty state / Messages
        const bodyText = document.body.innerText || '';
        result.emptyState = {
            hasEmptyStateClass: !!document.querySelector('.no-jobs, .no-results, .empty-state, [class*="empty-state"]'),
            hasNoOpportunitiesFound: bodyText.toLowerCase().includes('no matching opportunities') || bodyText.toLowerCase().includes('no opportunities found'),
            hasCouldNotFind: bodyText.toLowerCase().includes("couldn't find any matching"),
            bodySnippets: bodyText.split('\\n').map(s => s.trim()).filter(s => s.length > 10 && s.length < 150).slice(0, 15)
        };

        return result;
    }""")

    return analysis


async def main():
    print("🚀 Starting Live Instahyre UI Analysis & Flow Test...")
    print(f"📁 Chrome User Data: {CHROME_USER_DATA}")

    browser = Browser(
        headless=False,
        user_data_dir=CHROME_USER_DATA,
    )

    agent = SentinelAgent()

    try:
        print("🌐 Launching Browser (Chrome)...")
        await browser.start()

        page = await browser.get_current_page()
        if not page:
            page = await browser.new_page()

        print(f"🔗 Navigating to Instahyre: {INSTAHYRE_URL}...")
        await page.goto(INSTAHYRE_URL, wait_until="domcontentloaded", timeout=45000)
        print("⏳ Waiting 6 seconds for page and Angular to settle...")
        await asyncio.sleep(6)

        # 1. Initial State Screenshot & Deep Element Extraction
        ts = int(time.time())
        initial_shot = SCREENSHOT_DIR / f"01_initial_page_{ts}.png"
        await page.screenshot(path=str(initial_shot), full_page=False)
        print(f"📸 Initial screenshot captured: {initial_shot.name}")

        print("🔍 Performing deep DOM extraction and element analysis...")
        initial_analysis = await analyze_page_elements(page)

        analysis_file = OUTPUT_DIR / f"instahyre_elements_{ts}.json"
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(initial_analysis, f, indent=2)
        print(f"📄 Full element analysis saved: {analysis_file.name}")

        # 2. Test Full Agent Execution
        agent._page = page
        agent.browser = browser

        print("\n▶️ Running Full Instahyre Search Task via agent.run()...")
        success = await agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)
        print(f"\n📊 Task run completed: Success={success}, Task Complete={agent.state.task_complete}, Steps={agent.state.step_count}")

        ts_end = int(time.time())
        final_shot = SCREENSHOT_DIR / f"final_task_state_{ts_end}.png"
        await page.screenshot(path=str(final_shot), full_page=False)
        print(f"📸 Final screenshot captured: {final_shot.name}")

    except Exception as e:
        print(f"❌ Error during live test: {e}")
        import traceback
        traceback.print_exc()
        if agent._page:
            err_shot = SCREENSHOT_DIR / f"error_{int(time.time())}.png"
            await agent._page.screenshot(path=str(err_shot), full_page=False)
            print(f"📸 Error screenshot captured: {err_shot.name}")
    finally:
        print("🔒 Closing browser session...")
        try:
            await browser.close()
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
