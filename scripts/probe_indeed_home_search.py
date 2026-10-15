"""Probe the Indeed HOMEPAGE search form (the New handler entry point).

Dumps: URL/title/login state, presence+visibility of the documented search
selectors, and every visible input/button so we can see what Indeed actually
renders for the copied profile. Never submits a search.

Usage:
    .venv/bin/python -u scripts/probe_indeed_home_search.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

HOME = os.getenv("INDEED_HOME_URL", "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile")

DUMP_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const vis = n => !!(n && n.getClientRects().length);
    const desc = (n) => ({
        tag: n.tagName,
        id: n.id || null,
        name: n.getAttribute('name') || null,
        type: n.getAttribute('type') || null,
        aria: n.getAttribute('aria-label') || null,
        testid: n.getAttribute('data-testid') || null,
        cls: (n.getAttribute('class') || '').slice(0, 90),
        text: norm(n.innerText || n.value || '').slice(0, 60),
        visible: vis(n)
    });
    const sels = [
        '#text-input-what', '#text-input-where', 'input[name="q"]', 'input[name="l"]',
        'button.yosegi-InlineWhatWhere-primaryButton',
        'button[aria-label="Easily apply filter"]',
        'button[aria-label*="Easily apply" i]'
    ];
    const selState = {};
    for (const s of sels) {
        const els = Array.from(document.querySelectorAll(s));
        selState[s] = {
            count: els.length,
            visible: els.filter(vis).length,
            sample: els.slice(0, 1).map(desc)
        };
    }
    const inputs = Array.from(document.querySelectorAll('input, button, [role="button"], select, textarea'))
        .filter(vis)
        .slice(0, 60)
        .map(desc);
    const t = norm(document.body ? document.body.innerText : '');
    return {
        url: location.href,
        title: document.title,
        hasAccountMenu: !!document.querySelector(
            '#gnav-account-menu-button, [data-testid="gnav-account-menu-button"], [aria-label*="Account" i]'
        ),
        bodyHasSignIn: t.toLowerCase().includes('sign in'),
        bodySnippet: t.slice(0, 400),
        selState: selState,
        visibleControls: inputs
    };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page

        await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await agent._indeed_dismiss_overlays(page)
        await asyncio.sleep(1)

        dump = await page.evaluate(DUMP_JS)
        print("URL:", dump["url"])
        print("TITLE:", dump["title"])
        print("hasAccountMenu:", dump["hasAccountMenu"], "| bodyHasSignIn:", dump["bodyHasSignIn"])
        print("\nSELECTOR STATE:")
        for s, st in dump["selState"].items():
            print(f"  {s!r}: count={st['count']} visible={st['visible']}")
            for smp in st["sample"]:
                print(f"      -> {json.dumps(smp)}")
        print("\nVISIBLE CONTROLS:")
        for c in dump["visibleControls"]:
            print("  ", json.dumps(c))
        print("\nBODY SNIPPET:\n", dump["bodySnippet"])

        f = OUT / f"probe_indeed_home_{int(time.time())}.json"
        f.write_text(json.dumps(dump, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
