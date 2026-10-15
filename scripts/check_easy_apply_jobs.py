import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def check_jobs():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()
    agent = SentinelAgent()
    agent._page = page

    # Search jobs
    await page.goto("https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(2)
    jobs = await agent._indeed_collect_jobs(page)
    print(f"Total jobs: {len(jobs)}")

    for i, j in enumerate(jobs):
        jk = j.get('jk')
        view_url = f"https://in.indeed.com/viewjob?jk={jk}"
        await page.goto(view_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(1)
        has_easy = await agent._indeed_has_easy_apply(page)
        print(f"[{i}] jk={jk} EasyApply={has_easy} | {j.get('title')} @ {j.get('company')}")
        if has_easy:
            # Let's break after finding 3 easy apply jobs
            pass

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(check_jobs())
