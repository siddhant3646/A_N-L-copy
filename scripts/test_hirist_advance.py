import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def test():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    job_url = "https://www.hirist.tech/j/software-engineer-java-1675045"
    await page.goto(job_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(4)

    apply_btn = page.locator('button:has-text("Apply")').first
    await apply_btn.click()
    await asyncio.sleep(3)

    ta = page.locator('textarea').first
    print("Filling textarea with answer...")
    await ta.fill("4.2 years of experience building scalable backend architectures, microservices, and AI integrations.")
    await asyncio.sleep(1)

    next_btn = page.locator('button:has-text("Next"), button:has-text("Submit"), button:has-text("Confirm")').first
    is_disabled = await next_btn.is_disabled()
    print(f"Next button disabled: {is_disabled}")

    if not is_disabled:
        print("Clicking Next/Submit...")
        await next_btn.click()
        await asyncio.sleep(3)
        body_after = await page.evaluate("() => document.body ? document.body.innerText : ''")
        print("\nBODY AFTER NEXT:\n", body_after[:600])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
