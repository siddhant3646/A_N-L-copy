#!/usr/bin/env python3
"""
LinkedIn Job Search Selector Verification
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, stop_shared_playwright, cleanup_tmp_root


async def test_linkedin():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page()
    if not page:
        page = await browser.new_page()

    # Search URL with standard LinkedIn Easy Apply filter
    url = "https://www.linkedin.com/jobs/search/?keywords=Software%20Engineer&f_AL=true"
    print(f"Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(6)

    data = await page.evaluate("""() => {
        const res = {};
        
        // Job cards
        const cardSelectors = [
            '.scaffold-layout__list',
            '.scaffold-layout__list-container',
            'li.scaffold-layout__list-item',
            '[data-occludable-job-id]',
            'div[data-job-id]',
            '.jobs-search-results-list',
            '.job-card-container',
            'div[data-view-name="job-search-job-card"]'
        ];
        res.cards = {};
        cardSelectors.forEach(sel => {
            const els = document.querySelectorAll(sel);
            res.cards[sel] = {
                count: els.length,
                found: els.length > 0,
                sample_id: els[0] ? (els[0].getAttribute('data-job-id') || els[0].getAttribute('data-occludable-job-id')) : null
            };
        });

        // Easy Apply button in right pane
        const applySelectors = [
            '#jobs-apply-button-id',
            'button.jobs-apply-button',
            'button[aria-label*="Easy Apply"]',
            '.jobs-apply-button'
        ];
        res.apply_buttons = {};
        applySelectors.forEach(sel => {
            const els = document.querySelectorAll(sel);
            res.apply_buttons[sel] = {
                count: els.length,
                found: els.length > 0,
                visible: els[0] ? (els[0].offsetParent !== null) : false,
                text: els[0] ? els[0].innerText.trim() : null
            };
        });

        return res;
    }""")
    print("LinkedIn Search Selectors Result:")
    print(json.dumps(data, indent=2))

    await browser.stop()
    await stop_shared_playwright()
    cleanup_tmp_root()

if __name__ == "__main__":
    asyncio.run(test_linkedin())
