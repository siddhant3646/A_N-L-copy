"""Focused probe: reach the Indeed SmartApply surface for ONE easy-apply job
and run the apply flow with debug instrumentation enabled.

Usage:
    SENTINEL_INDEED_DEBUG=1 .venv/bin/python -u scripts/probe_indeed_apply_flow.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent


async def main():
    os.environ.setdefault("SENTINEL_INDEED_DEBUG", "1")
    os.environ.setdefault("INDEED_SEARCH_QUERY", "Java Developer")
    os.environ.setdefault("INDEED_SEARCH_LOCATION", "Bengaluru, Karnataka")

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser
    agent._current_platform = "indeed"

    try:
        seed = await agent._indeed_prepare_results(page)
        print("seed:", seed)
        if not seed:
            return
        await agent._indeed_dismiss_overlays(page)

        jobs = await agent._indeed_collect_jobs(page)
        easy = [j for j in jobs if j.get("easy")]
        print(f"jobs: {len(jobs)} easy: {len(easy)}")
        if not easy:
            print("no easy-apply jobs; abort")
            return

        target = easy[0]
        want_jk = os.getenv("SENTINEL_PROBE_JK", "").strip()
        want_co = os.getenv("SENTINEL_PROBE_COMPANY", "").strip().lower()
        if want_jk:
            for j in easy:
                if str(j.get("jk")) == want_jk:
                    target = j
                    break
        elif want_co:
            for j in easy:
                if want_co in str(j.get("company", "")).lower():
                    target = j
                    break
        print(f"target: {target.get('title')} | {target.get('company')} | jk={target.get('jk')}")

        opened = await agent._indeed_open_card(page, target)
        print("opened:", opened)
        if not opened:
            print("card click failed; abort")
            return
        await asyncio.sleep(3.0)
        await agent._indeed_dismiss_overlays(page)

        has_easy = await agent._indeed_has_easy_apply(page)
        print("easy apply control present:", has_easy)
        if not has_easy:
            print("no easy apply control; abort")
            return

        result = await agent._indeed_run_apply_flow(page)
        print("APPLY RESULT:", result)
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
