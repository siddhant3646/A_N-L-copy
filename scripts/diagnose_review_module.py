import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def diagnose_review_module():
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
    for step in range(8):
        await asyncio.sleep(2)
        if '/review-module' in (apply_page.url or ''):
            break
        # Answer any question
        await apply_page.evaluate("""() => {
            const yesRadio = document.querySelector('input[type="radio"][value="yes"], input[type="radio"][value="Yes"]');
            if (yesRadio && !yesRadio.checked) {
                const lbl = yesRadio.closest('label') || document.querySelector('label[for="' + yesRadio.id + '"]');
                if (lbl) lbl.click(); else yesRadio.click();
            }
        }""")
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
                    await loc.click()
                    break

    print(f"Reached URL: {apply_page.url}")
    await asyncio.sleep(4)

    # Now inspect the review page thoroughly
    details = await apply_page.evaluate("""() => {
        const bodyText = document.body ? document.body.innerText : '';
        const submitBtn = document.querySelector('button[data-testid="submit-application-button"]');
        const sections = Array.from(document.querySelectorAll('section, [class*="section" i], [class*="card" i]')).map(s => ({
            tag: s.tagName,
            className: s.className,
            text: s.innerText.substring(0, 200)
        }));
        const alerts = Array.from(document.querySelectorAll('[role="alert"], [class*="error" i], [class*="invalid" i]')).map(a => a.innerText.trim());
        const missingFields = Array.from(document.querySelectorAll('[aria-invalid="true"], [required]:invalid')).map(el => ({
            id: el.id,
            name: el.name,
            tag: el.tagName
        }));
        const allInputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
            type: el.type,
            name: el.name,
            id: el.id,
            checked: el.checked,
            value: el.value,
            visible: !!(el.offsetWidth || el.offsetHeight)
        }));
        return {
            bodyText: bodyText.substring(0, 3000),
            submitDisabled: submitBtn ? submitBtn.disabled : null,
            submitAriaDisabled: submitBtn ? submitBtn.getAttribute('aria-disabled') : null,
            submitClasses: submitBtn ? submitBtn.className : null,
            alerts,
            missingFields,
            allInputs
        };
    }""")

    print(f"\nSubmit button disabled: {details['submitDisabled']}, aria-disabled: {details['submitAriaDisabled']}")
    print(f"Submit classes: {details['submitClasses']}")
    print("Alerts:", details['alerts'])
    print("Missing fields:", details['missingFields'])
    print("Inputs on review:", details['allInputs'])
    print("\n--- BODY TEXT ---")
    print(details['bodyText'])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(diagnose_review_module())
