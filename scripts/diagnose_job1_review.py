import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def diagnose_job1_review():
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
    print(f"Testing Job 1: {target_job.get('title')} (jk={jk})")

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
    except Exception:
        pass

    # Navigate to review module
    for step in range(10):
        await asyncio.sleep(2)
        if '/review-module' in (apply_page.url or ''):
            print("Reached review-module!")
            break
        
        # Answer any question
        await apply_page.evaluate("""() => {
            const yesRadio = document.querySelector('input[type="radio"][value="yes"], input[type="radio"][value="Yes"]');
            if (yesRadio && !yesRadio.checked) {
                const lbl = yesRadio.closest('label') || document.querySelector('label[for="' + yesRadio.id + '"]');
                if (lbl) lbl.click(); else yesRadio.click();
            }
        }""")

        # Click real advance button
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
                    print(f"Step {step+1}: Clicked advance button: {btn_txt}")
                    await loc.click()
                    break

    await asyncio.sleep(6) # wait for review module to finish loading
    print(f"Current URL: {apply_page.url}")

    # Inspect review module
    review_info = await apply_page.evaluate("""() => {
        const bodyText = document.body ? document.body.innerText : '';
        const submitBtn = document.querySelector('button[data-testid="submit-application-button"]');
        const allButtons = Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.innerText.trim(),
            testid: b.getAttribute('data-testid'),
            disabled: b.disabled,
            ariaDisabled: b.getAttribute('aria-disabled'),
            type: b.getAttribute('type'),
            className: b.className
        })).filter(b => b.text || b.testid);

        const allInputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
            tag: el.tagName,
            type: el.type,
            name: el.name,
            id: el.id,
            checked: el.checked,
            value: el.value,
            disabled: el.disabled,
            required: el.required || el.getAttribute('aria-required') === 'true',
            visible: !!(el.offsetWidth || el.offsetHeight)
        }));

        const errorElements = Array.from(document.querySelectorAll('[role="alert"], [class*="error" i], [class*="alert" i], [aria-invalid="true"]')).map(e => e.innerText.trim()).filter(Boolean);

        return {
            bodyText: bodyText.substring(0, 2000),
            allButtons,
            allInputs,
            errorElements,
            hasPrepReview: bodyText.toLowerCase().includes('preparing review')
        };
    }""")

    print(f"\nHas 'Preparing review': {review_info['hasPrepReview']}")
    print("Error / Alert elements:", review_info['errorElements'])
    print("\nButtons on review:")
    for b in review_info['allButtons']:
        print(f"  button: '{b['text']}' testid='{b['testid']}' disabled={b['disabled']} ariaDisabled={b['ariaDisabled']}")

    print("\nInputs on review:")
    for inp in review_info['allInputs']:
        print(f"  input: {inp['tag']} type={inp['type']} name='{inp['name']}' req={inp['required']} vis={inp['visible']} checked={inp['checked']}")

    print("\n--- BODY TEXT ---")
    print(review_info['bodyText'])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(diagnose_job1_review())
