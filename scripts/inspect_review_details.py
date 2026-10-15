import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_job1_complete():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    seed_url = "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B"
    await page.goto(seed_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    jobs = await agent._indeed_collect_jobs(page)
    target_job = jobs[1]
    jk = target_job.get('jk')
    print(f"Testing Job 1: {target_job.get('title')} @ {target_job.get('company')} (jk={jk})")

    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

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
    await asyncio.sleep(3)

    # Dismiss cookie banner
    try:
        btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await btn.count() > 0:
            await btn.click()
            print("Dismissed cookies")
    except Exception:
        pass

    submitted = False
    for step in range(15):
        await asyncio.sleep(2)
        print(f"\n--- STEP {step + 1} --- URL: {apply_page.url}")

        if await agent._indeed_is_submitted(apply_page):
            print("🎉 Application SUBMITTED!")
            submitted = True
            break

        # Check for screening questions and answer them
        await agent._indeed_answer_questions(apply_page)

        # Check if there's a bachelor question specifically on this page and answer Yes
        answered_radios = await apply_page.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('fieldset, [data-testid*="question" i], .ia-Question').forEach(box => {
                const text = box.innerText.toLowerCase();
                if (text.includes('bachelor') || text.includes('degree')) {
                    const yesRadio = box.querySelector('input[type="radio"][value="yes"], input[type="radio"][value="Yes"]');
                    if (yesRadio && !yesRadio.checked) {
                        const lbl = yesRadio.closest('label') || box.querySelector('label[for="' + yesRadio.id + '"]');
                        if (lbl) lbl.click();
                        else yesRadio.click();
                        count++;
                    }
                }
            });
            return count;
        }""")
        if answered_radios > 0:
            print(f"Directly selected {answered_radios} Yes radio button(s)")
            await asyncio.sleep(1)

        # Check for Submit button on final review page
        submit_btn = apply_page.locator('button[data-testid="submit-application-button"]:not([data-testid^="hp-"])').first
        if await submit_btn.count() > 0 and await submit_btn.is_visible():
            dis = await submit_btn.is_disabled()
            print(f"Found submit button (disabled={dis})")
            if not dis:
                await submit_btn.scroll_into_view_if_needed()
                await submit_btn.click()
                print("🚀 Clicked submit button!")
                await asyncio.sleep(3)
                if await agent._indeed_is_submitted(apply_page):
                    print("🎉 Application SUBMITTED successfully!")
                    submitted = True
                    break
                continue

        # Look for the REAL advance button (explicitly EXCLUDING hp- honeypots and preview buttons)
        adv_loc = None
        for sel in (
            'button[data-testid="continue-button"]',
            'button:text-is("Continue"):not([data-testid^="hp-"]):not([aria-hidden="true"])',
            'button:has-text("Review your application"):not([data-testid^="hp-"]):not([aria-hidden="true"])',
            'button:has-text("Continue"):not([data-testid^="hp-"]):not([aria-hidden="true"])',
            '.ia-continueButton:not([data-testid^="hp-"])',
        ):
            loc = apply_page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                btn_txt = (await loc.inner_text()).strip()
                # Exclude honeypot, preview, save, close, report
                lower_t = btn_txt.lower()
                if any(bad in lower_t for bad in ['preview', 'save', 'exit', 'close', 'report', 'cookie']):
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
            print(f"➡️ Found REAL advance button: '{adv_text}' (testid={adv_tid}, disabled={dis}). Clicking...")
            if not dis:
                await adv_loc.scroll_into_view_if_needed()
                await adv_loc.click()
                await asyncio.sleep(2)
                continue
            else:
                print("Advance button is disabled! Waiting...")

    await asyncio.sleep(2)
    await browser.stop(fast=True)
    await reset_shared_playwright()
    print(f"\nFinal Result: submitted = {submitted}")

if __name__ == "__main__":
    asyncio.run(test_job1_complete())
