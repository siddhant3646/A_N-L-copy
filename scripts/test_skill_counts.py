"""Quick verification of fetching job counts per skill via page.evaluate."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright


async def main():
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()
    await page.goto("https://www.instahyre.com/candidate/opportunities/?matching=true", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    test_skills = ["Java", "Python", "React", "Spring Boot", "AWS", "SQL", "Docker", "Node.js", "Kubernetes", "TypeScript"]

    results = await page.evaluate("""async (skills) => {
        const out = {};
        for (const s of skills) {
            try {
                const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&skills=' + encodeURIComponent(s) + '&status=0');
                if (resp.ok) {
                    const data = await resp.json();
                    out[s] = {
                        total_count: data.meta ? data.meta.total_count : (data.objects ? data.objects.length : 0),
                        status: resp.status
                    };
                } else {
                    out[s] = { error: resp.status };
                }
            } catch (e) {
                out[s] = { error: String(e) };
            }
        }
        return out;
    }""", test_skills)

    print("\n📊 Verification Results:")
    print(json.dumps(results, indent=2))

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
