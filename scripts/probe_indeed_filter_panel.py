"""Inspect Indeed's expanded 'Easily apply' filter panel and apply it properly.

Clicks the 'Easily apply filter' disclosure, dumps the revealed controls, then
tries to activate the actual 'Easily apply' checkbox/toggle and captures the URL.
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

PANEL_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const out = [];
    document.querySelectorAll('[role="checkbox"], [role="menuitemcheckbox"], input[type="checkbox"], [aria-checked]').forEach(n => {
        const t = norm(n.innerText || n.textContent || n.getAttribute('aria-label') || '');
        if (/easily apply/i.test(t) || /easily apply/i.test(n.getAttribute('aria-label') || '')) {
            out.push({
                tag: n.tagName,
                role: n.getAttribute('role'),
                ariaLabel: n.getAttribute('aria-label'),
                checked: n.getAttribute('aria-checked'),
                cls: (typeof n.className === 'string' ? n.className : '').slice(0, 70),
                html: n.outerHTML.slice(0, 260)
            });
        }
    });
    return { url: location.href, matches: out };
}"""


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

        await page.evaluate(
            """() => { const b = document.querySelector('button[aria-label="Easily apply filter"]'); if (b) b.click(); }"""
        )
        await asyncio.sleep(2.5)
        panel = await page.evaluate(PANEL_JS)
        print("PANEL:", json.dumps(panel, indent=2)[:1500])

        # If a checkbox/toggle exists, click it.
        acted = await page.evaluate(r"""() => {
            const norm = s => (s || '').replace(/\s+/g, ' ').trim();
            const nodes = document.querySelectorAll('[role="checkbox"], [role="menuitemcheckbox"], input[type="checkbox"], [aria-checked]');
            for (const n of nodes) {
                const lbl = norm(n.getAttribute('aria-label') || n.innerText || n.textContent || '');
                if (/easily apply/i.test(lbl)) {
                    try { n.click(); } catch (e) {}
                    return { clicked: true, label: lbl.slice(0, 60) };
                }
            }
            return { clicked: false };
        }""")
        print("ACTED:", acted)

        for _ in range(8):
            await asyncio.sleep(1.0)
            if 'sc=' in page.url:
                break
        print(f"URL after: {page.url[:170]}")

        jobs = await agent._indeed_collect_jobs(page)
        print(f"jobs: {len(jobs)}")
        easy = 0
        for job in jobs[:5]:
            jk = job.get("jk")
            if not jk:
                continue
            await page.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2.2)
            await agent._indeed_dismiss_overlays(page)
            has = await agent._indeed_has_easy_apply(page)
            easy += 1 if has else 0
            print(f"  [{'EASY' if has else 'ext '}] {(job.get('title') or '')[:35]!r}")

        f = OUT / f"probe_indeed_filter_panel_{int(time.time())}.json"
        f.write_text(json.dumps({"panel": panel, "acted": acted, "url": page.url, "easy": easy}, indent=2), encoding="utf-8")
        print(f"EASY: {easy}/5")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
