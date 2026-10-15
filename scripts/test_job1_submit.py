import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_job1_submit():
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
    print(f"Applying to Job 1: {target_job.get('title')} (jk={jk})")

    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    apply_btn = page.locator('#indeedApplyButton, [data-testid="viewjob-indeed-apply"]').first
    await apply_btn.click()

    apply_page = page
    for _ in range(15):
        await asyncio.sleep(1)
        for p in page.context.pages:
            if 'smartapply' in (p.url or ''):
                apply_page = p
                break
        if 'smartapply' in (apply_page.url or ''):
            break

    # Dismiss cookies
    try:
        btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await btn.count() > 0:
            await btn.click()
            print("Dismissed cookies")
    except Exception:
        pass

    for step in range(8):
        await asyncio.sleep(2)
        print(f"\n--- Step {step + 1} --- URL: {apply_page.url}")

        # Check all buttons and inputs status
        stat = await apply_page.evaluate("""() => {
            const btn = document.querySelector('button[data-testid="submit-application-button"]');
            const cont = document.querySelector('button[data-testid="continue-button"], button.ia-continueButton');
            const body = document.body ? document.body.innerText : '';
            return {
                hasSubmit: !!btn,
                submitDisabled: btn ? btn.disabled : null,
                submitAriaDisabled: btn ? btn.getAttribute('aria-disabled') : null,
                hasCont: !!cont,
                contDisabled: cont ? cont.disabled : null,
                prepReview: body.toLowerCase().includes('preparing review'),
                bodyLen: body.length
            };
        }""")
        print(f"Status: {stat}")

        if stat['hasSubmit'] and not stat['submitDisabled'] and not stat['prepReview']:
            print("🚀 Submit button is ENABLED! Clicking now...")
            sub_loc = apply_page.locator('button[data-testid="submit-application-button"]').first
            await sub_loc.scroll_into_view_if_needed()
            await sub_loc.click()
            await asyncio.sleep(4)
            if await agent._indeed_is_submitted(apply_page):
                print("🎉 Application SUBMITTED verified!")
                break
            continue

        # If advance button is present and enabled
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
                if not await loc.is_disabled():
                    adv_loc = loc
                    adv_txt = btn_txt
                    break

        if adv_loc:
            print(f"Clicking advance: {adv_txt}")
            await adv_loc.click()
            continue

        # Answer any question
        await apply_page.evaluate("""() => {
            const yesRadio = document.querySelector('input[type="radio"][value="yes"], input[type="radio"][value="Yes"]');
            if (yesRadio && !yesRadio.checked) {
                const lbl = yesRadio.closest('label') || document.querySelector('label[for="' + yesRadio.id + '"]');
                if (lbl) lbl.click(); else yesRadio.click();
            }
        }""")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_job1_submit())
