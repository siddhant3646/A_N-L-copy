"""Clean, paced benchmark of Top 100 Tech & Software Engineering Skills on Instahyre."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

OUTPUT_DIR = Path("live_test_output/instahyre_skills")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Running Paced Benchmark for Top 100 Tech Skills on Instahyre...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()
    await page.goto("https://www.instahyre.com/candidate/opportunities/?matching=true", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)

    skills_to_test = [
        # Languages
        "Java", "Python", "JavaScript", "TypeScript", "Go", "Golang", "C++", "C#", "SQL",
        "Kotlin", "Scala", "Rust", "PHP", "Ruby", "Bash", "Shell", "Swift", "Dart", "R", "Perl",
        # Backend & Architecture
        "Spring Boot", "Spring", "Spring MVC", "Node.js", "Express.js", "Microservices",
        "Django", "FastAPI", "Flask", "Hibernate", "RESTful APIs", "REST API", "GraphQL",
        "gRPC", "NestJS", "System Design", "Distributed Systems", "OOP", "Data Structures",
        "Algorithms", "Backend Development", "Full Stack Development", "Software Engineering",
        # Frontend & Web
        "React", "React.js", "Next.js", "Redux", "Angular", "AngularJS", "Vue.js",
        "HTML", "HTML5", "CSS", "CSS3", "Tailwind CSS", "Bootstrap", "Web Development", "UI Development",
        # Cloud & DevOps
        "AWS", "Amazon Web Services", "Azure", "Microsoft Azure", "Google Cloud", "GCP",
        "Docker", "Kubernetes", "CI/CD", "DevOps", "Jenkins", "Terraform", "Ansible",
        "Linux", "Git", "GitHub", "GitLab", "Jira", "Cloud Computing", "Serverless", "Cloud Architecture",
        # Databases & Messaging
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Apache Kafka", "Kafka",
        "RabbitMQ", "Cassandra", "DynamoDB", "NoSQL", "MS SQL Server", "Oracle", "BigQuery",
        "Snowflake", "SQLite", "Memcached",
        # Data & AI / ML
        "Machine Learning", "Data Science", "Deep Learning", "Artificial Intelligence",
        "PyTorch", "TensorFlow", "Apache Spark", "Spark", "Airflow", "Data Engineering",
        "ETL", "Pandas", "NumPy", "Power BI", "Tableau", "Computer Vision", "NLP", "Big Data",
        # Testing & QA
        "Selenium", "Automation Testing", "Manual Testing", "Postman", "Cypress", "JMeter",
        "QA", "Test Automation", "JUnit",
        # Mobile
        "Android", "iOS", "React Native", "Flutter",
        # Methodologies & Management
        "Product Management", "Agile", "Scrum", "Project Management", "Technical Lead", "Solution Architecture"
    ]

    print(f"📊 Querying {len(skills_to_test)} skills with 500ms pacing...")

    results = await page.evaluate("""async (skills) => {
        const out = [];
        for (let i = 0; i < skills.length; i++) {
            const s = skills[i];
            let attempts = 0;
            let success = false;
            let count = 0;
            let status = 0;

            while (attempts < 3 && !success) {
                attempts++;
                try {
                    const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(s));
                    status = resp.status;
                    if (resp.status === 200) {
                        const data = await resp.json();
                        count = data.meta ? data.meta.total_count : (data.objects ? data.objects.length : 0);
                        success = true;
                    } else if (resp.status === 429) {
                        await new Promise(r => setTimeout(r, 2000));
                    } else {
                        success = true;
                    }
                } catch (e) {
                    await new Promise(r => setTimeout(r, 1000));
                }
            }
            out.push({ skill: s, jobCount: count, status: status });
            await new Promise(r => setTimeout(r, 550));
        }
        return out;
    }""", skills_to_test)

    # Sort descending by job count
    results.sort(key=lambda x: x["jobCount"], reverse=True)

    print("\n" + "=" * 65)
    print("🏆 TOP RANKED TECH SKILLS ON INSTAHYRE (BY LIVE JOB SEARCH COUNT):")
    print("=" * 65)
    for idx, r in enumerate(results, 1):
        print(f"  {idx:3d}. {r['skill']:<32} : {r['jobCount']:4d} jobs (status {r['status']})")

    out_file = OUTPUT_DIR / "instahyre_top_tech_skills_verified.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Saved verified results to: {out_file}")

    # Also test live search on UI with the top 10 tech skills
    top_10 = [r["skill"] for r in results[:10]]
    print(f"\n🖥️ Performing UI Search with Top 10 Tech Skills: {top_10}")

    ui_res = await page.evaluate("""(skills) => {
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
    }""", top_10)
    print("UI Action:", json.dumps(ui_res, indent=2))
    await asyncio.sleep(6)

    # Capture live UI screenshot
    shot_path = OUTPUT_DIR / "instahyre_top_10_live_results.png"
    await page.screenshot(path=str(shot_path), full_page=False)
    print(f"📸 Screenshot saved: {shot_path}")

    rendered_cards = await page.evaluate("() => document.querySelectorAll('.job-card, [class*=\"opportunity-card\"], .employer-row').length")
    print(f"✅ Total Live Job Cards Rendered: {rendered_cards}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
