import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_easy_apply_check():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    # Go to indeed search
    await page.goto("https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B", wait_until='domcontentloaded')
    await asyncio.sleep(3)

    jobs = await agent._indeed_collect_jobs(page)
    print(f"Collected {len(jobs)} jobs")

    for j in jobs[:3]:
        jk = j['jk']
        title = j['title']
        company = j['company']
        print(f"\n==========================================")
        print(f"Job: {title} @ {company} (jk={jk})")
        view_url = f"https://in.indeed.com/viewjob?jk={jk}"
        await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(2.5)

        # Inspect all possible buttons/links
        debug_info = await page.evaluate('''() => {
            const els = Array.from(document.querySelectorAll('button, a, div[data-testid*="apply"]')).map(el => ({
                tag: el.tagName,
                id: el.id,
                testid: el.getAttribute('data-testid'),
                href: el.getAttribute('href'),
                text: el.innerText ? el.innerText.trim().slice(0, 50) : '',
                ariaLabel: el.getAttribute('aria-label') || ''
            })).filter(x => x.text.toLowerCase().includes('apply') || (x.href && x.href.includes('smartapply')) || (x.testid && x.testid.toLowerCase().includes('apply')));
            return els;
        }''')
        print(f"DOM Apply elements found: {debug_info}")

        # Check has_easy_apply result
        has_ea = await agent._indeed_has_easy_apply(page)
        print(f"_indeed_has_easy_apply result: {has_ea}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_easy_apply_check())
