import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def debug_indeed():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    seed_url = "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B"
    print(f"Navigating to {seed_url}...")
    await page.goto(seed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(4)

    print(f"URL: {page.url}")
    print(f"Title: {await page.title()}")
    text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    print(f"Body text (len={len(text)}):\n{text[:600]}")
    await page.screenshot(path="live_test_output/indeed_debug.png")
    print("Screenshot saved to live_test_output/indeed_debug.png")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(debug_indeed())
