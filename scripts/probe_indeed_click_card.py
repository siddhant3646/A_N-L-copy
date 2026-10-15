"""Click an in-site Indeed card (like a user) and inspect the detail pane.

Confirms whether clicking loads a job with a real 'Easily apply' control, and
whether the agent's detection then succeeds.
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

SEED = "https://in.indeed.com/jobs?q=customer+support&l=Bengaluru%2C+Karnataka"

CARDS_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const out = [];
    document.querySelectorAll('.job_seen_beacon').forEach((c, i) => {
        if (i >= 10) return;
        const link = c.querySelector('h2.jobTitle a, a.jcs-JobTitle, h2 a, a[href*="jk="]');
        const t = norm(c.innerText || c.textContent || '');
        out.push({
            idx: i,
            title: link ? norm(link.innerText || '') : '',
            href: link ? (link.getAttribute('href') || '').slice(0, 80) : '',
            easy: /easily apply/i.test(t),
            text: t.slice(0, 120)
        });
    });
    return out;
}"""

PANE_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const vis = n => !!(n && n.getClientRects().length);
    const pane = document.querySelector('#jobsearch-ViewjobPaneWrapper') || document.querySelector('#viewJobSSRRoot') || document.body;
    const h = pane.querySelector('h1') || document.querySelector('[data-testid="jobsearch-JobInfoHeader-title"]');
    const applies = [];
    pane.querySelectorAll('button, a, [role="button"]').forEach(n => {
        const t = norm(n.innerText || '');
        const tid = n.getAttribute('data-testid') || '';
        if ((/apply/i.test(t) || /apply/i.test(tid)) && vis(n)) {
            applies.push({ tag: n.tagName, text: t.slice(0, 40), testid: tid,
                           href: (n.getAttribute('href') || '').slice(0, 70),
                           inCard: !!n.closest('[data-jk], .job_seen_beacon') });
        }
    });
    return {
        title: h ? norm(h.innerText || '') : '',
        applies,
        url: location.href
    };
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

        cards = await page.evaluate(CARDS_JS)
        print("CARDS:")
        target = None
        for c in cards:
            print(f"  [{c['idx']}] easy={c['easy']} href={c['href'][:45]!r}")
            print(f"        title={c['title'][:45]!r} text={c['text'][:80]!r}")
            if target is None and c["easy"] and "/pagead/" not in c["href"]:
                target = c
        if target is None:
            for c in cards:
                if c["easy"]:
                    target = c
                    break
        print(f"\nTARGET: {target}")

        if target is not None:
            card = page.locator(".job_seen_beacon").nth(target["idx"])
            link = card.locator("h2.jobTitle a, a.jcs-JobTitle, h2 a").first
            try:
                await link.click(timeout=8000)
            except Exception as e:
                print(f"   click link failed: {e}; trying card")
                try:
                    await card.click(timeout=8000)
                except Exception as e2:
                    print(f"   card click failed too: {e2}")
            await asyncio.sleep(4)
            await agent._indeed_dismiss_overlays(page)
            info = await page.evaluate(PANE_JS)
            print("\nPANE AFTER CLICK:")
            print(f"   url={info['url'][:110]}")
            print(f"   title={info['title'][:60]!r}")
            for a in info["applies"]:
                print(f"     {json.dumps(a)}")
            det = await agent._indeed_has_easy_apply(page)
            print(f"   AGENT detection -> {det}")

        f = OUT / f"probe_indeed_click_card_{int(time.time())}.json"
        f.write_text(json.dumps({"cards": cards, "target": target}, indent=2), encoding="utf-8")
        print(f"📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
