"""For a sponsored ("/pagead/clk") Indeed card, test how to reach the real job.

Compares navigating to the card's own href vs clicking the card, and reports
the detail-pane title + agent detection for each.
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

CARDS_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const out = [];
    document.querySelectorAll('.job_seen_beacon').forEach((c, i) => {
        if (i >= 12) return;
        const link = c.querySelector('h2.jobTitle a, a.jcs-JobTitle, h2 a, a[href*="jk="]');
        const t = norm(c.innerText || c.textContent || '');
        const jkEl = c.querySelector('[data-jk]') || (c.hasAttribute('data-jk') ? c : null);
        out.push({
            idx: i,
            jk: String(jkEl ? (jkEl.getAttribute('data-jk') || '') : (c.getAttribute('data-jk') || '')),
            title: link ? norm(link.innerText || '') : '',
            href: link ? (link.getAttribute('href') || '') : '',
            easy: /easily apply/i.test(t)
        });
    });
    return out;
}"""

PANE_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const pane = document.querySelector('#jobsearch-ViewjobPaneWrapper') || document.querySelector('#viewJobSSRRoot') || document.body;
    const h = pane.querySelector('h1') || document.querySelector('[data-testid="jobsearch-JobInfoHeader-title"]');
    const comp = pane.querySelector('[data-testid="inlineHeader-companyName"], .jobsearch-CompanyInfoContainer a');
    let act = '';
    const a = pane.querySelector('[data-testid="viewjob-indeed-apply"], a[href*="applystart"], a[href*="smartapply"]');
    if (a) act = norm(a.innerText || '') + ' | ' + (a.getAttribute('href') || '').slice(0, 55);
    return { title: h ? norm(h.innerText || '') : '', company: comp ? norm(comp.innerText || '') : '', apply: act, url: location.href };
}"""


async def sample(page, agent, tag):
    await agent._indeed_dismiss_overlays(page)
    info = await page.evaluate(PANE_JS)
    det = await agent._indeed_has_easy_apply(page)
    print(f"   [{tag}] url={info['url'][:85]}")
    print(f"          title={info['title'][:50]!r} company={info['company'][:30]!r} det={det}")
    print(f"          apply={info['apply'][:75]!r}")
    return {"tag": tag, **info, "det": det}


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    agent = SentinelAgent()
    out = {}
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()
        agent._page = page
        agent._current_platform = "indeed"

        await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        await agent._indeed_dismiss_overlays(page)
        cards = await page.evaluate(CARDS_JS)
        for c in cards[:8]:
            print(f"  [{c['idx']}] easy={c['easy']} href={c['href'][:50]!r} title={c['title'][:38]!r}")

        pagead = next((c for c in cards if c["easy"] and "/pagead/" in c["href"]), None)
        viewjob = next((c for c in cards if c["easy"] and "/viewjob" in c["href"]), None)
        rclk = next((c for c in cards if c["easy"] and "/rc/clk" in c["href"]), None)
        target = pagead or rclk or viewjob
        print(f"\nTARGET: easy={target['easy'] if target else None} href={target['href'][:45] if target else None!r}")

        if target:
            print("\n=== TEST A: goto card href ===")
            href = target["href"]
            full = href if href.startswith("http") else "https://in.indeed.com" + href
            await page.goto(full, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            out["goto_href"] = await sample(page, agent, "goto-href")

            print("\n=== TEST B: click card ===")
            await page.goto(SEED, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(5)
            await agent._indeed_dismiss_overlays(page)
            card = page.locator(".job_seen_beacon").nth(target["idx"])
            link = card.locator("h2.jobTitle a, a.jcs-JobTitle, h2 a").first
            await link.click(timeout=8000)
            await asyncio.sleep(4)
            out["click"] = await sample(page, agent, "click")

            print("\n=== TEST C: goto viewjob?jk= ===")
            await page.goto(f"https://in.indeed.com/viewjob?jk={target['jk']}", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            out["goto_jk"] = await sample(page, agent, "goto-jk")

        f = OUT / f"probe_indeed_reach_{int(time.time())}.json"
        f.write_text(json.dumps({"cards": cards, "results": out}, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
