"""Dump the live Indeed SmartApply DOM at each step.

Loads the search, opens the first in-site ("Easily apply") job, clicks the
apply control and then walks the SmartApply wizard, dumping the visible buttons
and form fields at every stage. Read-only with respect to submissions: it never
clicks the final submit button.
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

SEED = os.getenv("PROBE_SEED", "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka")

DUMP_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const vis = n => !!(n && n.getClientRects().length);
    const buttons = Array.from(document.querySelectorAll('button, a[role="button"], [role="button"], input[type="submit"]'))
        .filter(vis).slice(0, 80).map(b => ({
            tag: b.tagName,
            testid: b.getAttribute('data-testid') || '',
            text: norm(b.innerText || b.textContent || b.value || '').slice(0, 70),
            disabled: !!b.disabled,
            aria: b.getAttribute('aria-label') || ''
        }));
    const fields = Array.from(document.querySelectorAll('input, select, textarea'))
        .filter(vis).slice(0, 80).map(f => ({
            tag: f.tagName,
            type: f.type || '',
            testid: f.getAttribute('data-testid') || '',
            name: f.name || '',
            id: f.id || '',
            aria: f.getAttribute('aria-label') || '',
            value: (f.value || '').slice(0, 50)
        }));
    const questions = Array.from(document.querySelectorAll(
        'fieldset, .ia-Question, .ia-question, [data-testid*="question"], [data-testid*="Question"]'
    )).filter(vis).slice(0, 40).map(q => norm(q.innerText || '').slice(0, 260));
    const modals = Array.from(document.querySelectorAll('[role="dialog"], .ia-Modal, [data-testid*="modal"]'))
        .filter(vis).slice(0, 5).map(m => norm(m.innerText || '').slice(0, 300));
    const checks = Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')).slice(0, 20).map(c => {
        const l = c.closest('label') || (c.id ? document.querySelector('label[for="' + c.id + '"]') : null);
        return { id: c.id || '', checked: !!c.checked, vis: vis(c), testid: c.getAttribute('data-testid') || '',
                 label: norm((l ? l.innerText : '') || c.getAttribute('aria-label') || '').slice(0, 140) };
    });
    const alerts = Array.from(document.querySelectorAll('[role="alert"], [aria-live], .ia-Alert, [data-testid*="alert"]'))
        .filter(vis).slice(0, 8).map(a => norm(a.innerText || '').slice(0, 200));
    const iframes = Array.from(document.querySelectorAll('iframe')).map(f => {
        const r = f.getBoundingClientRect();
        return { src: (f.src || '').slice(0, 90), vis: vis(f), w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) };
    });
    const bodyTxt = document.body ? document.body.innerText : '';
    const kw = ['captcha', 'verify', 'robot', 'required', 'complete this', 'before you can', 'something went wrong', 'try again', 'please ', 'must be', 'not ready'].filter(k => new RegExp(k, 'i').test(bodyTxt));
    const sub = document.querySelector('button[data-testid="submit-application-button"]');
    const submitInfo = sub ? {
        disabled: sub.disabled,
        ariaDisabled: sub.getAttribute('aria-disabled'),
        title: sub.getAttribute('title') || '',
        cls: sub.className,
        parentText: norm(sub.parentElement ? sub.parentElement.innerText : '').slice(0, 200)
    } : null;
    return {
        url: location.href,
        bodyText: norm(document.body ? document.body.innerText : '').slice(0, 2500),
        buttons, fields, questions, modals, checks, submitInfo, iframes, kw, alerts
    };
}"""


