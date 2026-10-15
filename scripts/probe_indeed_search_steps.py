"""Isolate which sub-step of the Indeed search flow blanks the page.

Reproduces the handler steps manually, printing page.url after each:
  goto home -> dismiss overlays -> type role -> type location -> click Find jobs

Usage:
    .venv/bin/python -u scripts/probe_indeed_search_steps.py
"""

import asyncio
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

HOME = os.getenv("INDEED_HOME_URL", "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile")


async def show(page, label):
    try:
        url = page.url
    except Exception as e:
        url = f"<err {e!r}>"
    try:
        cnt = await page.locator("#text-input-what").count()
    except Exception as e:
        cnt = f"<err {e!r}>"
    print(f"   [{label}] url={url} what_count={cnt}")
    return url


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        print("== goto home ==")
        try:
            resp = await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            print("   goto status:", resp.status if resp else None)
        except Exception as e:
            print("   goto EXCEPTION:", repr(e))
        await asyncio.sleep(random.uniform(2.5, 4.5))
        await show(page, "after goto")

        print("== dismiss overlays ==")
        await agent._indeed_dismiss_overlays(page)
        await show(page, "after dismiss")

        print("== type role ==")
        ok = await agent._indeed_human_type(page, "#text-input-what", "React Developer")
        print("   typed:", ok)
        await show(page, "after type role")
        await asyncio.sleep(random.uniform(0.5, 1.1))

        print("== type location ==")
        ok = await agent._indeed_human_type(page, "#text-input-where", "Bengaluru, Karnataka")
        print("   typed:", ok)
        await show(page, "after type location")
        await asyncio.sleep(random.uniform(0.5, 1.1))

        print("== click Find jobs ==")
        clicked = False
        for sel in (
            "button.yosegi-InlineWhatWhere-primaryButton",
            'button:has-text("Find jobs")',
            'button[type="submit"]:has-text("Find")',
        ):
            try:
                loc = page.locator(sel).first
                c = await loc.count()
                v = await loc.is_visible() if c else False
                print(f"   try {sel!r}: count={c} visible={v}")
                if c > 0 and v:
                    await loc.click(timeout=8000)
                    clicked = True
                    break
            except Exception as e:
                print(f"   try {sel!r} EXC: {e!r}")
        print("   clicked:", clicked)
        await show(page, "after click")

        print("== wait for results ==")
        try:
            await page.wait_for_selector(".job_seen_beacon, div[data-jk], #mosaic-provider-jobcards, li[data-jk]", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(3)
        await show(page, "after wait")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
