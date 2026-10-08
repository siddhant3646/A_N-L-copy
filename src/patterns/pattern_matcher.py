from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple, Optional
import re
from collections import defaultdict
from datetime import datetime, timedelta

from .pattern_loader import PatternLoader
from .answer_validator import AnswerValidator


CATEGORY_KEYWORDS = {
    'salary': ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc', 'per annum', 'annual', 'fixed', 'variable', 'take home', 'monthly'],
    'experience': ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp', 'total exp'],
    'notice_period': ['notice', 'serving', 'join', 'availability', 'np', 'lwd', 'last working day', 'buyout', 'negotiable'],
    'location': ['location', 'city', 'relocate', 'preferred location', 'based in', 'located in', 'commute', 'relocation', 'locality', 'zone', 'residential', 'neighborhood'],
    'skills': ['proficiency', 'rate', 'scale', 'tech stack', 'libraries', 'database', 'dsa', 'algorithms', 'knowledge', 'framework', 'siem', 'soc', 'threat'],
    'yes_no': ['willing', 'comfortable', 'open to', 'are you', 'do you', 'have you', 'can you', 'ok to', 'okay'],
    'work_mode': ['remote', 'hybrid', 'wfh', 'wfo', 'work from', 'days working', 'office'],
    'availability': ['interview', 'available', 'join date', 'start date', 'joining', 'f2f', 'walk-in', 'walk in', 'drive'],
    'data_consent': ['consent', 'privacy', 'data', 'collect', 'store', 'process'],
    'education': ['degree', 'graduation', 'university', 'college', 'gpa', 'qualification', 'academic', '10th', '12th', 'cgpa', 'percentage', 'marks', 'backlog', 'arrears', 'gap', 'regular'],
    'personal_info': ['name', 'email', 'phone', 'address', 'gender', 'dob', 'date of birth', 'passport', 'pronouns'],
    'employment': ['current company', 'current organization', 'employer', 'designation', 'role', 'title', 'payroll', 'permanent', 'contract', 'which company', 'working at', 'work for', 'company'],
    'self_identification': ['disability', 'veteran', 'gender', 'race', 'ethnicity', 'identity', 'hispanic', 'latino', 'pronouns'],
    'work_authorization': ['authorized', 'visa', 'work permit', 'legally', 'citizenship', 'sponsorship', 'citizen'],
    'compliance': ['criminal', 'background', 'bond', 'nda', 'conflict', 'felony', 'conviction', 'non-compete', 'non compete', 'cooling', 'applied in the past', 'disciplinary', 'bgv', 'drug screen'],
}


