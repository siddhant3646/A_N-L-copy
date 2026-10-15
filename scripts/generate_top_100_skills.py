"""Comprehensive script to discover official Instahyre skills,
benchmark their job search counts, and rank the top 100 skills with maximum results.
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

OUTPUT_DIR = Path("live_test_output/instahyre_skills")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Starting Complete Instahyre Top 100 Skills Discovery & Live Benchmark...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()
    url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    print(f"🔗 Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    # Keywords to harvest official skills across all domains
    harvest_roots = [
        # Common tech keywords
        "java", "python", "script", "react", "node", "angular", "vue", "spring", "cloud", "aws",
        "azure", "google", "docker", "kube", "sql", "data", "web", "api", "micro", "test",
        "linux", "git", "ci", "devops", "design", "manage", "product", "net", "c++", "c#",
        "go", "rust", "kotlin", "swift", "php", "ruby", "spark", "kafka", "mongo", "redis",
        "elastic", "oracle", "mobile", "android", "ios", "ai", "machine", "learn", "deep",
        "security", "lead", "architect", "engineer", "stack", "front", "back", "ops",
        "server", "infra", "auto", "agile", "scrum", "qa", "nlp", "vision", "bi", "etl"
    ]

    print(f"🌾 Harvesting official skills from {len(harvest_roots)} root terms...")

    harvested_skills = await page.evaluate("""async (roots) => {
        const skillsMap = {};
        for (const root of roots) {
            try {
                const resp = await fetch('/api/v1/job_form/agency_skill?skills=' + encodeURIComponent(root));
                if (resp.ok) {
                    const data = await resp.json();
                    const list = data.objects || (Array.isArray(data) ? data : []);
                    for (const item of list) {
                        if (item.name && !skillsMap[item.name]) {
                            skillsMap[item.name] = {
                                id: item.id,
                                name: item.name,
                                slug: item.slug
                            };
                        }
                    }
                }
            } catch (e) {}
        }
        return Object.values(skillsMap);
    }""", harvest_roots)

    print(f"✅ Harvested {len(harvested_skills)} unique official Instahyre skills!")

    # Add core industry names directly if not already present
    core_names = [
        "Java", "Python", "JavaScript", "TypeScript", "React", "React.js", "Node.js", "Spring Boot",
        "Microservices", "AWS", "Amazon Web Services", "Microsoft Azure", "Azure", "GCP", "Google Cloud",
        "Docker", "Kubernetes", "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Apache Kafka", "Kafka",
        "CI/CD", "DevOps", "Linux", "Git", "System Design", "Distributed Systems", "Machine Learning",
        "Data Science", "Artificial Intelligence", "Deep Learning", "HTML5", "CSS3", "RESTful APIs",
        "Product Management", "Agile", "Scrum", "Jira", "Jenkins", "Terraform", "Ansible", "Selenium",
        "C++", "C#", "Golang", "Go", "Android", "iOS", "Flutter", "React Native", "PHP", "Ruby on Rails"
    ]

    existing_names = {s["name"].lower() for s in harvested_skills}
    for cn in core_names:
        if cn.lower() not in existing_names:
            harvested_skills.append({"name": cn, "id": None, "slug": cn.lower()})

    print(f"📊 Querying live job search counts for {len(harvested_skills)} skills...")

    # Query in batches to avoid overwhelming the browser
    batch_size = 30
    all_counted_skills = []

    for i in range(0, len(harvested_skills), batch_size):
        batch = harvested_skills[i:i + batch_size]
        batch_names = [s["name"] for s in batch]
        print(f"   Querying batch {i // batch_size + 1}/{(len(harvested_skills) + batch_size - 1) // batch_size} ({len(batch_names)} skills)...")

        batch_counts = await page.evaluate("""async (names) => {
            const out = [];
            for (const name of names) {
                try {
                    const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(name));
                    let count = 0;
                    if (resp.ok) {
                        const data = await resp.json();
                        count = data.meta ? data.meta.total_count : (data.objects ? data.objects.length : 0);
                    }
                    out.push({ name: name, jobCount: count });
                } catch (e) {
                    out.push({ name: name, jobCount: 0 });
                }
            }
            return out;
        }""", batch_names)

        all_counted_skills.extend(batch_counts)
        await asyncio.sleep(0.5)

    # Sort descending by jobCount
    all_counted_skills.sort(key=lambda x: x["jobCount"], reverse=True)

    # Filter out exact duplicates
    seen_final = set()
    unique_ranked = []
    for s in all_counted_skills:
        k = s["name"].lower().strip()
        if k not in seen_final:
            seen_final.add(k)
            unique_ranked.append(s)

    top_100 = unique_ranked[:100]

    print("\n" + "=" * 60)
    print("🏆 TOP 100 INSTAHYRE SKILLS BY MAXIMUM SEARCH RESULTS:")
    print("=" * 60)
    for rank, s in enumerate(top_100, 1):
        print(f"  {rank:3d}. {s['name']:<35} : {s['jobCount']:4d} jobs")

    # Save to JSON
    out_file = OUTPUT_DIR / "top_100_skills_ranked.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(top_100, f, indent=2)
    print(f"\n💾 Saved Top 100 skills to {out_file}")

    # Now run a live UI verification: enter the top 8 language + 7 tool skills in the UI
    print("\n🖥️ Performing Live UI Verification with Top 15 Ranked Skills...")
    top_15_names = [s["name"] for s in top_100[:15]]
    print(f"Top 15 Skills for UI test: {top_15_names}")

    ui_test = await page.evaluate("""(skills) => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (!el || !window.$) return { error: "no selectize" };
        const sel = window.$(el)[0]?.selectize;
        if (!sel) return { error: "no selectize" };

        sel.clear();
        for (const s of skills) {
            sel.addOption({ name: s, name_nopunc: ',' + s.toLowerCase() + ',' });
            sel.addItem(s);
        }

        const btn = document.querySelector('button.skills-search-btn') ||
                    document.querySelector('button#show-results') ||
                    document.querySelector('button[ng-click*="search"]');
        if (btn) {
            btn.scrollIntoView({ block: 'center' });
            btn.click();
            return { clicked: true, items: sel.items };
        }
        return { clicked: false };
    }""", top_15_names)
    print("UI Action:", json.dumps(ui_test, indent=2))
    await asyncio.sleep(6)

    # Capture live screenshot
    shot_path = OUTPUT_DIR / "instahyre_top_15_live_search.png"
    await page.screenshot(path=str(shot_path), full_page=False)
    print(f"📸 Live UI Search Screenshot saved: {shot_path}")

    cards_count = await page.evaluate("() => document.querySelectorAll('.job-card, [class*=\"opportunity-card\"], .employer-row').length")
    print(f"✅ Total Live Job Cards Rendered in DOM: {cards_count}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
