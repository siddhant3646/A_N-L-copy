"""Probe the Indeed SmartApply questions page DOM to see whether answers stick.

Reaches the first easy-apply job's questions page, dumps each question's input
structure, runs the agent's answerer, re-dumps the checked state, then clicks
Continue and reports whether the page advanced.

Usage:
    SENTINEL_INDEED_DEBUG=1 .venv/bin/python -u scripts/probe_indeed_questions.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

DUMP_JS = r"""() => {
    const vis = n => !!(n && n.getClientRects().length);
    const out = [];
    const boxes = new Set();
    document.querySelectorAll('.ia-TextQuestion, .ia-SelectQuestion, .ia-Question, fieldset, .ia-RadioButton-container').forEach(n => {
        const box = n.closest('.ia-question, fieldset, .ia-Question, .ia-Questions > div') || n;
        boxes.add(box);
    });
    boxes.forEach(box => {
        const legend = box.querySelector('label, legend, .ia-label, .ia-Question-label, .ia-QuestionLabel');
        const raw = (legend ? legend.innerText : box.innerText) || '';
        const q = raw.split('\n').map(s => s.trim()).filter(Boolean)[0] || '';
        const inputs = Array.from(box.querySelectorAll('input, select, textarea')).map(inp => ({
            tag: inp.tagName,
            type: inp.type || null,
            name: inp.name || null,
            id: inp.id || null,
            value: inp.value || null,
            checked: inp.checked === undefined ? null : inp.checked,
            required: !!inp.required,
            visible: vis(inp),
            aria: inp.getAttribute('aria-label') || null
        }));
        out.push({ q: q.slice(0, 100), inputs });
    });
    return out;
}"""


async def find_apply_page(agent, page, initial_ids):
    ctx = page.context
    apply_page = None
    for _ in range(20):
        await asyncio.sleep(0.75)
        if ctx:
            for p in ctx.pages:
                if id(p) not in initial_ids and ("smartapply" in (p.url or "") or "indeed.com/apply" in (p.url or "")):
                    apply_page = p
                    break
        if apply_page:
            break
        if "smartapply" in (page.url or ""):
            apply_page = page
            break
    return apply_page


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
            return
        target = easy[0]
        print(f"target: {target.get('title')} | jk={target.get('jk')}")
        if not await agent._indeed_open_card(page, target):
            print("card click failed")
            return
        await asyncio.sleep(3.0)
        await agent._indeed_dismiss_overlays(page)
        if not await agent._indeed_has_easy_apply(page):
            print("no easy apply control")
            return

        ctx = page.context
        initial_ids = {id(p) for p in ctx.pages} if ctx else {id(page)}
        if not await agent._indeed_click_apply_control(page):
            print("apply control click failed")
            return
        apply_page = await find_apply_page(agent, page, initial_ids)
        if apply_page is None:
            print("apply page not found")
            return
        try:
            await apply_page.bring_to_front()
        except Exception:
            pass
        await agent._indeed_apply_stealth(apply_page)
        print("apply url:", apply_page.url)

        # Wait for the questions page (/form/) and dismiss cookies.
        for _ in range(20):
            await agent._indeed_dismiss_smartapply_cookies(apply_page)
            if "/questions/" in (apply_page.url or "") or "/form/" in (apply_page.url or ""):
                break
            await asyncio.sleep(1.0)
        # Advance past the resume-selection module if that's where we are.
        if "resume-selection" in (apply_page.url or ""):
            for sel in ('button[data-testid="continue-button"]', 'button:has-text("Continue")'):
                loc = apply_page.locator(sel).first
                try:
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=8000)
                        await asyncio.sleep(3.0)
                        break
                except Exception:
                    continue
            for _ in range(15):
                await agent._indeed_dismiss_smartapply_cookies(apply_page)
                if "/questions/" in (apply_page.url or ""):
                    break
                await asyncio.sleep(1.0)

        print("questions url:", apply_page.url)
        before = await apply_page.evaluate(DUMP_JS)
        print("=== BEFORE answering ===")
        print(json.dumps(before, indent=2)[:5000])

        for t in [apply_page] + [f for f in apply_page.frames if f != apply_page.main_frame]:
            try:
                await agent._indeed_answer_questions(t)
            except Exception as e:
                print("answer exc:", e)

        after = await apply_page.evaluate(DUMP_JS)
        print("=== AFTER answering ===")
        print(json.dumps(after, indent=2)[:5000])

        # Try clicking Continue and see if the URL changes.
        for sel in (
            'button[data-testid="continue-button"]',
            'button:has-text("Continue")',
        ):
            loc = apply_page.locator(sel).first
            try:
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=8000)
                    break
            except Exception:
                continue
        await asyncio.sleep(4.0)
        print("url after continue:", apply_page.url)
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
