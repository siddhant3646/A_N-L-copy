"""Map Indeed card jk/href -> job actually loaded by viewjob?jk=.

Determines whether _indeed_collect_jobs yields usable job keys.
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

CARD_META_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const out = [];
    document.querySelectorAll('.job_seen_beacon').forEach((c, i) => {
        if (i >= 8) return;
        const jkEl = c.querySelector('[data-jk]') || (c.hasAttribute('data-jk') ? c : null);
        const jk = jkEl ? jkEl.getAttribute('data-jk') : (c.getAttribute('data-jk') || '');
        const link = c.querySelector('h2.jobTitle a, a.jcs-JobTitle, h2 a, a[href*="jk="]');
        out.push({
            idx: i,
            jk: String(jk || ''),
            title: link ? norm(link.innerText || '') : '',
            href: link ? (link.getAttribute('href') || '').slice(0, 90) : '',
            easy: /easily apply/.test(norm(c.innerText || c.textContent || ''))
        });
    });
    return out;
}"""

TITLE_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const el = document.querySelector('#jobsearch-ViewjobPaneWrapper h1, #jobsearch-ViewjobPaneWrapper h2, [data-testid="jobsearch-JobInfoHeader-title"]');
    const t = el ? norm(el.innerText || el.textContent || '') : '';
    let act = '';
    const a = document.querySelector('#jobsearch-ViewjobPaneWrapper [data-testid="viewjob-apply"], #jobsearch-ViewjobPaneWrapper a[href*="applystart"]');
    if (a) act = norm(a.innerText || '');
    const insite = Array.from(document.querySelectorAll('#jobsearch-ViewjobPaneWrapper button, #jobsearch-ViewjobPaneWrapper a'))
        .filter(n => /easily apply/i.test(norm(n.innerText || '')) && n.getClientRects().length)
        .filter(n => !n.closest('#mosaic-provider-jobcards, .job_seen_beacon'))
        .length;
    return { title: t.slice(0, 70), applyText: act.slice(0, 40), inSiteButtons: insite, href: location.href };
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

        meta = await page.evaluate(CARD_META_JS)
        print("CARDS:")
        for m in meta:
            print(f"  [{m['idx']}] easy={m['easy']} jk={m['jk']} href={m['href'][:60]!r} title={m['title'][:45]!r}")

        collected = await agent._indeed_collect_jobs(page)
        print(f"\n_indeed_collect_jobs -> {len(collected)}")
        for j in collected[:8]:
            print(f"  jk={j['jk']} title={j['title'][:45]!r}")

        print("\nNAVIGATE viewjob?jk= for first 6 collected:")
        for j in collected[:6]:
            jk = j["jk"]
            await page.goto(f"https://in.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3.2)
            await agent._indeed_dismiss_overlays(page)
            info = await page.evaluate(TITLE_JS)
            det = await agent._indeed_has_easy_apply(page)
            same = jk in (info.get("href") or "")
            print(f"  req jk={jk} cardTitle={j['title'][:30]!r}")
            print(f"     -> loaded={info['title'][:45]!r} applyText={info['applyText'][:25]!r} inSiteBtns={info['inSiteButtons']} det={det} jkPreserved={same}")

        f = OUT / f"probe_indeed_jk_map_{int(time.time())}.json"
        f.write_text(json.dumps({"meta": meta, "collected": collected}, indent=2), encoding="utf-8")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
