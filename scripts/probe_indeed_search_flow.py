"""Drive the new Indeed home -> search -> 'Easily apply' filter flow via the
real agent helpers and report each step. Never applies to / submits anything.

Usage:
    .venv/bin/python -u scripts/probe_indeed_search_flow.py
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

COUNTS_JS = r"""() => {
    const vis = n => !!(n && n.getClientRects().length);
    const count = s => {
        const els = Array.from(document.querySelectorAll(s));
        return { count: els.length, visible: els.filter(vis).length };
    };
    return {
        url: location.href,
        title: document.title,
        what: count('#text-input-what'),
        where: count('#text-input-where'),
        findBtn: count('button.yosegi-InlineWhatWhere-primaryButton'),
        easily: count('button[aria-label="Easily apply filter"]'),
        easilyAny: count('button[aria-label*="Easily apply" i]'),
        cards: count('.job_seen_beacon, div[data-jk], li[data-jk]')
    };
}"""


async def snapshot(page, label, report):
    state = await page.evaluate(COUNTS_JS)
    report[label] = state
    print("   " + label + ": " + json.dumps(state))
    return state


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    report = {}
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        print("== STEP: goto home ==")
        try:
            resp = await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else None
            print("   goto status: " + str(status))
        except Exception as e:
            print("   goto EXCEPTION: " + repr(e))
        await asyncio.sleep(4)
        await snapshot(page, "home", report)

        print("== STEP: type role/location + click Find jobs (via handler) ==")
        seed = await agent._indeed_search_from_home(page)
        print("   seed url: " + str(seed))
        await snapshot(page, "search", report)

        print("== STEP: apply 'Easily apply' filter (via handler) ==")
        ok = await agent._indeed_apply_easily_filter(page)
        print("   filter applied: " + str(ok))
        await asyncio.sleep(3)
        await snapshot(page, "filtered", report)

        jobs = await agent._indeed_collect_jobs(page)
        easy = sum(1 for j in jobs if j.get("easy"))
        print("   collected jobs: " + str(len(jobs)) + " easy: " + str(easy))
        report["jobs"] = jobs[:10]

        f = OUT / ("probe_indeed_search_flow_" + str(int(time.time())) + ".json")
        f.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("\n📄 saved " + str(f))
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
