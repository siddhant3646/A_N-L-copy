"""Dump Indeed results-page card structure + every apply control on the page."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

SEED = os.getenv(
    "INDEED_SEARCH_URL",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
)

DUMP_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const beacon = document.querySelectorAll('.job_seen_beacon');
    const cardOutline = document.querySelectorAll('div.cardOutline');
    const dataJk = document.querySelectorAll('[data-jk]');

    // All apply-ish controls anywhere on the page, with a short path.
    const path = el => {
        const parts = [];
        let n = el;
        for (let i = 0; i < 5 && n; i++) {
            let p = n.tagName.toLowerCase();
            if (n.id) p += '#' + n.id;
            else if (n.className && typeof n.className === 'string') {
                p += '.' + n.className.split(/\s+/).slice(0, 2).join('.');
            }
            parts.unshift(p);
            n = n.parentElement;
        }
        return parts.join(' > ');
    };
    const controls = [];
    document.querySelectorAll('button, a, [role="button"]').forEach(n => {
        const t = norm(n.innerText || n.textContent || '') + ' ' + norm(n.getAttribute('aria-label') || '');
        if (/apply/i.test(t)) {
            controls.push({
                tag: n.tagName, text: norm(n.innerText || ''),
                testid: n.getAttribute('data-testid'),
                href: (n.getAttribute('href') || '').slice(0, 80),
                visible: n.getClientRects().length > 0,
                path: path(n)
            });
        }
    });

    const firstBeacon = document.querySelector('.job_seen_beacon');
    return {
        counts: {beacon: beacon.length, cardOutline: cardOutline.length, dataJk: dataJk.length},
        first_beacon_html: firstBeacon ? firstBeacon.outerHTML.slice(0, 2500) : null,
        controls: controls.slice(0, 40),
        controls_count: controls.length
    };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"
        await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)
        await asyncio.sleep(1)
        dump = await page.evaluate(DUMP_JS)
        print("counts:", dump["counts"])
        print("controls_count:", dump["controls_count"])
        for c in dump["controls"]:
            print("  ", c["tag"], repr(c["text"])[:50], "testid=", c["testid"],
                  "vis=", c["visible"], "|", c["path"][:110])
        print("\n--- FIRST BEACON HTML ---")
        print((dump["first_beacon_html"] or "")[:2500])
        f = OUT / "probe_indeed_cards.json"
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
