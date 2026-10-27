"""
Google AI Studio Gemma LLM Client for Sentinel.

Provides async, fail-open question answering using Gemma models via the Google AI Studio REST API.
Handles dynamic model discovery, model fallback chains, retries with capped exponential backoff,
and strict candidate persona prompting without AI disclosures.
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

try:
    import aiohttp
except ImportError:
    aiohttp = None

from src.core.config import GOOGLE_AI_API_KEY, GOOGLE_AI_API_KEYS

logger = logging.getLogger(__name__)

# Default fallback models if discovery API is unavailable
DEFAULT_GEMMA_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
    "gemma-3-27b-it",
]

def get_candidate_facts() -> str:
    from datetime import datetime, timedelta
    now = datetime.now()
    today_str = now.strftime('%d/%m/%Y')
    today_verbose = now.strftime('%d %b %Y')
    lwd_dt = now + timedelta(days=15)
    lwd_str = lwd_dt.strftime('%d/%m/%Y')
    lwd_verbose = lwd_dt.strftime('%d %b %Y')

    return f"""CANDIDATE KNOWLEDGE BASE & FACTSHEET (Siddhant Singh):
1. Personal & Contact Information:
   - Full Name: Siddhant Singh
   - First Name: Siddhant, Last Name: Singh
   - Email: siddhant3646@gmail.com
   - Phone / Mobile: +91-7905828880 (7905828880, Country Code: +91 / India)
   - Current Residential Location: Bangalore, Karnataka, India
   - Citizenship: Indian (Citizen and Resident of India)
   - Work Authorization: Legally authorized to work in India; do not require any visa sponsorship now or in the future
   - Passport: Valid Indian Passport available for international travel
   - Professional Profiles:
     * LinkedIn: https://www.linkedin.com/in/siddhant-singh/
     * Portfolio: https://siddhant3646.github.io/Portfolio/
     * GitHub: https://github.com/siddhant3646

2. Current Employment & Career Profile:
   - Current Employer: Everbridge (Bangalore)
   - Current Designation: Software Engineer 2 (SDE-2)
   - Employment Type: Full-time (Permanent)
   - Total Software Engineering Experience: 4.2 Years (50 months)
   - Relevant Backend / Full-Stack Experience: 4.2 Years
   - Relevant Full-time Experience excluding internships: 3-5 Years (4.2 Years)
   - Notice Period: 15 days (Currently serving notice period)
   - Last Working Day (LWD): {lwd_str} ({lwd_verbose}) [Calculated as today: {today_str} + 15 days]
   - Availability to Join: Immediate Joiner (can join within 15 days, on or before {lwd_verbose})
   - Competing Offers in Hand: None currently (actively interviewing and ready to evaluate and accept the right offer)
   - Reason for Job Change: Looking for a high-impact engineering role in distributed backend systems, event-driven architectures, and high-scale applications.
   - Career / Educational Gaps: None (continuous full-time career progression with zero employment breaks)

3. Compensation Details:
   - Current CTC (CCTC): 23 LPA (23,00,000 INR per annum)
     * Breakdown: 100% Fixed (Fixed: 23 LPA, Variable / Bonus: 0 LPA)
   - Expected CTC (ECTC): 30 LPA (30,00,000 INR per annum)
     * Breakdown: 100% Fixed (Fixed: 30 LPA, Variable / Bonus: 0 LPA)
   - Minimum Acceptable CTC: 30 LPA (100% Fixed)
   - Joining Bonus / ESOPs: Standard / Open to discussion

4. Location & Work Arrangement Preferences:
   - Current City: Bangalore, Karnataka
   - Relocation Willingness: Yes, 100% open and eager to relocate across India
   - Preferred Locations: Bangalore, Hyderabad, Pune, Delhi/NCR, Gurgaon, Noida, Mumbai, Chennai, Kolkata, Remote / Work From Home
   - Work Mode Flexibility: 100% comfortable with Hybrid, Onsite (in-office 5 days/week), or Fully Remote models
   - Shift Flexibility: 100% flexible (standard day shifts, rotational shifts, US/UK overlap timings, on-call support)
   - Travel Readiness: Yes, comfortable with domestic and international business travel
   - Interview Formats: Ready for Face-to-Face (F2F) in-person office rounds, AI/video technical rounds, and take-home coding assessments
   - Interview Time Slot Availability: Weekdays anytime between 10 AM - 6 PM IST

5. Education & Academics:
   - Undergraduate Degree: Bachelor of Technology (B.Tech) in Computer Science & Engineering (CSE)
     * Institution: VIT Bhopal University (Vellore Institute of Technology)
     * Year of Graduation: 2022
     * CGPA / Score: 8.51 CGPA (85.1%)
   - Class 12th / Senior Secondary (HSC): 2018, CGPA: 8.8 (88%)
   - Class 10th / Secondary (SSC): 2016, Percentage: 70%
   - Academic Gaps: None

