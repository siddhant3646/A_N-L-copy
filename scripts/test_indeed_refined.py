import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def run_indeed_flow_test():
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

    # Wait for smartapply to load (either in current page or popup)
    apply_page = page
    for _ in range(15):
        await asyncio.sleep(1)
        if len(page.context.pages) > 1:
            for p in page.context.pages:
                if 'smartapply' in p.url or 'indeed.com/apply' in p.url:
                    apply_page = p
                    break
        if 'smartapply' in apply_page.url:
            break

    print(f"Apply Page URL: {apply_page.url}")

    # Wait for smartapply to reach a form or finish redirecting
    print("Waiting for Smartapply form to load...")
    for _ in range(15):
        await asyncio.sleep(1)
        try:
            cookie_btn = apply_page.locator('button:has-text("Accept All Cookies"), #onetrust-accept-btn-handler').first
            if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
                await cookie_btn.click()
                print("   Dismissed cookie banner")
        except Exception:
            pass
        if '/form/' in apply_page.url:
            print(f"   Reached form URL: {apply_page.url}")
            break

    # Step loop
    submitted = False
    no_btn_retries = 0

    for step in range(20):
        print(f"\n--- Smartapply Step {step + 1} (URL: {apply_page.url[:60]}) ---")
        await asyncio.sleep(2)

        # Dismiss cookies if re-appeared
        try:
            cookie_btn = apply_page.locator('button:has-text("Accept All Cookies"), #onetrust-accept-btn-handler').first
            if await cookie_btn.count() > 0 and await cookie_btn.is_visible():
                await cookie_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # Check if submitted
        is_done = await apply_page.evaluate("""() => {
            const t = (document.body ? document.body.innerText : '').toLowerCase();
            return t.includes('application submitted') ||
                   t.includes('your application has been submitted') ||
                   t.includes('applied successfully') ||
                   t.includes('you applied to') ||
                   t.includes('return to job search');
        }""")
        if is_done:
            print("   ✅ Application confirmed submitted!")
            submitted = True
            break

        # Check all targets (main frame + child frames)
        targets = [apply_page] + [f for f in apply_page.frames if f != apply_page.main_frame]

        # Check for submit button
        submit_btn = None
        for target in targets:
            for sel in (
                'button:has-text("Submit your application")',
                'button:has-text("Submit application")',
                '.ia-submitButton',
                'button[type="submit"]:has-text("Submit")',
            ):
                try:
                    loc = target.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        submit_btn = loc
                        print(f"   Found submit button: '{sel}'")
                        break
                except Exception:
                    continue
            if submit_btn:
                break

        if submit_btn:
            print("   Clicking Submit button...")
            await submit_btn.click()
            await asyncio.sleep(5)
            is_done_after = await apply_page.evaluate("""() => {
                const t = (document.body ? document.body.innerText : '').toLowerCase();
                return t.includes('application submitted') ||
                       t.includes('your application has been submitted') ||
                       t.includes('applied successfully') ||
                       t.includes('return to job search');
            }""")
            if is_done_after:
                print("   ✅ Application confirmed submitted post-click!")
                submitted = True
                break
            continue

        # Check for continue/next button
        adv_btn = None
        for target in targets:
            for sel in (
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button:has-text("Review your application")',
                'button:has-text("Review")',
                '.ia-continueButton',
            ):
                try:
                    loc = target.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        adv_btn = loc
                        print(f"   Found advance button: '{sel}'")
                        break
                except Exception:
                    continue
            if adv_btn:
                break

        if adv_btn:
            no_btn_retries = 0
            print("   Clicking Advance button...")
            await adv_btn.click()
            await asyncio.sleep(3)
            continue

        no_btn_retries += 1
        print(f"   ⚠️ No button found (attempt {no_btn_retries}/3)")
        if no_btn_retries >= 3:
            break
        await asyncio.sleep(3)

    print(f"\nFinal Result: Submitted = {submitted}")
    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(run_indeed_flow_test())
