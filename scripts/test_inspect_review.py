import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def inspect_review_page():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    vurl = "https://in.indeed.com/viewjob?jk=1415370380acd3fb"
    await page.goto(vurl, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(3)

    apply_btn = page.locator('[data-testid="viewjob-indeed-apply"]').first
    await apply_btn.click()

    # Wait for smartapply form
    for _ in range(12):
        await asyncio.sleep(1)
        if '/form/' in page.url:
            break

    # Dismiss cookies
    try:
        cb = page.locator('button:has-text("Accept All Cookies")').first
        if await cb.count() > 0:
            await cb.click()
    except Exception:
        pass
    await asyncio.sleep(3)

    info = await page.evaluate("""() => {
        const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).map(c => ({
            id: c.id,
            name: c.name,
            checked: c.checked,
            label: (c.closest('label') ? c.closest('label').innerText : '').trim()
        }));
        const errors = Array.from(document.querySelectorAll('[role="alert"], [class*="error" i], [class*="invalid" i]')).map(e => (e.innerText || '').trim()).filter(Boolean);
        const disabledButtons = Array.from(document.querySelectorAll('button:disabled')).map(b => ({
            text: (b.innerText || '').trim(),
            testid: b.getAttribute('data-testid') || '',
            cls: b.className
        }));
        const allText = document.body ? document.body.innerText : '';
        return { checkboxes, errors, disabledButtons, allText };
    }""")
    print("CHECKBOXES:", json.dumps(info['checkboxes'], indent=2))
    print("ERRORS:", json.dumps(info['errors'], indent=2))
    print("DISABLED BUTTONS:", json.dumps(info['disabledButtons'], indent=2))
    print("\nALL TEXT IN PAGE:\n", info['allText'])

    # Also inspect all frames
    for i, fr in enumerate(page.frames):
        if fr == page.main_frame: continue
        f_info = await fr.evaluate("""() => {
            return {
                url: location.href,
                checkboxes: Array.from(document.querySelectorAll('input[type="checkbox"]')).map(c => ({
                    id: c.id, checked: c.checked, label: (c.closest('label') ? c.closest('label').innerText : '').trim()
                })),
                errors: Array.from(document.querySelectorAll('[role="alert"], [class*="error" i]')).map(e => (e.innerText || '').trim()).filter(Boolean),
                text: (document.body ? document.body.innerText : '').slice(0, 400)
            };
        }""")
        print(f"\n--- FRAME {i} ---", json.dumps(f_info, indent=2))

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(inspect_review_page())