async def dump(page, tag):
    info = await page.evaluate(DUMP_JS)
    print(f"\n--- [{tag}] {info['url'][:95]}")
    print(f"    body: {info['bodyText'][:220]!r}")
    print("    buttons:")
    for b in info["buttons"][:25]:
        print(f"      - testid={b['testid']!r:32} disabled={b['disabled']!s:5} text={b['text'][:45]!r}")
    if info["fields"]:
        print("    fields:")
        for f in info["fields"][:25]:
            print(f"      - {f['tag']}/{f['type']:10} testid={f['testid']!r:26} name={f['name'][:18]!r} val={f['value'][:22]!r}")
    if info["questions"]:
        print("    questions:")
        for q in info["questions"][:12]:
            print(f"      - {q[:100]!r}")
    if info["modals"]:
        print("    modals:", [m[:90] for m in info["modals"]])
    if info.get("checks"):
        print("    checkboxes:")
        for c in info["checks"]:
            print(f"      - id={c['id']!r:10} vis={c['vis']!s:5} checked={c['checked']!s:5} label={c['label'][:90]!r}")
    if info.get("submitInfo"):
        print(f"    submitInfo: {json.dumps(info['submitInfo'])[:400]}")
    if info.get("iframes"):
        print("    iframes:")
        for f in info["iframes"]:
            print(f"      - vis={f['vis']!s:5} {f['w']}x{f['h']} @({f['x']},{f['y']}) {f['src'][:70]!r}")
    if info.get("kw"):
        print("    keyword-hits:", info["kw"])
    if info.get("alerts"):
        print("    alerts:", [a[:120] for a in info["alerts"]])
    return info


CLICK_PRIORITY = [
    'button[data-testid="submit-application-button"]:not([data-testid^="hp-"])',
    'button[data-testid="continue-button"]:not([data-testid^="hp-"])',
    'button[data-testid="to-review-button"]:not([data-testid^="hp-"])',
    'button:text-is("Continue"):not([data-testid^="hp-"])',
    'button:text-is("Next"):not([data-testid^="hp-"])',
    'button:has-text("Review your application"):not([data-testid^="hp-"])',
    'button:has-text("Review application"):not([data-testid^="hp-"])',
    'button:text-is("Review"):not([data-testid^="hp-"])',
]


async def click_advance(page, frames):
    for target in [page] + frames:
        for sel in CLICK_PRIORITY:
            try:
                loc = target.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    txt = (await loc.inner_text() or '').strip()
                    dis = await loc.is_disabled()
                    print(f"    -> candidate {sel!r} text={txt!r} disabled={dis}")
                    if not dis:
                        await loc.scroll_into_view_if_needed()
                        await loc.click(timeout=8000)
                        print(f"    -> CLICKED {sel!r}")
                        return txt
            except Exception as e:
                print(f"    -> click error {sel!r}: {e}")
    return None


