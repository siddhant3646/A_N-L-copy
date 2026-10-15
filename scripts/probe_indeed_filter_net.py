"""Capture the network request Indeed issues when 'Easily apply' is toggled.

Reveals the authoritative facet parameter for the 'Easily apply' filter.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright


OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

BASE = "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka"


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    captured = []
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()

        def on_request(req):
            u = req.url
            if "sc=" in u or "/jobs?" in u or "graphql" in u.lower() or "mosaic" in u.lower():
                captured.append({"method": req.method, "url": u[:300],
                                 "post": (req.post_data or "")[:400]})

        page.on("request", on_request)

        await page.goto(BASE, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        captured.clear()  # drop initial load noise

        html = await page.evaluate(r"""() => {
            const b = document.querySelector('button[aria-label="Easily apply filter"]');
            if (!b) return 'NO BUTTON';
            let p = b;
            for (let i = 0; i < 4 && p.parentElement; i++) p = p.parentElement;
            return p.outerHTML.slice(0, 1200);
        }""")
        print("FILTER CONTAINER:\n", html[:1200])

        await page.evaluate(
            """() => { const b = document.querySelector('button[aria-label="Easily apply filter"]'); if (b) b.click(); }"""
        )
        await asyncio.sleep(6)

        print(f"\nCaptured {len(captured)} matching requests:")
        for c in captured[:20]:
            print(f"  {c['method']} {c['url']}")
            if c.get("post"):
                print(f"      post: {c['post'][:200]}")

        f = OUT / f"probe_indeed_filter_net_{int(time.time())}.json"
        f.write_text(json.dumps({"container": html, "requests": captured}, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
