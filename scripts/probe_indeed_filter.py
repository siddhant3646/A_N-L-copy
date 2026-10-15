"""Probe the Indeed search filter UI for the 'Easily apply' facet.

Tries several seed URLs, dumps the filter area, and (when found) clicks the
'Easily apply' filter, then reports how many of the first few jobs are in-site
(Indeed Apply) using the agent's detection.
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

SEEDS = [
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
    "https://in.indeed.com/jobs?q=Software+Engineer&l=Bengaluru%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
]

FILTER_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const hits = [];
    document.querySelectorAll('button, a, label, [role="button"], [role="checkbox"]').forEach(n => {
        const t = norm(n.innerText || n.textContent || '') + ' ' + norm(n.getAttribute('aria-label') || '');
        if (/easily apply/.test(t)) {
            hits.push({
                tag: n.tagName,
                text: norm(n.innerText || n.textContent || '').slice(0, 40),
                aria: n.getAttribute('aria-label'),
                pressed: n.getAttribute('aria-pressed'),
                checked: n.getAttribute('aria-checked'),
                cls: (typeof n.className === 'string' ? n.className : '').slice(0, 90),
                href: (n.getAttribute('href') || '').slice(0, 80)
            });
        }
    });
    return hits;
}"""


async def test_seed(agent, page, seed):
    await page.goto(seed, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await agent._indeed_dismiss_overlays(page)
    await asyncio.sleep(1)

    hits = await page.evaluate(FILTER_JS)
    print(f"\n=== SEED: {seed}")
    print(f"    url now: {page.url[:120]}")
    print(f"    'Easily apply' filter hits: {len(hits)}")
    for h in hits[:6]:
        print(f"      {h['tag']} text={h['text']!r} pressed={h['pressed']} checked={h['checked']} cls={h['cls'][:60]!r}")

    jobs = await agent._indeed_collect_jobs(page)
    easy = 0
    sampled = []
    for job in jobs[:4]:
        jk = job.get("jk")
        if not jk:
            continue
        await page.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.2)
        await agent._indeed_dismiss_overlays(page)
        has = await agent._indeed_has_easy_apply(page)
        if has:
            easy += 1
        sampled.append({"jk": jk, "title": (job.get("title") or "")[:35], "easy": has})
        print(f"      [{('EASY' if has else 'ext ')}] {sampled[-1]['title']!r}")
    return {"seed": seed, "filter_hits": hits, "sampled": sampled, "easy_count": easy}


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"
        results = []
        for seed in SEEDS:
            try:
                results.append(await test_seed(agent, page, seed))
            except Exception as e:
                print(f"    ERROR: {e}")
                results.append({"seed": seed, "error": str(e)})
            await asyncio.sleep(1.5)
        f = OUT / f"probe_indeed_filter_{int(time.time())}.json"
        f.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
        print("\nSUMMARY:")
        for r in results:
            print(f"  easy={r.get('easy_count', '?')}  {r.get('seed', '')[:90]}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
