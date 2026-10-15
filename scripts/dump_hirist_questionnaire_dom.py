"""Dump the real DOM hierarchy of a Hirist inline questionnaire.

Clicking "Apply" on a Hirist job with screening questions opens an inline
"Submit a Form" panel. The page auto-marks the job applied but the questionnaire
itself is NOT submitted (the Next button stays disabled until required fields are
answered). This script opens such a questionnaire and dumps the HTML structure
so we can build accurate, resilient selectors.

Usage:
    python scripts/dump_hirist_questionnaire_dom.py
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

HIRIST_FEED_URL = os.getenv("HIRIST_FEED_URL", "https://www.hirist.tech/jobfeed")


HIERARCHY_JS = r"""() => {
    const path = el => {
        const parts = [];
        let n = el;
        for (let i = 0; i < 6 && n && n.tagName; i++) {
            let s = n.tagName.toLowerCase();
            if (n.id) s += '#' + n.id;
            const cls = (n.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 3);
            if (cls.length) s += '.' + cls.join('.');
            parts.unshift(s);
            n = n.parentElement;
        }
        return parts.join(' > ');
    };
    const questionFor = el => {
        // Walk up; whichever ancestor first exposes a question-like text node.
        let n = el;
        for (let i = 0; i < 8 && n; i++) {
            // preceding sibling text
            let sib = n.previousElementSibling;
            let hops = 0;
            while (sib && hops < 3) {
                const t = (sib.innerText || '').trim();
                if (t && (t.includes('?') || t.length > 12)) return t.slice(0, 160);
                sib = sib.previousElementSibling;
                hops++;
            }
            n = n.parentElement;
        }
        return '';
    };

    const textareas = Array.from(document.querySelectorAll('textarea')).map(t => ({
        question: questionFor(t),
        path: path(t),
        cls: String(t.className),
        placeholder: t.placeholder,
    }));
    const radiosByName = {};
    Array.from(document.querySelectorAll('input[type="radio"]')).forEach(r => {
        const nm = r.name || '(noname)';
        if (!radiosByName[nm]) {
            const l = r.closest('label') || (r.id && document.querySelector('label[for="' + r.id + '"]'));
            radiosByName[nm] = {
                question: questionFor(r),
                path: path(r.parentElement),
                options: [],
            };
        }
        const l = r.closest('label') || (r.id && document.querySelector('label[for="' + r.id + '"]'));
        radiosByName[nm].options.push({ value: r.value, label: l ? (l.innerText || '').trim() : '' });
    });

    // Find the smallest element that contains the form heading.
    let best = null;
    document.querySelectorAll('div, section, form, main').forEach(el => {
        const t = el.innerText || '';
        if (t.includes('Submit a Form') || t.includes('Mandatory Question') || t.includes('characters left')) {
            if (!best || t.length < (best.innerText || '').length) best = el;
        }
    });
    let html = '';
    let bestPath = '';
    if (best) {
        // climb two parents to include the submit button
        let root = best;
        for (let i = 0; i < 2 && root.parentElement; i++) root = root.parentElement;
        bestPath = path(root);
        html = root.outerHTML || '';
        if (html.length > 60000) html = html.slice(0, 60000);
    }

    const pills = Array.from(document.querySelectorAll('button')).filter(b =>
        /pill-option/i.test(String(b.className))
    ).map(b => ({ text: (b.innerText || '').trim(), cls: String(b.className), path: path(b) }));

    return { textareas, radioGroups: radiosByName, pills, bestPath, html };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    result = None
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent.browser = browser

        await page.goto(HIRIST_FEED_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._hirist_dismiss_dialogs(page)
        jobs = await agent._hirist_collect_jobs(page)
        print(f"Collected {len(jobs)} job links")

        for job in jobs[:12]:
            url = job.get("url")
            if not url:
                continue
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            await agent._hirist_dismiss_dialogs(page)
            status = await agent._hirist_click_apply(page)
            await asyncio.sleep(3)
            present = await agent._hirist_questionnaire_present(page)
            print(f"  {url.split('/')[-1][:50]} status={status} questionnaire={present}")
            if present:
                result = await page.evaluate(HIERARCHY_JS)
                break

        if not result:
            print("❌ No questionnaire encountered in the sampled jobs.")
            return

        out = OUT / f"hirist_dom_{int(time.time())}.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"📄 saved {out}")
        print("\n--- TEXTAREAS ---")
        print(json.dumps(result["textareas"], indent=2))
        print("\n--- RADIO GROUPS ---")
        print(json.dumps(result["radioGroups"], indent=2))
        print("\n--- PILLS ---")
        print(json.dumps(result["pills"], indent=2))
        print("\n--- BEST CONTAINER PATH ---")
        print(result["bestPath"])
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