async def diagnose_submit(page):
    nav = await page.evaluate("() => ({ webdriver: navigator.webdriver, chrome: !!window.chrome })")
    print("    DIAG nav:", nav)
    rc = await page.evaluate("""() => {
        const ifr = Array.from(document.querySelectorAll('iframe')).map(f => f.src || '').filter(s => /recaptcha|captcha/i.test(s));
        return { hasGrecaptcha: !!window.grecaptcha, recaptchaIframes: ifr };
    }""")
    print("    DIAG recaptcha:", json.dumps(rc)[:320])

    def _rc_texts():
        out = {}
        for fr in page.frames:
            u = fr.url or ""
            if "recaptcha" in u:
                key = "anchor" if "/anchor" in u else ("bframe" if "/bframe" in u else "other")
                out.setdefault(key, []).append(u[:60])
        return out

    print("    DIAG rc-frames before:", json.dumps(_rc_texts()))

    # Real mouse click on the SmartApply reCAPTCHA checkbox (main-column anchor,
    # NOT the global bottom-right badge). Opt-in via PROBE_RC_CLICK.
    if os.getenv("PROBE_RC_CLICK") == "1":
        boxes = await page.evaluate("""() => Array.from(document.querySelectorAll('iframe'))
            .filter(f => (f.src || '').includes('recaptcha/enterprise/anchor'))
            .map(f => { const r = f.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })""")
        print("    DIAG rc anchor boxes:", json.dumps(boxes)[:300])
        target = next((b for b in boxes if b["x"] < 1000 and 150 < b["w"] < 500), None)
        if target:
            cx = target["x"] + 30
            cy = target["y"] + 30
            print(f"    DIAG real-click rc checkbox at ({cx:.0f},{cy:.0f})")
            await page.mouse.move(cx - 50, cy - 30, steps=8)
            await asyncio.sleep(0.2)
            await page.mouse.move(cx, cy, steps=6)
            await asyncio.sleep(0.15)
            await page.mouse.click(cx, cy)
        await asyncio.sleep(4)

    texts = {}
    for fr in page.frames:
        if "recaptcha" in (fr.url or ""):
            key = "bframe" if "/bframe" in fr.url else "anchor"
            try:
                texts[key] = (await fr.evaluate("() => (document.body?document.body.innerText:'').slice(0,180)"))
            except Exception as e:
                texts[key] = f"<err {e}>"
    print("    DIAG rc texts after:", json.dumps(texts)[:400])

    st = await page.evaluate("""() => {
        const b = document.querySelector('button[data-testid="submit-application-button"]');
        return b ? { disabled: b.disabled } : null;
    }""")
    print("    DIAG submit after real rc click:", st)
    return rc, st


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    result = {"steps": []}
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        nav = await page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            plugins: navigator.plugins.length,
            languages: navigator.languages,
            chrome: !!window.chrome,
            ua: navigator.userAgent,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory
        })""")
        print("NAV:", json.dumps(nav))
        await agent._indeed_dismiss_overlays(page)

        # Open the first in-site card (retry: the results grid sometimes hydrates late).
        jobs, easy = [], []
        for attempt in range(6):
            jobs = await agent._indeed_collect_jobs(page)
            easy = [j for j in jobs if j.get("easy")]
            print(f"attempt {attempt}: url={(page.url or '')[:70]} jobs={len(jobs)} easy={len(easy)}")
            if jobs:
                break
            await asyncio.sleep(4)
        if not jobs:
            print("!! no job cards found; body:", (await page.evaluate("() => (document.body?document.body.innerText:'').slice(0,400)")))
            return
        # Prefer a non-sponsored in-site job (href "/rc/clk") — sponsored
        # ("/pagead/clk") ads sometimes route to a dead SmartApply.
        non_ad = [j for j in easy if "/pagead/" not in (j.get("href") or "")]
        target = (non_ad or easy or jobs)[0]
        print(f"non_ad_in_site={len(non_ad)} / easy={len(easy)}")
        print(f"opening: {target.get('title')!r} jk={target.get('jk')}")
        await agent._indeed_open_card(page, target)
        await asyncio.sleep(3.5)
        await agent._indeed_dismiss_overlays(page)

        det = await agent._indeed_has_easy_apply(page)
        print(f"detected in-site: {det}")
        result["detected"] = det

        initial_ids = {id(p) for p in page.context.pages}
        if not await agent._indeed_click_apply_control(page):
            print("!! no apply control clicked")
            return

        apply_page = page
        for _ in range(24):
            await asyncio.sleep(0.75)
            new = [p for p in page.context.pages if id(p) not in initial_ids]
            if new:
                apply_page = new[0]
                break
            if "smartapply" in (page.url or "") or "/form/" in (page.url or ""):
                break
        await asyncio.sleep(3)
        try:
            await apply_page.bring_to_front()
        except Exception:
            pass
        print(f"apply_page url: {(apply_page.url or '')[:90]}")

        logs = []
        try:
            apply_page.on('console', lambda m: logs.append(f"console.{m.type}: {m.text[:200]}"))
            apply_page.on('pageerror', lambda e: logs.append(f"pageerror: {str(e)[:200]}"))
            apply_page.on('requestfailed', lambda r: logs.append(f"reqfail: {(r.url or '')[:120]} :: {r.failure}"))
        except Exception:
            pass

        diag_done = False
        for step in range(16):
            await asyncio.sleep(2.5)
            await agent._indeed_dismiss_smartapply_cookies(apply_page)
            frames = [f for f in apply_page.frames if f != apply_page.main_frame]
            info = await dump(apply_page, f"step-{step}")
            result["steps"].append(info)
            try:
                await apply_page.screenshot(path=str(OUT / f"review_step{step}.png"), full_page=True)
            except Exception as _e:
                print("    screenshot err:", str(_e)[:80])
            for fr in apply_page.frames:
                if fr == apply_page.main_frame:
                    continue
                try:
                    t = await fr.evaluate("() => (document.body?document.body.innerText:'').slice(0,1800)")
                except Exception as e:
                    t = f"<err {str(e)[:60]}>"
                try:
                    fb = await fr.evaluate("""() => Array.from(document.querySelectorAll('button, a, input, [role="button"]')).map(b => ({
                        tag: b.tagName, testid: b.getAttribute('data-testid') || '', type: b.getAttribute('type') || '',
                        text: (b.innerText || b.value || '').trim().slice(0, 50), disabled: !!b.disabled }))
                        .filter(b => /submit|review|next|continue|apply/i.test(b.text) || /submit/i.test(b.testid))""")
                except Exception as e:
                    fb = f"<err {str(e)[:60]}>"
                if fr.url == "about:srcdoc" or t.strip():
                    print(f"    frame {fr.url[:55]!r}: text={t[:120]!r}")
                if isinstance(fb, list):
                    for b in fb:
                        print(f"        ctrl tag={b['tag']!r:8} testid={b['testid']!r:30} disabled={b['disabled']!s:5} text={b['text'][:36]!r}")
            if await agent._indeed_is_submitted(apply_page):
                print("   ✅ SUBMITTED")
                result["submitted"] = True
                break
            # stop before the final submit
            sub = next((b for b in info["buttons"] if b["testid"] == "submit-application-button"), None)
            if sub:
                if sub["disabled"]:
                    print("   .. submit button present but DISABLED; waiting")
                    if not diag_done:
                        diag_done = True
                        await diagnose_submit(apply_page)
                    continue
                print("   ⏸ reached review/submit — stopping before submit")
                if os.getenv("PROBE_SUBMIT") == "1":
                    print("   ▶ waiting for submit result")
                    clicked_real = False
                    for i in range(24):
                        await asyncio.sleep(1.5)
                        if await agent._indeed_is_submitted(apply_page):
                            print("   ✅ SUBMITTED")
                            result["submitted"] = True
                            break
                        if i == 3 and not clicked_real:
                            clicked_real = True
                            try:
                                loc = apply_page.locator('button[data-testid="submit-application-button"]').first
                                if await loc.count() > 0 and not await loc.is_disabled():
                                    await loc.click(force=True, timeout=5000)
                                    print("   ▶ real force-click done")
                            except Exception as e:
                                print("   real click err:", str(e)[:120])
                        if i % 4 == 0:
                            try:
                                b = await apply_page.evaluate("() => (document.body?document.body.innerText:'').slice(0,160)")
                            except Exception:
                                b = ''
                            print(f"   [{i}] url={(apply_page.url or '')[:68]} body={b[:80]!r}")
                    print("   final body:", (await apply_page.evaluate("() => (document.body?document.body.innerText:'').slice(0,300)")))
                break
            clicked = await click_advance(apply_page, frames)
            if not clicked:
                u = apply_page.url or ""
                if "review-module" in u or "applybyapplyablejobid" in u or "/form/" in u or "loading" in info["bodyText"][:40].lower():
                    print("   .. page still loading; waiting")
                    continue
                print("   !! no advance control found — stopping")
                break

        f = OUT / f"probe_indeed_smartapply_{int(time.time())}.json"
        result["logs"] = logs[-60:]
        f.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
        if logs:
            print("   console/network logs:")
            for ln in logs[-30:]:
                print("    -", ln[:160])
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
