import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_indeed_job_collection():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    seed_url = "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B"
    print(f"Navigating to {seed_url}...")
    await page.goto(seed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    # Let's inspect page state
    url_now = page.url
    title_now = await page.title()
    print(f"URL: {url_now}")
    print(f"Title: {title_now}")

    # Check for Cloudflare / bot challenge
    is_blocked = await page.evaluate("""() => {
        const t = (document.body ? document.body.innerText : '').toLowerCase();
        return {
            hasCloudflare: t.includes('cloudflare') || t.includes('verify you are human') || t.includes('security check'),
            hasCaptcha: !!document.querySelector('#challenge-running, #cf-challenge-running, .cf-turnstile'),
            cardOutlines: document.querySelectorAll('div.cardOutline').length,
            dataJks: document.querySelectorAll('[data-jk]').length,
            jobcards: document.querySelectorAll('#mosaic-provider-jobcards [data-jk]').length,
            allJks: Array.from(document.querySelectorAll('[data-jk]')).map(e => e.getAttribute('data-jk')).slice(0, 5)
        };
    }""")
    print("Diagnostics:", is_blocked)

    # Wait for cards if not loaded yet
    try:
        await page.wait_for_selector('[data-jk]', timeout=10000)
        print("wait_for_selector found [data-jk]")
    except Exception as e:
        print(f"wait_for_selector timed out: {e}")

    jobs = await agent._indeed_collect_jobs(page)
    print(f"agent._indeed_collect_jobs returned: {len(jobs)} jobs")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_indeed_job_collection())
