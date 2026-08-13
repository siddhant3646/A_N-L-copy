#!/usr/bin/env python3
"""
Generate 5000+ new patterns to improve the job application agent's resiliency.

This script uses structured data and templates to carefully craft patterns
across multiple batches.  It outputs a payload JSON that can be injected into
config/qa_patterns.json with inject_patterns.py.
"""

import json
from typing import Dict, Any, List
from pathlib import Path

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
OUT_PATH = SCRIPT_DIR.parent / "new_patterns_payload.json"

P: Dict[str, Any] = {}
C: Dict[str, Any] = {}


def norm_key(text: str) -> str:
    """Create a safe JSON key from a display name."""
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def make_itd(default: str, radio: str = None, select: str = None,
             text: str = None, number: str = None, checkbox: str = None,
             textarea: str = None) -> Dict[str, str]:
    """Build input_type_defaults dict, excluding None values."""
    itd = {}
    for k, v in [("radio", radio), ("select", select), ("text", text),
                 ("number", number), ("checkbox", checkbox), ("textarea", textarea)]:
        if v is not None:
            itd[k] = v
    # ensure at least a default mapping if not provided
    if not itd:
        itd["text"] = default
    return itd


def _norm_pattern(p: str) -> str:
    """Normalize a pattern for deduplication (lowercase, strip)."""
    return p.lower().strip()


def add_pat(key: str, patterns: List[str], category: str, default: str,
            priority: int = 7, itd: Dict[str, str] = None,
            negative_patterns: List[str] = None, exact: bool = False) -> None:
    """Add a pattern entry if the key is new."""
    # Deduplicate patterns case-insensitively while preserving order
    seen: set = set()
    unique_patterns = []
    for p in patterns:
        np = _norm_pattern(p)
        if np and np not in seen:
            unique_patterns.append(p)
            seen.add(np)

    if key in P:
        # append synonyms to existing entry, but don't overwrite
        existing = P[key]
        existing_seen = set(_norm_pattern(p) for p in existing["patterns"])
        for p in unique_patterns:
            if _norm_pattern(p) not in existing_seen:
                existing["patterns"].append(p)
                existing_seen.add(_norm_pattern(p))
        return

    d: Dict[str, Any] = {
        "patterns": unique_patterns,
        "category": category,
        "default": default,
        "priority": priority,
    }
    if itd:
        d["input_type_defaults"] = itd
    if negative_patterns:
        d["negative_patterns"] = negative_patterns
    if exact:
        d["requires_exact_match"] = True
    P[key] = d


def add_meta(key: str, desc: str, smart_fallback: bool,
             requires_exact_match: bool = False, default: str = None):
    """Add category metadata."""
    if key in C:
        return
    d: Dict[str, Any] = {"description": desc, "smart_fallback": smart_fallback}
    if requires_exact_match:
        d["requires_exact_match"] = requires_exact_match
    if default is not None:
        d["default"] = default
    C[key] = d


# ---------------------------------------------------------------------------
# Batch 1: Tech Skills Experience
# ---------------------------------------------------------------------------
PROGRAMMING_LANGUAGES = [
    "Rust", "Go", "Golang", "Scala", "Kotlin", "Swift", "TypeScript", "JavaScript",
    "Python", "Java", "C++", "C#", "PHP", "Ruby", "Perl", "R", "Julia", "Dart",
    "Elixir", "Erlang", "Haskell", "Clojure", "F#", "OCaml", "Lua", "Groovy",
    "Shell", "Bash", "PowerShell", "Objective-C", "VB.NET", "COBOL", "Fortran",
    "Assembly", "Matlab", "SAS", "ABAP", "Apex", "Solidity", "VBA", "Tcl",
    "Scheme", "Lisp", "Prolog", "Ada", "VHDL", "Verilog", "Nim", "Crystal",
    "Zig", "Carbon", "D", "Delphi", "Pascal", "RPG", "Scratch", "Smalltalk",
    "Ada", "Eiffel", "Forth", "PostScript", "ActionScript", "CoffeeScript",
    "Elm", "PureScript", "ReasonML", "ReScript", "WebAssembly", "WASM",
    "Visual Basic", "Q#", "Julia", "MATLAB", "Octave", "IDL", "PL/SQL", "T-SQL",
    "Transact-SQL", "NoSQL", "HTML", "CSS", "XML", "YAML", "JSON", "SQL",
    "GraphQL", "Markdown", "LaTeX", "RegEx", "Bash scripting", "Zsh",
]

FRONTEND_FRAMEWORKS = [
    "React", "Vue", "Angular", "Svelte", "SvelteKit", "Astro", "SolidJS", "Qwik",
    "Next.js", "Nuxt.js", "Gatsby", "Remix", "Redux", "Zustand", "MobX",
    "jQuery", "Backbone.js", "Ember.js", "Knockout.js", "Bootstrap", "Tailwind CSS",
    "Material UI", "Chakra UI", "Ant Design", "Styled Components", "Sass",
    "Less", "Webpack", "Vite", "Rollup", "Parcel", "Babel", "Storybook",
    "React Router", "Vue Router", "Angular Router", "TanStack Query", "SWR",
    "React Hook Form", "Formik", "React Testing Library", "Vue Testing Library",
    "Framer Motion", "Three.js", "D3.js", "Chart.js", "Recharts",
    "Tailwind UI", "Headless UI", "Radix UI", "shadcn/ui", "MUI", "Semantic UI",
    "Foundation", "Bulma", "Spectre", "Tachyons", "Windicss", "UnoCSS",
    "Preact", "Alpine.js", "Lit", "Stencil", "Polymer", "Backbone", "Marionette",
    "Electron", "Tauri", "Flutter Web", "Capacitor", "Ionic React",
]

BACKEND_FRAMEWORKS = [
    "Spring Boot", "Spring", "Django", "Flask", "FastAPI", "Express.js",
    "NestJS", "Ruby on Rails", "Laravel", "Symfony", "ASP.NET Core", "ASP.NET",
    "Phoenix", "Gin", "Fiber", "Echo", "Koa", "Hapi", "Fastify", "Tornado",
    "CakePHP", "CodeIgniter", "Zend Framework", "Play Framework", "Akka",
    "Quarkus", "Micronaut", "Ktor", "Rocket", "Actix", "Spring MVC",
    "Spring Cloud", "Spring Security", "Spring Data", "Spring Batch",
    "Hibernate", "MyBatis", "JPA", "Entity Framework", "Laravel Livewire",
    "Ruby Sinatra", "Padrino", "Hanami", "Bottle", "CherryPy", "Pyramid",
    "Tornado", "Sanic", "Aiohttp", "Vibora", "Falcon", "Hug", "Nameko",
    "Next.js API", "Nuxt server", "SvelteKit endpoints",
    "GraphQL Yoga", "Apollo Server", "Prisma", "Drizzle", "TypeORM",
    "Sequelize", "Mongoose", "SQLAlchemy", "Django ORM", "GORM",
    "EF Core", "NHibernate", "Realm", "Couchbase Lite",
]

CLOUD_PLATFORMS = [
    "AWS", "Amazon Web Services", "GCP", "Google Cloud", "Azure", "Microsoft Azure",
    "Oracle Cloud", "IBM Cloud", "DigitalOcean", "Heroku", "Firebase",
    "Alibaba Cloud", "Linode", "Vultr", "Cloudflare", "Vercel", "Netlify",
    "Render", "Fly.io", "Supabase", "AWS Lambda", "AWS EC2", "AWS S3",
    "AWS RDS", "AWS ECS", "AWS EKS", "AWS Fargate", "AWS CloudFormation",
    "AWS DynamoDB", "Google Cloud Run", "Google Kubernetes Engine", "Azure Functions",
    "Azure App Service", "Azure Kubernetes Service", "Azure DevOps",
    "AWS SQS", "AWS SNS", "AWS EventBridge", "AWS Step Functions", "AWS API Gateway",
    "AWS Amplify", "AWS AppSync", "AWS Cognito", "AWS IAM", "AWS Route 53",
    "AWS CloudFront", "AWS ElastiCache", "AWS OpenSearch", "AWS Redshift",
    "AWS SageMaker", "AWS CodePipeline", "AWS CodeBuild", "AWS CodeDeploy",
    "GCP Compute Engine", "GCP Cloud Storage", "GCP BigQuery", "GCP Pub/Sub",
    "GCP Cloud Functions", "GCP Cloud Run", "GCP GKE", "GCP Cloud SQL",
    "Azure Blob Storage", "Azure Functions", "Azure Cosmos DB", "Azure SQL Database",
    "Azure DevOps", "Azure Monitor", "Azure Active Directory",
    "Cloudflare Workers", "Cloudflare Pages", "Cloudflare R2",
    "Vercel Functions", "Netlify Functions", "AWS Sagemaker", "Databricks",
]

