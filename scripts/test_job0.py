import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_job0():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    jk = "09751a304b98082e"
    print(f"Testing Job 0: Java Backend Engineer-SDE-2 @ Digit88 Technologies (jk={jk})")

    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    has_easy = await agent._indeed_has_easy_apply(page)
    print(f"Has easy apply: {has_easy}")

    if has_easy:
        apply_btn = page.locator('#indeedApplyButton, [data-testid="viewjob-indeed-apply"]').first
        await apply_btn.click()
        print("Clicked apply button")

        apply_page = page
        for _ in range(15):
            await asyncio.sleep(1)
            for p in page.context.pages:
                if 'smartapply' in (p.url or ''):
                    apply_page = p
                    break
            if 'smartapply' in (apply_page.url or ''):
                break

        print(f"Apply page URL: {apply_page.url}")

        # Check steps
        for step in range(10):
            await asyncio.sleep(2)
            print(f"\n--- STEP {step + 1} --- URL: {apply_page.url}")
            
            # Dismiss cookie banner
            try:
                c_btn = apply_page.locator('#onetrust-accept-btn-handler')
                if await c_btn.count() > 0:
                    await c_btn.click()
            except Exception:
                pass

            # Check if submitted
            if await agent._indeed_is_submitted(apply_page):
                print("🎉 Application SUBMITTED!")
                break

            # Answer any questions
            await agent._indeed_answer_questions(apply_page)

            # Check submit button
            submit_btn = apply_page.locator('button[data-testid="submit-application-button"]:not([data-testid^="hp-"])').first
            if await submit_btn.count() > 0 and await submit_btn.is_visible():
                dis = await submit_btn.is_disabled()
                print(f"Submit button visible! (disabled={dis})")
                if not dis:
                    await submit_btn.scroll_into_view_if_needed()
                    await submit_btn.click()
                    print("🚀 Clicked submit button!")
                    await asyncio.sleep(3)
                    if await agent._indeed_is_submitted(apply_page):
                        print("🎉 Application SUBMITTED successfully!")
                        break
                    continue

            # Look for advance button
            adv_loc = None
            for sel in (
                'button[data-testid="continue-button"]',
                'button:has-text("Continue"):not([data-testid^="hp-"]):not([aria-hidden="true"])',
                'button:has-text("Review your application"):not([data-testid^="hp-"]):not([aria-hidden="true"])',
            ):
                loc = apply_page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    btn_txt = (await loc.inner_text()).strip().lower()
                    if any(bad in btn_txt for bad in ['preview', 'save', 'exit', 'close', 'report', 'cookie']):
                        continue
                    tid = await loc.get_attribute('data-testid') or ''
                    if tid.startswith('hp-'):
                        continue
                    adv_loc = loc
                    adv_text = btn_txt
                    adv_tid = tid
                    break

            if adv_loc:
                dis = await adv_loc.is_disabled()
                print(f"➡️ Found advance button: '{adv_text}' (testid={adv_tid}, disabled={dis}). Clicking...")
                if not dis:
                    await adv_loc.scroll_into_view_if_needed()
                    await adv_loc.click()
                    await asyncio.sleep(2)
                    continue

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_job0())
