"""Walk every Indeed job in the seed search and report, per job, whether the
detail pane offers an in-site (Easily apply) action or only an external one.

Uses the agent's new pane-scoped detection so the result is authoritative.
Never clicks or submits anything.
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

DETAIL_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const pane = document.querySelector('#jobsearch-ViewjobPaneWrapper')
        || document.querySelector('#viewJobSSRRoot')
        || document.querySelector('[data-testid="jobsearch-JobComponent"]')
        || document.querySelector('.jobsearch-JobComponent');
    const out = { pane: !!pane, controls: [] };
    if (!pane) return out;
    const inCard = n => !!n.closest('[data-jk], #mosaic-provider-jobcards, ul li, .job_seen_beacon');
    Array.from(pane.querySelectorAll('button, a, [role="button"]')).forEach(n => {
        const t = norm(n.innerText || n.textContent || '') + ' ' +
                  norm(n.getAttribute('aria-label') || '');
        if (/apply/.test(t)) {
            out.controls.push({
                tag: n.tagName,
                text: norm(n.innerText || ''),
                testid: n.getAttribute('data-testid'),
                href: (n.getAttribute('href') || '').slice(0, 60),
                inCard: inCard(n)
            });
        }
    });
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

        jobs = await agent._indeed_collect_jobs(page)
        print(f"Collected {len(jobs)} jobs")

        results = []
        easy_count = 0
        for job in jobs[:12]:
            jk = job.get("jk")
            title = (job.get("title") or "")[:40]
            company = (job.get("company") or "")[:25]
            try:
                await page.goto(f"https://in.indeed.com/viewjob?jk={jk}",
                                wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(2.5)
                await agent._indeed_dismiss_overlays(page)
                easy = await agent._indeed_has_easy_apply(page)
                detail = await page.evaluate(DETAIL_JS)
                texts = [c.get("text") for c in detail.get("controls", [])]
                if easy:
                    easy_count += 1
                mark = "EASY" if easy else "ext "
                print(f"  [{mark}] {jk} {title!r} @ {company!r} controls={texts}")
                results.append({"jk": jk, "title": title, "company": company,
                                "easy": easy, "detail": detail})
            except Exception as e:
                print(f"  [err ] {jk} {title!r}: {e}")
                results.append({"jk": jk, "title": title, "company": company, "error": str(e)})

        print(f"\nEASY-APPLY jobs: {easy_count}/{len(results)}")
        f = OUT / f"probe_indeed_all_jobs_{int(time.time())}.json"
        f.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