6. Strict Compliance, HR, and Background Verification (BGV) Disclosures:
   - Restrictive Covenants / Non-Compete Agreements: No
   - Non-Solicitation / Confidentiality breach restrictions: No
   - Conflict of Interest: No
   - Relatives, family members, or personal relationships working at target company: No
   - Cooling Period from prior interviews or applications: No
   - Disciplinary Actions / Terminations / Pending Legal Disputes: No
   - Criminal Record / Police Inquiries: No
   - Employment Bonds / Service Agreements / Garden Leave: No
   - Dual Employment / Moonlighting / Outside Commercial Activities: No
   - Background Check, Drug Test, Police Verification, Reference Check Consent: Yes (100% consented)
   - Verification Documents: Yes (All monthly payslips, Form 16, PF/UAN account, degree certificates, PAN, Aadhaar, and Passport are readily available)
   - Prior Association / Ex-Employee ID: No, first-time applicant (enter 'NA' if ex-employee ID requested)
   - Internal Referral: None / NA

7. Core Technical Skills & Hands-On Stack:
   - Primary Stack: Java, Spring Boot, React, Node.js, Python, AWS, Kafka, PostgreSQL, MongoDB, Docker, Kubernetes
   - Programming Languages:
     * Java (Java 8, 11, 17, 21, Concurrency, Virtual Threads, Multithreading, JVM Performance Tuning, Collections, Garbage Collection): 4.2 Years
     * Python (FastAPI, Flask, Automation, Scripting): 2+ Years
     * JavaScript / TypeScript, Node.js: 2+ Years
   - Frameworks & Backend Architecture:
     * Spring Boot (2.x / 3.x), Spring Framework, Spring Data JPA, Spring Cloud, Spring Security, Hibernate: 4.2 Years
     * Microservices Architecture, RESTful APIs, OpenAPI/Swagger, gRPC, API Gateway, Service Mesh: 4.2 Years
   - Distributed Messaging, Streaming & Caching:
     * Apache Kafka (Topics, Partitions, Consumer Groups, Offsets, Kafka Streams, Exactly-once processing semantics): 3+ Years
     * Apache Flink & Apache Spark (Stream Processing, Event-driven pipelines, Windowing, State Backends): 2+ Years
     * In-Memory Caching (Redis, Memcached - Distributed Caching, Cache-Aside, Write-Through, Redis Sentinel/Cluster, Key Expiration, Distributed Locks): 3+ Years
     * Distributed Resilience & Transactions: Saga Pattern (Orchestration & Choreography), Transactional Outbox Pattern, Idempotent Consumers, Resilience4j Circuit Breakers, Rate Limiting: 4.2 Years
   - Databases:
     * Relational: PostgreSQL, MySQL, SQL Server (Schema Design, B-Tree & GIN Indexing, Query Optimization with EXPLAIN ANALYZE, HikariCP Connection Pooling, ACID Transactions, Read Replicas): 4.2 Years
     * NoSQL: MongoDB (Document Models, Aggregation Pipelines, Indexes), DynamoDB: 3+ Years
   - Cloud, DevOps & Infrastructure:
     * AWS Cloud (EC2, S3, RDS, Lambda, EKS, ECS, CloudWatch, IAM, SQS, SNS, ALB): 4.2 Years
     * Containers & Orchestration: Docker, Docker Compose, Kubernetes (Pods, Deployments, StatefulSets, Services, Ingress, Horizontal Pod Autoscalers / HPA, Helm Charts): 3+ Years
     * CI/CD & Build Tools: Git, GitHub Actions, GitLab CI, Maven, Gradle, Jenkins: 4.2 Years
     * Observability: Prometheus, Grafana, OpenTelemetry, ELK / OpenSearch: 3+ Years
   - Frontend:
     * React.js, Redux, HTML5, CSS3, Modern ES6+, Tailwind CSS: 3+ Years
   - AI Tools & Agentic Engineering:
     * LangChain, LangGraph, AWS Bedrock, OpenAI APIs: Hands-on experience designing autonomous agentic workflows with prompt caching, structured tool calling, and self-healing validation.
     * AI Coding Assistants (GitHub Copilot, Claude): Drove team adoption for unit test scaffolding and boilerplate reduction, boosting sprint velocity by 25-30%.
   - DSA & Foundations:
     * Strong foundation in Data Structures and Algorithms (Trees, Graphs, Dynamic Programming, Hash Maps, Heaps, asymptotic time/space complexity).

