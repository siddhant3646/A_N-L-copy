"""Compare goto(viewjob?jk=) vs clicking a card for in-site Indeed jobs.

Determines whether _handle_indeed_apply_task must change from jk-navigation to
card-clicking to reach in-site "Easily apply" jobs.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent


OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

SEED = "https://in.indeed.com/jobs?q=customer+support&l=Bengaluru%2C+Karnataka"

CARDS_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const out = [];
    document.querySelectorAll('.job_seen_beacon').forEach((c, i) => {
        if (i >= 12) return;
        const link = c.querySelector('h2.jobTitle a, a.jcs-JobTitle, h2 a, a[href*="jk="]');
        const t = norm(c.innerText || c.textContent || '');
        const jkEl = c.querySelector('[data-jk]') || (c.hasAttribute('data-jk') ? c : null);
        out.push({
            idx: i,
            jk: String(jkEl ? (jkEl.getAttribute('data-jk') || '') : (c.getAttribute('data-jk') || '')),
            title: link ? norm(link.innerText || '') : '',
            href: link ? (link.getAttribute('href') || '').slice(0, 80) : '',
            easy: /easily apply/i.test(t)
        });
    });
    return out;
}"""


async def detect(page, agent):
    return await agent._indeed_has_easy_apply(page)


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

        cards = await page.evaluate(CARDS_JS)
        easy = [c for c in cards if c["easy"]]
        print(f"cards={len(cards)} easy={len(easy)}")
        for c in easy[:5]:
            print(f"  [{c['idx']}] jk={c['jk']} href={c['href'][:45]!r} title={c['title'][:40]!r}")

        results = {"goto": [], "click": []}

        print("\n=== PHASE A: goto(viewjob?jk=) ===")
        for c in easy[:4]:
            try:
                await page.goto(f"https://in.indeed.com/viewjob?jk={c['jk']}", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3.5)
                await agent._indeed_dismiss_overlays(page)
                det = await detect(page, agent)
                print(f"  jk={c['jk']} -> url={page.url[:70]} det={det}")
                results["goto"].append({"jk": c["jk"], "det": det, "url": page.url})
            except Exception as e:
                print(f"  jk={c['jk']} ERROR {e}")
                results["goto"].append({"jk": c["jk"], "det": None, "error": str(e)})

        print("\n=== PHASE B: click card ===")
        await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)
        cards2 = await page.evaluate(CARDS_JS)
        easy2 = [c for c in cards2 if c["easy"]]
        for c in easy2[:4]:
            try:
                card = page.locator(".job_seen_beacon").nth(c["idx"])
                link = card.locator("h2.jobTitle a, a.jcs-JobTitle, h2 a").first
                await link.click(timeout=8000)
                await asyncio.sleep(3.5)
                await agent._indeed_dismiss_overlays(page)
                det = await detect(page, agent)
                print(f"  idx={c['idx']} jk={c['jk']} -> url={page.url[:70]} det={det}")
                results["click"].append({"jk": c["jk"], "det": det, "url": page.url})
            except Exception as e:
                print(f"  idx={c['idx']} ERROR {e}")
                results["click"].append({"jk": c["jk"], "det": None, "error": str(e)})

        f = OUT / f"probe_indeed_goto_vs_click_{int(time.time())}.json"
        f.write_text(json.dumps({"cards": cards, "results": results}, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
        print("\nSUMMARY:")
        print("  goto  det True:", sum(1 for r in results["goto"] if r["det"]), "/", len(results["goto"]))
        print("  click det True:", sum(1 for r in results["click"] if r["det"]), "/", len(results["click"]))
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
