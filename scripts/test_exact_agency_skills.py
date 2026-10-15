"""Discover exact Instahyre agency_skill autocomplete tags."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()
    await page.goto("https://www.instahyre.com/candidate/opportunities/?matching=true", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    queries = [
        "spring", "kafka", "mongo", "postgre", "sql", "git", "cloud", "data", "develop", "engineer",
        "react", "node", "java", "python", "test", "docker", "kube", "micro", "web", "api",
        "c++", "cpp", "c#", "csharp", "ai", "ml", "machine", "deep", "learn", "manage"
    ]

    results = await page.evaluate("""async (queries) => {
        const out = {};
        for (const q of queries) {
            try {
                const resp = await fetch('/api/v1/job_form/agency_skill?skills=' + encodeURIComponent(q));
                if (resp.ok) {
                    const data = await resp.json();
                    out[q] = data.map(item => ({
                        id: item.id,
                        name: item.name,
                        slug: item.slug
                    }));
                }
            } catch (e) {
                out[q] = { error: String(e) };
            }
        }
        return out;
    }""", queries)

    print("\n🏷️ Autocomplete Tags Sample:")
    for q, items in list(results.items())[:15]:
        if isinstance(items, list):
            print(f"  Query '{q}' ({len(items)}): {[x['name'] for x in items[:5]]}")

    # Now take all unique skill names from these results and query job_search for each
    all_names = set()
    for items in results.values():
        if isinstance(items, list):
            for x in items:
                all_names.add(x["name"])

    print(f"\n📊 Querying job count for {len(all_names)} exact official Instahyre skill names...")
    name_list = list(all_names)
    counts = await page.evaluate("""async (names) => {
        const out = {};
        for (const n of names) {
            try {
                const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(n));
                if (resp.ok) {
                    const data = await resp.json();
                    out[n] = data.meta ? data.meta.total_count : (data.objects ? data.objects.length : 0);
                } else {
                    out[n] = 0;
                }
            } catch (e) {
                out[n] = 0;
            }
        }
        return out;
    }""", name_list)

    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    print("\n🔥 Top Discovered Skills by Job Count:")
    for n, c in sorted_counts[:30]:
        print(f"  {n:<32}: {c} jobs")

    # Save to file
    with open("live_test_output/instahyre_skills/exact_agency_skills_tested.json", "w", encoding="utf-8") as f:
        json.dump(sorted_counts, f, indent=2)

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
