"""Live diagnostic for the Indeed and Hirist task handlers.

Captures the real DOM needed to validate/refine:
  * Indeed  -> where the "Easily apply" surface lands (new tab vs iframe vs same tab)
  * Hirist  -> the actual screening-questionnaire DOM ("Submit a Form")

This script does NOT submit any Indeed application. For Hirist it clicks Apply
(which may auto-apply on jobs without a questionnaire), but never clicks a
questionnaire Submit. It stops early once enough evidence is gathered.

Usage:
    python scripts/diagnose_platforms.py both
    python scripts/diagnose_platforms.py indeed
    python scripts/diagnose_platforms.py hirist
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

INDEED_SEARCH_URL = os.getenv(
    "INDEED_SEARCH_URL",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka&sc=0kf%3Aattr(DSQF7)%3B",
)
HIRIST_FEED_URL = os.getenv("HIRIST_FEED_URL", "https://www.hirist.tech/jobfeed")

DUMP_APPLY_JS = r"""() => {
    const out = [];
    document.querySelectorAll('button, a, div[role="button"]').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        const aria = el.getAttribute('aria-label') || '';
        if (/apply/i.test(txt) || /apply/i.test(aria)) {
            out.push({
                tag: el.tagName, id: el.id, testid: el.getAttribute('data-testid'),
                text: txt.slice(0, 60), aria: aria.slice(0, 60), href: el.getAttribute('href') || '',
                visible: !!(el.offsetParent || el.offsetWidth),
            });
        }
    });
    return out;
}"""

DUMP_FORM_JS = r"""() => {
    const vis = el => !!(el.offsetParent || el.offsetWidth || el.offsetHeight);
    const labelOf = el => {
        const l = el.closest('label') || (el.id && document.querySelector('label[for="' + el.id + '"]'));
        return l ? (l.innerText || '').trim().slice(0, 80) : '';
    };
    return {
        textareas: Array.from(document.querySelectorAll('textarea')).map(t => ({
            placeholder: t.placeholder, value: t.value, cls: String(t.className).slice(0, 80), visible: vis(t)
        })),
        textInputs: Array.from(document.querySelectorAll('input[type="text"], input[type="number"]')).map(i => ({
            placeholder: i.placeholder, value: i.value, name: i.name, visible: vis(i)
        })),
        radios: Array.from(document.querySelectorAll('input[type="radio"]')).map(r => ({
            name: r.name, value: r.value, checked: r.checked, label: labelOf(r), visible: vis(r)
        })),
        selects: Array.from(document.querySelectorAll('select')).map(s => ({
            name: s.name, value: s.value,
            options: Array.from(s.options).map(o => (o.text || '').trim()).slice(0, 15), visible: vis(s)
        })),
        buttons: Array.from(document.querySelectorAll('button')).map(b => ({
            text: (b.innerText || '').trim().slice(0, 40), disabled: b.disabled,
            cls: String(b.className).slice(0, 60), visible: vis(b)
        })).filter(b => b.visible),
        dialogs: Array.from(document.querySelectorAll('div[role="dialog"], .MuiDialog-root')).map(d => ({
            text: (d.innerText || '').replace(/\s+/g, ' ').slice(0, 300), visible: vis(d)
        })),
        bodyText: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 1500),
    };
}"""


async def diag_indeed(page, agent):
    print("\n" + "=" * 60)
    print("🔎 INDEED DIAGNOSTIC")
    print("=" * 60)
    await page.goto(INDEED_SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await agent._indeed_dismiss_overlays(page)

    logged_in = await agent._indeed_is_logged_in(page)
    print(f"   Logged in: {logged_in}")

    jobs = await agent._indeed_collect_jobs(page)
    print(f"   Collected {len(jobs)} job cards")

    records = []
    for job in jobs[:8]:
        jk = job.get("jk")
        title = job.get("title")
        view = f"https://in.indeed.com/viewjob?jk={jk}"
        await page.goto(view, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.5)
        await agent._indeed_dismiss_overlays(page)
        has_easy = await agent._indeed_has_easy_apply(page)
        apply_btns = await page.evaluate(DUMP_APPLY_JS)
        rec = {"jk": jk, "title": title, "has_easy": has_easy, "apply_buttons": apply_btns}
        print(f"   [{jk}] has_easy={has_easy} | {title}")
        for b in apply_btns[:4]:
            print(f"        btn tag={b['tag']} id={b['id']} testid={b['testid']} text={b['text']!r} href={b['href'][:40]!r}")

        if has_easy:
            pre_ids = {id(p) for p in page.context.pages}
            clicked = False
            for sel in ("#indeedApplyButton", '[data-testid="viewjob-indeed-apply"]',
                        '[data-testid="primary-apply-action"]', 'a:has-text("Apply now")'):
                loc = page.locator(sel).first
                try:
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(timeout=8000)
                        clicked = True
                        break
                except Exception:
                    continue
            await asyncio.sleep(6)
            new_pages = [p.url for p in page.context.pages if id(p) not in pre_ids]
            frames = [f.url for f in page.frames if f != page.main_frame]
            for p in page.context.pages:
                if id(p) in pre_ids:
                    continue
                for f in p.frames:
                    if f != p.main_frame:
                        frames.append(f"{p.url[:30]}:: {f.url}")
            rec.update({
                "clicked_apply": clicked,
                "new_tabs": new_pages,
                "frames_after_click": frames,
                "same_tab_url_after": page.url,
            })
            print(f"        clicked={clicked} new_tabs={new_pages} same_tab_url={page.url[:70]}")
            for u in frames:
                print(f"        frame: {u[:100]}")
            for p in list(page.context.pages):
                if id(p) not in pre_ids:
                    try:
                        await p.close()
                    except Exception:
                        pass
        records.append(rec)

    out = OUT / f"indeed_diag_{int(time.time())}.json"
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"   📄 saved {out}")
    return records


async def diag_hirist(page, agent):
    print("\n" + "=" * 60)
    print("🔎 HIRIST DIAGNOSTIC")
    print("=" * 60)
    await page.goto(HIRIST_FEED_URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(5)
    await agent._hirist_dismiss_dialogs(page)

    meta = await agent._hirist_read_meta(page)
    print(f"   Logged in: {meta.get('isLoggedIn')}")

    jobs = await agent._hirist_collect_jobs(page)
    print(f"   Collected {len(jobs)} job links")

    records = []
    questionnaire_found = 0
    for job in jobs[:8]:
        url = job.get("url")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)
        await agent._hirist_dismiss_dialogs(page)

        info = await agent._hirist_read_meta(page)
        title = info.get("jobTitle") or job.get("title")
        apply_btns = await page.evaluate(DUMP_APPLY_JS)
        rec = {"url": url, "title": title, "isLoggedIn": info.get("isLoggedIn"),
               "apply_buttons": apply_btns}

        status = await agent._hirist_click_apply(page)
        rec["click_status"] = status
        await asyncio.sleep(3)

        present = await agent._hirist_questionnaire_present(page)
        rec["questionnaire_present"] = present
        if present:
            questionnaire_found += 1
            rec["form"] = await page.evaluate(DUMP_FORM_JS)

        print(f"   {title} | status={status} questionnaire={present}")

        records.append(rec)
        out = OUT / f"hirist_diag_{int(time.time())}.json"
        out.write_text(json.dumps(records, indent=2), encoding="utf-8")

        if present:
            print("      --- QUESTIONNAIRE FORM DUMP ---")
            f = rec["form"]
            print(f"      textareas={json.dumps(f['textareas'])[:400]}")
            print(f"      textInputs={json.dumps(f['textInputs'])[:400]}")
            print(f"      radios={json.dumps(f['radios'])[:600]}")
            print(f"      selects={json.dumps(f['selects'])[:400]}")
            print(f"      buttons={json.dumps(f['buttons'])[:500]}")
            print(f"      dialogs={json.dumps(f['dialogs'])[:500]}")

        if questionnaire_found >= 2:
            print("   ✅ Captured 2 questionnaires — stopping Hirist diag.")
            break

    out = OUT / f"hirist_diag_{int(time.time())}.json"
    out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"   📄 saved {out}")
    return records


async def main():
    which = (sys.argv[1].lower() if len(sys.argv) > 1 else "both")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent.browser = browser
        if which in ("both", "indeed"):
            try:
                await diag_indeed(page, agent)
            except Exception as e:
                print(f"❌ Indeed diag error: {e}")
                import traceback
                traceback.print_exc()
        if which in ("both", "hirist"):
            try:
                await diag_hirist(page, agent)
            except Exception as e:
                print(f"❌ Hirist diag error: {e}")
                import traceback
                traceback.print_exc()
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