DATABASES = [
    "PostgreSQL", "MySQL", "MariaDB", "SQLite", "Oracle Database", "Microsoft SQL Server",
    "MongoDB", "Cassandra", "Couchbase", "CouchDB", "DynamoDB", "Firebase Firestore",
    "Redis", "Memcached", "Elasticsearch", "Solr", "Neo4j", "Amazon Neptune",
    "InfluxDB", "TimescaleDB", "ClickHouse", "Snowflake", "BigQuery", "Redshift",
    "CockroachDB", "PlanetScale", "Supabase", "FaunaDB", "ArangoDB", "OrientDB",
    "GraphQL", "RavenDB", "Firebird", "DB2", "Sybase", "Informix", "Teradata",
    "MariaDB", "TiDB", "YugabyteDB", "Vitess", "SingleStore", "MemSQL",
    "Aerospike", "ScyllaDB", "HBase", "Accumulo", "Amazon DocumentDB",
    "Amazon Keyspaces", "Azure Cosmos DB", "Google Firestore", "MongoDB Atlas",
    "Amazon Redshift", "Google BigQuery", "Azure Synapse", "Databricks SQL",
    "DuckDB", "SQLite", "LevelDB", "RocksDB", "Berkeley DB", "Tarantool",
    "Dragonfly", "KeyDB", "Valkey", "Aiven", "Upstash", "Redis Cloud",
    "Pinecone", "Weaviate", "Milvus", "Qdrant", "Chroma", "Vespa", "Meilisearch",
    "Typesense", "Algolia", "OpenSearch", "Sphinx", "Manticore", "Meilisearch",
    "Vector DB", "Graph database", "Document database", "Key-value store",
]

DEVOPS_TOOLS = [
    "Docker", "Kubernetes", "Helm", "Terraform", "Ansible", "Puppet", "Chef",
    "Pulumi", "CloudFormation", "Jenkins", "GitLab CI", "GitHub Actions",
    "CircleCI", "Travis CI", "TeamCity", "Bamboo", "ArgoCD", "Flux", "Spinnaker",
    "SonarQube", "Nexus", "JFrog Artifactory", "Git", "GitHub", "GitLab",
    "Bitbucket", "SVN", "Mercurial", "Prometheus", "Grafana", "GitHub Packages",
    "GitLab Container Registry", "Docker Hub", "Harbor", "Quay", "ECR", "ACR", "GCR",
    "GitOps", "DevSecOps", "MLOps", "AIOps", "DataOps", "FinOps",
    "Nomad", "Consul", "Vault", "Boundary", "Waypoint", "Vagrant", "Packer",
    "Rancher", "OpenShift", "EKS", "GKE", "AKS", "K3s", "K9s", "Minikube", "Kind",
    "Istio", "Linkerd", "Envoy", "Kong", "Traefik", "Nginx", "HAProxy",
    "Caddy", "Apache HTTP Server", "Tomcat", "Jetty", "WildFly", "WebLogic",
    "Buildkite", "Drone CI", "Concourse", "Tekton", "Keptn", "Flagger", "Knative",
    "OpenFaaS", "Kubeless", "Fission", "Serverless Framework", "Chalice",
]

AI_ML_TOOLS = [
    "TensorFlow", "PyTorch", "Keras", "Scikit-learn", "XGBoost", "LightGBM",
    "Pandas", "NumPy", "SciPy", "Matplotlib", "Seaborn", "Plotly", "OpenCV",
    "NLTK", "SpaCy", "Gensim", "Hugging Face", "Transformers", "LangChain",
    "LlamaIndex", "OpenAI API", "Anthropic API", "CrewAI", "AutoGen",
    "MLflow", "Kubeflow", "Airflow", "Prefect", "Dagster", "Ray", "Spark",
    "PySpark", "Apache Spark", "Databricks", "Snowflake ML", "Amazon SageMaker",
    "Google Vertex AI", "Azure ML", "OpenCV", "PIL", "Scikit-image",
    "TensorBoard", "Weights and Biases", "Neptune.ai", "DVC", "Feast",
    "Tecton", "Great Expectations", "Evidently AI", "Weights & Biases",
    "BentoML", "Triton Inference Server", "TorchServe", "TensorFlow Serving",
    "ONNX", "ONNX Runtime", "TensorRT", "OpenVINO", "CoreML",
    "Stable Diffusion", "Midjourney", "GPT", "GPT-4", "Claude", "Gemini",
    "Whisper", "BERT", "RoBERTa", "T5", "GPT-3", "LLaMA", "Mistral",
    "Pinecone", "Weaviate", "Chroma", "Qdrant", "FAISS", "Annoy",
    "Scikit-optimize", "Optuna", "Hyperopt", "Ray Tune", "Ax",
    "spaCy", "Stanford NLP", "Gensim", "Pattern", "TextBlob", "Polyglot",
    "PyTorch Lightning", "KerasTuner", "FastAI", "Jax", "Flax", "Haiku",
    "H2O.ai", "MLlib", "Mahout", "Weka", "RapidMiner", "Knime",
]

TESTING_TOOLS = [
    "Selenium", "Cypress", "Playwright", "Puppeteer", "Jest", "Mocha",
    "Jasmine", "Vitest", "Karma", "JUnit", "TestNG", "pytest", "unittest",
    "Robot Framework", "Cucumber", "Gherkin", "Postman", "Insomnia",
    "REST Assured", "Karate", "Gatling", "k6", "JMeter", "Locust",
    "SonarQube", "OWASP ZAP", "Burp Suite", "SoapUI",
    "Cypress Component Testing", "Storybook Test Runner", "Testing Library",
    "Enzyme", "React Testing Library", "Vue Test Utils", "Angular Testing Library",
    "Mockito", "PowerMock", "WireMock", "Mountebank", "VCR.py",
    "Faker", "Factory Boy", "Hypothesis", "Tox", "Nox", "Coverage.py",
    "JaCoCo", "Cobertura", "Codecov", "Coveralls", "Stryker", "Infection",
    "Artillery", "Tsung", "Bees with Machine Guns", "Fortio", "Vegeta",
    "Pact", "Spring Cloud Contract", "Hoverfly", "Mountebank", "VCR",
]

MESSAGE_QUEUES = [
    "Apache Kafka", "RabbitMQ", "ActiveMQ", "RocketMQ", "Amazon SQS", "Amazon SNS",
    "Azure Service Bus", "Google Pub/Sub", "NATS", "Apache Pulsar", "Redis Pub/Sub",
    "ZeroMQ", "Celery", "Sidekiq", "BullMQ", "Kinesis", "Apache Flink",
    "AWS EventBridge", "AWS Step Functions", "Temporal", "Camunda", "Zeebe",
    "Confluent Kafka", "Redpanda", "Pulsar", "RabbitMQ Streams",
    "Debezium", "Materialize", "ksqlDB", "Kafka Connect", "Kafka Streams",
    "Storm", "Samza", "Google Dataflow", "Azure Stream Analytics",
]

SECURITY_TOOLS = [
    "OAuth", "OIDC", "SAML", "JWT", "LDAP", "Active Directory",
    "HashiCorp Vault", "AWS KMS", "Azure Key Vault", "Google Cloud KMS",
    "OWASP", "Snyk", "Veracode", "Checkmarx", "SonarQube", "Burp Suite",
    "Wireshark", "Nmap", "Metasploit", "OpenVAS", "CrowdStrike", "Splunk SOAR",
    "Okta", "Auth0", "Keycloak", "Cognito", "OneLogin", "Ping Identity",
    "Let's Encrypt", "Certbot", "OpenSSL", "LibreSSL", "BoringSSL",
    "WAF", "Cloudflare WAF", "AWS WAF", "ModSecurity", "Snort",
    "Suricata", "Zeek", "Fail2ban", "Tripwire", "AIDE", "OSSEC",
    "HashiCorp Boundary", "Teleport", "BeyondCorp", "Zero Trust",
    "PKI", "HSM", "TPM", "YubiKey", "FIDO2", "WebAuthn",
    "Fortify", "Black Duck", "WhiteSource", "FOSSA", "Trivy", "Grype",
    "Clair", "Anchore", "Snyk Container", "Aqua Security", "Sysdig",
    "Brakeman", "Bandit", "Safety", "npm audit", "yarn audit",
]

MONITORING_TOOLS = [
    "Prometheus", "Grafana", "Datadog", "New Relic", "Splunk", "ELK Stack",
    "Elastic Stack", "OpenTelemetry", "Jaeger", "Zipkin", "AppDynamics",
    "Dynatrace", "Nagios", "Zabbix", "PagerDuty", "Opsgenie", "VictoriaMetrics",
    "Sentry", "Rollbar", "Bugsnag", "Airbrake", "Raygun", "LogRocket",
    "Honeycomb", "Lightstep", "Signoz", "UptimeRobot", "StatusCake",
    "Pingdom", "Catchpoint", "ThousandEyes", "Grafana Loki", "Cortex",
    "Thanos", "Mimir", "Tempo", "AWS CloudWatch", "Google Cloud Monitoring",
    "Azure Monitor", "GCP Cloud Trace", "Azure Application Insights",
    "Fluentd", "Fluent Bit", "Logstash", "Vector", "Filebeat", "Winlogbeat",
    "Kibana", "Grafana Tempo", "Jaeger", "OpenTracing",
]

MOBILE_TECH = [
    "React Native", "Flutter", "Swift", "Kotlin", "Ionic", "Cordova",
    "PhoneGap", "Xamarin", "Android SDK", "iOS SDK", "Jetpack Compose",
    "SwiftUI", "Firebase Mobile", "Realm", "SQLite Mobile",
    "Expo", "React Native Navigation", "Flutter Riverpod", "Provider",
    "GetX", "BLoC", "MobX", "Redux Toolkit", "ReSwift",
    "Apple Watch", "Wear OS", "tvOS", "Android TV", "Unity Mobile",
    "Unreal Engine Mobile", "Cocos2d", "Godot", "SpriteKit",
    "Push notifications", "FCM", "APNs", "OneSignal", "Pusher Beams",
]

