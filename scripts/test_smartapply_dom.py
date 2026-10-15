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

    vurl = "https://in.indeed.com/viewjob?jk=1415370380acd3fb"
    await page.goto(vurl, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    apply_btn = page.locator('[data-testid="viewjob-indeed-apply"], #indeedApplyButton, button:has-text("Apply now"), a:has-text("Apply now")').first
    await apply_btn.click()
    print("Clicked apply, waiting 8s...")
    await asyncio.sleep(8)

    # Click Accept Cookies if present
    cookie_btn = page.locator('button:has-text("Accept All Cookies"), #onetrust-accept-btn-handler').first
    if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
        print("Clicking Accept Cookies...")
        await cookie_btn.click()
        await asyncio.sleep(2)

    print(f"URL: {page.url}")
    print(f"Frames count: {len(page.frames)}")
    for i, fr in enumerate(page.frames):
        text = await fr.evaluate("() => document.body ? document.body.innerText : ''")
        print(f"\n--- FRAME {i} (URL: {fr.url[:80]}) --- (len={len(text)})")
        print(text[:400].strip())
        btns = await fr.evaluate("""() => {
            return Array.from(document.querySelectorAll('button, a[role="button"], input[type="submit"]')).map(b => (b.innerText || b.value || '').trim()).filter(Boolean);
        }""")
        print(f"Buttons in frame {i}: {btns}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
