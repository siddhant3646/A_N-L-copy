import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    feed_url = "https://www.hirist.tech/jobfeed"
    print(f"Navigating to {feed_url}...")
    await page.goto(feed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(5)
    await agent._hirist_dismiss_dialogs(page)

    jobs = await agent._hirist_collect_jobs(page)
    print(f"Collected {len(jobs)} jobs from Hirist feed:")
    for j in jobs[:8]:
        print(f"  - [{j.get('id')}] {j.get('title')} ({j.get('url')})")

    meta = await agent._hirist_read_meta(page)
    print("Meta on feed:", json.dumps(meta, indent=2))

    # Test the first 2-3 jobs to see what their apply buttons and modals/questionnaires look like
    for j in jobs[:3]:
        url = j.get('url')
        print(f"\n--- Testing Job: {url} ---")
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(4)
        await agent._hirist_dismiss_dialogs(page)
        
        j_meta = await agent._hirist_read_meta(page)
        print(f"Job title: {j_meta.get('jobTitle')}, company: {j_meta.get('companyName')}")
        
        apply_buttons = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, a')).map(el => {
                const t = (el.innerText || el.textContent || '').trim();
                return {
                    tag: el.tagName,
                    text: t.slice(0, 50),
                    cls: el.className ? String(el.className).slice(0, 50) : '',
                    visible: !!(el.offsetWidth || el.offsetHeight)
                };
            }).filter(x => /apply/i.test(x.text));
        }""")
        print("Apply buttons:", json.dumps(apply_buttons, indent=2))

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
