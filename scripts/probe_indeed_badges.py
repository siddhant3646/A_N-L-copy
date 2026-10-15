"""Clean per-card 'Easily apply' badge survey across many Indeed India queries.

Counts .job_seen_beacon cards whose OWN text advertises an in-site apply
affordance (excluding the shared filter pill, which lives outside cards).
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
    "https://in.indeed.com/jobs?q=Java+Developer&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=software+engineer&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=data+entry&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=customer+support&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=sales&l=Bengaluru%2C+Karnataka",
    "https://in.indeed.com/jobs?q=developer&l=India",
    "https://in.indeed.com/jobs?q=software",
]

SCAN_JS = r"""() => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const cards = Array.from(document.querySelectorAll('.job_seen_beacon'));
    let badge = 0;
    const samples = [];
    cards.forEach(c => {
        const t = norm(c.innerText || c.textContent || '');
        const isEasy = /easily apply/.test(t);
        if (isEasy) badge++;
        if (samples.length < 2) samples.push({ easy: isEasy, text: t.slice(0, 150) });
    });
    return {
        url: location.href,
        cards: cards.length,
        badge: badge,
        samples: samples,
    };
}"""


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    try:
        await browser.start()
        page = await browser.get_current_page() or await browser.new_page()

        results = []
        for url in QUERIES:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4.5)
                data = await page.evaluate(SCAN_JS)
                data["seed"] = url
                results.append(data)
                print(f"\n{url}")
                print(f"   cards={data['cards']} easilyApplyBadges={data['badge']}")
                for s in data["samples"]:
                    print(f"     {'EASY' if s['easy'] else 'ext '} {s['text'][:90]!r}")
            except Exception as e:
                print(f"\n{url} -> ERROR {e}")
                results.append({"seed": url, "error": str(e)})

        f = OUT / f"probe_indeed_badges_{int(time.time())}.json"
        f.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n📄 saved {f}")
        print("\nSUMMARY (cards / easilyApplyBadges):")
        for r in results:
            print(f"   {r.get('cards', '?')} / {r.get('badge', '?')}   {r.get('seed', '')[:80]}")
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