API_TECH = [
    "REST API", "GraphQL", "gRPC", "SOAP", "WebSocket", "WebRTC",
    "tRPC", "OpenAPI", "Swagger", "Postman", "API Gateway", "Apollo",
    "Falcor", "JSON-RPC", "XML-RPC",
    "RESTful API", "REST API design", "API development", "API testing",
    "GraphQL API", "GraphQL federation", "GraphQL subscription",
    "gRPC protobuf", "Protocol Buffers", "Avro", "Thrift", "MessagePack",
    "Webhook", "Event-driven API", "AsyncAPI", "API documentation",
    "RapidAPI", "Stoplight", "Insomnia", "Postman Collections",
    "Kong Gateway", "Tyk", "Apigee", "AWS API Gateway", "Azure API Management",
    "Google API Gateway", "GraphQL Yoga", "Hasura", "Prisma",
]

BLOCKCHAIN_WEB3 = [
    "Blockchain", "Ethereum", "Solidity", "Smart Contracts", "Web3.js",
    "Ethers.js", "Hyperledger Fabric", "Corda", "Ripple", "Binance Smart Chain",
    "Polygon", "Solana", "Rust Smart Contracts", "NFT", "DeFi",
    "Bitcoin", "Litecoin", "Cardano", "Polkadot", "Chainlink",
    "The Graph", "IPFS", "Filecoin", "Arweave", "MetaMask",
    "Truffle", "Hardhat", "Foundry", "Brownie", "Remix IDE",
    "Web3.py", "Web3.php", "Moralis", "Alchemy", "Infura",
    "Decentralized Finance", "DAOs", "Crypto", "Zero Knowledge",
    "zkSync", "StarkNet", "Arbitrum", "Optimism", "Base",
    "Cosmos SDK", "Tendermint", "Substrate", "NEAR Protocol", "Aptos",
    "Move language", "Sui", "Mina", "Tezos", "EOS",
]

DATA_ENG_TOOLS = [
    "Apache Airflow", "Prefect", "Dagster", "Apache Kafka", "Apache Spark",
    "Apache Flink", "Apache Beam", "dbt", "Fivetran", "Stitch", "Airbyte",
    "Talend", "Informatica", "Pentaho", "Databricks", "Snowflake", "Hadoop",
    "Hive", "Presto", "Trino", "Druid", "ClickHouse", "Delta Lake", "Iceberg",
    "Hudi", "Great Expectations", "Apache NiFi",
    "AWS Glue", "AWS EMR", "AWS Athena", "AWS Redshift Spectrum",
    "Google Dataflow", "Google Dataproc", "Google BigQuery", "Azure Data Factory",
    "Azure Synapse", "Azure Databricks", "Databricks Delta Live Tables",
    "Spark Streaming", "Kafka Streams", "Flink SQL", "Spark SQL",
    "Pandas", "Polars", "Dask", "Vaex", "Modin", "Ray Data",
    "SQL", "NoSQL", "GraphQL", "dbt", "SQLMesh", "Soda Core",
    "Amundsen", "DataHub", "OpenLineage", "Monte Carlo", "Bigeye",
    "Looker", "Tableau", "Power BI", "Superset", "Metabase", "Redash",
    "Mode Analytics", "ThoughtSpot", "Qlik Sense", "Sisense",
]

# Deduplicate while preserving order
ALL_TECH = list(dict.fromkeys(
    PROGRAMMING_LANGUAGES + FRONTEND_FRAMEWORKS + BACKEND_FRAMEWORKS +
    CLOUD_PLATFORMS + DATABASES + DEVOPS_TOOLS + AI_ML_TOOLS + TESTING_TOOLS +
    MESSAGE_QUEUES + SECURITY_TOOLS + MONITORING_TOOLS + MOBILE_TECH +
    API_TECH + BLOCKCHAIN_WEB3 + DATA_ENG_TOOLS
))


EXPERIENCE_TEMPLATES = [
    "{tech} experience", "years of experience in {tech}",
    "how many years of {tech} experience", "{tech} proficiency",
    "experience with {tech}", "worked with {tech}", "expertise in {tech}",
    "{tech} skills", "{tech} years of experience", "have you worked on {tech}",
    "do you know {tech}", "proficiency in {tech}", "working knowledge of {tech}",
    "practical experience in {tech}", "hands on experience in {tech}",
    "familiarity with {tech}", "competency in {tech}", "comfortable with {tech}",
    "have you used {tech}", "do you have experience with {tech}",
]
PROFICIENCY_TEMPLATES = [
    "rate your {tech} proficiency", "how proficient are you in {tech}",
    "{tech} skill level", "rate yourself in {tech}", "{tech} rating",
    "how would you rate your {tech} skills", "what is your {tech} level",
    "self assess {tech}", "evaluate your {tech} skills",
]
YES_NO_TEMPLATES = [
    "have you worked with {tech}", "do you have experience in {tech}",
    "are you familiar with {tech}", "do you know {tech}",
    "have you used {tech} before", "are you comfortable with {tech}",
]
WORKED_TEMPLATES = [
    "worked on {tech}", "projects using {tech}", "used {tech} in projects",
    "practical exposure to {tech}", "{tech} project experience",
]


def _tech_key(prefix: str, tech: str) -> str:
    base = norm_key(tech)
    return f"{prefix}_{base}" if not base.startswith(prefix) else base


def experience_patterns_for_tech(tech: str):
    """Generate an experience pattern for a given technology."""
    tech_lower = tech.lower()
    key = _tech_key("exp", tech)
    patterns = [t.format(tech=tech) for t in EXPERIENCE_TEMPLATES]
    patterns += [t.format(tech=tech_lower) for t in EXPERIENCE_TEMPLATES if t.format(tech=tech) != t.format(tech=tech_lower)]
    itd = {
        "radio": "4", "select": "4 Years", "text": "4 Years", "number": "4",
    }
    add_pat(key, patterns, "experience", "4 Years", priority=8, itd=itd,
            negative_patterns=["salary", "notice period", "ctc", "expected", "current"])


def proficiency_patterns_for_tech(tech: str):
    key = _tech_key("prof", tech)
    tech_lower = tech.lower()
    patterns = [t.format(tech=tech) for t in PROFICIENCY_TEMPLATES]
    patterns += [t.format(tech=tech_lower) for t in PROFICIENCY_TEMPLATES if t.format(tech=tech) != t.format(tech=tech_lower)]
    itd = {
        "radio": "Advanced", "select": "Advanced", "text": "Advanced", "number": "4",
    }
    add_pat(key, patterns, "skills", "Advanced", priority=7, itd=itd)


def yes_no_patterns_for_tech(tech: str):
    key = _tech_key("yn", tech)
    tech_lower = tech.lower()
    patterns = [t.format(tech=tech) for t in YES_NO_TEMPLATES]
    patterns += [t.format(tech=tech_lower) for t in YES_NO_TEMPLATES if t.format(tech=tech) != t.format(tech=tech_lower)]
    itd = {
        "radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "checked",
    }
    add_pat(key, patterns, "yes_no", "Yes", priority=7, itd=itd)


def worked_patterns_for_tech(tech: str):
    key = _tech_key("worked", tech)
    tech_lower = tech.lower()
    patterns = [t.format(tech=tech) for t in WORKED_TEMPLATES]
    patterns += [t.format(tech=tech_lower) for t in WORKED_TEMPLATES if t.format(tech=tech) != t.format(tech=tech_lower)]
    itd = {
        "radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "checked",
    }
    add_pat(key, patterns, "yes_no", "Yes", priority=7, itd=itd)


def generate_batch1_tech_skills_experience() -> int:
    """Generate tech skills experience, proficiency, and yes/no patterns."""
    for tech in ALL_TECH:
        experience_patterns_for_tech(tech)
        proficiency_patterns_for_tech(tech)
        yes_no_patterns_for_tech(tech)
        worked_patterns_for_tech(tech)
    return len([k for k in P if k.startswith(("exp_", "prof_", "yn_", "worked_"))])


# ---------------------------------------------------------------------------
# Batch 2: Skills Proficiency / Self-Assessment
# ---------------------------------------------------------------------------
ADDITIONAL_SKILLS = [
    "problem solving", "critical thinking", "analytical skills",
    "debugging", "troubleshooting", "root cause analysis", "technical writing",
    "mentoring", "code review", "pair programming", "agile", "scrum", "kanban",
    "cross functional collaboration", "client communication",
    "requirement gathering", "system design",
    "architecture design", "microservices", "event driven architecture",
    "serverless architecture", "domain driven design", "clean architecture",
    "test driven development", "behavior driven development",
    "continuous integration", "continuous delivery", "continuous deployment",
    "infrastructure as code", "platform engineering", "site reliability engineering",
    "incident management", "disaster recovery", "backup and recovery",
    "data modeling", "data warehousing", "etl", "data pipelines",
    "machine learning", "deep learning", "natural language processing",
    "computer vision", "generative ai", "large language models",
    "prompt engineering", "fine tuning", "model deployment",
    "ux design", "ui design", "accessibility", "responsive design",
    "web performance", "seo", "web analytics", "growth hacking",
]


