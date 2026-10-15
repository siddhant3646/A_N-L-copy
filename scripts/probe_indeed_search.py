"""Probe the Indeed search-results page structure.

Dumps every job card with its title/company/jk and the apply affordances inside
that card, then clicks the first card that has an in-site "Easily apply" button
to see whether SmartApply opens (new tab / same tab / iframe).

Never submits anything.
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

SEED = os.getenv(
    "INDEED_SEARCH_URL",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
)

CARDS_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const cards = Array.from(document.querySelectorAll('[data-jk]'));
    const seen = new Set();
    const out = [];
    for (const c of cards) {
        const jk = c.getAttribute('data-jk');
        if (!jk || seen.has(jk)) continue;
        seen.add(jk);
        const title = norm((c.querySelector('h2, [class*="jobTitle"], a[aria-label]') || {}).innerText || '');
        const company = norm((c.querySelector('[data-testid="company-name"], [class*="companyName"]') || {}).innerText || '');
        const applyNodes = Array.from(c.querySelectorAll('button, a'))
            .map(n => ({
                tag: n.tagName,
                text: norm(n.innerText || n.textContent || ''),
                testid: n.getAttribute('data-testid'),
                href: (n.getAttribute('href') || '').slice(0, 70),
                aria: n.getAttribute('aria-label')
            }))
            .filter(n => /apply/i.test((n.text || '') + ' ' + (n.aria || '')));
        out.push({ jk, title, company, applyNodes });
    }
    return out;
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

        cards = await page.evaluate(CARDS_JS)
        print(f"Cards: {len(cards)}")
        easy_jk = None
        for c in cards:
            texts = [n.get("text") for n in c.get("applyNodes", [])]
            print(f"  [{c['jk']}] {c['title'][:45]!r} @ {c['company'][:25]!r} apply={texts}")
            if not easy_jk and any("easily apply" in (t or "").lower() for t in texts):
                easy_jk = c["jk"]

        print(f"\nFirst card with 'Easily apply': {easy_jk}")

        result = {"cards": cards, "easy_jk": easy_jk}
        if easy_jk:
            ctx = page.context
            before = {id(p) for p in ctx.pages}
            clicked = await page.evaluate(r"""(jk) => {
                const card = Array.from(document.querySelectorAll('[data-jk]'))
                    .find(c => c.getAttribute('data-jk') === jk);
                if (!card) return false;
                const btn = Array.from(card.querySelectorAll('button, a'))
                    .find(n => /easily apply/i.test(n.innerText || n.textContent || ''));
                if (!btn) return false;
                btn.click();
                return true;
            }""", easy_jk)
            result["clicked"] = clicked
            print(f"clicked={clicked}")

            for _ in range(24):
                await asyncio.sleep(0.75)
                new_pages = [p for p in ctx.pages if id(p) not in before]
                if new_pages:
                    result["new_tab"] = new_pages[0].url[:100]
                    break
                if "smartapply" in (page.url or ""):
                    result["new_tab"] = page.url[:100]
                    break
            print(f"new_tab={result.get('new_tab')}")
            print(f"page.url={page.url[:100]}")

            # If a new tab, inspect it for the apply form.
            target = None
            new_pages = [p for p in ctx.pages if id(p) not in before]
            if new_pages:
                target = new_pages[0]
            elif "smartapply" in (page.url or ""):
                target = page
            if target is not None:
                try:
                    await target.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                result["apply_surface"] = await target.evaluate(r"""() => {
                    const ids = ['#ia-container', '.ia-BasePage', '.ia-Questions',
                                 'iframe', 'div[role="dialog"]', 'form'];
                    const found = {};
                    for (const s of ids) found[s] = !!document.querySelector(s);
                    return {url: location.href.slice(0, 100),
                            title: document.title,
                            found: found,
                            body: (document.body.innerText || '').slice(0, 300)};
                }""")
                print("apply_surface:", json.dumps(result["apply_surface"], indent=2)[:800])

        f = OUT / f"probe_indeed_search_{int(time.time())}.json"
        f.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
