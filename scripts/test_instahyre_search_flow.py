"""Live test of Instahyre search button click and skill search API parameters."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

OUTPUT_DIR = Path("live_test_output/instahyre_skills")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Testing Instahyre Search Flow & API Parameters with Skills...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()

    api_calls = []

    async def on_response(response):
        url = response.url
        if 'candidate_matching' in url or 'opportunities' in url or 'job' in url:
            if 'api' in url:
                try:
                    data = await response.json()
                    total = data.get('meta', {}).get('total_count', len(data.get('objects', [])))
                    objects_count = len(data.get('objects', []))
                    api_calls.append({
                        "url": url,
                        "status": response.status,
                        "total_count": total,
                        "objects_count": objects_count,
                        "sample_titles": [obj.get('job', {}).get('title') or obj.get('title') for obj in data.get('objects', [])[:3]]
                    })
                    print(f"📡 API Result: count={objects_count} (total={total}) | URL: {url[:100]}")
                except Exception:
                    pass

    page.on("response", on_response)

    url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    print(f"🔗 Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(6)

    # Check how many jobs initially before entering skills
    initial_cards = await page.evaluate("() => document.querySelectorAll('.job-card, [class*=\"opportunity-card\"], .employer-row').length")
    print(f"Initial job cards in DOM: {initial_cards}")

    # Now let's test adding 'Java' into selectize
    print("\n1️⃣ Adding 'Java' into selectize and clicking Search...")
    search_res_1 = await page.evaluate("""() => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (!el || !window.$) return { error: "no el" };
        const sel = window.$(el)[0]?.selectize;
        if (!sel) return { error: "no sel" };

        sel.clear();
        sel.addOption({ name: 'Java', id: 3911, name_nopunc: ',java,' });
        sel.addItem('Java');

        const btn = document.querySelector('button.skills-search-btn') ||
                    document.querySelector('button#show-results') ||
                    document.querySelector('button[ng-click*="search"]');
        if (btn) {
            btn.click();
            return { clicked: true, btnText: btn.innerText.trim() };
        }
        return { clicked: false, btn: null };
    }""")
    print("Action 1 (Java):", json.dumps(search_res_1, indent=2))
    await asyncio.sleep(5)

    cards_after_java = await page.evaluate("() => document.querySelectorAll('.job-card, [class*=\"opportunity-card\"], .employer-row').length")
    print(f"Job cards after 'Java': {cards_after_java}")

    # Now let's test adding 15 skills like Sentinel was doing
    skills_15 = ["Java", "Java 17", "Java 21", "Core Java", "JVM", "Python", "JavaScript", "TypeScript", "Docker", "Kubernetes", "AWS", "Git", "Linux", "CI/CD", "DevOps"]
    print(f"\n2️⃣ Adding 15 skills into selectize and clicking Search: {skills_15}...")
    search_res_15 = await page.evaluate("""(skills) => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (!el || !window.$) return { error: "no el" };
        const sel = window.$(el)[0]?.selectize;
        if (!sel) return { error: "no sel" };

        sel.clear();
        for (const s of skills) {
            sel.addOption({ name: s, name_nopunc: ',' + s.toLowerCase() + ',' });
            sel.addItem(s);
        }

        const btn = document.querySelector('button.skills-search-btn') ||
                    document.querySelector('button#show-results') ||
                    document.querySelector('button[ng-click*="search"]');
        if (btn) {
            btn.click();
            return { clicked: true, items: sel.items };
        }
        return { clicked: false, items: sel.items };
    }""", skills_15)
    print("Action 2 (15 skills):", json.dumps(search_res_15, indent=2))
    await asyncio.sleep(5)

    cards_after_15 = await page.evaluate("""() => {
        const cards = document.querySelectorAll('.job-card, [class*="opportunity-card"], .employer-row');
        const bodyText = document.body ? document.body.innerText : '';
        return {
            count: cards.length,
            hasNoOpp: bodyText.includes('No matching opportunities found') || bodyText.includes('no opportunities found')
        };
    }""")
    print(f"Job cards after 15 skills:", json.dumps(cards_after_15, indent=2))

    # Save details
    out = OUTPUT_DIR / f"search_flow_result_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "api_calls": api_calls,
            "cards_after_java": cards_after_java,
            "cards_after_15": cards_after_15
        }, f, indent=2)
    print(f"\n💾 Saved search flow results to {out}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
