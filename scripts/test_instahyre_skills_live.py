"""Live diagnostic test for Instahyre skills input and search results."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

OUTPUT_DIR = Path("live_test_output/instahyre_skills")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Launching Live Instahyre Skills & Search Investigation...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()

    url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    print(f"🔗 Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(6)

    # 1. Inspect the Selectize configuration on the skills input
    selectize_info = await page.evaluate("""() => {
        const el = document.querySelector('#skills-drop-select-job-search, #skills, [name="skills"]');
        let sel = null;
        if (window.$ && el) {
            sel = window.$(el)[0]?.selectize;
        }
        if (!sel && window.$) {
            const allSel = Array.from(document.querySelectorAll('.selectize-control')).map(c => {
                const prev = c.previousElementSibling;
                return prev && prev.selectize ? prev.selectize : null;
            }).filter(Boolean);
            sel = allSel.find(s => s.settings && (s.settings.placeholder || '').toLowerCase().includes('skill'));
        }

        const info = {
            found: !!sel,
            settings: sel ? {
                placeholder: sel.settings.placeholder,
                maxItems: sel.settings.maxItems,
                create: sel.settings.create,
                valueField: sel.settings.valueField,
                labelField: sel.settings.labelField,
                searchField: sel.settings.searchField,
                hasLoad: typeof sel.settings.load === 'function',
                loadStr: sel.settings.load ? sel.settings.load.toString().slice(0, 300) : null
            } : null,
            preloadedOptionsCount: sel ? Object.keys(sel.options || {}).length : 0,
            sampleOptions: sel ? Object.keys(sel.options || {}).slice(0, 50) : [],
            currentItems: sel ? sel.items : []
        };
        return info;
    }""")
    print("\n📋 Selectize Info:", json.dumps(selectize_info, indent=2))

    # 2. Check Angular scope / filter data
    angular_info = await page.evaluate("""() => {
        const el = document.querySelector('[ng-controller], .opportunities-container, #job-search, body');
        if (!window.angular || !el) return { angular: false };
        const scope = window.angular.element(el).scope();
        if (!scope) return { scope: false };
        
        const keys = Object.keys(scope).filter(k => !k.startsWith('$'));
        return {
            scopeKeys: keys,
            totalOpportunities: scope.total_opportunities || scope.totalOpportunities || scope.count || null,
            filters: scope.filters || scope.search_params || scope.params || null,
            opportunitiesCount: scope.opportunities ? scope.opportunities.length : (scope.jobs ? scope.jobs.length : null)
        };
    }""")
    print("\n🅰️ Angular Scope Info:", json.dumps(angular_info, indent=2))

    # 3. Check what happens with currently entered skills vs NO skills
    current_search_state = await page.evaluate("""() => {
        const jobCards = document.querySelectorAll('.job-card, [class*="opportunity-card"], [class*="job-listing"], .opportunity-card, .employer-row');
        const emptyMsg = document.querySelector('.no-jobs, .no-results, .empty-state, [class*="empty-state"]');
        const bodyText = document.body.innerText || '';
        const noOpp = bodyText.includes('No matching opportunities found') || bodyText.includes('no opportunities found');
        return {
            jobCardCount: jobCards.length,
            hasEmptyMsg: !!emptyMsg,
            noOppFound: noOpp,
            bodySnippet: bodyText.split('\\n').map(s => s.trim()).filter(s => s.length > 5).slice(0, 10)
        };
    }""")
    print("\n🔍 Current Search Results State:", json.dumps(current_search_state, indent=2))

    # 4. Save results to output
    out = OUTPUT_DIR / f"instahyre_initial_probe_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "selectize": selectize_info,
            "angular": angular_info,
            "current_state": current_search_state
        }, f, indent=2)
    print(f"\n💾 Saved probe to {out}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