def generate_batch2_skills_proficiency() -> int:
    for skill in ADDITIONAL_SKILLS:
        key = norm_key(f"soft_skill_{skill}")
        skill_lower = skill.lower()
        patterns = [
            f"rate your {skill_lower} skills",
            f"how would you rate your {skill_lower}",
            f"{skill_lower} proficiency",
            f"do you have {skill_lower} experience",
            f"are you good at {skill_lower}",
        ]
        itd = {
            "radio": "Advanced", "select": "Advanced", "text": "Advanced", "number": "4",
        }
        add_pat(key, patterns, "soft_skills", "Advanced", priority=6, itd=itd)

        # Add yes/no variant
        key2 = norm_key(f"soft_yn_{skill}")
        patterns2 = [
            f"do you have {skill_lower} skills",
            f"are you experienced in {skill_lower}",
            f"have you worked on {skill_lower}",
        ]
        add_pat(key2, patterns2, "yes_no", "Yes", priority=6,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})
    return len([k for k in P if k.startswith("soft_")])


# ---------------------------------------------------------------------------
# Batch 3: Synonym Expansions for existing high-frequency categories
# ---------------------------------------------------------------------------

def _add_synonym_cluster(key: str, patterns: List[str], category: str,
                         default: str, priority: int = 7,
                         itd: Dict[str, str] = None,
                         negative_patterns: List[str] = None):
    add_pat(key, patterns, category, default, priority=priority, itd=itd,
            negative_patterns=negative_patterns)


EXPERIENCE_PHRASINGS = [
    "total years of professional experience", "how much experience do you have",
    "years of professional experience", "total work experience",
    "overall experience", "career experience", "industry experience",
    "years of industry experience", "years of it experience",
    "years of relevant experience", "total relevant experience",
    "how many years have you worked", "years in the industry",
    "professional experience", "relevant work experience",
    "total years of relevant experience", "how long have you been working",
    "years of software development experience", "years of coding experience",
    "years of technical experience", "years of hands-on experience",
]

CURRENT_SALARY_PHRASINGS = [
    "what is your present ctc", "current annual gross salary",
    "current fixed annual salary", "current in hand salary", "current pay",
    "current ctc", "current total compensation", "current gross salary",
    "current annual ctc", "present annual ctc", "current package",
    "current remuneration", "current salary package", "existing ctc",
    "fixed component of current ctc", "current take home",
]

EXPECTED_SALARY_PHRASINGS = [
    "what is your desired ctc", "expected annual gross salary",
    "salary you are expecting", "expected in hand salary",
    "expected remuneration", "expected ctc", "expected salary",
    "desired ctc", "desired salary", "expected compensation",
    "salary expectation", "expected package", "expected pay",
    "salary asked", "compensation expected", "expected annual package",
]

NOTICE_PHRASINGS = [
    "what is the notice period in your current company",
    "how much notice period do you have", "your notice period duration",
    "how many days notice do you need", "time required to join",
    "what is your notice period", "notice period", "np", "joining period",
    "how soon can you join", "when can you join", "available to join",
    "how early can you join", "joining availability",
]

LOCATION_CURRENT_PHRASINGS = [
    "where do you currently live", "current city", "present location",
    "where are you based", "your current city", "current location",
    "where do you stay", "where do you reside", "present city",
    "city you currently live in", "base location",
]

LOCATION_PREFERRED_PHRASINGS = [
    "preferred work location", "desired location", "preferred city",
    "where would you like to work", "location of interest",
    "preferred job location", "preferred work city", "desired work location",
    "where do you want to work", "preferred location",
]

LANGUAGE_PHRASINGS = [
    "english proficiency", "hindi proficiency", "regional language proficiency",
    "language skills", "languages known", "languages you speak",
    "fluency in english", "fluency in hindi", "communication language",
    "native language", "proficiency in english",
]

EDUCATION_PHRASINGS = [
    "highest qualification", "highest degree", "educational qualification",
    "academic qualification", "degree completed", "graduation details",
    "college name", "university name", "year of passing",
    "percentage in graduation", "cgpa", "grade",
]

WORK_AUTH_PHRASINGS = [
    "do you require sponsorship", "will you require visa sponsorship",
    "are you authorized to work in india", "do you have work authorization for india",
    "legally eligible to work", "authorized to work", "legally authorized",
    "do you need visa sponsorship", "sponsorship required",
    "are you eligible to work", "work permit status",
]

RELOCATION_PHRASINGS = [
    "open to relocation", "willing to move", "can relocate to",
    "ready to relocate", "relocation flexibility", "willing to relocate",
    "open to moving", "relocation willing",
]

REMOTE_WORK_PHRASINGS = [
    "open to remote work", "willing to work remotely", "remote work preference",
    "work from home", "wfh", "remote first", "hybrid work",
    "do you prefer remote work", "comfortable with remote work",
]

IMMEDIATE_JOINING_PHRASINGS = [
    "can you join immediately", "immediate joiner", "can join within 15 days",
    "ready to join immediately", "available to start immediately",
    "how soon can you join", "can you join within a week",
    "are you serving notice", "serving notice period",
]


