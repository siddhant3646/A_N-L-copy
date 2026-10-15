import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

async def test():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    job_url = "https://www.hirist.tech/j/software-engineer-java-1675045"
    await page.goto(job_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(4)

    apply_btn = page.locator('button:has-text("Apply")').first
    await apply_btn.click()
    await asyncio.sleep(3)

    # Dump full form structure
    form_info = await page.evaluate("""() => {
        const textareas = Array.from(document.querySelectorAll('textarea')).map(t => ({
            placeholder: t.placeholder,
            id: t.id,
            name: t.name,
            value: t.value,
            cls: t.className,
            visible: !!(t.offsetWidth || t.offsetHeight)
        }));
        const inputs = Array.from(document.querySelectorAll('input')).map(i => ({
            type: i.type,
            placeholder: i.placeholder,
            id: i.id,
            name: i.name,
            value: i.value,
            checked: i.checked,
            cls: i.className,
            visible: !!(i.offsetWidth || i.offsetHeight)
        }));
        const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim(),
            cls: b.className,
            disabled: b.disabled,
            visible: !!(b.offsetWidth || b.offsetHeight)
        }));
        // Find question container
        const allText = document.body ? document.body.innerText : '';
        return { textareas, inputs, buttons, allText };
    }""")
    print("TEXTAREAS:", json.dumps(form_info['textareas'], indent=2))
    print("INPUTS:", json.dumps(form_info['inputs'], indent=2))
    print("BUTTONS:", json.dumps(form_info['buttons'], indent=2))
    print("\nALL TEXT:\n", form_info['allText'])

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
