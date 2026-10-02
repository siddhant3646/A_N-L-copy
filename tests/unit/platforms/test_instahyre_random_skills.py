import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestInstahyreRandomSkills(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_selection_size_split_and_uniqueness(self):
        skills = self.agent._get_instahyre_skills()
        self.assertEqual(len(skills), 15)
        self.assertEqual(len(set(skills)), 15)

        languages = skills[: self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT]
        tools = skills[self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT :]

        self.assertEqual(len(languages), 8)
        self.assertEqual(len(tools), 7)
        for skill in languages:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_LANGUAGES)
        for skill in tools:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_TOOLS)

    def test_selection_is_stable_within_task(self):
        first = self.agent._get_instahyre_skills()
        second = self.agent._get_instahyre_skills()
        self.assertIs(first, second)
        self.assertEqual(first, second)

    def test_reset_clears_cached_selection(self):
        self.agent._get_instahyre_skills()
        self.assertIsNotNone(self.agent._instahyre_skills)

        self.agent.reset_per_task_state()
        self.assertIsNone(self.agent._instahyre_skills)

        refreshed = self.agent._get_instahyre_skills()
        self.assertEqual(len(refreshed), 15)

    def test_reset_produces_new_draw(self):
        with patch('src.sentinel.agent.random.sample') as mock_sample:
            mock_sample.side_effect = [
                ['L%d' % i for i in range(8)], ['T%d' % i for i in range(7)],
                ['X%d' % i for i in range(8)], ['Y%d' % i for i in range(7)],
            ]
            first = self.agent._get_instahyre_skills()
            self.agent.reset_per_task_state()
            second = self.agent._get_instahyre_skills()

        self.assertEqual(first[:8], ['L%d' % i for i in range(8)])
        self.assertEqual(second[:8], ['X%d' % i for i in range(8)])
        self.assertNotEqual(first, second)

    def test_skills_pool_completeness_and_uniqueness(self):
        """Verify that all 205 skills are present without duplicates."""
        expected_skills = {
            "Java", "Java 17", "Java 21", "Python", "JavaScript", "TypeScript", "Golang", "Go",
            "C++", "C#", "SQL", "Kotlin", "Scala", "Rust", "Shell Scripting", "Bash", "Node.js",
            "NodeJS", "Core Java", "JVM", "Spring", "Spring Boot", "Spring Cloud", "Spring Security",
            "Spring Data JPA", "Spring MVC", "Spring WebFlux", "Hibernate", "JPA", "Microservices",
            "RESTful APIs", "REST API", "gRPC", "GraphQL", "SOAP", "Fastify", "Express.js", "NestJS",
            "Django", "FastAPI", "Flask", "Dropwizard", "Micronaut", "Quarkus", "Reactive Programming",
            "React", "React.js", "ReactJS", "Redux", "Redux Toolkit", "Next.js", "HTML5", "CSS3",
            "Tailwind CSS", "Bootstrap", "Material UI", "Webpack", "Vite", "NPM", "Yarn", "WebSockets",
            "Front-End Development", "Full Stack", "System Design", "High-Level Design (HLD)",
            "Low-Level Design (LLD)", "Object-Oriented Programming (OOP)", "SOLID Principles",
            "Design Patterns", "Distributed Systems", "Event-Driven Architecture",
            "Service-Oriented Architecture (SOA)", "Domain-Driven Design (DDD)",
            "Microservices Architecture", "CAP Theorem", "BASE Properties", "Concurrency",
            "Multithreading", "Rate Limiting", "Load Balancing", "Caching Strategies",
            "Data Consistency", "High Availability", "Fault Tolerance", "Scalability",
            "Relational Databases (RDBMS)", "MySQL", "PostgreSQL", "Oracle SQL", "MS SQL Server",
            "NoSQL", "MongoDB", "Cassandra", "Redis", "DynamoDB", "Elasticsearch", "OpenSearch",
            "Memcached", "Database Indexing", "Query Optimization", "Database Sharding",
            "Connection Pooling", "Replication", "Vector Databases", "ChromaDB", "Pinecone",
            "Milvus", "Apache Kafka", "Kafka Streams", "Apache Flink", "Apache Spark",
            "Spark Streaming", "Apache Airflow", "Apache Storm", "RabbitMQ", "ActiveMQ", "AWS SQS",
            "AWS SNS", "Pub/Sub", "Event Streaming", "Data Streaming", "Real-Time Analytics",
            "ETL Pipelines", "Data Engineering", "DBT (Data Build Tool)", "Data Warehousing",
            "Snowflake", "AWS", "Amazon Web Services", "Microsoft Azure",
            "GCP (Google Cloud Platform)", "Cloud Computing", "Amazon EC2", "AWS S3", "AWS Lambda",
            "AWS RDS", "AWS CloudWatch", "AWS ECS", "AWS EKS", "AWS IAM", "AWS API Gateway",
            "Cloud Architecture", "Serverless", "PCF (Pivotal Cloud Foundry)", "Azure DevOps",
            "Azure Functions", "Azure Blob Storage", "Docker", "Kubernetes (K8s)", "CI/CD",
            "Jenkins", "GitLab CI", "GitHub Actions", "Terraform", "Ansible", "Helm", "Linux",
            "Maven", "Gradle", "Git", "GitHub", "GitLab", "Bitbucket", "Containerization",
            "Orchestration", "Infrastructure as Code (IaC)", "DevOps", "Splunk", "Grafana",
            "Prometheus", "ELK Stack", "Datadog", "New Relic", "Distributed Tracing",
            "APM (Application Performance Monitoring)", "OpenTelemetry", "Fortify", "SonarQube",
            "Application Security", "SAST / DAST", "SOC 2", "FedRAMP", "OWASP Top 10",
            "OAuth 2.0", "JWT (JSON Web Tokens)", "Generative AI", "Large Language Models (LLMs)",
            "RAG (Retrieval-Augmented Generation)", "LangChain", "LlamaIndex", "Hugging Face",
            "OpenAI API", "Ollama", "DeepSeek", "Qwen", "Gemma", "Vector Search", "Semantic Search",
            "Prompt Engineering", "Computer Vision", "YOLO", "MediaPipe", "PyTorch",
            "Machine Learning", "AI Platform",
        }
        all_pool_skills = set(self.agent.INSTAHYRE_SKILL_LANGUAGES) | set(self.agent.INSTAHYRE_SKILL_TOOLS)
        self.assertEqual(all_pool_skills, expected_skills)
        self.assertEqual(len(self.agent.INSTAHYRE_SKILL_LANGUAGES) + len(self.agent.INSTAHYRE_SKILL_TOOLS), 205)
        # Check no overlap between the two pools
        self.assertEqual(set(self.agent.INSTAHYRE_SKILL_LANGUAGES) & set(self.agent.INSTAHYRE_SKILL_TOOLS), set())


class TestInstahyreSkillsInjection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        self.agent._task_description = "Apply to jobs on Instahyre"
        self.mock_page = AsyncMock()
        self.mock_page.url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
        self.mock_page.evaluate = AsyncMock(return_value='NO_ACTION')
        self.agent._page = self.mock_page

    async def test_fallback_injects_skills_global(self):
        await self.agent._handle_scripted_fallback()

        injected = [
            call.args
            for call in self.mock_page.evaluate.await_args_list
            if len(call.args) >= 2
            and isinstance(call.args[0], str)
            and '__SENTINEL_INSTAHYRE_SKILLS__' in call.args[0]
        ]
        self.assertTrue(injected, "Skills global was not injected")
        payload = injected[-1][1]
        self.assertEqual(len(payload), 15)


if __name__ == '__main__':
    unittest.main()
