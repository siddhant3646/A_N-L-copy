import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_indeed():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    seed_url = "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B"
    print(f"Direct goto {seed_url}...")
    await page.goto(seed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(4)
    print(f"Page URL: {page.url}")

    # Inspect DOM right here
    raw_cards = await page.evaluate("""() => {
        return {
            allWithDataJk: Array.from(document.querySelectorAll('[data-jk]')).map(el => el.getAttribute('data-jk')),
            cardOutlineCount: document.querySelectorAll('.cardOutline').length,
            beaconCount: document.querySelectorAll('.job_seen_beacon').length,
            htmlLen: document.body ? document.body.innerHTML.length : 0
        };
    }""")
    print("Raw cards check:", raw_cards)

    jobs = await agent._indeed_collect_jobs(page)
    print(f"_indeed_collect_jobs result: {len(jobs)}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_indeed())
