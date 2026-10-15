import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test():
    print("Launching browser...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page()
    if not page:
        page = await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    vurl = "https://in.indeed.com/viewjob?jk=1415370380acd3fb"
    print(f"\nOpening job: {vurl}")
    await page.goto(vurl, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    apply_btn = page.locator('[data-testid="viewjob-indeed-apply"], #indeedApplyButton, button:has-text("Apply now"), a:has-text("Apply now")').first
    target_attr = await apply_btn.get_attribute("target")
    href_attr = await apply_btn.get_attribute("href")
    print(f"Apply button target: '{target_attr}', href: '{href_attr}'")

    # Set up listener for new pages
    new_pages = []
    page.context.on("page", lambda p: new_pages.append(p))

    print("Clicking Apply button...")
    await apply_btn.click()
    await asyncio.sleep(5)

    print(f"Total open pages in context: {len(page.context.pages)}")
    for i, p in enumerate(page.context.pages):
        try:
            print(f"Page {i}: URL = {p.url}, Title = {await p.title()}")
            print(f"  Frames count: {len(p.frames)}")
            for f in p.frames:
                print(f"    - Frame URL: {f.url}")
        except Exception as e:
            print(f"  Error reading page {i}: {e}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
