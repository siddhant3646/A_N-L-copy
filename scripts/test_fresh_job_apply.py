import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_fresh_job_apply():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    # Let's test a fresh job: Senior Software Engineer - AI Trainer @ DataAnnotation
    jk = "2fe2dfe2cd26b5a9"
    print(f"Applying to fresh job: jk={jk}")

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

    print(f"Smartapply URL: {apply_page.url}")

    # Dismiss cookies
    try:
        btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await btn.count() > 0:
            await btn.click()
            print("Dismissed cookies")
    except Exception:
        pass

    submitted = False
    for step in range(12):
        await asyncio.sleep(2.5)
        print(f"\n--- Step {step + 1} --- URL: {apply_page.url}")

        if await agent._indeed_is_submitted(apply_page):
            print("🎉 Application SUBMITTED successfully!")
            submitted = True
            break

        # Check if on review page
        if '/review-module' in (apply_page.url or ''):
            print("On review page! Waiting for submit button to be enabled...")
            for w in range(15):
                stat = await apply_page.evaluate("""() => {
                    const btn = document.querySelector('button[data-testid="submit-application-button"]');
                    const prep = (document.body ? document.body.innerText : '').toLowerCase().includes('preparing review');
                    return {
                        hasSubmit: !!btn,
                        disabled: btn ? btn.disabled : null,
                        prep
                    };
                }""")
                if stat['hasSubmit'] and not stat['disabled'] and not stat['prep']:
                    print(f"Submit button is READY to click after {w}s!")
                    break
                await asyncio.sleep(1.0)

            sub_loc = apply_page.locator('button[data-testid="submit-application-button"]:not([data-testid^="hp-"])').first
            if await sub_loc.count() > 0 and not await sub_loc.is_disabled():
                await sub_loc.scroll_into_view_if_needed()
                await sub_loc.click()
                print("🚀 Clicked submit button!")
                await asyncio.sleep(5)
                if await agent._indeed_is_submitted(apply_page):
                    print("🎉 Application SUBMISSION CONFIRMED!")
                    submitted = True
                    break
                continue

        # Answer any questions on the current step
        await agent._indeed_answer_questions(apply_page)
        # Directly answer bachelor question if present
        await apply_page.evaluate("""() => {
            document.querySelectorAll('fieldset, [data-testid*="question" i], .ia-Question').forEach(box => {
                const text = box.innerText.toLowerCase();
                if (text.includes('bachelor') || text.includes('degree')) {
                    const yesRadio = box.querySelector('input[type="radio"][value="yes"], input[type="radio"][value="Yes"]');
                    if (yesRadio && !yesRadio.checked) {
                        const lbl = yesRadio.closest('label') || box.querySelector('label[for="' + yesRadio.id + '"]');
                        if (lbl) lbl.click(); else yesRadio.click();
                    }
                }
            });
        }""")

        # Look for the legitimate advance button
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
                    adv_tid = tid
                    break

        if adv_loc:
            print(f"Clicking advance: '{adv_txt}' (testid={adv_tid})")
            await adv_loc.click()
            continue

    await asyncio.sleep(2)
    await browser.stop(fast=True)
    await reset_shared_playwright()
    print(f"\nFinal Result: submitted = {submitted}")

if __name__ == "__main__":
    asyncio.run(test_fresh_job_apply())
