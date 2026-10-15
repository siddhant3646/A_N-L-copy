import asyncio
import os
import sys

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

    # Let's test job: 1415370380acd3fb
    vurl = "https://in.indeed.com/viewjob?jk=1415370380acd3fb"
    print(f"Navigating to {vurl}...")
    await page.goto(vurl, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    apply_btn = page.locator('[data-testid="viewjob-indeed-apply"], #indeedApplyButton, button:has-text("Apply now"), a:has-text("Apply now")').first
    if await apply_btn.count() == 0:
        print("Apply button not found")
        await browser.stop(fast=True)
        return

    print("Clicking Apply button...")
    await apply_btn.click()
    await asyncio.sleep(6)

    # Dismiss cookies
    try:
        cookie_btn = page.locator('button:has-text("Accept All Cookies"), #onetrust-accept-btn-handler').first
        if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
            print("Accepting cookies...")
            await cookie_btn.click()
            await asyncio.sleep(2)
    except Exception:
        pass

    print(f"Apply Page URL: {page.url}")

    # Check for Submit / Continue button across main page and frames
    submit_btn = None
    for loc_ctx in [page] + page.frames:
        for sel in (
            'button:has-text("Submit your application")',
            'button:has-text("Submit application")',
            '.ia-submitButton',
            'button[type="submit"]:has-text("Submit")',
        ):
            try:
                l = loc_ctx.locator(sel).first
                if await l.count() > 0 and await l.is_visible():
                    submit_btn = l
                    print(f"Found submit button: {sel} in {loc_ctx}")
                    break
            except Exception:
                continue
        if submit_btn:
            break

    if submit_btn:
        print("Clicking submit button...")
        await submit_btn.click()
        await asyncio.sleep(5)
        print(f"Post-submit URL: {page.url}")
        body = await page.evaluate("() => document.body ? document.body.innerText : ''")
        print("Post-submit body snippet:\n", body[:500])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