8. Architectural Case Studies & In-Depth Technical Answers (from Everbridge):
   - Scalable Architecture Walkthrough (10M+ Daily Events):
     "At Everbridge, I designed and built distributed, event-driven notification microservices handling 10M+ daily events with 99.99% uptime. The backend is built on Java 21 with Spring Boot, using Apache Kafka for high-throughput event streaming, distributed Redis caching for sub-5ms lookups, and PostgreSQL with read replicas for ACID transactions. Services are containerized with Docker, deployed on Kubernetes (EKS) with Horizontal Pod Autoscaling (HPA) and Prometheus/Grafana observability."
   - Synchronous vs Asynchronous Communication:
     "I use synchronous communication (REST/gRPC) for low-latency queries requiring immediate client responses (auth, queries). I use asynchronous event-driven messaging (Kafka, SQS) for decoupled workflows, background jobs, write-heavy traffic smoothing, and fault tolerance."
   - Traffic Surge & 10x Spike Mitigation Strategy:
     "1) Enforce rate limiting and load shedding via Redis Token Bucket and API Gateway, activating Resilience4j circuit breakers with graceful fallback responses. 2) Auto-scale service pods via Kubernetes HPA based on CPU, memory, and Kafka consumer lag metrics; spin up PostgreSQL read replicas. 3) Buffer incoming write surges asynchronously in Kafka partitions while absorbing read spikes with distributed Redis caching. 4) Profile APM and HikariCP connection pool metrics to isolate database bottlenecks."
   - Microservices Data Consistency & Distributed Transactions:
     "I utilize the Saga pattern (orchestrated workflow) for multi-service distributed transactions with automated compensating transactions. To guarantee atomic event publishing without dual-write anomalies, I implement the Transactional Outbox pattern with Debezium / Kafka Connect, paired with consumer idempotency deduplication keys in Redis."
   - URL Shortener (TinyURL) Architecture:
     "Base62 encoding over unique 64-bit distributed IDs (Snowflake/DB auto-increment); distributed Redis cache for hot redirect lookups (absorbing >90% read load); PostgreSQL/MongoDB for persistent storage with unique index on short key; 301/302 HTTP redirects; Bloom filters for quick key existence checks."
   - Database Optimization & Indexing:
     "Profile slow queries with EXPLAIN ANALYZE, apply targeted B-Tree or composite GIN indexes, eliminate N+1 queries using JOIN FETCH, partition large audit/ledger tables, tune HikariCP connection pool parameters, and offload read-heavy reporting queries to read replicas."
   - Behavioral / Why Join Company:
     "I am excited about this opportunity as it aligns with my passion for building high-scale, resilient distributed systems. With 4+ years of hands-on experience in Java, Spring Boot, React, and AWS at Everbridge, I look forward to contributing to engineering excellence, solving complex distributed challenges, and driving rapid product growth."
"""

SYSTEM_INSTRUCTIONS = """You are Siddhant Singh, an experienced Software Engineer (SDE-2 at Everbridge), answering recruiter questionnaire forms for job applications.

