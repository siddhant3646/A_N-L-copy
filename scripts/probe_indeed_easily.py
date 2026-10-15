"""Deterministically apply Indeed's 'Easily apply' filter and capture the URL.

1. Load a plain search (no sc param).
2. Force-click the button with aria-label 'Easily apply filter'.
3. Poll the URL for up to ~12s.
4. Re-collect jobs and sample the first few via the agent's detail-pane detection.
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

BASE = "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka"


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        await page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)
        await asyncio.sleep(1)

        print(f"before: {page.url[:130]}")

        state = await page.evaluate(r"""() => {
            const b = document.querySelector('button[aria-label="Easily apply filter"]');
            if (b) { b.click(); return { found: true, expanded: b.getAttribute('aria-expanded') }; }
            return { found: false };
        }""")
        print(f"clicked: {state}")

        changed = False
        for i in range(12):
            await asyncio.sleep(1.0)
            if page.url != BASE and 'sc=' in page.url:
                changed = True
                break
        print(f"after : {page.url[:170]}  (url_changed={changed})")

        exp = await page.evaluate(
            """() => { const b = document.querySelector('button[aria-label="Easily apply filter"]'); return b ? b.getAttribute('aria-expanded') : null; }"""
        )
        print(f"aria-expanded now: {exp}")

        jobs = await agent._indeed_collect_jobs(page)
        print(f"jobs after filter: {len(jobs)}")
        easy = 0
        sampled = []
        for job in jobs[:6]:
            jk = job.get("jk")
            if not jk:
                continue
            await page.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2.2)
            await agent._indeed_dismiss_overlays(page)
            has = await agent._indeed_has_easy_apply(page)
            if has:
                easy += 1
            t = (job.get("title") or "")[:35]
            sampled.append({"jk": jk, "title": t, "easy": has})
            print(f"  [{'EASY' if has else 'ext '}] {t!r}")

        result = {"base": BASE, "url_after": page.url, "click_state": state,
                  "aria_expanded": exp, "jobs": len(jobs), "easy_count": easy, "sampled": sampled}
        f = OUT / f"probe_indeed_easily_{int(time.time())}.json"
        f.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nEASY-APPLY: {easy}/{len(sampled)}")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
