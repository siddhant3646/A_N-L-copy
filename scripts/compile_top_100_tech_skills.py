"""Compile and rank the Top 100 Software Engineering / Tech Skills on Instahyre."""

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
    await asyncio.sleep(3)

    # 150+ focused tech skills covering Languages, Frameworks, Cloud, DevOps, DBs, Architecture, QA, AI
    tech_skills = [
        "Product Management", "Amazon Web Services", "Python", "Google Cloud", "AWS",
        "MS SQL Server", "Microsoft Azure", "Java", "Azure", "NoSQL", "GCP", "CI/CD",
        "Agile", "Go", "DevOps", "JavaScript", "Microservices", "Kubernetes", "React",
        "TypeScript", "Golang", "Docker", "MySQL", "Jira", "Spring Boot", "Terraform",
        "Jenkins", "Selenium", "C#", "Scrum", "TensorFlow", "Tableau", "PHP", "Ansible",
        "BigQuery", "Ruby", "Swift", "Perl", "Bash", "Cassandra", "J2EE", "JVM", "Blockchain",
        "Spring", "Node.js", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "Apache Kafka",
        "Kafka", "RabbitMQ", "Angular", "AngularJS", "Vue.js", "Next.js", "Redux", "GraphQL",
        "Django", "FastAPI", "Flask", "Hibernate", "RESTful APIs", "REST API", "NestJS",
        "Git", "GitHub", "GitLab", "Linux", "System Design", "Distributed Systems",
        "Machine Learning", "Data Science", "Artificial Intelligence", "Deep Learning",
        "Data Engineering", "Apache Spark", "Spark", "Airflow", "ETL", "Power BI",
        "Automation Testing", "Manual Testing", "Postman", "Cypress", "JMeter",
        "Android", "iOS", "React Native", "Flutter", "HTML", "HTML5", "CSS", "CSS3",
        "Tailwind CSS", "Bootstrap", "C++", "Kotlin", "Scala", "Rust", "Shell Scripting",
        "SQL", "Oracle", "DynamoDB", "Cloud Computing", "Serverless", "Software Engineering",
        "Backend Development", "Full Stack Development", "Web Development", "API Development",
        "Object Oriented Programming", "Data Structures", "Algorithms", "Computer Vision",
        "NLP", "PyTorch", "Pandas", "NumPy", "Scikit-Learn", "Hadoop", "Cyber Security",
        "Information Security", "Network Security", "Cloud Architecture", "Spring MVC",
        "Spring Security", "Spring Cloud", "Express.js", "ASP.NET", ".NET", ".NET Core",
        "Ruby on Rails", "Laravel", "Webpack", "Front End Development", "UI Development",
        "SQLite", "MariaDB", "Helm", "QA", "Test Automation", "JUnit", "Appium",
        "Solution Architecture", "Technical Lead", "Project Management", "Microservices Architecture",
        "Event-Driven Architecture", "Big Data", "Data Analysis", "Snowflake", "OAuth 2.0"
    ]

    print(f"🔎 Testing {len(tech_skills)} pure tech skills against Instahyre search API...")

    results = await page.evaluate("""async (skills) => {
        const out = [];
        for (const s of skills) {
            try {
                const resp = await fetch('/api/v1/job_search?company_size=0&job_type=0&status=0&skills=' + encodeURIComponent(s));
                let count = 0;
                if (resp.ok) {
                    const data = await resp.json();
                    count = data.meta ? data.meta.total_count : (data.objects ? data.objects.length : 0);
                }
                out.push({ skill: s, jobCount: count });
            } catch (e) {
                out.push({ skill: s, jobCount: 0 });
            }
        }
        return out;
    }""", tech_skills)

    # Sort descending
    results.sort(key=lambda x: x["jobCount"], reverse=True)

    # Deduplicate aliases / variants
    seen = set()
    ranked_top = []
    for r in results:
        norm = r["skill"].lower().strip()
        if norm not in seen:
            seen.add(norm)
            ranked_top.append(r)

    print("\n" + "=" * 60)
    print("🏆 TOP 100 TECH SKILLS ON INSTAHYRE RANKED BY SEARCH RESULTS:")
    print("=" * 60)
    for i, r in enumerate(ranked_top[:100], 1):
        print(f"  {i:3d}. {r['skill']:<32} : {r['jobCount']:4d} jobs")

    with open("live_test_output/instahyre_skills/top_100_tech_skills_final.json", "w", encoding="utf-8") as f:
        json.dump(ranked_top[:100], f, indent=2)

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
