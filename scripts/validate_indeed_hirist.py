"""Side-effect-free live validation of the Indeed + Hirist handlers.

Indeed:  confirms `_indeed_has_easy_apply` now detects the in-site button and
         that clicking it surfaces a SmartApply page/iframe (NOSUBMIT here).
Hirist:  opens a real questionnaire, runs the new scanner + answer picker +
         filler (but never clicks Next/Submit), and prints the per-question
         decisions so we can verify them against the real DOM.

Usage:
    python scripts/validate_indeed_hirist.py both
    python scripts/validate_indeed_hirist.py indeed
    python scripts/validate_indeed_hirist.py hirist
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

INDEED_HOME = "https://in.indeed.com/?from=gnav-jobsearch--indeedmobile"
HIRIST_FEED = os.getenv("HIRIST_FEED_URL", "https://www.hirist.tech/jobfeed")


async def validate_indeed(agent, browser):
    page = await browser.get_current_page() or await browser.new_page()
    agent._page = page
    agent._current_platform = "indeed"

    print("\n" + "=" * 60)
    print("🔎 INDEED VALIDATION (search UI + card-click + apply-surface, no submit)")
    print("=" * 60)

    # Exercise the real handler path: home -> search -> Easily apply filter.
    explicit = (os.getenv("INDEED_SEARCH_URL") or "").strip()
    if explicit:
        await page.goto(explicit, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await agent._indeed_dismiss_overlays(page)
    else:
        seed = await agent._indeed_search_from_home(page)
        print(f"   search seeded: {seed}")
    filtered = await agent._indeed_apply_easily_filter(page)
    print(f"   'Easily apply' filter applied: {filtered}")

    jobs = await agent._indeed_collect_jobs(page)
    print(f"   Collected {len(jobs)} job cards ({sum(1 for j in jobs if j.get('easy'))} advertise easy-apply)")

    results = []
    for job in jobs:
        if len(results) >= 4:
            break
        jk = job.get("jk")
        if not jk:
            continue

        # Click the result card (sponsored '/pagead/clk' cards only reveal their
        # real apply surface when clicked — /viewjob?jk= silently redirects).
        opened = await agent._indeed_open_card(page, job)
        await asyncio.sleep(3)
        await agent._indeed_dismiss_overlays(page)

        has_easy = await agent._indeed_has_easy_apply(page)
        row = {"jk": jk, "title": job.get("title"), "opened": opened,
               "has_easy_apply": has_easy, "clicked": False,
               "new_tab": None, "apply_iframe": None}
        print(f"   [{jk}] {job.get('title')} → opened={opened} has_easy_apply={has_easy}")

        if has_easy:
            ctx = page.context
            before = {id(p) for p in ctx.pages} if ctx else {id(page)}
            clicked = await agent._indeed_click_apply_control(page)
            row["clicked"] = clicked
            print(f"        clicked={clicked}")

            if clicked:
                # Poll up to 15s for a new tab / apply URL / apply iframe.
                for _ in range(20):
                    await asyncio.sleep(0.75)
                    new_pages = [p for p in (ctx.pages if ctx else []) if id(p) not in before]
                    if new_pages:
                        row["new_tab"] = (new_pages[0].url or "")[:80]
                        break
                    if "smartapply" in (page.url or "") or "/apply" in (page.url or ""):
                        row["new_tab"] = (page.url or "")[:80]
                        break
                fr = await agent._indeed_wait_for_apply_frame(page, timeout=8)
                if fr is not None:
                    try:
                        row["apply_iframe"] = (fr.url or "")[:80] or "<frame>"
                    except Exception:
                        row["apply_iframe"] = "<frame>"
                print(f"        new_tab={row['new_tab']} apply_iframe={row['apply_iframe']}")

                # Close any tab we opened; DO NOT submit.
                if ctx:
                    for p in list(ctx.pages):
                        if id(p) not in before:
                            try:
                                await p.close()
                            except Exception:
                                pass
                if "smartapply" in (page.url or ""):
                    await page.go_back(wait_until="domcontentloaded")
                    await asyncio.sleep(1)

        results.append(row)
        await asyncio.sleep(1.5)

    out = OUT / f"validate_indeed_{int(time.time())}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"   📄 saved {out}")
    return results


async def validate_hirist(agent, browser):
    page = await browser.get_current_page() or await browser.new_page()
    agent._page = page
    agent._current_platform = "hirist"

    print("\n" + "=" * 60)
    print("🔎 HIRIST VALIDATION (scan + pick + fill, no submit)")
    print("=" * 60)
    await page.goto(HIRIST_FEED, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(5)
    await agent._hirist_dismiss_dialogs(page)

    jobs = await agent._hirist_collect_jobs(page)
    print(f"   Collected {len(jobs)} job links")

    captured = None
    for job in jobs[:10]:
        url = job.get("url")
        if not url:
            continue
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)
        await agent._hirist_dismiss_dialogs(page)
        status = await agent._hirist_click_apply(page)
        await asyncio.sleep(3)
        present = await agent._hirist_questionnaire_present(page)
        print(f"   {url.split('/')[-1][:52]} status={status} questionnaire={present}")
        if not present:
            continue

        questions = await agent._hirist_scan_questionnaire(page)
        print(f"      scanned {len(questions)} question(s)")
        decisions = []
        for q in questions:
            ans, conf = agent._fuzzy_match_question(q.get("question", ""))
            row = {"question": q.get("question"), "kind": q.get("kind"),
                   "answer": ans, "conf": round(conf, 3) if conf else conf,
                   "prefilled": q.get("prefilled")}
            if q.get("kind") == "single":
                texts = [o.get("text", "") for o in q.get("options", [])]
                pick = agent._hirist_pick_option(ans or "", texts, q.get("question", ""))
                row["options"] = texts
                row["picked"] = pick
            decisions.append(row)
            print(f"        • [{q.get('kind')}] {str(q.get('question'))[:80]}")
            print(f"            answer={ans!r} conf={conf}")
            if q.get("kind") == "single":
                print(f"            options={texts} → picked={pick!r}")

        filled = await agent._hirist_fill_questionnaire(page, questions)
        print(f"      filled {filled} field(s)")

        # Verify the DOM actually holds the values now.
        await asyncio.sleep(1)
        values = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('div.screening-question-container').forEach(c => {
                const ta = c.querySelector('textarea, input[type="text"], input[type="number"]');
                const pill = c.querySelector('button.pill-option.selected, button.pill-option[aria-pressed="true"]');
                const radio = c.querySelector('input[type="radio"]:checked');
                out.push({
                    text: ta ? ta.value : null,
                    pill: pill ? (pill.innerText || '').trim() : null,
                    radioChecked: !!radio
                });
            });
            return out;
        }""")
        captured = {"url": url, "decisions": decisions, "filled": filled, "values": values}
        break

    if captured:
        out = OUT / f"validate_hirist_{int(time.time())}.json"
        out.write_text(json.dumps(captured, indent=2), encoding="utf-8")
        print(f"   📄 saved {out}")
    else:
        print("   ❌ no questionnaire encountered")
    return captured


async def main():
    targets = sys.argv[1:] or ["both"]
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        if "indeed" in targets or "both" in targets:
            await validate_indeed(agent, browser)
        if "hirist" in targets or "both" in targets:
            await validate_hirist(agent, browser)
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
