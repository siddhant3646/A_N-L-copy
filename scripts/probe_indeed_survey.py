"""Survey Indeed for in-site ('Easily apply') jobs across several queries/domains.

For each query reports: number of job cards, how many cards advertise an
in-site apply affordance, and the outerHTML of the 'Easily apply' filter control
(which reveals the authoritative facet attributes/URL).
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright


OUT = Path("live_test_output/diagnose")
OUT.mkdir(parents=True, exist_ok=True)

QUERIES = [
    ("in", "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka"),
    ("in", "https://in.indeed.com/jobs?q=software+engineer&l=Bengaluru%2C+Karnataka"),
    ("in", "https://in.indeed.com/jobs?q=data+entry&l=Bengaluru%2C+Karnataka"),
    ("in", "https://in.indeed.com/jobs?q=developer&l=Remote"),
    ("us", "https://www.indeed.com/jobs?q=software+engineer&l=New+York%2C+NY"),
]

SURVEY_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const cards = document.querySelectorAll('div.cardOutline.tapItem.result, .job_seen_beacon, div[data-jk]');
    let badge = 0;
    let sampleText = '';
    cards.forEach((c, i) => {
        const t = norm(c.innerText || c.textContent || '');
        if (/easily apply|apply with indeed|apply now/.test(t)) badge++;
        if (i === 0) sampleText = t.slice(0, 180);
    });
    let filterHtml = '';
    document.querySelectorAll('button, a, label, [role="button"]').forEach(n => {
        const t = norm(n.innerText || n.textContent || '');
        if (!filterHtml && t.includes('easily apply')) {
            filterHtml = n.outerHTML.slice(0, 400);
        }
    });
    return {
        url: location.href,
        cardCount: cards.length,
        badgeCount: badge,
        sampleText: sampleText,
        filterHtml: filterHtml
    };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()

        results = []
        for tag, url in QUERIES:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4.5)
                data = await page.evaluate(SURVEY_JS)
                data["tag"] = tag
                data["seed"] = url
                results.append(data)
                print(f"\n[{tag}] {url}")
                print(f"   final: {data['url'][:110]}")
                print(f"   cards={data['cardCount']} badge={data['badgeCount']}")
                print(f"   sample: {data['sampleText'][:110]!r}")
                print(f"   filter: {data['filterHtml'][:220]!r}")
            except Exception as e:
                print(f"\n[{tag}] {url} -> ERROR {e}")
                results.append({"tag": tag, "seed": url, "error": str(e)})

        f = OUT / f"probe_indeed_survey_{int(time.time())}.json"
        f.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
        print("\nSUMMARY (cards / badges):")
        for r in results:
            print(f"   {r.get('cardCount', '?')} / {r.get('badgeCount', '?')}   {r.get('seed', '')[:80]}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
