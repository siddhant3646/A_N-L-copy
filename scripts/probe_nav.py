"""Minimal navigation probe: why does page.goto(Indeed) leave us on about:blank?

Prints every context page's URL before/after, any goto exception, and the
resulting document state. Never submits anything.

Usage:
    .venv/bin/python -u scripts/probe_nav.py
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

HOME = os.getenv("INDEED_HOME_URL", "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile")


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    try:
        await browser.start()
        ctx = browser.context
        print("context:", ctx)
        print("pages before:", [(p.url, p.is_closed()) for p in (ctx.pages if ctx else [])])

        page = await browser.get_current_page() or await browser.new_page()
        print("chosen page url:", page.url)

        try:
            resp = await page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            print("goto returned status:", (resp.status if resp else None))
        except Exception as e:
            print("goto EXCEPTION:", repr(e))
            traceback.print_exc()

        print("url immediately after goto:", page.url)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception as e:
            print("wait_for_load_state exception:", repr(e))
        await asyncio.sleep(3)
        print("url after settle:", page.url)
        try:
            print("title:", await page.title())
        except Exception as e:
            print("title exception:", repr(e))
        try:
            n = await page.evaluate("() => ({inputs: document.querySelectorAll('input').length, html: document.documentElement.outerHTML.length})")
            print("dom:", n)
        except Exception as e:
            print("dom exception:", repr(e))

        print("pages after:", [(p.url, p.is_closed()) for p in (ctx.pages if ctx else [])])
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
