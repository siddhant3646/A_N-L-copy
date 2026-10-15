"""Dump the Indeed detail pane for a job whose search card shows 'Easily apply'.

Pinpoints why ``_indeed_has_easy_apply`` returns False for in-site jobs.
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

SEED = "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka"

PICK_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const cards = Array.from(document.querySelectorAll('.job_seen_beacon'));
    for (const c of cards) {
        const t = norm(c.innerText || c.textContent || '');
        if (!/easily apply/.test(t)) continue;
        const jkEl = c.querySelector('[data-jk]') || (c.hasAttribute('data-jk') ? c : null);
        const jk = jkEl ? jkEl.getAttribute('data-jk') : (c.getAttribute('data-jk') || '');
        const titleEl = c.querySelector('h2.jobTitle a, h2.jobTitle span, a.jcs-JobTitle, h2 a');
        return { jk: String(jk || ''), title: titleEl ? titleEl.innerText.trim() : '' };
    }
    return { jk: '', title: '' };
}"""

DUMP_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const vis = n => !!(n && n.getClientRects().length);
    const panes = {
        '#jobsearch-ViewjobPaneWrapper': !!document.querySelector('#jobsearch-ViewjobPaneWrapper'),
        '#viewJobSSRRoot': !!document.querySelector('#viewJobSSRRoot'),
        '[data-testid=jobsearch-JobComponent]': !!document.querySelector('[data-testid="jobsearch-JobComponent"]'),
        '.jobsearch-JobComponent': !!document.querySelector('.jobsearch-JobComponent'),
        '#jobsearch-ViewJobPaneDeferredHeader': !!document.querySelector('#jobsearch-ViewJobPaneDeferredHeader')
    };
    const applyish = [];
    document.querySelectorAll('button, a, [role="button"], [data-testid]').forEach(n => {
        const txt = norm(n.innerText || n.textContent || '');
        const tid = n.getAttribute('data-testid') || '';
        const al = n.getAttribute('aria-label') || '';
        if (/apply/i.test(txt) || /apply/i.test(tid) || /apply/i.test(al)) {
            applyish.push({
                tag: n.tagName,
                text: txt.slice(0, 45),
                testid: tid,
                aria: al.slice(0, 40),
                href: (n.getAttribute('href') || '').slice(0, 70),
                visible: vis(n),
                cls: (typeof n.className === 'string' ? n.className : '').slice(0, 50),
                inCard: !!n.closest('[data-jk], #mosaic-provider-jobcards, .job_seen_beacon')
            });
        }
    });
    const sr = (document.querySelector('#viewJobSSRRoot') || {});
    const panePath = (() => {
        const p = document.querySelector('#jobsearch-ViewjobPaneWrapper');
        if (!p) return 'NO PANE';
        return p.outerHTML.slice(0, 600);
    })();
    return { url: location.href, panes, applyish, panePath };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)

        picked = await page.evaluate(PICK_JS)
        print("PICKED:", picked)
        jk = picked.get("jk")
        if not jk:
            print("!! no easily-apply card found")
            return

        await page.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await agent._indeed_dismiss_overlays(page)
        await asyncio.sleep(1)

        dump = await page.evaluate(DUMP_JS)
        print("URL:", dump["url"][:140])
        print("PANES:", json.dumps(dump["panes"], indent=2))
        print("APPLYISH:")
        for a in dump["applyish"]:
            print("   ", json.dumps(a))
        print("PANE PATH:", dump["panePath"][:400])

        det = await agent._indeed_has_easy_apply(page)
        print("AGENT _indeed_has_easy_apply ->", det)

        f = OUT / f"probe_indeed_detail_dump_{int(time.time())}.json"
        f.write_text(json.dumps({"picked": picked, "dump": dump, "detected": det}, indent=2), encoding="utf-8")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