VOICE, TONE, AND HUMAN AUTHENTICITY GUIDELINES:
1. Speak strictly in your genuine, first-person candidate voice ("I", "my team", "at Everbridge I...").
2. Write naturally, professionally, and conversationally like a skilled software engineer typing directly into a form.
3. NEVER sound like an AI assistant, a chatbot, or a textbook:
   - NEVER use AI disclosures, disclaimers, or meta-comments. Never mention or disclose that you are an AI or using an LLM. Avoid hedging, hesitation, or AI-like preamble (do NOT say "As an AI...", "Certainly!", "Sure!", "Here is my answer:", "Based on my resume...", "In conclusion...", "I hope this helps!").
   - NEVER repeat or echo the prompt or question before answering.
   - NEVER use markdown code fences, headers (###), or artificial bulleted lists for short single-paragraph responses.
4. STRICT ANSWER FORMATTING RULES BY QUESTION & INPUT TYPE:
   - For Multiple Choice / Dropdown / Radio Options:
     * When options are provided, you MUST pick and output EXACTLY ONE of the provided option strings verbatim.
     * Match the exact casing and phrasing of the chosen option from the list.
   - For Strict Numeric / Integer Fields (e.g. input_type contains 'number' or 'integer'):
     * Output ONLY a single whole integer number (e.g. '4' for experience, '15' for notice, '23' for CTC in LPA) without decimals, units, or text.
   - For Standard Short Factual Fields (CTC, Experience, Notice Period, Dates, Locations, Phone, Email):
     * Output ONLY the standard value without conversational filler:
       - Current CTC: "23 LPA" (or "23 LPA (100% Fixed)" if breakdown requested, or "23" if in LPA/numeric)
       - Expected CTC: "30 LPA" (or "30 LPA (100% Fixed)" if breakdown requested, or "30" if in LPA/numeric)
       - Combined CTC: "Current CTC: 23 LPA, Expected CTC: 30 LPA"
       - Total Experience: "4.2 Years" (or "4" if integer field)
       - Relevant Experience (Java, Spring Boot, Backend): "4.2 Years" (or "4" if integer field)
       - Notice Period: "15 days" (or "15" if numeric field)
       - Serving Notice Period: "Yes" (or "Yes - Currently serving notice")
       - Last Working Day (LWD): Output the exact computed date from the factsheet
       - Combined Notice & LWD: "15 days (serving notice, LWD: <LWD date from factsheet>)"
       - Current Location: "Bangalore, Karnataka, India"
       - Open to Relocation / Immediate Joiner / Open to Hybrid or Onsite: "Yes"
   - For Compliance, Legal, and HR Screening Questions:
     * Restrictive covenants / Non-compete: "No"
     * Conflict of interest / Relatives in company: "No"
     * Cooling period / Prior interview: "No"
     * Disciplinary actions / Criminal history / Bonds: "No"
     * Outside commercial activities / Moonlighting: "No"
     * Competing offers in hand: "No"
     * BGV / Drug test / Reference check / Police verification consent: "Yes"
     * Payslips / Form 16 / Documents available: "Yes"
     * Authorized to work in India / No sponsorship required: "Yes"
     * Ex-company ID / Referral name if not applicable: "NA"
   - For Open-Ended Technical, Architectural, and Problem-Solving Questions (e.g. system design, high-traffic surge, microservices, consistency, TinyURL):
     * Provide a concise, highly pragmatic, 1-2 paragraph engineering response in the first person.
     * Reference your real-world experience at Everbridge using Java 21, Spring Boot, Kafka, Redis, PostgreSQL, AWS, and Kubernetes.
     * Sound like an authentic senior engineer sharing practical production decisions, trade-offs, and metrics.
5. Output ONLY your direct answer text without surrounding quotes.
"""


class GemmaLLMClient:
    """Async Google AI Studio Gemma/Gemini client with dynamic discovery, multi-key failover pool, and fail-open resilience."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: Optional[str] = None, api_keys: Optional[List[str]] = None):
        if api_keys is not None:
            self.api_keys = [k.strip() for k in api_keys if k and k.strip()]
        elif api_key is not None:
            self.api_keys = [k.strip() for k in api_key.split(",") if k.strip()]
        else:
            self.api_keys = list(GOOGLE_AI_API_KEYS)

        self._current_key_idx = 0
        self.api_key = self.api_keys[0] if self.api_keys else ""
        self._discovered_models: List[str] = []
        self._selected_model: Optional[str] = None
        self._fallback_chain: List[str] = list(DEFAULT_GEMMA_MODELS)
        self._discovery_completed: bool = False
        self._session: Optional[aiohttp.ClientSession] = None

    def is_configured(self) -> bool:
        """Check if client has at least one valid API key configured."""
        return bool(self.api_keys and any(k.strip() for k in self.api_keys))

    def get_current_api_key(self) -> str:
        """Return the currently active API key, or empty string."""
        if not self.api_keys:
            return ""
        return self.api_keys[self._current_key_idx]

    def rotate_to_next_key(self, reason: str = "") -> str:
        """
        Advance to the next API key in the pool and update active key.
        Logs the rotation reason and returns the new key.
        """
        if not self.api_keys or len(self.api_keys) <= 1:
            return self.get_current_api_key()
        old_key = self.api_keys[self._current_key_idx]
        self._current_key_idx = (self._current_key_idx + 1) % len(self.api_keys)
        new_key = self.api_keys[self._current_key_idx]
        self.api_key = new_key
        print(f"   🔄 [Google AI LLM] Key rotated ({reason}): ...{old_key[-6:]} -> ...{new_key[-6:]} (Pool {self._current_key_idx + 1}/{len(self.api_keys)})")
        return new_key

    async def _get_session(self):
        global aiohttp
        if aiohttp is None:
            try:
                import aiohttp as _aiohttp
                aiohttp = _aiohttp
            except ImportError:
                return None
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _http_get(self, url: str, timeout: float = 15.0) -> Tuple[int, str]:
        """Perform async GET request via aiohttp with urllib fallback."""
        session = await self._get_session()
        if session is not None:
            try:
                async with session.get(url, timeout=timeout) as resp:
                    text = ""
                    if hasattr(resp, "text"):
                        try:
                            res = resp.text() if not callable(resp.text) else resp.text()
                            if asyncio.iscoroutine(res):
                                text = await res
                            elif isinstance(res, str):
                                text = res
                        except Exception:
                            pass
                    if not text and hasattr(resp, "json"):
                        try:
                            res = resp.json() if not callable(resp.json) else resp.json()
                            if asyncio.iscoroutine(res):
                                data = await res
                                text = json.dumps(data)
                            elif isinstance(res, (dict, list)):
                                text = json.dumps(res)
                        except Exception:
                            pass
                    return resp.status, text or "{}"
            except Exception as e:
                logger.debug(f"aiohttp GET error: {e}, attempting urllib fallback")

        # Fallback to standard library urllib
        def _urllib_get():
            import urllib.request
            import urllib.error
            req = urllib.request.Request(url, headers={"User-Agent": "Sentinel/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.getcode(), resp.read().decode("utf-8")
            except urllib.error.HTTPError as he:
                return he.code, he.read().decode("utf-8", errors="ignore")
            except Exception as ex:
                return 500, str(ex)

        return await asyncio.to_thread(_urllib_get)

    async def _http_post(self, url: str, payload: dict, timeout: float = 120.0) -> Tuple[int, str]:
        """Perform async POST request via aiohttp with urllib fallback."""
        session = await self._get_session()
        if session is not None:
            try:
                async with session.post(url, json=payload, timeout=timeout) as resp:
                    text = ""
                    if hasattr(resp, "text"):
                        try:
                            res = resp.text() if not callable(resp.text) else resp.text()
                            if asyncio.iscoroutine(res):
                                text = await res
                            elif isinstance(res, str):
                                text = res
                        except Exception:
                            pass
                    if not text and hasattr(resp, "json"):
                        try:
                            res = resp.json() if not callable(resp.json) else resp.json()
                            if asyncio.iscoroutine(res):
                                data = await res
                                text = json.dumps(data)
                            elif isinstance(res, (dict, list)):
                                text = json.dumps(res)
                        except Exception:
                            pass
                    return resp.status, text or "{}"
            except Exception as e:
                logger.debug(f"aiohttp POST error: {e}, attempting urllib fallback")

        # Fallback to standard library urllib
        def _urllib_post():
            import urllib.request
            import urllib.error
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "Sentinel/1.0"}
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.getcode(), resp.read().decode("utf-8")
            except urllib.error.HTTPError as he:
                return he.code, he.read().decode("utf-8", errors="ignore")
            except Exception as ex:
                return 500, str(ex)

        return await asyncio.to_thread(_urllib_post)

    async def verify_and_select_model(self) -> str:
        """
        Verify available model IDs via GET /v1beta/models.
        Filters model IDs supporting generateContent and selects primary.
        Prioritizes: Gemini 3.5 Flash Lite, Gemini 3.5 Flash, Gemini Flash, then Gemma.
        """
        if self._discovery_completed and self._selected_model:
            return self._selected_model

        if not self.is_configured():
            print("   ⚠️ [Google AI LLM] No API keys configured. Using default model chain.")
            self._selected_model = self._fallback_chain[0]
            self._discovery_completed = True
            return self._selected_model

        max_attempts = max(len(self.api_keys), 1)
        for _ in range(max_attempts):
            active_key = self.get_current_api_key()
            try:
                url = f"{self.API_BASE}/models?key={active_key}"
                status, text = await self._http_get(url, timeout=15.0)
                if status == 200:
                    data = json.loads(text)
                    all_models = data.get("models", [])
                    
                    # Filter models supporting generateContent
                    available = []
                    for m in all_models:
                        name = m.get("name", "")
                        clean_name = name.replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if not methods or "generateContent" in methods:
                            available.append(clean_name)

                    # Prioritize: 
                    # 1. gemini-3.5-flash-lite (fastest, ~1.8s)
                    # 2. gemini-3.5-flash
                    # 3. gemini-3-flash-preview
                    # 4. Other gemini flash models
                    # 5. gemma-4-26b-a4b-it / gemma-4-31b-it / other gemma
                    ordered = []
                    for m in available:
                        if "gemini-3.5-flash-lite" in m and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemini-3.5-flash" in m and "lite" not in m and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemini-3-flash" in m and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemini" in m.lower() and "flash" in m.lower() and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemma" in m.lower() and "26b" in m.lower() and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemma" in m.lower() and "31b" in m.lower() and m not in ordered:
                            ordered.append(m)
                    for m in available:
                        if "gemma" in m.lower() and m not in ordered:
                            ordered.append(m)

                    if ordered:
                        self._discovered_models = ordered
                        primary = ordered[0]
                        self._selected_model = primary
                        self._fallback_chain = ordered
                        print(f"   🤖 [Google AI LLM] Discovered {len(ordered)} model(s) (key ...{active_key[-6:]}). Selected primary: {primary}")
                        self._discovery_completed = True
                        return primary
                elif status == 429 or status >= 500 or status == 403:
                    self.rotate_to_next_key(f"Discovery status {status}")
                    continue
                else:
                    print(f"   ⚠️ [Google AI LLM] Model discovery returned status {status}: {text[:100]}")
                    break
            except Exception as e:
                print(f"   ⚠️ [Google AI LLM] Model discovery failed on key ...{active_key[-6:]}: {e}")
                self.rotate_to_next_key("Discovery exception")

        # Fallback to defaults
        self._selected_model = self._fallback_chain[0]
        self._discovery_completed = True
        print(f"   ℹ️ [Google AI LLM] Using fallback model: {self._selected_model}")
        return self._selected_model

    discover_and_select_model = verify_and_select_model

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/mp3") -> Optional[str]:
        """Transcribe audio clips using Google AI's gemini-3.5-transcribe model with failover across API keys."""
        if not self.is_configured() or not audio_bytes:
            return None
        import base64
        b64_data = base64.b64encode(audio_bytes).decode("utf-8")
        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": (
                            "Transcribe ONLY the numbers or words spoken in this audio. "
                            "Output only the transcription without punctuation or formatting, nothing else."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }]
        }

        max_attempts = max(len(self.api_keys), 1)
        for _ in range(max_attempts):
            active_key = self.get_current_api_key()
            url = f"{self.API_BASE}/models/gemini-3.5-transcribe:generateContent?key={active_key}"
            try:
                status, text = await self._http_post(url, payload, timeout=20.0)
                if status == 200:
                    data = json.loads(text)
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            ans = parts[0]["text"].strip()
                            print(f"      🎙️ [Gemini 3.5 Transcribe] Result (key ...{active_key[-6:]}): {ans!r}")
                            return ans
                elif status == 429 or status >= 500 or status == 403:
                    self.rotate_to_next_key(f"Audio transcription status {status}")
                    continue
                else:
                    logger.warning(f"Audio transcription returned status {status}: {text[:120]}")
                    break
            except Exception as e:
                logger.error(f"Audio transcription failed on key ...{active_key[-6:]}: {e}")
                self.rotate_to_next_key("Audio transcription exception")
        return None

    def _build_prompt(self, question: str, options: Optional[List[str]] = None,
                      input_type: str = "text", context: Optional[str] = None) -> str:
        """Construct candidate-aligned prompt for Gemma."""
        facts = get_candidate_facts()
        prompt_parts = [
            f"{SYSTEM_INSTRUCTIONS}\n",
            f"{facts}\n",
        ]

        if context:
            prompt_parts.append(
                f"RECOMMENDED CANDIDATE PATTERN / CONTEXT (from verified knowledge base):\n"
                f"{context}\n"
                f"(Adhere closely to this recommendation unless the available options require a specific option choice string).\n"
            )

        prompt_parts.append(f"Input Type: {input_type}\n")

        if options and len(options) > 0:
            formatted_opts = "\n".join(f"- {opt}" for opt in options)
            prompt_parts.append(
                f"Available Options (You MUST choose and output EXACTLY ONE of these exact strings verbatim):\n{formatted_opts}\n"
            )

        prompt_parts.append(
            f"Question: {question}\n\n"
            f"Direct Answer:"
        )

        return "\n".join(prompt_parts)

    def _match_chosen_option(self, raw_answer: str, options: List[str]) -> str:
        if not options:
            return raw_answer
        strip_chars = "\"'` "
        cleaned_raw = raw_answer.strip().strip(strip_chars).lower()

        # 1. Exact match (case-insensitive)
        for opt in options:
            if opt.strip().lower() == cleaned_raw:
                return opt

        # 2. Substring match
        for opt in options:
            opt_clean = opt.strip().lower()
            if opt_clean in cleaned_raw or cleaned_raw in opt_clean:
                return opt

        # 3. Yes/No matching
        if cleaned_raw.startswith("yes"):
            for opt in options:
                if "yes" in opt.strip().lower():
                    return opt
        elif cleaned_raw.startswith("no"):
            for opt in options:
                if "no" in opt.strip().lower():
                    return opt

        # 4. Numeric Range Matching (e.g. 4.2 -> '3-5 years', 15 -> '15-30 days')
        try:
            from src.patterns.input_aware_resolver import NumericRangeMatcher
            num_m = re.search(r"(\d+(?:\.\d+)?)", cleaned_raw)
            if num_m:
                val = float(num_m.group(1))
                target_val = 4.2 if (3.5 <= val <= 5.5) else val
                has_covering = False
                for opt in options:
                    extracted = NumericRangeMatcher.extract_range(opt)
                    if extracted:
                        low, high, rtype = extracted
                        if (low == 4.0 or (target_val >= low and target_val <= high)) and high > 4.0:
                            has_covering = True
                            break

                best_opt = None
                best_score = -1
                for opt in options:
                    extracted = NumericRangeMatcher.extract_range(opt)
                    if extracted:
                        low, high, rtype = extracted
                        if target_val >= 4.0 and high <= 4.0 and has_covering:
                            continue
                        if low <= target_val <= high:
                            score = 100
                            if low == 4.0:
                                score += 10
                            if score > best_score:
                                best_score = score
                                best_opt = opt
                if best_opt:
                    return best_opt
        except Exception:
            pass

        # 5. Token overlap match fallback
        try:
            tokens_raw = set(re.findall(r"[a-z0-9]+", cleaned_raw))
            if tokens_raw:
                best_opt = None
                best_overlap = 0
                for opt in options:
                    tokens_opt = set(re.findall(r"[a-z0-9]+", opt.lower()))
                    overlap = len(tokens_raw & tokens_opt)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_opt = opt
                if best_opt and best_overlap >= 1:
                    return best_opt
        except Exception:
            pass

        # Return the original raw answer if no match found
        return raw_answer.strip()

    def _normalize_uniform_answer(self, answer: str, question: str, input_type: str = "text") -> str:
        """Post-process short field answers to enforce strict uniformity across questionnaires."""
        if not answer:
            return answer
        
        q_lower = question.lower().strip()
        ans_trimmed = answer.strip().strip("\"'`")

        # Guard: Do not collapse descriptive essays, architectural case studies, or multi-sentence explanations
        is_descriptive = any(kw in q_lower for kw in [
            'describe', 'explain', 'walk us through', 'tell us', 'architecture', 'system design',
            'challenging', 'project', 'overview', 'details', 'why do you', 'why should', 'essay'
        ])
        if is_descriptive and len(ans_trimmed) > 60:
            return ans_trimmed

        # 0. Strict Numeric / Integer Input Formatting (e.g. 4.2 -> 4)
        if any(kw in input_type.lower() for kw in ["number", "integer", "numeric"]):
            match = re.search(r"(\d+(?:\.\d+)?)", ans_trimmed)
            if match:
                val = float(match.group(1))
                return str(int(round(val)))

        # Skip multi-part questions (e.g. experience + ctc + notice period + location)
        has_exp = "experience" in q_lower or "years" in q_lower or "exp" in q_lower
        has_ctc = "ctc" in q_lower or "salary" in q_lower or "compensation" in q_lower or "cctc" in q_lower or "ectc" in q_lower
        has_np = "notice" in q_lower or "lwd" in q_lower or "last working day" in q_lower
        has_loc = "location" in q_lower or "city" in q_lower or "based" in q_lower

        # If 3 or more aspects are combined in the question, don't collapse to a single field
        combined_aspects = sum([1 if has_exp else 0, 1 if has_ctc else 0, 1 if has_np else 0, 1 if has_loc else 0])
        if combined_aspects >= 3:
            return ans_trimmed

        is_current = "current" in q_lower or "cctc" in q_lower or "present" in q_lower
        is_expected = "expected" in q_lower or "ectc" in q_lower or "expecting" in q_lower

        # 1. Salary / CTC Uniformity
        if is_current and is_expected and has_ctc:
            return "Current CTC: 23 LPA, Expected CTC: 30 LPA"
        elif is_current and has_ctc and not is_expected:
            if "breakdown" not in q_lower and "fixed" not in q_lower and "variable" not in q_lower:
                match = re.search(r"23\s*LPA", ans_trimmed, re.IGNORECASE)
                if match:
                    return "23 LPA"
                if re.search(r"\b23\b", ans_trimmed):
                    return "23 LPA"
            else:
                match = re.search(r"23\s*LPA", ans_trimmed, re.IGNORECASE)
                if match and ("fixed" in ans_trimmed.lower() or "variable" in ans_trimmed.lower() or "breakdown" in q_lower):
                    return "23 LPA (Fixed: 23 LPA, Variable: 0 LPA)"
                if re.search(r"\b23\b", ans_trimmed):
                    return "23 LPA (Fixed: 23 LPA, Variable: 0 LPA)"
        elif is_expected and has_ctc and not is_current:
            if "breakdown" not in q_lower and "fixed" not in q_lower and "variable" not in q_lower:
                match = re.search(r"30\s*LPA", ans_trimmed, re.IGNORECASE)
                if match:
                    return "30 LPA"
                if re.search(r"\b30\b", ans_trimmed):
                    return "30 LPA"
            else:
                match = re.search(r"30\s*LPA", ans_trimmed, re.IGNORECASE)
                if match:
                    return "30 LPA (100% Fixed)"
                if re.search(r"\b30\b", ans_trimmed):
                    return "30 LPA (100% Fixed)"

        # 2. Experience Uniformity
        if ("how many years" in q_lower or "total experience" in q_lower or "work experience" in q_lower or "years of experience" in q_lower) and "deployment" not in q_lower and not has_ctc and not has_np:
            match = re.search(r"4(?:\.2)?\s*years?", ans_trimmed, re.IGNORECASE)
            if match:
                return "4.2 Years"

        # 3. Location Uniformity
        if "current location" in q_lower and not has_ctc and not has_exp:
            if "bangalore" in ans_trimmed.lower() or "bengaluru" in ans_trimmed.lower():
                return "Bangalore, Karnataka, India"

        # 4. Notice Period & LWD Uniformity
        if ("notice" in q_lower or "np" in q_lower or "lwd" in q_lower or "last working day" in q_lower) and not has_ctc and not has_exp:
            from datetime import datetime, timedelta
            lwd_date = datetime.now() + timedelta(days=15)
            lwd_formatted = lwd_date.strftime('%d %B %Y')
            lwd_short = lwd_date.strftime('%d/%m/%Y')
            if ("last working day" in q_lower or "lwd" in q_lower) and "notice" in q_lower:
                return f"15 days (serving notice, LWD: {lwd_formatted})"
            elif ("last working day" in q_lower or "lwd" in q_lower) and "notice" not in q_lower:
                date_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", ans_trimmed)
                if date_match:
                    return date_match.group(0)
                return lwd_formatted
            elif "notice" in q_lower and not any(kw in input_type.lower() for kw in ["number", "integer", "numeric"]):
                if ans_trimmed in ["15.0", "15", "15 days", "15days"]:
                    return "15 days"

        # 5. Clean trailing periods and floating decimals on short single-line values
        if len(ans_trimmed.split("\n")) == 1 and len(ans_trimmed) < 40:
            if ans_trimmed.endswith(".0"):
                ans_trimmed = ans_trimmed[:-2].strip()
            elif ans_trimmed.endswith("."):
                ans_trimmed = ans_trimmed[:-1].strip()

        return ans_trimmed

    async def answer_question(self, question: str, options: Optional[List[str]] = None,
                              input_type: str = "text", context: Optional[str] = None) -> Optional[str]:
        """
        Answer a questionnaire question with dynamic model discovery, multi-key failover pool, and fail-open resilience.
        Returns the answer string, or None if all models and API keys fail.
        """
        if not question or not question.strip():
            return None

        if not self.is_configured():
            print("   ⚠️ [Google AI LLM] No API keys configured. Failing open to pattern matching.")
            return None

        # Ensure model is verified
        if not self._discovery_completed:
            await self.verify_and_select_model()

        models_to_try = list(self._fallback_chain)
        prompt = self._build_prompt(question, options=options, input_type=input_type, context=context)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 16000,
                "topK": 20,
                "topP": 0.8
            }
        }

        num_keys = max(len(self.api_keys), 1)

        for model_id in models_to_try:
            clean_model = model_id.replace("models/", "")

            for key_attempt in range(num_keys):
                active_key = self.get_current_api_key()
                endpoint = f"{self.API_BASE}/models/{clean_model}:generateContent?key={active_key}"
                start_time = time.time()
                try:
                    status, text = await self._http_post(endpoint, payload=payload, timeout=60.0)
                    elapsed = time.time() - start_time
                    if status == 200:
                        data = json.loads(text)
                        candidates = data.get("candidates", [])
                        if candidates and len(candidates) > 0:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and len(parts) > 0:
                                # 1. Separate thought parts from actual output parts
                                non_thought_parts = [p.get("text", "") for p in parts if not p.get("thought", False)]
                                raw_text = "".join(non_thought_parts).strip()

                                # 2. Fallback if all parts were marked or unmarked
                                if not raw_text:
                                    all_text = "".join(p.get("text", "") for p in parts).strip()
                                    stripped = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", all_text, flags=re.DOTALL).strip()
                                    if stripped and not stripped.startswith(("*   Role:", "*   User wants", "*   Constraint")):
                                        raw_text = stripped

                                if not raw_text:
                                    print(f"   ⚠️ [Google AI LLM] No non-thought answer produced by {clean_model} (key ...{active_key[-6:]}). Failing over...")
                                    self.rotate_to_next_key("No non-thought output")
                                    continue

                                cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                                cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()
                                cleaned_text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", cleaned_text, flags=re.DOTALL).strip()
                                cleaned_text = cleaned_text.strip("\"'` ")

                                # Guard: if the text still looks like thinking/reasoning bullet points, reject it
                                if cleaned_text.startswith(("*   Role:", "*   User wants", "*   Constraint", "Role: Job applicant")):
                                    print(f"   ⚠️ [Google AI LLM] Detected reasoning spillover in output from {clean_model} (key ...{active_key[-6:]}). Failing over...")
                                    self.rotate_to_next_key("Reasoning spillover")
                                    continue

                                if options:
                                    final_answer = self._match_chosen_option(cleaned_text, options)
                                else:
                                    final_answer = self._normalize_uniform_answer(cleaned_text, question, input_type=input_type)

                                print(f"   🤖 [Google AI LLM] Model: {clean_model} (key ...{active_key[-6:]}) | Latency: {elapsed:.2f}s | Q: '{question[:40]}...' -> A: '{final_answer}'")
                                return final_answer
                    elif status == 429:
                        print(f"   ⚠️ [Google AI LLM] Rate limited (429) on key ...{active_key[-6:]}. Failing over to next key...")
                        self.rotate_to_next_key("Rate limit (429)")
                        continue
                    elif status == 403:
                        print(f"   ⚠️ [Google AI LLM] Quota / Permission error (403) on key ...{active_key[-6:]}. Failing over to next key...")
                        self.rotate_to_next_key("Quota error (403)")
                        continue
                    elif status >= 500:
                        print(f"   ⚠️ [Google AI LLM] Server error ({status}) on key ...{active_key[-6:]}. Failing over to next key...")
                        self.rotate_to_next_key(f"Server error ({status})")
                        continue
                    elif status == 404 or status == 400:
                        print(f"   ⚠️ [Google AI LLM] {clean_model} returned {status}: {text[:80]}. Trying next fallback model...")
                        break
                    else:
                        print(f"   ⚠️ [Google AI LLM] {clean_model} returned status {status}: {text[:80]}. Failing over...")
                        self.rotate_to_next_key(f"Status {status}")
                        continue
                except asyncio.TimeoutError:
                    print(f"   ⏱️ [Google AI LLM] {clean_model} timed out after 60s on key ...{active_key[-6:]}. Failing over...")
                    self.rotate_to_next_key("Timeout")
                    continue
                except Exception as ex:
                    print(f"   ⚠️ [Google AI LLM] Request error on {clean_model} (key ...{active_key[-6:]}): {ex}. Failing over...")
                    self.rotate_to_next_key("Request exception")
                    continue

        print(f"   ❌ [Google AI LLM] All models and API keys failed for question: '{question[:40]}...'. Failing open to pattern matching.")
        return None
