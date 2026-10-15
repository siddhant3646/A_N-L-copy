import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def inspect_inputs():
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
    job = jobs[0]
    jk = job.get('jk')
    view_url = f"https://in.indeed.com/viewjob?jk={jk}"
    await page.goto(view_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    apply_btn = page.locator('#indeedApplyButton, [data-testid="viewjob-indeed-apply"]').first
    await apply_btn.click()
    await asyncio.sleep(3)

    apply_page = page
    for p in page.context.pages:
        if 'smartapply' in (p.url or ''):
            apply_page = p
            break

    print(f"Apply page: {apply_page.url}")

    # Wait for review page
    for _ in range(10):
        if '/review-module' in (apply_page.url or ''):
            break
        await asyncio.sleep(1)

    # Click Accept Cookies
    try:
        cookie_btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await cookie_btn.count() > 0:
            await cookie_btn.click()
            print("Clicked accept cookies!")
    except Exception as e:
        print("Cookie click failed:", e)

    await asyncio.sleep(2)

    # Inspect the form and submit button
    res = await apply_page.evaluate("""() => {
        const submit = document.querySelector('button[data-testid="submit-application-button"]');
        const form = submit ? submit.closest('form') : null;
        const allInputs = Array.from(document.querySelectorAll('input, button')).map(el => ({
            tag: el.tagName,
            type: el.type,
            name: el.name,
            id: el.id,
            disabled: el.disabled,
            ariaDisabled: el.getAttribute('aria-disabled'),
            ariaHidden: el.getAttribute('aria-hidden'),
            text: el.innerText ? el.innerText.trim() : '',
            checked: el.checked
        }));
        return {
            submitDisabled: submit ? submit.disabled : null,
            submitOuterHTML: submit ? submit.outerHTML : null,
            formAction: form ? form.action : null,
            inputs: allInputs
        };
    }""")
    print("\nSubmit Disabled:", res['submitDisabled'])
    print("Submit OuterHTML:", res['submitOuterHTML'])
    print("\nAll Inputs/Buttons:")
    for inp in res['inputs']:
        print(f"  {inp['tag']} type={inp['type']} name='{inp['name']}' disabled={inp['disabled']} ariaDisabled={inp['ariaDisabled']} text='{inp['text']}' checked={inp['checked']}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(inspect_inputs())
