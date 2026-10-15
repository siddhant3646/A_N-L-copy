import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def inspect_form():
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

    apply_page = page
    for _ in range(15):
        await asyncio.sleep(1)
        for p in page.context.pages:
            if 'smartapply' in (p.url or ''):
                apply_page = p
                break
        if '/review-module' in (apply_page.url or ''):
            break

    print(f"Apply page URL: {apply_page.url}")

    # Wait for content to render
    await asyncio.sleep(5)

    # Dismiss cookie banner if present
    try:
        btn = apply_page.locator('#onetrust-accept-btn-handler')
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            print("Dismissed cookies")
    except Exception:
        pass

    await asyncio.sleep(2)

    # Let's inspect everything about the submit button and surrounding elements
    data = await apply_page.evaluate("""() => {
        const submit = document.querySelector('button[data-testid="submit-application-button"]');
        if (!submit) return { error: 'No submit button found' };
        
        // Find form or container
        const container = submit.closest('form') || submit.closest('[class*="review" i]') || submit.parentElement;
        
        // Check disabled reasons / attributes
        const attrs = {};
        for (let i = 0; i < submit.attributes.length; i++) {
            attrs[submit.attributes[i].name] = submit.attributes[i].value;
        }

        // Check if there are unfulfilled inputs or checkboxes
        const inputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
            tag: el.tagName,
            type: el.type,
            name: el.name,
            id: el.id,
            required: el.required || el.getAttribute('aria-required') === 'true',
            checked: el.checked,
            value: el.value,
            visible: !!(el.offsetWidth || el.offsetHeight),
            invalid: el.getAttribute('aria-invalid')
        }));

        // Check computed styles and listeners
        const style = window.getComputedStyle(submit);

        return {
            buttonAttrs: attrs,
            buttonText: submit.innerText,
            buttonDisabled: submit.disabled,
            pointerEvents: style.pointerEvents,
            cursor: style.cursor,
            inputs: inputs,
            containerHtml: container ? container.innerHTML.substring(0, 1500) : ''
        };
    }""")

    print("\n--- BUTTON ATTRS ---")
    print(data.get('buttonAttrs'))
    print(f"Text: '{data.get('buttonText')}', Disabled: {data.get('buttonDisabled')}")
    print(f"pointer-events: {data.get('pointerEvents')}, cursor: {data.get('cursor')}")

    print("\n--- ALL INPUTS ON REVIEW PAGE ---")
    for inp in data.get('inputs', []):
        print(inp)

    print("\n--- CONTAINER HTML SNIPPET ---")
    print(data.get('containerHtml', '')[:1000])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(inspect_form())