def generate_batch3_synonym_expansions() -> int:
    itd_exp = {"radio": "4", "select": "4 Years", "text": "4 Years", "number": "4"}
    itd_sal_curr = {"radio": "23", "select": "23 LPA", "text": "23 LPA", "number": "23"}
    itd_sal_exp = {"radio": "30", "select": "30 LPA", "text": "30 LPA", "number": "30"}
    itd_np = {
        "radio": "15 Days or less(Serving Notice)",
        "select": "Serving Notice Period",
        "text": "Serving Notice Period",
        "number": "15",
        "checkbox": "Less than a month",
    }
    itd_yes = {"radio": "Yes", "select": "Yes", "text": "Yes", "checkbox": "checked"}

    _add_synonym_cluster("experience_total_syn1", EXPERIENCE_PHRASINGS, "experience", "4 Years",
                         priority=3, itd=itd_exp, negative_patterns=["java", "python", "react", "salary", "notice"])

    _add_synonym_cluster("current_salary_phrases", CURRENT_SALARY_PHRASINGS, "salary", "23 LPA",
                         priority=7, itd=itd_sal_curr, negative_patterns=["expected", "ectc", "desired"])

    _add_synonym_cluster("expected_salary_phrases", EXPECTED_SALARY_PHRASINGS, "salary", "30 LPA",
                         priority=7, itd=itd_sal_exp, negative_patterns=["current", "cctc", "present"])

    _add_synonym_cluster("notice_period_phrases", NOTICE_PHRASINGS, "notice_period", "15 Days",
                         priority=9, itd=itd_np, negative_patterns=["salary", "ctc", "experience"])

    _add_synonym_cluster("location_current_phrases", LOCATION_CURRENT_PHRASINGS, "location", "Bangalore",
                         priority=8, itd={"radio": "Bangalore", "select": "Bangalore", "text": "Bangalore"},
                         negative_patterns=["preferred", "relocate"])

    _add_synonym_cluster("location_preferred_phrases", LOCATION_PREFERRED_PHRASINGS, "location",
                         "Bangalore, Delhi NCR, Hyderabad, Mumbai, Pune", priority=7,
                         negative_patterns=["current", "present", "stay"])

    _add_synonym_cluster("language_proficiency_phrases", LANGUAGE_PHRASINGS, "skills", "Fluent",
                         priority=6, itd={"radio": "Fluent", "select": "Fluent", "text": "Fluent"})

    _add_synonym_cluster("education_phrases", EDUCATION_PHRASINGS, "education", "B.E / B.Tech",
                         priority=7, itd={"radio": "B.E / B.Tech", "select": "B.E / B.Tech", "text": "B.E / B.Tech"})

    _add_synonym_cluster("work_authorization_syn", WORK_AUTH_PHRASINGS, "work_authorization",
                         "Yes, I am legally authorized to work in India.", priority=8,
                         itd={"radio": "Yes", "select": "Yes", "text": "Yes, I am legally authorized to work in India."})

    _add_synonym_cluster("willing_to_relocate_syn", RELOCATION_PHRASINGS, "location", "Yes",
                         priority=7, itd=itd_yes)

    _add_synonym_cluster("remote_work_syn", REMOTE_WORK_PHRASINGS, "work_mode", "Yes",
                         priority=7, itd=itd_yes)

    _add_synonym_cluster("immediate_joining_syn", IMMEDIATE_JOINING_PHRASINGS, "notice_period", "Yes",
                         priority=9, itd=itd_yes)

    # More specific question variants for common categories
    yes_no_variants = [
        "are you comfortable working", "are you open to", "do you have any",
        "do you have experience in", "have you ever", "do you currently",
        "are you willing to", "do you agree to", "can you provide",
        "are you available for", "would you be willing", "are you open for",
        "are you interested in", "do you consent to", "can you confirm",
        "are you ready to", "do you accept", "will you be able to",
        "are you fine with", "are you okay with", "do you have",
    ]
    for variant in yes_no_variants:
        key = norm_key(f"yes_no_{variant}")
        add_pat(key, [variant], "yes_no", "Yes", priority=5, itd=itd_yes)

    # Salary related phrases (do not override the existing take_home_salary entry)
    salary_phrases = [
        "fixed salary", "variable salary", "gross salary", "net salary",
        "ctc breakup", "salary structure",
        "basic salary", "hra", "bonus", "retention bonus",
        "performance bonus", "variable pay", "stock options",
        "esops", "rsu", "employee stock purchase", "profit sharing",
        "insurance", "medical insurance", "health insurance",
        "transport allowance", "food allowance", "internet allowance",
    ]
    for phrase in salary_phrases:
        key = norm_key(f"salary_{phrase}")
        add_pat(key, [phrase], "salary", "23 LPA", priority=6, itd=itd_sal_curr)

    # Availability phrases
    availability_phrases = [
        "available for discussion", "available for call",
        "available for meeting", "available for interview",
        "available to start", "when can you start", "start date",
        "joining date", "date of joining", "tentative joining date",
        "preferred joining date", "earliest joining date",
    ]
    for phrase in availability_phrases:
        key = norm_key(f"avail_{phrase}")
        add_pat(key, [phrase], "availability", "Yes", priority=6, itd=itd_yes)

    # Personal info phrases
    personal_phrases = [
        "full name", "first name", "last name", "middle name",
        "date of birth", "dob", "place of birth", "age",
        "gender", "nationality", "marital status", "blood group",
        "permanent address", "current address", "address",
        "alternate mobile", "alternate email", "secondary contact",
        "emergency contact", "relationship with emergency contact",
        "pan number", "aadhaar number", "passport number",
        "visa validity", "visa expiry", "work permit number",
    ]
    for phrase in personal_phrases:
        key = norm_key(f"personal_{phrase}")
        add_pat(key, [phrase], "personal_info", "Please provide", priority=8,
                itd={"text": "Please provide"}, exact=False)

    # Education phrases
    education_phrases = [
        "college name", "university name", "degree name",
        "branch", "specialization", "major", "minor",
        "year of passing", "graduation year", "passing year",
        "percentage", "cgpa", "grade", "marks",
        "roll number", "registration number", "enrollment number",
        "board of education", "state board", "cbse", "icse",
    ]
    for phrase in education_phrases:
        key = norm_key(f"edu_{phrase}")
        add_pat(key, [phrase], "education", "B.E / B.Tech", priority=7,
                itd={"text": "B.E / B.Tech", "select": "B.E / B.Tech"})

    # Work authorization more specific
    work_auth_phrases = [
        "citizenship", "nationality", "visa status", "work permit",
        "passport country", "country of citizenship",
        "are you a citizen", "do you have work authorization",
        "do you require sponsorship now or in the future",
        "will you now or in the future require sponsorship",
        "are you legally authorized to work in",
    ]
    for phrase in work_auth_phrases:
        key = norm_key(f"wa_{phrase}")
        add_pat(key, [phrase], "work_authorization",
                "Yes, I am legally authorized to work in India.", priority=8,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes, I am legally authorized to work in India."})

    # Compliance phrases (criminal record is intentionally omitted — handled
    # separately with answer "No" by the existing criminal_background pattern).
    compliance_phrases = [
        "background check", "background verification", "bgv",
        "drug test", "medical check", "reference check",
        "non compete", "non-disclosure", "nda", "non solicitation",
        "consent to process data", "privacy policy", "gdpr",
        "terms and conditions", "code of conduct", "ethics policy",
        "equal opportunity", "affirmative action", "diversity",
    ]
    for phrase in compliance_phrases:
        key = norm_key(f"compliance_{phrase}")
        add_pat(key, [phrase], "compliance", "Yes", priority=8,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    # Location relocation phrases
    location_phrases = [
        "willing to relocate within india", "willing to relocate abroad",
        "open to relocation within india", "open to relocation to us",
        "open to relocation to uk", "open to relocation to canada",
        "open to relocation to europe", "open to relocation to australia",
        "willing to relocate to bangalore", "willing to relocate to hyderabad",
        "willing to relocate to mumbai", "willing to relocate to pune",
        "willing to relocate to chennai", "willing to relocate to delhi",
        "willing to relocate to gurgaon", "willing to relocate to noida",
        "current location", "preferred location", "base location",
    ]
    for phrase in location_phrases:
        key = norm_key(f"loc_{phrase}")
        if "current" in phrase:
            add_pat(key, [phrase], "location", "Bangalore", priority=8,
                    itd={"text": "Bangalore", "select": "Bangalore"})
        else:
            add_pat(key, [phrase], "location", "Yes", priority=7,
                    itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    return len([k for k in P if "_syn" in k or "_phrases" in k or k.startswith(("yes_no_", "salary_", "avail_", "personal_", "edu_", "wa_", "compliance_", "loc_"))])


# ---------------------------------------------------------------------------
# Batch 4: New Categories
# ---------------------------------------------------------------------------
PROJECT_CATEGORIES = [
    "Enterprise Application", "E-commerce Platform", "Healthcare System",
    "Fintech Product", "EdTech Platform", "SaaS Product", "Mobile Application",
    "Data Pipeline", "Machine Learning Model", "Cloud Migration",
    "Microservices Architecture", "Real-time Analytics", "IoT Platform",
    "Blockchain Solution", "DevOps Automation", "Security Implementation",
    "CRM System", "ERP System", "CMS Platform", "Social Media App",
    "Payment Gateway", "Banking Application", "Insurance Platform",
    "Logistics Platform", "Travel Booking", "Food Delivery App",
    "Streaming Service", "Gaming Platform", "AI Product",
    "Data Warehouse", "Search Platform", "Recommendation Engine",
    "Customer Portal", "Admin Dashboard", "Analytics Platform",
    "Inventory Management", "HRMS", "LMS", "Marketplace",
    "Chatbot", "Voice Assistant", "Workflow Automation",
    "Sales Enablement Tool", "Marketing Automation", "Customer Support Platform",
    "Telemedicine Platform", "Online Learning", "Digital Wallet",
    "Cryptocurrency Exchange", "Supply Chain Platform", "Warehouse Management",
    "Project Management Tool", "Collaboration Tool", "Video Conferencing",
    "Cybersecurity Platform", "Identity Management", "Fraud Detection",
    "Quality Management System", "Document Management", "Asset Management",
    "Ticketing System", "Helpdesk", "Knowledge Base",
    "Reservation System", "Billing System", "Invoicing System",
    "Subscription Management", "Content Management", "Digital Asset Management",
    "Observability Platform", "Feature Flagging", "A/B Testing Platform",
    "Data Governance", "Master Data Management", "ETL Pipeline",
    "Reverse ETL", "Data Lake", "Data Mesh", "Data Catalog",
    "Data Quality Platform", "Feature Store", "Model Registry",
    "Experiment Tracking", "MLOps Platform", "AI Governance",
    "Cloud Cost Management", "FinOps Platform", "Sustainability Platform",
    "Carbon Accounting", "ESG Reporting", "Compliance Management",
    "Risk Management", "Audit Management", "Policy Management",
    "Vendor Management", "Procurement Platform", "Expense Management",
    "Payroll System", "Benefits Administration", "Time Tracking",
    "Attendance Management", "Performance Management", "Goal Management",
    "Learning Experience Platform", "Virtual Classroom", "Assessment Platform",
    "Remote Work Platform", "Digital Workplace", "Intranet",
    "Employee Engagement", "Survey Platform", "Feedback Platform",
    "Onboarding Platform", "Offboarding Platform", "Exit Management",
    "Applicant Tracking System", "Recruitment Platform", "Background Verification",
    "Identity Verification", "KYC Platform", "AML Platform",
    "Fraud Prevention", "Chargeback Management", "Dispute Resolution",
    "Subscription Billing", "Usage Based Billing", "Metered Billing",
    "Tax Management", "Invoice Factoring", "Payment Reconciliation",
    "Treasury Management", "Cash Management", "Financial Planning",
    "Budgeting Platform", "Forecasting Platform", "Investor Relations",
    "Crowdfunding Platform", "Peer to Peer Lending", "Neobank",
    "Insurance Claim", "Underwriting Platform", "Policy Administration",
    "Telehealth", "Electronic Health Record", "Practice Management",
    "Medical Billing", "Clinical Trial", "Patient Engagement",
    "Fitness Tracking", "Wellness Platform", "Mental Health Platform",
    "Smart Home", "Smart City", "Connected Vehicle",
    "Drone Management", "Robotics Platform", "Industrial IoT",
    "Predictive Maintenance", "Digital Twin", "Simulation Platform",
    "CAD Platform", "PLM System", "BIM Software",
    "Legal Practice Management", "Contract Lifecycle Management",
    "Document Automation", "E Signature Platform", "Notarization",
    "Virtual Event Platform", "Webinar Platform", "Community Platform",
    "Membership Management", "Donation Platform", "Fundraising Platform",
    "Loyalty Program", "Referral Program", "Affiliate Marketing",
    "Influencer Marketing", "Brand Monitoring", "Social Listening",
    "Review Management", "Reputation Management", "CRM",
    "News Aggregator", "Content Recommendation", "Personalization Engine",
    "Translation Platform", "Localization Platform", "Accessibility Tool",
    "Cybersecurity Training", "Phishing Simulation", "Vulnerability Management",
    "Threat Intelligence", "SIEM", "SOAR", "EDR",
    "Network Monitoring", "Bandwidth Management", "Load Balancing",
    "CDN", "Edge Computing", "Quantum Computing",
]

SOFT_SKILL_TRAITS = [
    "leadership", "teamwork", "communication", "problem solving",
    "adaptability", "creativity", "critical thinking", "time management",
    "emotional intelligence", "empathy", "negotiation", "decision making",
    "conflict management", "collaboration", "accountability",
    "initiative", "self motivation", "resilience", "stress management",
    "attention to detail", "organization", "planning", "multitasking",
    "work ethic", "integrity", "professionalism", "humility",
    "open mindedness", "curiosity", "growth mindset",
    "customer focus", "results orientation", "strategic thinking",
    "innovation", "agility", "flexibility", "patience", "diplomacy",
    "presentation skills", "mentoring", "coaching", "delegation",
    "active listening", "feedback", "transparency", "trust",
    "reliability", "dependability", "punctuality", "discipline",
    "resourcefulness", "perseverance", "determination", "optimism",
    "diplomacy", "tact", "assertiveness", "influence", "persuasion",
    "facilitation", "mediation", "arbitration", "conflict resolution",
    "brainstorming", "ideation", "design thinking", "systems thinking",
    "analytical thinking", "logical thinking", "lateral thinking",
    "data driven thinking", "evidence based decision making",
    "risk management", "crisis management",
    "vendor management", "client management", "partner management",
    "team building", "conflict coaching", "motivational skills",
    "cultural awareness", "cross cultural communication",
    "global mindset", "language skills", "writing skills",
    "verbal communication", "non verbal communication", "storytelling",
    "visual communication", "technical communication", "business communication",
    "interpersonal skills", "social skills", "networking", "relationship building",
    "sales skills", "marketing skills", "negotiation skills",
    "public speaking", "presentation delivery", "pitching",
    "teaching", "training", "knowledge sharing", "documentation",
    "requirement elicitation", "user research", "market research",
    "competitive analysis", "benchmarking", "gap analysis",
    "root cause analysis", "five whys", "fishbone analysis",
    "process improvement", "lean thinking", "six sigma",
    "quality management", "risk assessment", "compliance awareness",
    "ethical judgment", "decision making under uncertainty",
    "judgment", "common sense", "intuition", "wisdom",
    "self awareness", "self regulation", "self confidence",
    "mindfulness", "focus", "concentration", "deep work",
    "energy management", "work life balance", "boundaries",
    "boundless enthusiasm", "positive attitude", "grit",
    "tenacity", "drive", "ambition", "passion", "commitment",
    "loyalty", "engagement", "ownership", "pride in work",
    "craftsmanship", "excellence", "perfectionism balanced",
    "pragmatism", "realism", "idealism balanced",
    "diplomacy", "charm", "charisma", "likeability",
    "sense of humor", "approachability", "accessibility",
]

BEHAVIORAL_QUESTIONS = [
    ("conflict_resolution", "Describe a time you resolved a conflict",
     "I resolved the conflict by listening actively, finding common ground, and agreeing on a solution."),
    ("teamwork", "Tell us about a time you worked in a team",
     "I collaborated effectively, communicated openly, and supported team goals."),
    ("failure", "Describe a time you failed and what you learned",
     "I learned from the failure, analyzed what went wrong, and applied the lesson to future work."),
    ("initiative", "Describe a time you took initiative",
     "I identified an opportunity, proposed a solution, and drove it to completion."),
    ("pressure", "How do you handle pressure",
     "I prioritize tasks, stay organized, and focus on what I can control."),
    ("feedback", "Tell us about constructive feedback you received",
     "I accepted the feedback, reflected on it, and made improvements."),
    ("difficult_person", "How do you deal with a difficult coworker",
     "I remain professional, communicate directly, and seek common ground."),
    ("decision", "Describe a difficult decision you made",
     "I gathered information, weighed options, and made a well-reasoned decision."),
    ("leadership", "Describe a time you demonstrated leadership",
     "I stepped up to guide the team, clarified goals, and ensured successful delivery."),
    ("adaptability", "How do you adapt to change",
     "I stay open-minded, learn quickly, and adjust my approach as needed."),
    ("mistake", "Describe a mistake you made at work",
     "I owned the mistake, fixed it, and implemented safeguards to prevent recurrence."),
    ("goal", "Tell us about a goal you achieved",
     "I set a clear goal, created a plan, and worked consistently to achieve it."),
    ("disagreement", "Describe a time you disagreed with your manager",
     "I shared my perspective respectfully, discussed options, and supported the final decision."),
    ("deadline", "Describe a time you met a tight deadline",
     "I prioritized tasks, communicated progress, and delivered quality work on time."),
    ("challenge", "Describe a challenging project you worked on",
     "I broke down the challenge, sought help when needed, and delivered a successful outcome."),
    ("customer", "Describe a time you went above and beyond for a customer",
     "I understood the customer's needs and provided a solution that exceeded expectations."),
    ("learning", "How do you learn new technologies",
     "I combine documentation, hands-on projects, and community resources."),
    ("motivation", "What motivates you at work",
     "Solving meaningful problems and seeing the impact of my work."),
    ("strength", "What is your greatest strength",
     "My ability to learn quickly and solve complex problems collaboratively."),
    ("weakness", "What is your greatest weakness",
     "I sometimes focus too much on details, but I use checklists to balance it."),
    ("success", "Describe your greatest professional success",
     "I led a project that delivered significant business value and improved user experience."),
    ("innovation", "Describe a time you introduced innovation",
     "I proposed and implemented a solution that improved efficiency and reduced costs."),
    ("prioritization", "How do you prioritize tasks",
     "I prioritize based on impact, urgency, and dependencies."),
    ("communication", "Describe a time you communicated complex information",
     "I broke down the information clearly and tailored it to my audience."),
    ("ownership", "Describe a time you took ownership",
     "I took responsibility for the outcome and ensured the work was completed successfully."),
    ("risk", "Describe a time you managed risk",
     "I identified potential risks early and put mitigation plans in place."),
    ("mentoring", "Describe a time you mentored someone",
     "I provided guidance, shared knowledge, and supported their growth."),
    ("diversity", "How do you work with diverse teams",
     "I value different perspectives and create an inclusive environment."),
    ("quality", "How do you ensure quality in your work",
     "I follow best practices, review my work, and seek feedback."),
    ("scope_creep", "How do you handle scope creep",
     "I communicate impact, document changes, and align with stakeholders."),
    ("ambiguity", "How do you handle ambiguous requirements",
     "I ask clarifying questions, make reasonable assumptions, and validate early."),
    ("burnout", "How do you prevent burnout",
     "I maintain work-life balance, take breaks, and prioritize effectively."),
    ("ethics", "Describe an ethical dilemma you faced",
     "I followed company policies and chose the option that upheld integrity."),
    ("growth", "How do you seek growth opportunities",
     "I set goals, seek feedback, and take on stretch assignments."),
    ("boredom", "How do you handle repetitive tasks",
     "I automate where possible and find ways to improve the process."),
    ("overqualified", "Why would you take this role if you seem overqualified",
     "I am excited by the challenge and the opportunity to make an impact."),
    ("gap", "Explain a gap in your employment",
     "I used the time for upskilling, personal projects, and family responsibilities."),
    ("relocation", "Why do you want to relocate",
     "I am seeking better career opportunities and growth."),
    ("salary_expectation", "What are your salary expectations",
     "I am looking for a competitive package aligned with my skills and experience."),
    ("dream_job", "What is your dream job",
     "A role where I can solve challenging problems and continuously grow."),
    ("hobby", "What do you do in your free time",
     "I enjoy learning, side projects, and staying active."),
    ("question", "Do you have any questions for us",
     "Yes, I would love to learn more about the team and growth opportunities."),
    ("ideal_workplace", "Describe your ideal workplace",
     "A collaborative environment that values learning and innovation."),
    ("supervisor", "What kind of supervisor do you work best with",
     "Someone who provides clear goals, autonomy, and constructive feedback."),
    ("team_culture", "What kind of team culture do you prefer",
     "A culture of transparency, collaboration, and continuous improvement."),
    ("remote_work_experience", "Describe your remote work experience",
     "I have successfully worked remotely, staying productive and communicative."),
    ("documentation", "How do you document your work",
     "I write clear docs, diagrams, and comments for maintainability."),
    ("legacy_code", "How do you handle legacy code",
     "I understand it first, write tests, and refactor incrementally."),
    ("technical_debt", "How do you manage technical debt",
     "I prioritize paying it down incrementally and prevent it through reviews."),
    ("debugging", "Describe your debugging process",
     "I reproduce the issue, isolate the cause, and verify the fix."),
]

CAREER_GOALS = [
    "short term goal", "long term goal", "career aspiration",
    "where do you see yourself in 5 years", "5 year plan",
    "career objective", "professional goal", "career path",
    "where do you see yourself in 10 years", "future plans",
    "career growth", "professional development", "learning goals",
    "aspirations", "career milestone",
]

INTERVIEW_TYPES = [
    "phone interview", "video interview", "virtual interview",
    "in person interview", "onsite interview", "technical interview",
    "coding interview", "behavioral interview", "panel interview",
    "screening interview", "hr interview", "manager interview",
    "system design interview", "take home assignment", "live coding",
    "whiteboard interview", "pair programming interview", "final round",
    "initial screening", "recruiter screen", "hr screening",
    "culture fit interview", "case study interview", "portfolio review",
    "assignment review", "project discussion", "architecture review",
    "code review interview", "debugging interview", "algorithm interview",
    "data structures interview", "database interview", "frontend interview",
    "backend interview", "full stack interview", "devops interview",
    "machine learning interview", "data science interview",
    "product interview", "design interview", "ux interview",
    "leadership interview", "executive interview", "director interview",
    "vp interview", "cto interview", "ceo interview",
    "team interview", "peer interview", "cross functional interview",
    "client interview", "stakeholder interview", "vendor interview",
    "group discussion", "aptitude test", "psychometric test",
    "personality test", "english assessment", "verbal reasoning",
    "numerical reasoning", "logical reasoning", "abstract reasoning",
    "wipro interview", "tcs interview", "infosys interview",
    "google interview", "amazon interview", "facebook interview",
    "microsoft interview", "apple interview", "netflix interview",
    "startup interview", "mnc interview", "consulting interview",
    "walk in interview", "scheduled interview", "rescheduled interview",
    "group interview", "one on one interview", "structured interview",
    "unstructured interview", "competency based interview",
    "stress interview", "case interview", "situational interview",
]

DOMAINS = [
    "fintech", "healthcare", "ecommerce", "edtech", "logistics",
    "retail", "manufacturing", "automotive", "media", "gaming",
    "banking", "insurance", "travel", "hospitality", "real estate",
    "telecom", "energy", "government", "nonprofit", "sas",
    "cybersecurity", "data analytics", "artificial intelligence",
    "blockchain", "iot", "cloud computing",
    "space technology", "satellite", "drones", "robotics",
    "autonomous vehicles", "electric vehicles", "clean energy",
    "renewable energy", "climate tech", "carbon capture",
    "circular economy", "sustainable fashion", "agritech",
    "foodtech", "watertech", "waste management", "recycling",
    "green building", "smart infrastructure", "proptech",
    "legaltech", "regtech", "insurtech", "wealthtech",
    "crypto", "blockchain", "web3", "defi", "nft",
    "metaverse", "ar/vr", "mixed reality", "spatial computing",
    "voice tech", "conversational ai", "generative ai",
    "ai ethics", "ai safety", "responsible ai",
    "quantum computing", "edge ai", "federated learning",
    "digital health", "telemedicine", "diagnostics",
    "medical devices", "wearables", "healthtech",
    "mental health", "wellness", "fitness", "nutrition",
    "edtech", "corporate training", "online learning",
    "hrtech", "recruitment", "payroll", "benefits",
    "retailtech", "e-commerce", "marketplace",
    "supply chain", "procurement", "inventory",
    "cybersecurity", "data privacy", "identity",
    "devtools", "nocode", "lowcode", "productivity",
    "collaboration", "communication", "email",
    "social media", "content", "creator economy",
    "adtech", "martech", "adtech platform",
    "sportstech", "gaming industry", "esports",
    "media streaming", "music", "podcast", "publishing",
    "news", "journalism", "public relations",
    "interior design", "architecture", "urban planning",
    "civil engineering", "mechanical engineering",
    "electrical engineering", "chemical engineering",
    "marine", "aviation", "railways",
    "shipping", "ports", "warehousing",
    "mining", "oil and gas", "petrochemicals",
    "textiles", "apparel", "footwear",
    "furniture", "home decor", "consumer durables",
    "appliances", "electronics manufacturing",
    "semiconductors", "chip design", "hardware",
    "instrumentation", "automation", "control systems",
]

CERTIFICATIONS = [
    "AWS Solutions Architect", "AWS Developer", "AWS DevOps Engineer",
    "Azure Administrator", "Azure Solutions Architect", "Azure DevOps Engineer",
    "Google Cloud Professional", "Google Cloud Architect",
    "Certified Kubernetes Administrator", "Certified Kubernetes Application Developer",
    "Docker Certified Associate", "HashiCorp Terraform Associate",
    "CCNA", "CompTIA Security+", "CISSP", "CEH", "OSCP",
    "PMP", "Scrum Master", "Product Owner", "Agile Coach",
    "Oracle Certified Professional", "MongoDB Certified Developer",
    "Salesforce Administrator", "Salesforce Platform Developer",
    "ISTQB", "Selenium Certification", "Tableau Desktop Specialist",
    "AWS Solutions Architect Professional", "AWS Security Specialty",
    "AWS Machine Learning Specialty", "AWS Data Analytics Specialty",
    "Azure AI Engineer", "Azure Data Engineer", "Azure Security Engineer",
    "Google Cloud Data Engineer", "Google Cloud Security Engineer",
    "CKAD", "CKS", "CKA", "Terraform Associate", "Vault Associate",
    "Consul Associate", "Nomad Associate", "Boundary Associate",
    "Red Hat Certified Engineer", "Red Hat Certified Administrator",
    "Linux Foundation Certified Engineer", "Linux Foundation Certified Administrator",
    "Cisco CCNP", "Cisco CCIE", "Juniper JNCIA", "Juniper JNCIS",
    "Certified Ethical Hacker", "Offensive Security Certified Professional",
    "Certified Information Security Manager", "Certified Cloud Security Professional",
    "PMI Agile Certified Practitioner", "PMI Risk Management Professional",
    "Certified Scrum Product Owner", "Certified Scrum Master",
    "Scaled Agile Framework", "SAFe Agilist", "SAFe Scrum Master",
    "Six Sigma Green Belt", "Six Sigma Black Belt", "ITIL Foundation",
    "COBIT", "TOGAF", "ArchiMate", "Certified Information Systems Auditor",
    "Certified Internal Auditor", "Certified Public Accountant",
    "Chartered Financial Analyst", "Financial Risk Manager",
    "Certified Data Professional", "Cloudera Certified Data Analyst",
    "Databricks Data Engineer Associate", "Databricks Data Engineer Professional",
    "Snowflake Core Certification", "Snowflake Advanced Architect",
    "dbt Analytics Engineering", "Google Analytics Certification",
    "HubSpot Inbound Marketing", "Google Ads Certification",
    "Meta Blueprint Certification", "LinkedIn Marketing Certification",
]


def generate_batch4_new_categories() -> int:
    # project_details
    for project in PROJECT_CATEGORIES:
        key = norm_key(f"project_{project}")
        p_name = project.lower()
        add_pat(key, [
            f"describe your {p_name} project",
            f"tell me about a {p_name} project",
            f"{p_name} project details",
            f"explain your {p_name} project",
            f"share details of your {p_name} project",
            f"have you worked on a {p_name}",
            f"{p_name} project experience",
        ], "preference",
        f"Worked on {project} involving design, development, testing, and deployment.",
        priority=6)

    # soft skill traits
    for trait in SOFT_SKILL_TRAITS:
        key = norm_key(f"soft_trait_{trait}")
        trait_lower = trait.lower()
        add_pat(key, [
            f"rate your {trait_lower}",
            f"how do you rate your {trait_lower}",
            f"{trait_lower} skills",
            f"do you have {trait_lower}",
            f"describe your {trait_lower}",
        ], "soft_skills", "Advanced", priority=6,
                itd={"radio": "Advanced", "select": "Advanced", "text": "Advanced"})

    # achievements
    achievement_types = [
        "award", "certification", "publication", "patent", "recognition",
        "promotion", "scholarship", "hackathon", "open source contribution",
        "performance award", "client appreciation", "leadership award",
        "best performer", "employee of the month", "innovation award",
        "top performer", "academic achievement", "sports achievement",
    ]
    for ach in achievement_types:
        key = norm_key(f"achievement_{ach}")
        add_pat(key, [
            f"describe your {ach}",
            f"any {ach} you received",
            f"tell us about your {ach}",
            f"mention your {ach}",
            f"have you received any {ach}",
        ], "preference", "Received recognition for outstanding contribution and impact.", priority=6)

    # career goals
    for goal in CAREER_GOALS:
        key = norm_key(f"career_{goal}")
        add_pat(key, [
            f"what is your {goal}",
            f"describe your {goal}",
            f"tell us about your {goal}",
            f"explain your {goal}",
        ], "preference",
        "Aiming to grow as a senior engineer, solve impactful problems, and lead initiatives.",
        priority=5)

    # behavioral questions
    for key, question, answer in BEHAVIORAL_QUESTIONS:
        add_pat(key, [
            question.lower(),
            f"{question.lower()}?",
            f"give an example of {question.lower()}",
            f"can you {question.lower()}",
        ], "soft_skills", answer, priority=5)

    # interview preferences
    for pref in INTERVIEW_TYPES:
        key = norm_key(f"pref_{pref}")
        add_pat(key, [
            f"are you comfortable with {pref}",
            f"available for {pref}",
            f"can you attend {pref}",
            f"are you open to {pref}",
        ], "availability", "Yes", priority=6,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes, available."})

    # domain specific
    for domain in DOMAINS:
        key = norm_key(f"domain_{domain}")
        add_pat(key, [
            f"do you have {domain} experience",
            f"{domain} domain experience",
            f"experience in {domain}",
            f"have you worked in {domain}",
            f"{domain} industry experience",
        ], "experience", "4 Years", priority=7, itd={
            "radio": "4", "select": "4 Years", "text": "4 Years", "number": "4"
        })

    # certifications
    for cert in CERTIFICATIONS:
        key = norm_key(f"cert_{cert}")
        add_pat(key, [
            f"do you hold {cert} certification",
            f"are you {cert} certified",
            f"{cert} certification",
            f"have you completed {cert}",
        ], "education", "Yes", priority=6,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    # languages spoken
    languages = ["English", "Hindi", "Spanish", "French", "German", "Mandarin",
                 "Japanese", "Korean", "Arabic", "Portuguese", "Russian",
                 "Tamil", "Telugu", "Marathi", "Bengali", "Gujarati",
                 "Kannada", "Malayalam", "Punjabi", "Urdu"]
    for lang in languages:
        key = norm_key(f"lang_{lang}")
        lang_lower = lang.lower()
        add_pat(key, [
            f"do you speak {lang_lower}",
            f"{lang_lower} language proficiency",
            f"are you proficient in {lang_lower}",
            f"{lang_lower} fluency",
        ], "skills", "Fluent", priority=6,
                itd={"radio": "Fluent", "select": "Fluent", "text": "Fluent"})

    # work preferences
    pref_topics = [
        "overtime", "weekend work", "night shift", "rotational shift",
        "travel", "business travel", "relocation", "remote work",
        "hybrid work", "onsite work", "contract role", "full time role",
        "part time role", "freelance", "internship", "temporary role",
    ]
    for topic in pref_topics:
        key = norm_key(f"pref_{topic}")
        topic_lower = topic.lower()
        add_pat(key, [
            f"are you open to {topic_lower}",
            f"willing to {topic_lower}",
            f"do you accept {topic_lower}",
            f"comfortable with {topic_lower}",
        ], "preference", "Yes", priority=6,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    return len([k for k in P if k.startswith(("project_", "soft_trait_", "achievement_",
                                               "career_", "pref_", "domain_", "cert_",
                                               "lang_"))])


# ---------------------------------------------------------------------------
# Batch 5: Platform-Specific Patterns
# ---------------------------------------------------------------------------
WORKDAY_PHRASINGS = [
    "please select the value", "please choose one", "required field",
    "enter a value", "select from dropdown", "workday screening",
    "please enter a valid", "this field is required workday",
]
GREENHOUSE_PHRASINGS = [
    "drop files here", "upload resume", "paste resume",
    "how did you hear about us", "referral source",
    "greenhouse application", "additional documents",
]
LEVER_PHRASINGS = [
    "application", "additional information", "voluntary disclosure",
    "lever application", "equal opportunity",
]
ICIMS_PHRASINGS = [
    "screening questions", "qualifying questions", "pre-screen",
    "icims application", "talent acquisition",
]
TALEO_PHRASINGS = [
    "oracle taleo", "taleo application", "oracle recruiting",
    "taleo screening", "oracle cloud recruiting",
]
WORKABLE_PHRASINGS = [
    "workable application", "workable screening", "workable assessment",
]


def generate_batch5_platform_specific() -> int:
    for phrasing in WORKDAY_PHRASINGS:
        key = norm_key(f"workday_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    for phrasing in GREENHOUSE_PHRASINGS:
        key = norm_key(f"greenhouse_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    for phrasing in LEVER_PHRASINGS:
        key = norm_key(f"lever_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    for phrasing in ICIMS_PHRASINGS:
        key = norm_key(f"icims_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    for phrasing in TALEO_PHRASINGS:
        key = norm_key(f"taleo_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    for phrasing in WORKABLE_PHRASINGS:
        key = norm_key(f"workable_{phrasing}")
        add_pat(key, [phrasing], "yes_no", "Yes", priority=2,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    # Common platform fields
    platform_fields = [
        "linkedin profile", "portfolio website", "github url",
        "twitter handle", "personal website", "blog url",
        "cover letter", "resume/CV", "transcript", "certification document",
        "reference contact", "emergency contact", "pan card", "aadhaar",
        "passport number", "driving license", "visa status",
    ]
    for field in platform_fields:
        key = norm_key(f"field_{field}")
        add_pat(key, [field, f"please provide your {field}"], "preference",
                "https://example.com/profile", priority=6)

    return len([k for k in P if k.startswith(("workday_", "greenhouse_", "lever_", "icims_",
                                               "taleo_", "workable_", "field_"))])


# ---------------------------------------------------------------------------
# Batch 6: Miscellaneous / Fill-in-the-gap patterns
# ---------------------------------------------------------------------------
def generate_batch6_miscellaneous() -> int:
    # Hobbies and interests
    hobbies = [
        "reading", "writing", "traveling", "photography", "music",
        "sports", "fitness", "gaming", "cooking", "painting",
        "volunteering", "mentoring", "public speaking", "blogging",
        "open source", "competitive programming", "hiking", "cycling",
        "yoga", "meditation", "chess", "gardening", "diy projects",
    ]
    for hobby in hobbies:
        key = norm_key(f"hobby_{hobby}")
        add_pat(key, [
            f"what are your hobbies",
            f"interested in {hobby}",
            f"do you like {hobby}",
            f"hobbies and interests",
        ], "preference", f"{hobby.title()}, continuous learning, and technology." , priority=4)

    # References
    references = [
        "professional reference", "personal reference", "reference contact",
        "emergency contact", "contact person", "reference name",
        "relationship with reference", "reference phone", "reference email",
    ]
    for ref in references:
        key = norm_key(f"ref_{ref}")
        add_pat(key, [ref], "personal_info", "Available upon request", priority=8,
                itd={"text": "Available upon request"})

    # Notice period negotiation
    np_topics = [
        "buyout", "negotiable notice", "notice period negotiable",
        "can you reduce notice period", "early release possible",
        "will current employer release early", "notice period waiver",
    ]
    for topic in np_topics:
        key = norm_key(f"np_{topic}")
        add_pat(key, [topic], "notice_period", "Yes", priority=8,
                itd={"radio": "Yes", "select": "Yes", "text": "Yes"})

    # Job search status (avoid overlap with existing notice_period / serving_notice patterns)
    job_search_status = [
        "actively looking", "passively looking", "not looking",
        "open to opportunities", "exploring opportunities",
        "immediately available",
    ]
    for status in job_search_status:
        key = norm_key(f"js_{status}")
        add_pat(key, [f"job search status {status}", status], "employment",
                "Open to new opportunities", priority=7,
                itd={"radio": "Open to new opportunities", "select": "Open to new opportunities", "text": "Open to new opportunities"})

    # Application source
    sources = [
        "linkedin", "naukri", "instahyre", "company website",
        "referral", "friend", "recruiter", "job board", " Indeed",
        "glassdoor", "monster", "shine", "timesjobs",
    ]
    for source in sources:
        key = norm_key(f"source_{source}")
        add_pat(key, [f"how did you hear about us {source}", f"source {source}"],
                "preference", f"{source.title()}", priority=6)

    # Social profiles
    social_profiles = [
        "linkedin url", "github url", "gitlab url", "stackoverflow url",
        "twitter url", "medium url", "dev.to url", "personal website",
        "portfolio url", "blog url", "youtube url",
    ]
    for profile in social_profiles:
        key = norm_key(f"social_{profile}")
        add_pat(key, [profile, f"please provide your {profile}"],
                "preference", "https://example.com/profile", priority=6)

    # Why this company / role
    motivation_questions = [
        "why do you want to work here", "why this company",
        "why do you want this job", "what interests you about this role",
        "why should we hire you", "what makes you a good fit",
        "why are you applying for this position", "what attracted you to this role",
    ]
    for q in motivation_questions:
        key = norm_key(f"motivation_{q}")
        add_pat(key, [q], "preference",
                "The role aligns with my skills and career goals.", priority=6)

    # Additional comments / cover letter
    additional = [
        "additional comments", "additional information",
        "anything else you want to add", "cover letter", "message to recruiter",
        "summary", "professional summary", "about yourself",
        "tell us about yourself", "describe yourself",
        "is there anything else we should know", "remarks", "notes",
        "additional details", "supporting information", "supplementary info",
        "final comments", "closing statement", "personal statement",
        "statement of purpose", "objective", "career objective",
        "summary of qualifications", "key achievements", "key accomplishments",
        "highlights", "career highlights", "professional highlights",
        "value proposition", "elevator pitch", "self introduction",
        "introduce yourself", "walk me through your resume",
        "tell me about your background", "give us a brief overview",
        "short bio", "biography", "about me section",
        "candidate summary", "applicant summary", "recruiter note",
        "special instructions", "additional instructions",
        "anything to add", "further comments", "other comments",
        "other information", "other details", "other considerations",
    ]
    for item in additional:
        key = norm_key(f"additional_{item}")
        add_pat(key, [item], "preference",
                "Experienced software engineer with strong problem-solving skills.", priority=5)

    return len([k for k in P if k.startswith(("hobby_", "ref_", "np_", "js_",
                                               "source_", "social_", "motivation_", "additional_"))])


# ---------------------------------------------------------------------------
# Meta categories
# ---------------------------------------------------------------------------
def add_new_category_meta() -> None:
    # No new categories needed; we reuse existing ones.
    pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Generating 5000+ new patterns...")
    counts = {}

    counts["batch1_tech_experience"] = generate_batch1_tech_skills_experience()
    print(f"  Batch 1 (Tech Skills Experience): {counts['batch1_tech_experience']} entries")

    counts["batch2_skills_proficiency"] = generate_batch2_skills_proficiency()
    print(f"  Batch 2 (Skills Proficiency): {counts['batch2_skills_proficiency']} entries")

    counts["batch3_synonym_expansions"] = generate_batch3_synonym_expansions()
    print(f"  Batch 3 (Synonym Expansions): {counts['batch3_synonym_expansions']} entries")

    counts["batch4_new_categories"] = generate_batch4_new_categories()
    print(f"  Batch 4 (New Categories): {counts['batch4_new_categories']} entries")

    counts["batch5_platform_specific"] = generate_batch5_platform_specific()
    print(f"  Batch 5 (Platform-Specific): {counts['batch5_platform_specific']} entries")

    counts["batch6_miscellaneous"] = generate_batch6_miscellaneous()
    print(f"  Batch 6 (Miscellaneous): {counts['batch6_miscellaneous']} entries")

    add_new_category_meta()

    payload = {"patterns": P, "categories": C, "metadata": {"source": "generate_all_new_patterns.py"}}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total_patterns = len(P)
    total_synonyms = sum(len(p["patterns"]) for p in P.values())
    print(f"\n✅ Done. Generated {total_patterns} new pattern entries with {total_synonyms} synonyms.")
    print(f"Payload written to: {OUT_PATH}")


if __name__ == "__main__":
    main()
