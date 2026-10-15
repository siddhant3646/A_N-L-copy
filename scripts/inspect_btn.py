import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def inspect_button_text():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    jk = "aa8c6e17e26beb37"
    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    loc = page.locator('#indeedApplyButton, [data-testid="viewjob-indeed-apply"], [data-testid="primary-apply-action"]').first
    print("Count:", await loc.count())
    if await loc.count() > 0:
        print("Inner text:", repr(await loc.inner_text()))
        print("Aria label:", repr(await loc.get_attribute('aria-label')))
        print("Outer HTML:", repr(await loc.evaluate("el => el.outerHTML")))

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(inspect_button_text())
