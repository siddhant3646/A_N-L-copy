"""Live DOM/flow inspection for Indeed and Hirist.

Launches Chrome with the seeded profile (CHROME_USER_DATA) and dumps the real
DOM structure, iframes, apply buttons and Next.js state needed to apply to jobs.
Use this to verify/refine the selectors used by:

  * SentinelAgent._handle_indeed_apply_task  (Indeed Apply, nested iframes)
  * SentinelAgent._handle_hirist_apply_task  (Hirist Next.js SPA)

Usage:
    python scripts/inspect_indeed_hirist_live.py            # both
    python scripts/inspect_indeed_hirist_live.py indeed     # Indeed only
    python scripts/inspect_indeed_hirist_live.py hirist     # Hirist only

Output: live_test_output/indeed_hirist/<platform>_inspection_<ts>.json
        live_test_output/indeed_hirist/screenshots/*.png
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA, RESUME_FILE_PATH
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

OUTPUT_DIR = Path("live_test_output/indeed_hirist")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

INDEED_SEARCH_URL = os.getenv(
    "INDEED_SEARCH_URL",
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bangalore%2C+Karnataka"
    "&sc=0kf%3Aattr(DSQF7)%3B",
)
HIRIST_FEED_URL = os.getenv("HIRIST_FEED_URL", "https://www.hirist.tech/jobfeed")


# ---------------------------------------------------------------------------
# Indeed extraction
# ---------------------------------------------------------------------------
INDEED_EXTRACT_JS = r"""() => {
    const out = {
        url: window.location.href,
        title: document.title,
        timestamp: new Date().toISOString(),
        cards: [],
        applyButtons: [],
        jobView: {},
        overlays: []
    };
    const seen = new Set();
    document.querySelectorAll(
        'div.cardOutline.tapItem.result, .job_seen_beacon, div[data-jk], li[data-jk]'
    ).forEach(card => {
        let jk = card.getAttribute('data-jk');
        if (!jk) { const i = card.querySelector('[data-jk]'); if (i) jk = i.getAttribute('data-jk'); }
        if (!jk || seen.has(jk)) return;
        seen.add(jk);
        const t = card.querySelector('h2.jobTitle a, h2.jobTitle span, a.jcs-JobTitle, h2 a');
        const c = card.querySelector('[data-testid="company-name"], .companyName');
        const l = card.querySelector('[data-testid="text-location"], .companyLocation');
        const s = card.querySelector('.salary-snippet-container, [data-testid="attribute_snippet_testid"]');
        out.cards.push({
            jk, title: t ? t.innerText.trim() : '',
            company: c ? c.innerText.trim() : '',
            location: l ? l.innerText.trim() : '',
            salary: s ? s.innerText.trim() : ''
        });
    });
    document.querySelectorAll('button, a').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        const aria = el.getAttribute('aria-label') || '';
        if (/apply/i.test(txt) || /apply/i.test(aria)) {
            out.applyButtons.push({
                tag: el.tagName, id: el.id, testid: el.getAttribute('data-testid'),
                text: txt.slice(0, 60), aria: aria.slice(0, 60),
                href: el.getAttribute('href') || '',
                visible: !!el.offsetParent
            });
        }
    });
    const jt = document.querySelector('[data-testid="vj-job-title"], h1.jobsearch-JobInfoHeader-title');
    if (jt) out.jobView.title = jt.innerText.trim();
    const jd = document.querySelector('#jobDescriptionText, [data-testid="viewjob-job-content"]');
    if (jd) out.jobView.descriptionLength = (jd.innerText || '').length;
    ['[data-testid="passport-intercept-type-modal"]', '#onetrust-banner-sdk',
     '.icl-Modal', '[role="dialog"]'].forEach(sel => {
        const el = document.querySelector(sel);
        if (el) out.overlays.push({ selector: sel, text: (el.innerText || '').trim().slice(0, 120) });
    });
    return out;
}"""

INDEED_FRAME_JS = r"""() => {
    const out = { url: location.href, title: document.title, ia: {}, questions: [] };
    ['#ia-container', '.ia-BasePage', '.ia-Questions', '.ia-continueButton',
     '.ia-submitButton', '.ia-Resume', 'form', 'input[type="file"]'].forEach(sel => {
        out.ia[sel] = document.querySelectorAll(sel).length;
    });
    document.querySelectorAll('.ia-TextQuestion, .ia-SelectQuestion, .ia-Question, fieldset').forEach(n => {
        const box = n.closest('.ia-question, fieldset, .ia-Question') || n;
        const lbl = box.querySelector('label, legend, .ia-label');
        out.questions.push({
            q: (lbl ? lbl.innerText : box.innerText || '').trim().slice(0, 100),
            hasInput: !!box.querySelector('input[type="text"], input[type="number"], textarea'),
            hasSelect: !!box.querySelector('select'),
            radios: box.querySelectorAll('input[type="radio"]').length,
            options: Array.from(box.querySelectorAll('option')).map(o => o.text.trim()).slice(0, 12)
        });
    });
    out.bodySnippet = (document.body ? document.body.innerText : '').slice(0, 600);
    return out;
}"""


# ---------------------------------------------------------------------------
# Hirist extraction
# ---------------------------------------------------------------------------
HIRIST_FEED_JS = r"""() => {
    const out = {
        url: window.location.href, title: document.title,
        timestamp: new Date().toISOString(),
        links: [], applyButtons: [], nextData: {}
    };
    const seen = new Set();
    document.querySelectorAll('a[href*="/j/"]').forEach(a => {
        const href = a.getAttribute('href') || '';
        const pos = href.indexOf('/j/');
        if (pos === -1) return;
        let tail = href.substring(pos + 3).split('?')[0].split('#')[0];
        const id = tail.split('/')[0];
        if (!id || seen.has(id)) return;
        seen.add(id);
        out.links.push({ id, href, title: (a.innerText || '').trim().slice(0, 80) });
    });
    document.querySelectorAll('button, a').forEach(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        if (/apply/i.test(txt)) {
            out.applyButtons.push({
                tag: el.tagName, text: txt.slice(0, 60),
                href: el.getAttribute('href') || '',
                cls: String(el.className).slice(0, 80),
                visible: !!el.offsetParent
            });
        }
    });
    try {
        const nd = window.__NEXT_DATA__;
        if (nd) {
            const pp = (nd.props && nd.props.pageProps) || {};
            out.nextData.topKeys = Object.keys(pp);
            out.nextData.auth = pp.initialState && pp.initialState.auth;
            out.nextData.job = pp.jobMandateInfo || pp.jobDetail || null;
        }
    } catch (e) { out.nextData.error = String(e); }
    return out;
}"""


async def inspect_indeed(page, agent):
    print("\n" + "=" * 60)
    print("🔎 INDEED INSPECTION")
    print("=" * 60)
    print(f"🔗 Navigating to Indeed search: {INDEED_SEARCH_URL}")
    await page.goto(INDEED_SEARCH_URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(5)
    await agent._indeed_dismiss_overlays(page)

    ts = int(time.time())
    await page.screenshot(path=str(SCREENSHOT_DIR / f"indeed_01_search_{ts}.png"))

    feed = await page.evaluate(INDEED_EXTRACT_JS)
    print(f"   Found {len(feed.get('cards', []))} cards, "
          f"{len(feed.get('applyButtons', []))} apply-like buttons")
    print(f"   Overlays: {feed.get('overlays')}")

    result = {"search": feed, "viewjob": None, "frames": []}

    cards = feed.get("cards", [])
    if cards:
        jk = cards[0]["jk"]
        view_url = f"https://in.indeed.com/viewjob?jk={jk}"
        print(f"➡️  Opening first job: {view_url}")
        await page.goto(view_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await agent._indeed_dismiss_overlays(page)
        await page.screenshot(path=str(SCREENSHOT_DIR / f"indeed_02_viewjob_{ts}.png"))

        result["viewjob"] = await page.evaluate(INDEED_EXTRACT_JS)
        has_easy = await agent._indeed_has_easy_apply(page)
        print(f"   Easy-apply detected: {has_easy}")

        if has_easy:
            print("▶️  Clicking apply and capturing apply frames...")
            try:
                clicked = False
                for sel in ("#indeedApplyButton", '[data-testid="viewjob-indeed-apply"]',
                            '[data-testid="primary-apply-action"]', 'button:has-text("Apply now")'):
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.click(timeout=8000)
                        clicked = True
                        break
                print(f"   Apply clicked: {clicked}")
                await asyncio.sleep(6)
            except Exception as e:
                print(f"   ⚠️ Apply click failed: {e}")

            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                info = {"url": frame.url, "name": frame.name}
                try:
                    info["dom"] = await frame.evaluate(INDEED_FRAME_JS)
                except Exception as e:
                    info["error"] = str(e)
                result["frames"].append(info)
                print(f"   🖼️ frame: {frame.url[:90]}")

            await page.screenshot(path=str(SCREENSHOT_DIR / f"indeed_03_apply_{ts}.png"))

    out = OUTPUT_DIR / f"indeed_inspection_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"📄 Saved: {out}")


async def inspect_hirist(page, agent):
    print("\n" + "=" * 60)
    print("🔎 HIRIST INSPECTION")
    print("=" * 60)
    print(f"🔗 Navigating to Hirist feed: {HIRIST_FEED_URL}")
    await page.goto(HIRIST_FEED_URL, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(6)
    await agent._hirist_dismiss_dialogs(page)

    ts = int(time.time())
    await page.screenshot(path=str(SCREENSHOT_DIR / f"hirist_01_feed_{ts}.png"))

    feed = await page.evaluate(HIRIST_FEED_JS)
    print(f"   Found {len(feed.get('links', []))} job links; "
          f"logged in: {feed.get('nextData', {}).get('auth')}")
    print(f"   Apply-like buttons on feed: {len(feed.get('applyButtons', []))}")

    result = {"feed": feed, "job": None}

    links = feed.get("links", [])
    if links:
        job_url = links[0]["href"]
        if job_url.startswith("/"):
            job_url = "https://www.hirist.tech" + job_url
        print(f"➡️  Opening first job: {job_url}")
        await page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._hirist_dismiss_dialogs(page)
        await page.screenshot(path=str(SCREENSHOT_DIR / f"hirist_02_job_{ts}.png"))

        result["job"] = await page.evaluate(HIRIST_FEED_JS)
        status = await agent._hirist_click_apply(page)
        print(f"   Apply click status: {status}")
        if status == "applied":
            await asyncio.sleep(3)
            await agent._hirist_confirm_modal(page)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"hirist_03_applied_{ts}.png"))
            result["verify_applied"] = await agent._hirist_verify_applied(page)

    out = OUTPUT_DIR / f"hirist_inspection_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"📄 Saved: {out}")


async def main():
    which = (sys.argv[1].lower() if len(sys.argv) > 1 else "both")
    print("🚀 Starting Indeed/Hirist live inspection")
    print(f"📁 Chrome User Data: {CHROME_USER_DATA}")
    print(f"📄 Resume path: {RESUME_FILE_PATH}")

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()

    try:
        print("🌐 Launching Chrome...")
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent.browser = browser

        if which in ("both", "indeed"):
            await inspect_indeed(page, agent)
        if which in ("both", "hirist"):
            await inspect_hirist(page, agent)
    except Exception as e:
        print(f"❌ Error during inspection: {e}")
        import traceback
        traceback.print_exc()
        try:
            if agent._page:
                await agent._page.screenshot(
                    path=str(SCREENSHOT_DIR / f"error_{int(time.time())}.png"))
        except Exception:
            pass
    finally:
        print("🔒 Closing browser session...")
        try:
            await browser.close()
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