class PatternMatcher:
    DEFAULT_THRESHOLD = 0.65

    def __init__(self, patterns: Dict[str, Any], threshold: float = DEFAULT_THRESHOLD):
        self.patterns = patterns
        self.threshold = threshold
        self._pattern_cache: Dict[str, List[str]] = {}
        self._norm_pattern_cache: Dict[str, List[str]] = {}
        self._negative_cache: Dict[str, List[str]] = {}
        self._category_index: Dict[str, List[str]] = defaultdict(list)
        self._build_index()

    def _build_index(self):
        if 'patterns' not in self.patterns:
            return
        for pattern_id, pattern_data in self.patterns['patterns'].items():
            strs = pattern_data.get('patterns', [])
            if strs:
                self._pattern_cache[pattern_id] = strs
                self._norm_pattern_cache[pattern_id] = [
                    self._normalize(s) for s in strs if self._normalize(s)
                ]
                cat = pattern_data.get('category', 'unknown')
                self._category_index[cat].append(pattern_id)
            negs = pattern_data.get('negative_patterns', [])
            if negs:
                self._negative_cache[pattern_id] = [n.lower() for n in negs]

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        # Preserve programming language symbols before stripping punctuation
        text = re.sub(r'\bc\+\+\b', 'cpp', text)
        text = re.sub(r'\bc#\b', 'csharp', text)
        text = re.sub(r'\.net\b', 'dotnet', text)
        # Normalize common abbreviations and typos in experience questions
        text = re.sub(r'\b(expr|experince|experiance)\b', 'experience', text)
        # Strip common form label boilerplates
        text = re.sub(r'\b(this field is required|required|optional)\b', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = ' '.join(text.split())
        return text.strip()

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _detect_categories(self, question: str) -> List[Tuple[str, int]]:
        q = question.lower()
        scores = []
        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > 0:
                scores.append((cat, score))
        scores.sort(key=lambda x: -x[1])
        return scores

    def _passes_negative(self, pattern_id: str, question_lower: str) -> bool:
        negs = self._negative_cache.get(pattern_id, [])
        if not negs:
            return True
        for neg in negs:
            if neg in question_lower:
                return False
        return True

    def _resolve_question_intent(self, question: str, answer: Optional[str], score: float, input_type: str = None) -> Tuple[Optional[str], float]:
        if not answer or score <= 0.0:
            return answer, score

        ql = question.lower().strip()
        al = answer.strip()

        # 0. Detect LWD (Official Last Working Day / Date) questions
        is_lwd = bool(re.search(r'\b(last working day|last working date|official last working|official last working day|lwd)\b', ql))
        if is_lwd:
            lwd_date = datetime.now() + timedelta(days=15)
            lwd_formatted = lwd_date.strftime('%d %b %Y')
            if al in ('15', '15 days', 'yes', 'no') or not re.search(r'\d{4}|[A-Za-z]{3}', al):
                return lwd_formatted, max(score, 0.98)

        # 0a. Privacy & Data Consent safety guard (prevent number hijacking e.g. "for up to 2 years")
        is_privacy_consent = bool(re.search(r'\b(privacy policy|data consent|allowing .* contact|contact me about future|future job opportunities)\b', ql))
        if is_privacy_consent:
            return ('Yes' if (input_type in ('radio', 'checkbox', 'select') or al in ('4', '4.2', '5', '50', '2')) else answer), max(score, 0.98)

        # 0b. Offers in Hand safety guard (prevent current CTC hijacking e.g. "mention if any with CTC offered")
        is_offers_in_hand = bool(re.search(r'\b(offers? in hand|competing offers?|other offers?)\b', ql))
        if is_offers_in_hand:
            if 'else 0' in ql or 'else mention 0' in ql or 'amount in lpa' in ql:
                return '0', max(score, 0.98)
            if al in ('23', '23 LPA', '2300000', '30', '30 LPA') or al.isdigit():
                return ('None' if input_type in ('text', 'textarea', None) else 'No'), max(score, 0.98)

        # 0c. Industry / Domain Project inquiry (prevent CTC hijacking)
        is_industry_project = bool(re.search(r'\b(industry|domain)\b', ql) and re.search(r'\b(life science|banking|insurance|finance|telecom|retail)\b', ql) and re.search(r'\b(project|projects|mention name)\b', ql))
        if is_industry_project:
            return 'BFSI - Dispute Expert Toolkit & Real-time Settlement Reporting System (Everbridge)', max(score, 0.98)

        # 0d. Salary cut below minimum acceptable threshold guardrail (e.g. "ok with 12 to 13 lpa")
        is_low_salary_offer = bool(re.search(r'\b(ok with|comfortable with|accept)\b.*?\b(\d{1,2})\s*(?:to|-)\s*(\d{1,2})\s*lpa\b', ql))
        if is_low_salary_offer:
            m = re.search(r'\b(\d{1,2})\s*(?:to|-)\s*(\d{1,2})\s*lpa\b', ql)
            if m and float(m.group(2)) < 20:
                return 'No', max(score, 0.98)

        # 0e. Fresher / Graduation in 2025/2026 guardrail
        is_fresher_grad = bool(re.search(r'\b(completing|graduating|bachelor\'?s?)\b', ql) and re.search(r'\b(2025|2026)\b', ql))
        if is_fresher_grad:
            return 'No', max(score, 0.98)

        # 0f. System Design - URL shortener (TinyURL) high-level architecture
        if bool(re.search(r'\b(tinyurl|url shortener)\b', ql)):
            tinyurl_ans = (
                "A high-level URL shortener system (TinyURL) comprises: "
                "1) API: POST /api/v1/shorten (accepts longURL, returns shortURL) and GET /{shortCode} (HTTP 301/302 redirect). "
                "2) Short Code Generation: Base62 encoding (using unique 64-bit distributed IDs from Snowflake/Zookeeper) or MurmurHash3 truncated to 7 characters (handling collisions via DB lookup/salt). "
                "3) Storage: Distributed NoSQL/Key-Value store (DynamoDB/Cassandra) or PostgreSQL (sharded by shortCode hash) storing {short_code, original_url, user_id, created_at, expires_at}. "
                "4) High-Throughput Read Caching: Redis cluster caching top 20% most accessed URLs with LRU eviction. "
                "5) Scalability & Availability: Stateless application servers behind an API Gateway with rate limiting (Token Bucket), Kafka for asynchronous analytics/click-tracking ingestion, and global CDN caching."
            )
            return tinyurl_ans, max(score, 0.98)

        # 0g. Scalable Backend System / High-Traffic Architecture
        if bool(re.search(r'\b(scalable backend system|architecture would you choose|design a scalable|design scalable backend)\b', ql)):
            return (
                "I would choose an event-driven microservices architecture using Java/Spring Boot for core domain services, "
                "PostgreSQL with read replicas and connection pooling (HikariCP) for ACID transaction data (orders/payments), "
                "Redis for low-latency distributed caching, and Apache Kafka for asynchronous order/payment event streams. "
                "The architecture incorporates an API Gateway with token-bucket rate limiting, load balancing, idempotent API endpoints, "
                "and horizontal pod autoscaling on Kubernetes with multi-AZ deployment to guarantee high availability, fault tolerance, "
                "and sub-second latency under peak traffic."
            ), max(score, 0.98)

        # 0h. Robust & Secure REST APIs in Spring Boot Best Practices
        if bool(re.search(r'\b(robust and secure rest apis|best practices do you follow.*spring boot|spring boot.*best practices)\b', ql)) or ('secure rest apis' in ql and 'spring boot' in ql):
            return (
                "I implement RESTful principles with versioned endpoints, Spring Security with OAuth2/JWT for stateless authentication, "
                "and role-based access control (RBAC). Key best practices include: 1) Strict input validation via Hibernate Validator (@Valid), "
                "2) Centralized exception handling via @RestControllerAdvice returning standardized RFC 7807 problem details, "
                "3) DTO separation with MapStruct to prevent entity leakage, 4) Idempotent endpoints with unique idempotency keys for mutations, "
                "5) Connection pooling (HikariCP) and pagination for data retrieval, 6) Structured logging with correlation IDs (MDC/Micrometer) for distributed tracing, "
                "and 7) OpenAPI/Swagger documentation and OWASP top 10 security headers."
            ), max(score, 0.98)

        # 0i. Equity / ESOP in Current Company
        is_equity_q = bool(re.search(r'\b(hold(ing)?\s+(any\s+)?equity|equity\s+in(\s+the)?\s+current|esop|stock\s+options?\s+in)\b', ql) or
                           ('equity' in ql and ('current company' in ql or 'employer' in ql or 'hold' in ql)))
        if is_equity_q:
            return 'No', max(score, 0.98)

        # 0j. Address
        is_address_q = bool(ql in ('address', 'current address', 'permanent address', 'residential address', 'street address', 'address line 1', 'address line 2') or
                            (ql.startswith('address') and len(ql) <= 20 and not any(k in ql for k in ['email', 'ip', 'mac', 'web'])))
        if is_address_q:
            return 'Bengaluru, Karnataka, India', max(score, 0.98)

        # 0k. Tools & Platforms Proficiency
        is_tools_proficient = bool(re.search(r'\b(tools.*platforms.*technologies.*proficient|tools, platforms, or technologies|technologies are you proficient in|tools and platforms you are proficient)\b', ql) or
                                   ('proficient in' in ql and ('jira' in ql or 'tools' in ql or 'platforms' in ql)))
        if is_tools_proficient:
            return 'Git, GitHub, Jira, Docker, Kubernetes, AWS, Postman, IntelliJ IDEA, VS Code, CI/CD', max(score, 0.98)

        # 0l. Resume Attachment Prompt in Text Input
        if bool(re.search(r'\b(attach (your )?updated resume|upload (your )?resume|resume link|share your resume)\b', ql)) and not any(kw in ql for kw in ['experience', 'years', 'how many']):
            return 'https://siddhant3646.github.io/Portfolio/', max(score, 0.98)

        # 0m. Offer in hand / Holding offers / Competing offers
        if bool(re.search(r'\b(offer\s+in\s+hand|holding\s+(any\s+)?offers?|competing\s+offers?|existing\s+offers?)\b', ql)):
            if 'else 0' in ql or 'else mention 0' in ql or 'amount in lpa' in ql:
                return '0', max(score, 0.98)
            if input_type in ('number', 'numeric'):
                return '0', max(score, 0.98)
            return 'No', max(score, 0.98)

        # 0n. Side Projects & GitHub URL
        if ('personal or side projects' in ql or 'side projects' in ql) and ('github' in ql or 'share' in ql or 'link' in ql):
            return 'Yes, GitHub: https://github.com/siddhant3646 | Portfolio: https://siddhant3646.github.io/Portfolio/', max(score, 0.98)

        # 0o. Visa Sponsorship Requirement
        if 'sponsorship' in ql or 'visa sponsorship' in ql:
            if any(kw in ql for kw in ['require', 'need', 'future require', 'visa status', 'employment visa', 'sponsorship for employment']):
                return 'No', max(score, 0.98)

        # 0p. Accommodation requirement / preference
        if 'accommodation' in ql and any(kw in ql for kw in ('require', 'need', 'special accommodation')):
            return 'Not required', max(score, 0.98)

        # 0q. Direct GitHub Profile / Repo link (distinct from portfolio)
        is_github_direct = bool(re.search(r'\b(github\s+(profile|link|url|username|handle|id)|link\s+to\s+github|your\s+github)\b', ql) or ql in ('github', 'github link', 'github url', 'github profile'))
        if is_github_direct and not any(kw in ql for kw in ['portfolio', 'website', 'personal site', 'side projects']):
            return 'https://github.com/siddhant3646', max(score, 0.98)

        # 0r. Rating scale (1-5) bounded proficiency (guard against 1-10 or experience overrides)
        is_rating_scale_5 = bool(re.search(r'\b(rate\s+(your\s+)?proficiency|proficiency\s*\(1[-–]5\)|rate\s+(yourself\s+)?(1[-–]5|1\s+to\s+5)|scale\s+of\s+1\s*(to|[-–])\s*5|rating\s*\(1[-–]5\)|scale\s+1[-–]5)\b', ql) or ('scale of 1-5' in ql) or ('scale of 1 to 5' in ql))
        if is_rating_scale_5 and not bool(re.search(r'\b(how many years)\b', ql)):
            if al in ('8/10', '9/10', '10/10', '7/10', '8', '9', '10', '4.2', '4.2 Years', '4 Years', 'Yes', 'No') or '/' in al or not al:
                return '4', max(score, 0.98)

        # 0b. Restrictive covenants / Non-compete compliance
        if any(w in ql for w in ('restrictive covenant', 'restrictive covenants', 'noncompete', 'non-compete', 'non-solicitation')) or (
            'confidentiality agreement' in ql and any(r in ql for r in ('restrict', 'bound', 'covenant', 'employer', 'perform'))
        ):
            return 'No', max(score, 0.99)

        # 0g. Career gaps
        if 'gap' in ql and any(w in ql for w in ('education to job', 'between jobs', 'what are your gap')):
            return 'None of the above and not much gap', max(score, 0.98)

        # 0e. Agentic AI / AI Agent use case and contribution
        if ('agentic ai' in ql or 'ai agent' in ql) and any(w in ql for w in ('explain', 'use case', 'contribution', 'describe')):
            essay = 'Yes, I have architected and deployed autonomous Agentic AI systems using LangChain, LangGraph, and LLM APIs. In my implementations, I designed a multi-agent workflow featuring specialized planning, tool execution, self-healing reflection, and deterministic validation stages. My primary contribution was building the resilient tool orchestration layer, integrating schema-aware browser automation and fuzzy entity resolution with dynamic retry logic, and optimizing latency and token usage through structured JSON outputs and prompt caching.'
            return essay, max(score, 0.99)

        # 0u. Spring Boot modules worked with
        if 'spring boot modules' in ql or ('spring boot' in ql and 'modules' in ql and any(w in ql for w in ('which', 'worked with', 'what'))):
            return 'Spring Boot, Spring MVC, Spring Data JPA/Hibernate, Spring Security (OAuth2/JWT), Spring Cloud (Config/Eureka), Spring Kafka, and Spring Boot Actuator for health checks and observability.', max(score, 0.98)

        # 0v. REST API types developed
        if ('rest api' in ql or 'rest apis' in ql) and any(w in ql for w in ('what type', 'types of rest', 'which type', 'have you developed')):
            return 'Designed and developed secure, scalable RESTful microservices, event-driven APIs (Kafka/RabbitMQ), public-facing webhook listeners, asynchronous batch processing APIs, and CRUD endpoints with OAuth2/JWT security.', max(score, 0.98)

        # 0w. Complex PostgreSQL query example
        if 'postgresql' in ql and any(w in ql for w in ('complex query', 'example of a complex', 'query you have written', 'written a complex')):
            return 'At Everbridge, I wrote complex queries utilizing Common Table Expressions (CTEs), window functions (ROW_NUMBER(), RANK(), LEAD/LAG) for financial settlement calculations, partitioned table scans, and optimized execution using EXPLAIN ANALYZE and composite B-tree/GIN indexes.', max(score, 0.98)

        # 0x. Database optimization techniques
        if 'database' in ql and any(w in ql for w in ('optimization technique', 'optimization techniques', 'techniques have you used', 'optimisation technique')):
            return 'Database indexing (B-Tree, GIN, composite indexes), query plan analysis with EXPLAIN ANALYZE, connection pooling tuning (HikariCP), database partitioning, query refactoring to avoid N+1 queries, and multi-level caching with Redis.', max(score, 0.98)

        # 0y. JWT authentication implementations
        if 'jwt' in ql and any(w in ql for w in ('authentication implementation', 'authentication implementations', 'implementations have you', 'worked on')):
            return 'Implemented stateless authentication using Spring Security and Nimbus/JJWT libraries, RSA/HMAC signing, refresh token rotation with Redis storage, claims-based authorization, and custom OncePerRequestFilter for token validation.', max(score, 0.98)

        # 0z. Docker experience descriptive
        if 'docker' in ql and any(w in ql for w in ('describe your experience', 'development or deployment', 'experience with docker')):
            if input_type in ('textarea', 'text') or len(ql) > 40:
                return 'Extensive experience containerizing Spring Boot and Node.js microservices with multi-stage Dockerfiles, optimizing image sizes, managing local multi-service environments with Docker Compose, and deploying containers to AWS ECS/EKS.', max(score, 0.98)

        # 0aa. Git repository tools
        if 'git' in ql and any(w in ql for w in ('repository tools', 'repository tool', 'github, gitlab', 'which git')):
            return 'GitHub, GitLab, Bitbucket', max(score, 0.98)

        # 0ab. JavaScript frameworks or libraries
        if ('javascript' in ql or 'js' in ql) and any(w in ql for w in ('frameworks or libraries', 'frameworks and libraries', 'libraries have you worked', 'frameworks have you worked')):
            return 'React.js, Node.js, Express.js, TypeScript, Next.js, Redux, and Jest', max(score, 0.98)

        # 0ac. Most complex backend application
        if ('complex backend application' in ql or 'most complex backend' in ql) and any(w in ql for w in ('describe', 'developed', 'architected')):
            return 'At Everbridge, I architected and built a real-time settlement and dispute management microservices engine handling thousands of transactions per second, utilizing Java, Spring Boot, Kafka, Redis, and PostgreSQL with 99.99% uptime.', max(score, 0.98)

        # 0ad. Role in designing application architecture
        if ('designing application architecture' in ql or 'application architecture' in ql) and any(w in ql for w in ('what was your role', 'role in designing', 'your role')):
            return 'As a Software Engineer 2, I led the architectural design for microservices, defining API contracts (OpenAPI), schema design in PostgreSQL, Kafka event topics and partition strategies, Redis caching layers, and high-availability patterns.', max(score, 0.98)

        # 0ae. Fit for Kotlin & Java Developer role
        if ('kotlin' in ql or 'java developer' in ql) and any(w in ql for w in ('strong fit', 'why you believe you are a strong fit', 'fit for this')):
            return 'With 4+ years of professional backend software engineering experience building scalable microservices in Java and Spring Boot, combined with strong OOP, clean architecture principles, and JVM ecosystem proficiency, I quickly adapt to and excel in Kotlin and modern backend environments.', max(score, 0.98)

        # 0af. FE fundinfo / Zenith Investment Partners
        if 'fe fundinfo' in ql or 'zenith investment' in ql:
            if any(w in ql for w in ('unique id', '7-digit', 'id number', 'if currently employed')):
                return 'N/A', max(score, 0.98)
            return 'No', max(score, 0.98)

        # 0ag. Reusable software components and libraries example
        if 'reusable software components' in ql or 'reusable software components, libraries' in ql:
            return 'Yes, at Everbridge I designed and developed reusable Java Spring Boot starters and shared libraries for authentication/authorization filters, standardized error handling, and distributed Redis caching used by 4+ engineering teams.', max(score, 0.98)

        # 0ah. CI/CD pipelines and automated testing contract gates
        if ('ci/cd' in ql or 'cicd' in ql) and any(w in ql for w in ('automated testing', 'contract and quality', 'quality gates', 'unit, integration')):
            return 'Yes, extensive experience designing and maintaining CI/CD pipelines with GitLab CI/GitHub Actions, automated testing using JUnit 5, Mockito, Testcontainers for integration tests, contract testing with Spring Cloud Contract / Pact, and SonarQube quality gates.', max(score, 0.98)

        # 0ai. Endava competitor, supplier, client financial interest or personal relationships
        if ('endava' in ql or 'competitor' in ql or 'supplier' in ql or 'client' in ql) and any(w in ql for w in ('financial interest', 'personal or family relationships', 'personal relationships', 'family relationships')):
            return 'No', max(score, 0.98)

        # 0aj. Azure certifications (if yes, specify)
        if 'azure certification' in ql or 'azure certifications' in ql:
            if 'specify' in ql or 'if yes' in ql:
                return 'Yes, Azure Fundamentals (AZ-900)', max(score, 0.98)

        # 0p. Yes/No experience questions (numeric threshold or specific tech stack)
        is_yn_num_exp = bool(re.search(r'^(do you have|have you|are you|can you|will you|would you)\b.*?\b\d+[-–+]?\s*(?:to\s*\d+)?\s*(?:\+)?\s*(?:years?|yoe)\b.*?\bexperience\b', ql))
        is_yn_tech_exp = (
            bool(re.search(r'^(do you have|have you|are you)\b.*?\b(java(?:/j2ee)?|j2ee|react|angular|rest apis?|microservices?|spring|node|sql|docker|kubernetes|git)\b.*?\b(experience|hands-on|knowledge)\b', ql)) or
            bool(re.search(r'^(do you have|have you|are you)\b.*?\b(experience|hands-on|knowledge)\b.*?\b(in|with|developing|working with)\b.*?\b(java(?:/j2ee)?|j2ee|react|angular|rest apis?|microservices?|spring|node|sql|docker|kubernetes|git)\b', ql))
        )
        is_descriptive_exp = any(w in ql for w in ('which ones', 'explain', 'describe', 'details', 'cloud', 'bfsi', 'fintech', 'banking', 'production', 'on-call', 'oncall', 'support'))
        if (is_yn_num_exp or is_yn_tech_exp) and not is_descriptive_exp and not any(w in ql for w in ('how many', 'how much', 'what is your', 'total years', 'number of years', 'rate your', 'scale of')):
            return 'Yes', max(score, 0.98)

        # Fastest ETA achieved from BRD to live in days
        if 'fastest eta' in ql or ('brd' in ql and 'live' in ql and 'eta' in ql):
            return ('14' if input_type == 'number' else '14 Days'), max(score, 0.98)

        # Role / Roles applying for
        if ('role' in ql or 'roles' in ql) and any(w in ql for w in ('applying for', 'you are applying', 'applied for')):
            return 'Software Engineer 2 (SDE-2)', max(score, 0.98)

        # Relevant full-time experience excluding internship
        if 'excluding internship' in ql or ('full-time experience' in ql and 'internship' in ql):
            return ('4.2' if input_type == 'number' else '3-5 Years'), max(score, 0.98)

        # Employee referral name or relationship
        if ('employee' in ql or 'referral' in ql) and any(w in ql for w in ("name", "who referred", "how you know", "indicate how", "put n/a", "enter n/a", "type n/a", "write n/a", "put na", "enter na", "if not referred", "list their name")):
            return 'N/A', max(score, 0.98)

        # Deloitte auditor association
        if 'deloitte' in ql or 'independent auditor' in ql:
            return 'No, I have never been associated with Deloitte', max(score, 0.98)

        # Company affiliations / former employee (Agoda, Booking Holdings, Strategy, Nextiva, Simplify360)
        if any(c in ql for c in ('agoda', 'booking holdings', 'strategy', 'nextiva', 'simplify360')) and any(w in ql for w in ('personal relationship', 'employed by', 'former employee', 'subsidiaries', 'affiliated', 'associated')):
            return 'No', max(score, 0.98)

        # Veteran status
        if any(w in ql for w in ('veteran', 'military service', 'military spouse', 'protected veteran')):
            return 'No', max(score, 0.98)

        # Visa sponsorship
        if ('sponsorship' in ql or 'visa' in ql) and any(w in ql for w in ('require', 'need', 'now or in the future', 'will you require')):
            return 'No', max(score, 0.98)

        # AI coding tools adoption and impact
        if 'ai coding tools' in ql or ('coding tools' in ql and any(w in ql for w in ('adopted', 'adoption', 'velocity', 'copilot'))):
            essay = 'I actively drove the adoption of GitHub Copilot and Claude within our backend engineering workflows. By establishing clear prompt engineering guidelines, pair-programming patterns, and automated test generation templates, we increased sprint velocity by over 25% while maintaining strict code quality and test coverage standards.'
            return essay, max(score, 0.98)

        # Cloud & AI Platform Architecture
        if 'architecture' in ql and ('cloud' in ql or 'ai platform' in ql) and any(w in ql for w in ('what', 'which', 'worked on', 'describe')):
            essay = 'Architected and built scalable cloud-native microservices on AWS (ECS, Lambda, S3, RDS PostgreSQL, DynamoDB, Kafka) and integrated LLM-based Agentic workflows using LangChain, LangGraph, and Amazon Bedrock with robust observability via CloudWatch and distributed tracing.'
            return essay, max(score, 0.98)

        # Locations willing to relocate to
        if ('relocate' in ql or 'relocating' in ql) and any(w in ql for w in ('which of these locations', 'which locations', 'locations are you willing', 'city you are currently residing or willing')):
            if 'gurugram' in ql or 'gurgaon' in ql:
                if input_type in ('select', 'radio'):
                    return 'Gurugram', max(score, 0.98)
                return 'Bengaluru (Willing to relocate to Gurugram)', max(score, 0.98)
            if input_type in ('text', 'textarea'):
                return 'Bangalore, Hyderabad, Pune, Remote', max(score, 0.98)
            return 'Bengaluru', max(score, 0.98)

        # Education discipline / field of study
        if ql in ('discipline', 'field of study', 'major') or ('discipline' in ql and 'education' in ql):
            return 'Computer Science', max(score, 0.98)

        # Currently attend institution
        if 'currently attend' in ql and 'institution' in ql:
            return 'No', max(score, 0.98)

        # Bengaluru office location alignment
        if 'bengaluru office' in ql and any(w in ql for w in ('align with your location', 'ability to work', 'onsite four days', 'location alignment', 'alignment')):
            return 'I live in Bengaluru and can work onsite/hybrid', max(score, 0.98)

        # WFO Bangalore HSR Layout + F2F interview + location readiness
        if ('wfo' in ql or 'face to face' in ql or 'f2f' in ql) and ('bangalore' in ql or 'hsr' in ql) and any(w in ql for w in ('ready', 'located', 'location')):
            if input_type in ('radio', 'select', 'checkbox'):
                return 'Yes', max(score, 0.98)
            return 'Yes, I am ready for face-to-face interviews and WFO at Bangalore office (HSR layout). Currently located in Bangalore, India.', max(score, 0.98)

        # Data Structures & Algorithms experience brief
        if any(d in ql for d in ('data structures', 'dsa', 'algorithms', 'data structure')) and any(b in ql for b in ('give brief', 'brief on', 'give a brief', 'describe', 'briefly explain', 'briefly describe', 'summary of')) and 'lru' not in ql:
            if input_type in ('radio', 'select', 'checkbox'):
                return 'Yes', max(score, 0.98)
            return 'Yes, strong foundation in Data Structures and Algorithms with 4.2 years of backend engineering experience. Proficient in Trees, Graphs, Dynamic Programming, Hash Maps, Heaps, and optimizing time and space complexity in distributed systems.', max(score, 0.98)

        # Experience in Java / Go / Rust
        if 'java' in ql and any(l in ql for l in ('go', 'rust')) and any(e in ql for e in ('experience', 'years')):
            if input_type == 'number':
                return '4.2', max(score, 0.98)
            return '4.2 Years', max(score, 0.98)

        # Joining timeline with explicit mention in days
        if any(w in ql for w in ('how soon', 'how quickly', 'when')) and 'join' in ql and any(d in ql for d in ('in days', 'mention in days', 'number of days')):
            if input_type == 'number':
                return '15', max(score, 0.98)
            return '15', max(score, 0.98)

        # Expected CTC in number - LPA (example: 7 if its 7 LPA)
        if any(w in ql for w in ('expected ctc', 'expected salary', 'ectc')) and any(u in ql for u in ('in number- lpa', 'in number - lpa', 'in number lpa', 'example- 7', 'example 7')):
            return '30', max(score, 0.98)

        # Flexible working from location / open to location
        if ('flexible working' in ql or 'comfortable working' in ql or 'willing to work' in ql) and any(loc in ql for loc in ('hyderabad', 'bangalore', 'bengaluru', 'pune', 'chennai', 'gurgaon', 'delhi', 'mumbai', 'noida')):
            return 'Yes', max(score, 0.98)

        # 0k. Email and contact number combined
        is_email_and_contact = bool(re.search(r'\b(email)\b', ql) and re.search(r'\b(phone|contact number|contact no|mobile)\b', ql))
        if is_email_and_contact:
            return 'siddhant3646@gmail.com, 7905828880', max(score, 0.98)

        # 0n. City and state of residence
        if any(w in ql for w in ('city and state', 'city & state', 'city and state of residence', 'current city and state')):
            return 'Bangalore, Karnataka', max(score, 0.98)

        # 0s. Interview time slot availability
        if any(w in ql for w in ('9- 3 pm', '9-3 pm', '9 to 3 pm', '9 am to 3 pm')):
            return 'Anytime between 10 AM - 2 PM', max(score, 0.98)
        if any(w in ql for w in ('time slot in between', 'mention the time slot', 'available time slot', 'time slot for interview', 'what time you will be available', 'at what time you will be available')):
            return 'Anytime between 10 AM - 4 PM', max(score, 0.98)

        # 0t. Notice period and LWD combined
        if ('notice' in ql or 'np' in ql) and any(w in ql for w in ('lwd', 'last working day', 'ldw')):
            if any(w in ql for w in ('19102026', 'enter as', 'if not serving enter')):
                return '23102026', max(score, 0.98)
            lwd_date = datetime.now() + timedelta(days=15)
            return f"15 Days, LWD: {lwd_date.strftime('%d %b %Y')}", max(score, 0.98)

        # 1. Disability safety guard: Candidate has NO disability
        if 'disability' in ql:
            if al.lower() in ('yes', 'true', '1') or 'do you have' in ql or 'any kind of disability' in ql:
                return 'No', max(score, 0.98)

        # 2. Relocation willingness in city presence questions (e.g. "residing in Chennai or willing to relocate")
        is_reloc_willing = bool(re.search(r'\b(relocat|willing to|open to|ready to|willing)\b', ql))
        if is_reloc_willing and any(city in ql for city in ('chennai', 'hyderabad', 'pune', 'mumbai', 'delhi', 'gurgaon', 'gurugram', 'noida', 'kolkata')):
            if input_type in ('radio', 'checkbox', 'select', None) or al.lower() in ('no', 'false', '0'):
                return 'Yes', max(score, 0.98)

        # 3. Company interest questions (e.g. "Are You really interested work with TECH Mahindra")
        is_interest_work = bool(re.search(r'\b(interested work with|interested to work|interested in working|interested for .* proceedings|fulltime proceedings|full time proceedings)\b', ql))
        if is_interest_work:
            return 'Yes', max(score, 0.98)

        # 4. Currency and Unit Detection for Salary / CTC questions
        is_multi_topic = bool(re.search(r'\b(notice|location|fintech|managerial|mentoring|lead modules)\b', ql) and re.search(r'\b(experience|years)\b', ql))
        is_salary_q = bool(re.search(r'\b(salary|ctc|compensation|pay|package|remuneration)\b', ql))
        if is_salary_q and not is_multi_topic:
            is_combined_ctc = bool(re.search(r'\b(current|present|cctc)\b', ql) and re.search(r'\b(expected|expectation|ectc)\b', ql))
            if is_combined_ctc:
                return 'Current CTC: 23 LPA, Expected CTC: 30 LPA', max(score, 0.98)
            is_current = bool(re.search(r'\b(current|present|cctc)\b', ql))
            is_raw_inr_example = bool(re.search(r'\b(700000|mention as \d{6,}|example.*\d{6,})\b', ql))
            is_take_home = bool(re.search(r'\b(take[- ]home|in[- ]hand|net pay)\b', ql))
            is_compliance_yes_no = bool(re.search(r'^(does|is|can|are|do|will|have)\b', ql) and re.search(r'\b(match|agree|confirm|credit|payslip)\b', ql))
            is_monthly = bool(re.search(r'\b(monthly compensation|fixed monthly|monthly salary|gross monthly|per month)\b', ql) or ('monthly' in ql and 'compensation' in ql))
            if not is_take_home and not is_compliance_yes_no:
                if is_raw_inr_example:
                    return ('2300000' if is_current else '3000000'), max(score, 0.98)
                elif is_monthly and (al in ('0.5', '15', '23', '30', '3000000', '2300000') or not al or '0.5' in al or 'month' in al.lower()):
                    return ('191667' if is_current else '250000'), max(score, 0.98)
            is_usd = bool(re.search(r'\b(usd|dollars?|\$)\b', ql))
            is_in_lakhs = bool(re.search(r'\b(lakhs?|lacs?|lpa)\b', ql))
            if not is_take_home and not is_compliance_yes_no:
                if is_usd:
                    if is_monthly or 'per month' in ql or 'monthly' in ql:
                        return ('3500' if is_current else '5000'), max(score, 0.98)
                    return ('40000' if is_current else '60000'), max(score, 0.98)
                elif is_in_lakhs:
                    return ('23' if is_current else '30'), max(score, 0.98)

        # 5. Textarea Technical Essay & Conceptual Architecture Handling (avoid short digits in open-ended technical essays)
        is_yes_no_q = bool(
            re.search(r'\b(are you|would you|do you|can you|could you|will you|should you|is there|is it|willing|comfortable|aligned with|okay with|agree|consent|opt[- ]in|authorized|sponsorship|visa|eligible|permit|clearance|conflict of interest|non[- ]compete|disciplinary|convicted|crime|ex-employee|previously employed)\b', ql) or
            re.search(r'^(have you|were you|did you|will you|should you|is it|can we|shall we)\b', ql)
        )
        is_notice_q = bool(re.search(r'\b(notice|how soon|how quickly|joining|join us|available to start|start date|earliest start|lwd|official last)\b', ql))
        is_salary_q = bool(re.search(r'\b(salary|ctc|compensation|pay\b|package|remuneration|gross|net pay|fixed pay|variable pay|take home)\b', ql))
        is_location_q = bool(re.search(r'\b(location|city|country|state|reside|relocate|relocation|based in|where do you live|bengaluru|bangalore)\b', ql))
        is_conditional_q = bool(re.search(r'\b(if\s+(yes|any|applicable|so)|details\s+if\s+any|please\s+(specify|describe|explain)\s+if)\b', ql))
        is_simple_field_q = is_yes_no_q or is_notice_q or is_salary_q or is_location_q or is_conditional_q

        is_conceptual_q = bool(re.search(r'\b(explain|architecture|design an?|how does|what steps|stabilize and scale|internal working|trade-offs)\b', ql))
        is_open_ended_q = (is_conceptual_q or bool(re.search(
            r'\b(describe\s+(your|a\s+|how|the|yourself|what|situations?|projects?)|tell us about|walk through|hands-on experience working with|experience taking over|cover\s*letter|why\s*(should\s*we\s*hire|hire\s*you|work\s*here|join)|background|summary\s*of\s*(your\s*)?experience|elevator\s*pitch|overview|aspirations|motivation)\b',
            ql
        ))) and not is_conditional_q

        # Never overwrite intentional non-applicable answers ('N/A', 'None', etc.)
        is_na_answer = al.strip().lower() in ('n/a', 'none', 'na', 'not applicable', 'not required')

        is_textarea_essay = is_open_ended_q and not is_simple_field_q and not is_na_answer
        if is_textarea_essay and (al in ('4', '4.2', '5', '9', '10', '4.2 Years', '5 Years', 'Yes', 'No') or len(al) < 15):
            tech_summary = (
                "4+ years of professional full-stack software engineering experience specializing in distributed systems, "
                "RESTful microservices, and modern web architectures. Hands-on expertise in backend services (Java/Spring Boot, Python, Node.js), "
                "scalable cloud infrastructure (AWS, Docker, Kubernetes), and intuitive frontend integrations. Experienced in end-to-end SDLC, "
                "designing resilient database architectures (PostgreSQL, MongoDB), building automated CI/CD pipelines, and troubleshooting complex production issues."
            )
            return tech_summary, max(score, 0.98)

        # 6. Detect if the question is asking for meeting requirements or eligibility
        is_meet_req = bool(re.search(r'\b(meet (the )?requirements|meet all requirements|eligible for (this )?(position|role))\b', ql) or
                          ('qualifications and technical skills' in ql and 'meet' in ql))
        if is_meet_req:
            return 'Yes', max(score, 0.98)

        # 7. Detect 12th/10th Board percentage / aggregate
        is_board_pct = bool(re.search(r'\b(12th|10th|hsc|ssc|intermediate)\b', ql) and re.search(r'\b(%|percent|percentage|marks|aggregate)\b', ql))
        if is_board_pct:
            return ('88' if re.search(r'\b(10th|ssc)\b', ql) else '85'), max(score, 0.98)

        # 8. Detect company / payroll company questions vs numeric / salary false positives
        is_company_q = bool(re.search(r'\b(current company|payroll company|which company|working at|current payroll|current employer)\b', ql) and
                           not re.search(r'\b(relative|family|experience|years|how many|early release|resign|notice|buy ?out|negotiable|equity|stock|shares|esop|bonus|holding|hold|noc|relieving|payslip|salary slip|letter|form 16|tax|document|can you provide|provide)\b', ql))
        if is_company_q:
            if re.search(r'^\d+$', al) or al.lower() in ('yes', 'no', '4.2', '4.2 years', '4 years'):
                return 'Everbridge', max(score, 0.98)

        # 9. Detect GitHub / portfolio link in text inputs
        is_portfolio_link = bool((re.search(r'\b(portfolio link|portfolio url|online portfolio|repo link|portfolio or best work|best work link|add your portfolio|work link)\b', ql) or
                                 (re.search(r'\b(github url|github link|github profile)\b', ql) and not re.search(r'\b(tools|platforms|technologies|proficient|e\.?g\.?)\b', ql))) and
                                 not is_tools_proficient)
        if is_portfolio_link:
            if input_type in ('radio', 'checkbox'):
                return 'Yes', max(score, 0.98)
            if al.lower() in ('yes', 'true', '4', '4.2', '4.2 years', '5') or not al.startswith('http'):
                return 'https://siddhant3646.github.io/Portfolio/', max(score, 0.98)
            return al, max(score, 0.98)

        # 10. Detect if the question is asking for numeric years of experience
        is_num_years = bool(re.search(
            r'\b(how many years|how many yrs|how much experience|experience you hold|years of experience|yrs of experience|relevant years|total years|experience in years|how long have you|number of years|no\.?\s*of\s*years|years of exp|total exp|working expr|total working|total expr|working experience)\b',
            ql
        ) or (re.search(r'\b(expr|experience)\b', ql) and re.search(r'\b(total|working|years|yrs)\b', ql)))

        # 11. Detect if the question is a Yes/No boolean question
        is_yes_no = bool(
            re.search(r'^(do you|have you|are you|can you|is it|did you|would you|will you|willing to|comfortable with|open to|do you have|have you worked|are you familiar|do you know)\b', ql) or
            re.search(r'\b(are you on notice|are you currently on notice|are you based in|are you located in|are you in|do you stay in)\b', ql) or
            (input_type in ('radio', 'checkbox') and not is_num_years)
        )

        is_purely_numeric = bool(re.fullmatch(r'\s*([<>]?\s*\d+(?:\.\d+)?(?:\s*-\s*\d+)?|\d+\+?)\s*(?:years?|yrs?|months?|days?)?\s*', al, re.IGNORECASE))

        if is_num_years:
            if al.lower() in ('yes', 'true', '1') or (not re.search(r'\d', al) and len(al) <= 20):
                return '4.2 Years', max(score, 0.95)
            return answer, score

        if input_type in ('radio', 'checkbox'):
            if is_purely_numeric:
                num_m = re.search(r'\d+(\.\d+)?', al)
                val = float(num_m.group(0)) if num_m else 0.0
                return ('Yes' if val > 0 else 'No'), max(score, 0.95)
            if al.lower().startswith(('no', 'never', 'none', 'not')):
                return answer, score
            if 'select all' in ql:
                return answer, max(score, 0.98)
            if al.lower() not in ('yes', 'no') and (al.startswith('http') or len(al) > 20):
                return 'Yes', max(score, 0.95)

        if is_yes_no and not is_num_years:
            # If answer is purely numeric experience (e.g. "4.2", "4.2 Years", "<5 years", "4-5 years") or notice period days ("15")
            if is_purely_numeric:
                num_m = re.search(r'\d+(\.\d+)?', al)
                val = float(num_m.group(0)) if num_m else 0.0
                return ('Yes' if val > 0 else 'No'), max(score, 0.95)
            if al == '15' and 'notice' in ql and not is_lwd:
                return 'Yes', max(score, 0.95)
            if 'bangalore' in ql or 'bengaluru' in ql:
                if 'based' in ql or 'located' in ql or 'currently in' in ql or 'stay' in ql:
                    return 'Yes', max(score, 0.95)

        if not is_yes_no and ('notice period' in ql or 'notice' in ql) and al.lower() in ('yes', 'true', '1') \
                and not is_lwd and not re.search(r'\b(negotia|buy ?out|early release|resign)\w*', ql):
            return '15', max(score, 0.95)

        return answer, score

    def fuzzy_match(self, question: str, input_type: str = None) -> Tuple[Optional[str], float]:
        if not question:
            return None, 0.0

        normalized_q = self._normalize(question)
        question_lower = question.lower()

        # Tier 1: Exact/word-boundary match (fast, reliable)
        result = self._tier1_match(normalized_q, question_lower, question, input_type)
        if result[0]:
            return self._resolve_question_intent(question, result[0], result[1], input_type)

        # Tier 2: Category-scoped fuzzy match
        result = self._tier2_match(normalized_q, question_lower, question, input_type)
        if result[0]:
            return self._resolve_question_intent(question, result[0], result[1], input_type)

        # Tier 3: Global fuzzy fallback
        result = self._tier3_match(normalized_q, question_lower, question, input_type)
        return self._resolve_question_intent(question, result[0], result[1], input_type)

    def _tier1_match(self, normalized_q: str, question_lower: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        # 1. Exact match check across all pattern strings
        exact_id = None
        exact_priority = -1
        exact_len = -1
        for pattern_id, norm_patterns in self._norm_pattern_cache.items():
            if not self._passes_negative(pattern_id, question_lower):
                continue
            pattern_data = self.patterns['patterns'].get(pattern_id, {})
            for norm_p in norm_patterns:
                if norm_p == normalized_q:
                    priority = pattern_data.get('priority', 5)
                    if priority > exact_priority or (priority == exact_priority and len(norm_p) > exact_len):
                        exact_id = pattern_id
                        exact_priority = priority
                        exact_len = len(norm_p)

        if exact_id:
            answer = self._get_answer(exact_id, input_type)
            cat = self.patterns['patterns'][exact_id].get('category', '')
            is_valid, _ = AnswerValidator.validate(answer or '', cat, question)
            confidence = 0.98 if is_valid else 0.85
            return answer, confidence

        # 2. Word-boundary substring match (only if no exact match exists)
        best_id = None
        best_priority = -1
        best_len = -1

        for pattern_id, norm_patterns in self._norm_pattern_cache.items():
            if not self._passes_negative(pattern_id, question_lower):
                continue
            pattern_data = self.patterns['patterns'].get(pattern_id, {})
            for norm_p in norm_patterns:
                if len(norm_p) >= 2:
                    if len(norm_p) <= 3:
                        match = bool(re.search(rf"\b{re.escape(norm_p)}\b", normalized_q))
                    else:
                        match = (rf" {norm_p} " in f" {normalized_q} " or bool(re.search(rf"\b{re.escape(norm_p)}\b", normalized_q)))
                    if match:
                        priority = pattern_data.get('priority', 5)
                        if priority > best_priority or (priority == best_priority and len(norm_p) > best_len):
                            best_id = pattern_id
                            best_priority = priority
                            best_len = len(norm_p)

        if best_id:
            answer = self._get_answer(best_id, input_type)
            cat = self.patterns['patterns'][best_id].get('category', '')
            is_valid, _ = AnswerValidator.validate(answer or '', cat, question)
            confidence = 0.98 if is_valid else 0.85
            return answer, confidence

        return None, 0.0

    def _tier2_match(self, normalized_q: str, question_lower: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        detected_cats = self._detect_categories(question)
        if not detected_cats:
            return None, 0.0

        best_id = None
        best_score = 0.0
        best_priority = -1
        q_words = set(normalized_q.split())

        for cat, cat_score in detected_cats:
            pattern_ids = self._category_index.get(cat, [])
            for pid in pattern_ids:
                if not self._passes_negative(pid, question_lower):
                    continue
                pdata = self.patterns['patterns'].get(pid, {})
                for norm_p in self._norm_pattern_cache.get(pid, []):
                    p_words = set(norm_p.split())
                    if not (q_words & p_words) and norm_p not in normalized_q and normalized_q not in norm_p:
                        continue
                    sim = self._similarity(normalized_q, norm_p)
                    if len(norm_p) >= 4 and (f" {norm_p} " in f" {normalized_q} " or re.search(rf"\b{re.escape(norm_p)}\b", normalized_q)):
                        coverage = len(norm_p) / max(len(normalized_q), 1)
                        if coverage >= 0.5 or len(norm_p.split()) >= 3:
                            sim = max(sim, 0.85)
                        elif coverage >= 0.25:
                            sim = max(sim, 0.70)
                    if sim >= self.threshold:
                        priority = pdata.get('priority', 5)
                        if sim > best_score or (sim == best_score and priority > best_priority):
                            best_score = sim
                            best_id = pid
                            best_priority = priority

        if best_id:
            answer = self._get_answer(best_id, input_type)
            return answer, best_score

        return None, 0.0

    def _tier3_match(self, normalized_q: str, question_lower: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        best_id = None
        best_score = 0.0
        best_priority = -1
        q_words = set(normalized_q.split())

        for pattern_id, norm_patterns in self._norm_pattern_cache.items():
            if not self._passes_negative(pattern_id, question_lower):
                continue
            pattern_data = self.patterns['patterns'].get(pattern_id, {})
            for norm_p in norm_patterns:
                p_words = set(norm_p.split())
                if not (q_words & p_words) and norm_p not in normalized_q and normalized_q not in norm_p:
                    continue
                sim = self._similarity(normalized_q, norm_p)
                if len(norm_p) >= 4 and (f" {norm_p} " in f" {normalized_q} " or re.search(rf"\b{re.escape(norm_p)}\b", normalized_q)):
                    coverage = len(norm_p) / max(len(normalized_q), 1)
                    if coverage >= 0.5 or len(norm_p.split()) >= 3:
                        sim = max(sim, 0.85)
                    elif coverage >= 0.25:
                        sim = max(sim, 0.70)
                if sim >= self.threshold:
                    priority = pattern_data.get('priority', 5)
                    if sim > best_score or (sim == best_score and priority > best_priority):
                        best_score = sim
                        best_id = pattern_id
                        best_priority = priority

        if best_id:
            answer = self._get_answer(best_id, input_type)
            return answer, best_score

        return None, 0.0

    @staticmethod
    def _resolve_dynamic(answer: Optional[str]) -> Optional[str]:
        """Resolve dynamic date markers like __DYNAMIC_LWD__ or __DYNAMIC_START_DATE__."""
        if not answer or not isinstance(answer, str):
            return answer
        now = datetime.now()
        if '__DYNAMIC_LWD__' in answer:
            lwd_date = now + timedelta(days=15)
            answer = answer.replace('__DYNAMIC_LWD__', lwd_date.strftime('%d %b %Y'))
        if '__DYNAMIC_LWD_SHORT__' in answer:
            lwd_date = now + timedelta(days=15)
            answer = answer.replace('__DYNAMIC_LWD_SHORT__', lwd_date.strftime('%d-%b-%y'))
        if '__DYNAMIC_START_DATE__' in answer:
            start_date = now + timedelta(days=15)
            answer = answer.replace('__DYNAMIC_START_DATE__', start_date.strftime('%d/%m/%Y'))
        if '__DYNAMIC_START_DATE_US__' in answer:
            start_date = now + timedelta(days=15)
            answer = answer.replace('__DYNAMIC_START_DATE_US__', start_date.strftime('%m/%d/%Y'))
        if '__DYNAMIC_TODAY_US__' in answer:
            answer = answer.replace('__DYNAMIC_TODAY_US__', now.strftime('%m/%d/%Y'))
        if '__DYNAMIC_TODAY__' in answer:
            answer = answer.replace('__DYNAMIC_TODAY__', now.strftime('%d/%m/%Y'))
        if '__DYNAMIC_TODAY_ISO__' in answer:
            answer = answer.replace('__DYNAMIC_TODAY_ISO__', now.strftime('%Y-%m-%d'))
        if '__DYNAMIC_TODAY_TEXT__' in answer:
            answer = answer.replace('__DYNAMIC_TODAY_TEXT__', now.strftime('%d %b %Y'))
        return answer

    def _get_answer(self, pattern_id: str, input_type: str = None) -> Optional[str]:
        pattern = self.patterns['patterns'].get(pattern_id)
        if not pattern:
            return None
        if input_type:
            input_type = input_type.lower().strip()
            itd = pattern.get('input_type_defaults', {})
            if itd and input_type in itd:
                return self._resolve_dynamic(itd[input_type])
            if input_type == 'number':
                return self._resolve_dynamic(
                    pattern.get('numeric_default') or pattern.get('default')
                )

        return self._resolve_dynamic(pattern.get('default'))

    def match_with_details(self, question: str) -> Dict[str, Any]:
        answer, confidence = self.fuzzy_match(question)
        return {
            'question': question,
            'answer': answer,
            'confidence': confidence,
            'matched': answer is not None
        }

    def get_all_matches(self, question: str, min_confidence: float = 0.5) -> List[Tuple[str, str, float]]:
        matches = []
        normalized_q = self._normalize(question)
        for pattern_id, norm_strings in self._norm_pattern_cache.items():
            pattern = self.patterns['patterns'].get(pattern_id)
            if not pattern:
                continue
            best_sim = 0.0
            for normalized_p in norm_strings:
                sim = self._similarity(normalized_q, normalized_p)
                best_sim = max(best_sim, sim)
            if best_sim >= min_confidence:
                matches.append((pattern_id, pattern.get('default', ''), best_sim))
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    def update_patterns(self, patterns: Dict[str, Any]):
        self.patterns = patterns
        self._pattern_cache.clear()
        self._category_index.clear()
        self._build_index()

    def detect_duplicate_patterns(self, new_pattern_id: str, similarity_threshold: float = 0.85) -> List[Tuple[str, float]]:
        """
        Check if a newly added pattern is too similar to existing patterns.

        Returns list of (existing_pattern_id, similarity_score) tuples above threshold.
        """
        new_patterns = self._pattern_cache.get(new_pattern_id, [])
        if not new_patterns:
            return []
        duplicates = []
        norm_new = [self._normalize(p) for p in new_patterns]
        for pid, pat_strings in self._pattern_cache.items():
            if pid == new_pattern_id:
                continue
            for np in norm_new:
                for ps in pat_strings:
                    sim = self._similarity(np, self._normalize(ps))
                    if sim >= similarity_threshold:
                        duplicates.append((pid, sim))
                        break
                else:
                    continue
                break
        duplicates.sort(key=lambda x: x[1], reverse=True)
        return duplicates


def create_matcher(json_path: Optional[str] = None, threshold: float = PatternMatcher.DEFAULT_THRESHOLD) -> PatternMatcher:
    loader = PatternLoader(json_path)
    patterns = loader.load()
    return PatternMatcher(patterns, threshold)