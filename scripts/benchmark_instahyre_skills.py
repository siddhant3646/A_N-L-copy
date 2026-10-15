"""Comprehensive live benchmark of Instahyre skills and search results.

Harvests official Instahyre skills, tests job count for each,
evaluates filter impacts, and produces the top 100 skills by job count.
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
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Starting Comprehensive Instahyre Skill Benchmark...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()

    url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    print(f"🔗 Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    # 1. Candidate skill candidates to test across all tech disciplines
    # Seed list covering Languages, Frameworks, Cloud, DevOps, DBs, Architecture, AI/ML, Tools
    seed_queries = [
        # Programming Languages
        "Java", "Python", "JavaScript", "TypeScript", "C++", "C#", "Golang", "Go", "Ruby", "PHP",
        "Swift", "Kotlin", "Scala", "Rust", "Dart", "R", "Perl", "Shell", "Bash", "C",
        # Frontend
        "React", "React.js", "ReactJS", "Angular", "AngularJS", "Vue.js", "Vue", "Next.js", "Nuxt.js",
        "HTML", "HTML5", "CSS", "CSS3", "Sass", "Tailwind CSS", "Bootstrap", "Redux", "GraphQL", "jQuery",
        "Webpack", "Front End Development", "UI Development", "Web Development",
        # Backend Frameworks
        "Spring Boot", "Spring", "Spring MVC", "Node.js", "NodeJS", "Express.js", "Django", "FastAPI",
        "Flask", "Hibernate", "Microservices", "RESTful APIs", "REST API", "NestJS", "Ruby on Rails",
        "ASP.NET", ".NET", ".NET Core", "Laravel", "Dropwizard", "Kafka", "Apache Kafka", "RabbitMQ",
        # Databases & Caching
        "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "Oracle", "Cassandra",
        "DynamoDB", "NoSQL", "MS SQL Server", "SQLite", "MariaDB", "Couchbase", "Memcached",
        # Cloud & DevOps
        "AWS", "Amazon Web Services", "Azure", "Microsoft Azure", "GCP", "Google Cloud",
        "Docker", "Kubernetes", "CI/CD", "Jenkins", "Terraform", "Ansible", "Linux", "Git",
        "GitHub", "GitLab", "DevOps", "Helm", "Cloud Computing", "Serverless",
        # Architecture & Engineering
        "System Design", "Distributed Systems", "Object Oriented Programming", "OOP",
        "Data Structures", "Algorithms", "Backend Development", "Full Stack Development",
        "Software Engineering", "API Development",
        # Data & AI / ML
        "Machine Learning", "Data Science", "Artificial Intelligence", "Deep Learning",
        "NLP", "Natural Language Processing", "Computer Vision", "PyTorch", "TensorFlow",
        "Pandas", "NumPy", "Scikit-Learn", "Data Analysis", "Big Data", "Spark", "Apache Spark",
        "Hadoop", "Airflow", "ETL", "Data Engineering", "Power BI", "Tableau",
        # Testing & QA
        "Selenium", "Automation Testing", "Manual Testing", "JUnit", "Cypress", "Postman",
        "QA", "Test Automation", "JMeter", "Appium",
        # Mobile
        "Android", "iOS", "React Native", "Flutter",
        # Security & Management
        "Cyber Security", "Information Security", "Network Security",
        "Agile", "Scrum", "Jira", "Product Management"
    ]

    print(f"🔎 Testing {len(seed_queries)} tech skills directly against Instahyre search API...")

    # Run in batches via page.evaluate
    skill_results = await page.evaluate("""async (queries) => {
        const out = [];
        for (let i = 0; i < queries.length; i++) {
            const skill = queries[i];
            try {
                // 1. Check autocomplete to see if skill is officially recognized
                const acResp = await fetch('/api/v1/job_form/agency_skill?skills=' + encodeURIComponent(skill));
                let matchedName = skill;
                let recognized = false;
                if (acResp.ok) {
                    const acData = await acResp.json();
                    if (acData && acData.length > 0) {
                        recognized = true;
                        matchedName = acData[0].name;
                    }
                }

                // 2. Query job search with the skill
                const searchResp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(matchedName));
                let count = 0;
                if (searchResp.ok) {
                    const sData = await searchResp.json();
                    count = sData.meta ? sData.meta.total_count : (sData.objects ? sData.objects.length : 0);
                }

                out.push({
                    query: skill,
                    matchedName: matchedName,
                    recognized: recognized,
                    jobCount: count
                });
            } catch (e) {
                out.push({
                    query: skill,
                    matchedName: skill,
                    recognized: false,
                    jobCount: 0,
                    error: String(e)
                });
            }
        }
        return out;
    }""", seed_queries)

    # Sort descending by job count
    sorted_skills = sorted(skill_results, key=lambda x: x["jobCount"], reverse=True)

    print("\n🏆 Top 25 Skills by Search Results:")
    for idx, s in enumerate(sorted_skills[:25], 1):
        print(f"  {idx:2d}. {s['matchedName']:<28} : {s['jobCount']:4d} jobs (Query: '{s['query']}')")

    # 2. Also harvest additional skills from autocomplete letters A-Z to discover more high-count skills
    print("\n🌾 Harvesting additional official Instahyre skills using A-Z prefixes...")
    harvested = await page.evaluate("""async () => {
        const letters = 'abcdefghijklmnopqrstuvwxyz'.split('');
        const seenNames = new Set();
        const skillList = [];

        for (const l of letters) {
            try {
                const resp = await fetch('/api/v1/job_form/agency_skill?skills=' + l);
                if (resp.ok) {
                    const data = await resp.json();
                    for (const item of data) {
                        if (item.name && !seenNames.has(item.name.toLowerCase())) {
                            seenNames.add(item.name.toLowerCase());
                            skillList.push(item.name);
                        }
                    }
                }
            } catch (e) {}
        }
        return skillList;
    }""")
    print(f"Found {len(harvested)} unique official skills from autocomplete!")

    # Test the harvested skills that weren't tested yet
    already_tested = {s["matchedName"].lower() for s in sorted_skills}
    new_to_test = [name for name in harvested if name.lower() not in already_tested][:100]

    if new_to_test:
        print(f"📊 Testing job counts for {len(new_to_test)} additional harvested skills...")
        additional_results = await page.evaluate("""async (names) => {
            const out = [];
            for (const name of names) {
                try {
                    const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(name));
                    let count = 0;
                    if (resp.ok) {
                        const sData = await resp.json();
                        count = sData.meta ? sData.meta.total_count : (sData.objects ? sData.objects.length : 0);
                    }
                    out.push({
                        query: name,
                        matchedName: name,
                        recognized: true,
                        jobCount: count
                    });
                } catch (e) {
                    out.push({ query: name, matchedName: name, recognized: true, jobCount: 0 });
                }
            }
            return out;
        }""", new_to_test)
        all_skills = sorted_skills + additional_results
    else:
        all_skills = sorted_skills

    # Deduplicate and sort
    final_dict = {}
    for s in all_skills:
        name = s["matchedName"]
        if name not in final_dict or final_dict[name]["jobCount"] < s["jobCount"]:
            final_dict[name] = s

    all_sorted = sorted(final_dict.values(), key=lambda x: x["jobCount"], reverse=True)
    top_100 = all_sorted[:100]

    # 3. Test filter effects: What happens when Company Size = Large vs All?
    print("\n🧪 Testing Filter Impact on Results:")
    filter_test = await page.evaluate("""async () => {
        const skill = "Java";
        const tests = [
            { name: "All Company Sizes (0)", url: '/api/v1/job_search?company_size=0&job_type=0&status=0&skills=Java' },
            { name: "Large Companies Only (2)", url: '/api/v1/job_search?company_size=2&job_type=0&status=0&skills=Java' },
            { name: "Medium Companies Only (1)", url: '/api/v1/job_search?company_size=1&job_type=0&status=0&skills=Java' },
            { name: "Small / Startup Companies (3)", url: '/api/v1/job_search?company_size=3&job_type=0&status=0&skills=Java' },
            { name: "With Location=Bangalore", url: '/api/v1/job_search?company_size=0&job_type=0&status=0&skills=Java&location=Bangalore' },
            { name: "Job Functions=All (no filter)", url: '/api/v1/job_search?company_size=0&job_type=0&status=0&skills=Java' },
            { name: "Job Function=Software Engineering (1)", url: '/api/v1/job_search?company_size=0&job_type=0&status=0&skills=Java&job_categories=1' }
        ];

        const out = [];
        for (const t of tests) {
            try {
                const resp = await fetch(t.url);
                if (resp.ok) {
                    const data = await resp.json();
                    out.push({
                        test: t.name,
                        jobCount: data.meta ? data.meta.total_count : 0
                    });
                }
            } catch (e) {
                out.push({ test: t.name, error: String(e) });
            }
        }
        return out;
    }""")
    for ft in filter_test:
        print(f"  • {ft.get('test')}: {ft.get('jobCount', 0)} jobs")

    # 4. Live Browser UI Test: Enter the top 5 skills in the UI and click Search
    print("\n🖥️ Performing Live Browser UI Test with top skills...")
    top_5_names = [s["matchedName"] for s in top_100[:5]]
    print(f"Entering in UI selectize: {top_5_names}")

    ui_result = await page.evaluate("""(skills) => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (!el || !window.$) return { error: "no selectize el" };
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
    }""", top_5_names)
    print("UI Action:", json.dumps(ui_result, indent=2))
    await asyncio.sleep(6)

    # Capture screenshot of live results
    ts = int(time.time())
    shot_path = SCREENSHOT_DIR / f"instahyre_top_skills_results_{ts}.png"
    await page.screenshot(path=str(shot_path), full_page=False)
    print(f"📸 Live screenshot saved: {shot_path}")

    ui_cards = await page.evaluate("""() => {
        const cards = document.querySelectorAll('.job-card, [class*="opportunity-card"], .employer-row');
        return Array.from(cards).slice(0, 5).map(c => {
            const title = c.querySelector('h3, h4, .job-title, [class*="title"]');
            const comp = c.querySelector('.company-name, .employer-name, [class*="company"]');
            return {
                title: title ? title.innerText.trim() : '<untitled>',
                company: comp ? comp.innerText.trim() : '<unknown>'
            };
        });
    }""")
    print("Sample Live Job Cards in DOM:", json.dumps(ui_cards, indent=2))

    # 5. Save comprehensive report
    report_file = OUTPUT_DIR / f"top_100_skills_{ts}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": ts,
            "filter_impact": filter_test,
            "top_100": top_100,
            "all_tested_count": len(all_sorted),
            "ui_sample_cards": ui_cards
        }, f, indent=2)
    print(f"\n💾 Full report saved to: {report_file}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
