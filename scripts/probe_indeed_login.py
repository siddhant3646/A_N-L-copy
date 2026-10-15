"""Check whether the copied Chrome profile is logged into Indeed.

Prints account-menu presence, sign-in prompts, and a sample job card's HTML so
we can see whether Indeed exposes any in-site ('Easily apply') affordance.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright


OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()

        await page.goto("https://in.indeed.com/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)

        home = await page.evaluate(r"""() => {
            const t = (document.body ? document.body.innerText : '').toLowerCase();
            return {
                url: location.href,
                hasAccountMenu: !!document.querySelector(
                    '#gnav-account-menu-button, [data-testid="gnav-account-menu-button"], [aria-label*="Account" i]'
                ),
                signInText: !!document.querySelector('a[href*="login"], a[href*="account/login"]'),
                bodyHasSignIn: t.includes('sign in'),
                bodySnippet: t.replace(/\s+/g, ' ').slice(0, 200)
            };
        }""")
        print("HOME:", json.dumps(home, indent=2))

        await page.goto(
            "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka",
            wait_until="domcontentloaded", timeout=45000,
        )
        await asyncio.sleep(4)

        card = await page.evaluate(r"""() => {
            const c = document.querySelector('div.cardOutline.tapItem.result, .job_seen_beacon, div[data-jk]');
            if (!c) return { found: false };
            const t = (c.innerText || '').replace(/\s+/g, ' ').trim();
            return {
                found: true,
                text: t.slice(0, 300),
                hasEasilyApplyBadge: /easily apply/i.test(t),
                links: Array.from(c.querySelectorAll('a')).map(a => (a.getAttribute('href') || '').slice(0, 60)).slice(0, 3),
                buttons: Array.from(c.querySelectorAll('button')).map(b => (b.innerText || '').trim().slice(0, 30)).slice(0, 4)
            };
        }""")
        print("CARD:", json.dumps(card, indent=2))

        f = OUT / f"probe_indeed_login_{int(time.time())}.json"
        f.write_text(json.dumps({"home": home, "card": card}, indent=2), encoding="utf-8")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
