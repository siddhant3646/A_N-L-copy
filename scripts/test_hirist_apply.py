import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    # Let's test a job: e.g. software-engineer-java-1675045 or another one from feed
    job_url = "https://www.hirist.tech/j/software-engineer-java-1675045"
    print(f"Opening job: {job_url}")
    await page.goto(job_url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(4)
    await agent._hirist_dismiss_dialogs(page)

    apply_btn = page.locator('button:has-text("Apply")').first
    print("Clicking Apply...")
    await apply_btn.click()
    await asyncio.sleep(4)

    # Check what appeared on screen!
    diag_dump = await page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('[role="dialog"], .MuiDialog-root, .MuiModal-root')).map(d => {
            return {
                text: (d.innerText || '').slice(0, 800),
                buttons: Array.from(d.querySelectorAll('button, a')).map(b => (b.innerText || '').trim()),
                inputs: Array.from(d.querySelectorAll('input, select, textarea')).map(i => ({
                    tag: i.tagName,
                    type: i.type,
                    name: i.name,
                    placeholder: i.placeholder,
                    value: i.value
                }))
            };
        });
        const bodyText = (document.body ? document.body.innerText : '').slice(0, 1000);
        return { dialogs, bodySnippet: bodyText };
    }""")
    print("MODAL / DIALOG DUMP:\n", json.dumps(diag_dump, indent=2))

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test())
