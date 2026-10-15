"""Inspect Indeed home overlay controls and find which click blanks the page.

Steps:
  1. goto home, print url
  2. dump #onetrust button + every [role=dialog]/modal + their close candidates
  3. click the cookie button only, print url
  4. for each modal close candidate: reload home, click just that one, print url

Usage:
    .venv/bin/python -u scripts/probe_indeed_overlays.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

HOME = os.getenv("INDEED_HOME_URL", "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile")

DUMP_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 160);
    const vis = n => !!(n && n.getClientRects().length);
    const desc = n => ({
        tag: n.tagName,
        id: n.id || null,
        cls: (n.className && String(n.className).slice(0, 80)) || null,
        role: n.getAttribute('role') || null,
        testid: n.getAttribute('data-testid') || null,
        aria: n.getAttribute('aria-label') || null,
        href: n.getAttribute('href') || null,
        visible: vis(n),
        text: norm(n.innerText || n.textContent || '')
    });
    const cookie = document.querySelector('#onetrust-accept-btn-handler');
    const modals = Array.from(document.querySelectorAll(
        '[role="dialog"], .icl-Modal, [data-testid="passport-intercept-type-modal"]'
    ));
    const dialogs = modals.map(m => {
        const closes = Array.from(m.querySelectorAll(
            'button[aria-label*="close" i], [data-testid="close-button"], .icl-Modal-close, a[aria-label*="close" i]'
        ));
        return { modal: desc(m), closes: closes.map(desc) };
    });
    return {
        url: location.href,
        cookie: cookie ? desc(cookie) : null,
        dialogCount: modals.length,
        dialogs
    };
}"""


async def settle(page, secs=3.0):
    await asyncio.sleep(secs)


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()

        print("== goto home (1) ==")
        try:
            r = await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            print("   status:", r.status if r else None)
        except Exception as e:
            print("   EXC:", repr(e))
        await settle(page, 4)
        print("   url:", page.url)

        dump = await page.evaluate(DUMP_JS)
        print("== overlay dump ==")
        print(json.dumps(dump, indent=2)[:4000])

        # Collect close candidates from the first dialog to test individually.
        candidates = []
        for d in dump.get("dialogs", []):
            for c in d.get("closes", []):
                candidates.append(c)
        print(f"== {len(candidates)} close candidate(s) ==")

        # Test the cookie button.
        print("== click cookie button only ==")
        await page.evaluate("""() => {
            const b = document.querySelector('#onetrust-accept-btn-handler');
            if (b) b.click();
        }""")
        await settle(page, 1.5)
        print("   url after cookie click:", page.url)

        # Test each close candidate after a fresh home load.
        for i, c in enumerate(candidates[:6]):
            print(f"== reload + click close candidate #{i}: {c.get('tag')} aria={c.get('aria')} testid={c.get('testid')} cls={str(c.get('cls'))[:40]} ==")
            try:
                await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print("   goto EXC:", repr(e))
            await settle(page, 3)
            before = page.url
            await page.evaluate("""(spec) => {
                const modals = document.querySelectorAll('[role="dialog"], .icl-Modal, [data-testid="passport-intercept-type-modal"]');
                for (const m of modals) {
                    const closes = m.querySelectorAll('button[aria-label*="close" i], [data-testid="close-button"], .icl-Modal-close, a[aria-label*="close" i]');
                    for (const x of closes) {
                        if ((x.getAttribute('aria-label') || null) === spec.aria
                            && (x.getAttribute('data-testid') || null) === spec.testid) {
                            try { x.click(); } catch (e) {}
                            return;
                        }
                    }
                }
            }""", {"aria": c.get("aria"), "testid": c.get("testid")})
            await settle(page, 1.5)
            print(f"   url before={before}")
            print(f"   url after ={page.url}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
