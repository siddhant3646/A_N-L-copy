"""Probe what Indeed's in-site "Easily apply" click actually opens.

Navigates to a viewjob page that reports an easy-apply surface, records the
state, clicks the same button the handler uses, then dumps every page/frame/URL
and any apply container so we can see whether SmartApply opens as a new tab,
same-tab navigation, or an in-page iframe. Never submits anything.
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

INDEED_SEED = os.getenv(
    "INDEED_SEARCH_URL",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
)


def snapshot(page):
    frames = []
    for fr in page.frames:
        frames.append((fr.url or "")[:90])
    return {"url": page.url, "frames": frames}


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    out = []
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        await page.goto(INDEED_SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await agent._indeed_dismiss_overlays(page)
        jobs = await agent._indeed_collect_jobs(page)
        print(f"Collected {len(jobs)} jobs")

        for job in jobs[:3]:
            jk = job.get("jk")
            if not jk:
                continue
            await page.goto(f"https://in.indeed.com/viewjob?jk={jk}",
                            wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            await agent._indeed_dismiss_overlays(page)

            has_easy = await agent._indeed_has_easy_apply(page)
            rec = {"jk": jk, "title": job.get("title"), "has_easy": has_easy}

            # Identify the button we would click.
            info = await page.evaluate("""() => {
                const scopes = ['#viewJobSSRRoot', '.jobsearch-JobComponent', '#vjs-container',
                                '[data-testid="jobsearch-JobComponent"]', '#jobsearch-ViewjobPaneWrapper', 'main', 'body'];
                const out = {scopeUsed: null, buttons: []};
                for (const s of scopes) {
                    const scope = document.querySelector(s);
                    if (!scope) continue;
                    const btns = Array.from(scope.querySelectorAll('button, a'))
                        .filter(b => /apply/i.test((b.innerText||'') + ' ' + (b.getAttribute('aria-label')||'')));
                    if (btns.length) {
                        out.scopeUsed = s;
                        out.buttons = btns.slice(0, 6).map(b => ({
                            tag: b.tagName,
                            text: (b.innerText||'').trim().slice(0, 60),
                            testid: b.getAttribute('data-testid'),
                            href: b.getAttribute('href'),
                            aria: b.getAttribute('aria-label')
                        }));
                        break;
                    }
                }
                return out;
            }""")
            rec["apply_buttons"] = info
            print(f"\n[{jk}] {job.get('title')} has_easy={has_easy}")
            print(f"   scopeUsed={info.get('scopeUsed')}")
            for b in info.get("buttons", []):
                print(f"     {b}")

            if not has_easy:
                out.append(rec)
                continue

            ctx = page.context
            before_ids = {id(p) for p in ctx.pages}
            rec["before"] = snapshot(page)

            clicked = False
            for scope in ("#viewJobSSRRoot", ".jobsearch-JobComponent", ""):
                for sel in ('button:has-text("Easily apply")', 'a:has-text("Easily apply")',
                            'button:has-text("Apply now")', '[data-testid="viewjob-indeed-apply"]',
                            '#indeedApplyButton'):
                    full = f"{scope} {sel}".strip()
                    try:
                        loc = page.locator(full).first
                        if await loc.count() > 0 and await loc.is_visible():
                            print(f"   clicking: {full}")
                            await loc.click(timeout=8000)
                            clicked = True
                            break
                    except Exception as e:
                        print(f"   click failed {full}: {e}")
                if clicked:
                    break
            rec["clicked"] = clicked

            await asyncio.sleep(6)
            rec["after_page"] = snapshot(page)
            rec["after_pages"] = [(p.url or "")[:90] for p in ctx.pages]
            rec["after_new_pages"] = [(p.url or "")[:90] for p in ctx.pages if id(p) not in before_ids]
            # look for apply containers anywhere
            rec["apply_container"] = await page.evaluate("""() => {
                const sel = ['#ia-container', '.ia-BasePage', '.ia-Questions',
                             'iframe[src*="smartapply"]', 'iframe[id*="indeedapply"]',
                             'div[role="dialog"]'];
                const found = [];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el) found.push(s);
                }
                const body = (document.body ? document.body.innerText : '').slice(0, 200);
                return {found, body};
            }""")
            print(f"   after url: {rec['after_page']['url'][:90]}")
            print(f"   other pages: {rec['after_pages']}")
            print(f"   frames: {rec['after_page']['frames']}")
            print(f"   apply_container: {rec['apply_container']}")

            # cleanup new tab
            for p in list(ctx.pages):
                if id(p) not in before_ids:
                    try:
                        await p.close()
                    except Exception:
                        pass
            if page.url != rec["before"]["url"]:
                try:
                    await page.goto(rec["before"]["url"], wait_until="domcontentloaded")
                    await asyncio.sleep(1)
                except Exception:
                    pass

            out.append(rec)

        f = OUT / f"probe_indeed_click_{int(time.time())}.json"
        f.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
