import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_submit_action():
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
    print(f"Testing submit for jk={jk}: {job.get('title')}")
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

    print(f"Apply page URL: {apply_page.url}")
    await asyncio.sleep(5)

    # Dismiss cookies
    try:
        btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await btn.count() > 0:
            await btn.click()
            print("Dismissed cookies")
    except Exception:
        pass

    await asyncio.sleep(3)

    # Try triggering submit via JS click or simulated click
    result = await apply_page.evaluate("""() => {
        const btn = document.querySelector('button[data-testid="submit-application-button"]');
        if (!btn) return 'No submit button';
        
        // Remove disabled attribute
        btn.removeAttribute('disabled');
        btn.disabled = false;
        
        // Click it
        btn.click();
        return 'Clicked submit button via JS!';
    }""")
    print("JS result:", result)

    # Wait and check if URL changes or submitted
    for s in range(10):
        await asyncio.sleep(1)
        u = apply_page.url
        body = await apply_page.evaluate("() => document.body.innerText")
        submitted = await agent._indeed_is_submitted(apply_page)
        print(f"[{s}s] URL: {u[:60]} | submitted: {submitted} | bodyLen: {len(body)}")
        if submitted or 'submitted' in body.lower():
            print("🎉 SUCCESS! Application was SUBMITTED!")
            break

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_submit_action())
