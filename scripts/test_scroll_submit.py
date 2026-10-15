import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def inspect_react_fiber():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    seed_url = "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B"
    await page.goto(seed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    jobs = await agent._indeed_collect_jobs(page)
    job = jobs[0]
    jk = job.get('jk')
    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    apply_btn = page.locator('#indeedApplyButton, [data-testid="viewjob-indeed-apply"]').first
    await apply_btn.click()

    apply_page = page
    for _ in range(15):
        await asyncio.sleep(1)
        for p in page.context.pages:
            if 'smartapply' in (p.url or ''):
                apply_page = p
                break
        if '/review-module' in (apply_page.url or ''):
            break

    await asyncio.sleep(4)

    # Walk React fiber up from the button
    fiber_info = await apply_page.evaluate("""() => {
        const btn = document.querySelector('button[data-testid="submit-application-button"]');
        if (!btn) return { error: 'no button' };
        let fiberKey = Object.keys(btn).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
        let f = btn[fiberKey];
        const chain = [];
        while (f && chain.length < 25) {
            let name = f.type ? (typeof f.type === 'string' ? f.type : (f.type.displayName || f.type.name || 'Component')) : 'Unknown';
            let props = {};
            if (f.memoizedProps && typeof f.memoizedProps === 'object') {
                for (let k of Object.keys(f.memoizedProps)) {
                    if (typeof f.memoizedProps[k] !== 'function' && typeof f.memoizedProps[k] !== 'object') {
                        props[k] = f.memoizedProps[k];
                    }
                }
            }
            chain.push({ name, props });
            f = f.return;
        }
        return { chain };
    }""")

    print("\n--- REACT FIBER CHAIN ---")
    for node in fiber_info.get('chain', []):
        print(f"  Component: {node['name']} props={node['props']}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(inspect_react_fiber())
