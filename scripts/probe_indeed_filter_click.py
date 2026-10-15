"""Click Indeed's 'Easily apply' filter and measure whether it surfaces in-site jobs.

Captures the resulting URL (the authoritative filter param) and samples the
first few jobs with the agent's detection.
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

        url_before = page.url
        print(f"before: {url_before[:130]}")

        # Click the 'Easily apply' filter control.
        clicked = False
        try:
            loc = page.locator('button:has-text("Easily apply")').first
            if await loc.count() > 0:
                await loc.click(timeout=8000)
                clicked = True
        except Exception as e:
            print(f"click error: {e}")
        print(f"clicked filter: {clicked}")

        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)
        url_after = page.url
        print(f"after : {url_after[:160]}")

        # Also try reading the page's applied filter chips.
        chips = await page.evaluate(r"""() => {
            const norm = s => (s || '').replace(/\s+/g, ' ').trim();
            const out = [];
            document.querySelectorAll('button, [role="button"], [role="checkbox"]').forEach(n => {
                const t = norm(n.innerText || n.textContent || '').toLowerCase();
                if (t.includes('easily apply')) {
                    out.push({
                        text: t.slice(0, 30),
                        pressed: n.getAttribute('aria-pressed'),
                        cls: (typeof n.className === 'string' ? n.className : '').slice(0, 60)
                    });
                }
            });
            return out;
        }""")
        print(f"filter chips: {chips}")

        jobs = await agent._indeed_collect_jobs(page)
        easy = 0
        sampled = []
        for job in jobs[:5]:
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

        result = {"url_before": url_before, "url_after": url_after, "clicked": clicked,
                  "chips": chips, "sampled": sampled, "easy_count": easy}
        f = OUT / f"probe_indeed_filter_click_{int(time.time())}.json"
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
