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

from src.core.config import GOOGLE_AI_API_KEY

logger = logging.getLogger(__name__)

# Default fallback models if discovery API is unavailable
DEFAULT_GEMMA_MODELS = [
    "gemma-3-27b-it",
    "gemma-2-27b-it",
    "gemma-2-9b-it",
    "gemma-2-2b-it"
]

def get_candidate_facts() -> str:
    from datetime import datetime, timedelta
    now = datetime.now()
    today_str = now.strftime('%d/%m/%Y')
    today_verbose = now.strftime('%d %b %Y')
    lwd_dt = now + timedelta(days=15)
    lwd_str = lwd_dt.strftime('%d/%m/%Y')
    lwd_verbose = lwd_dt.strftime('%d %b %Y')

    return f"""CANDIDATE FACTSHEET (Siddhant Singh):
1. Personal & Contact Information:
   - Full Name: Siddhant Singh
   - Email: siddhant3646@gmail.com
   - Phone: +91-7905828880 (Mobile: 7905828880, Country Code: India / +91)
   - Current Location: Bangalore, Karnataka, India
   - Citizenship: Indian (Citizen & Resident of India)
   - Visa / Sponsorship: Authorized to work in India; do not require any visa sponsorship
   - Online Profiles:
     * LinkedIn: https://www.linkedin.com/in/siddhant-singh/
     * Portfolio / Website: https://siddhant3646.github.io/Portfolio/
     * GitHub: https://github.com/siddhant3646

2. Current Employment & Career Profile:
   - Current Employer: Everbridge (Bangalore)
   - Current Designation: Software Engineer 2 (SDE-2)
   - Employment Type: Full-time (Permanent)
   - Total Software Engineering Experience: 4.2 Years (50 months)
   - Notice Period: 15 days (Currently serving notice period)
   - Last Working Day (LWD): {lwd_str} ({lwd_verbose}) [Calculated as today: {today_str} + 15 days]
   - Immediate Joiner: Yes, available to join immediately on or before {lwd_verbose}
   - Offers in Hand: None currently (actively interviewing and ready to evaluate and accept the right offer)
   - Reason for Job Change: Looking for a high-impact engineering role in distributed systems, backend architectures, and high-scale applications.
   - Career Breaks: None (Continuous full-time work history)

3. Compensation Details:
   - Current CTC (CCTC): 23 LPA (23,00,000 INR per annum)
     * Structure: 100% Fixed (Fixed: 23 LPA, Variable: 0 LPA)
   - Expected CTC (ECTC): 30 LPA (30,00,000 INR per annum)
     * Structure: 100% Fixed (Fixed: 30 LPA, Variable: 0 LPA)
   - Negotiable / Flexibility: Standard expectation is 30 LPA (100% Fixed).

4. Location & Work Arrangement Preferences:
   - Current City: Bangalore
   - Willingness to Relocate: Yes, 100% open to relocation across India.
   - Preferred Locations: Bangalore, Delhi/NCR, Gurgaon, Noida, Hyderabad, Mumbai, Pune, Chennai, Kolkata, Ahmedabad, Remote / Work From Home.
   - Work Mode Flexibility: Comfortable with On-site (in-office), Hybrid, or Fully Remote work models.
   - Shifts: Comfortable with standard day shifts / flexible engineering hours.
   - Interview Formats: Willing and available for both F2F (in-person office rounds) and AI/video technical interview rounds.

5. Education & Academics:
   - Undergraduate Degree: Bachelor of Technology (B.Tech) in Computer Science & Engineering (CSE)
     * Institution: Vellore Institute of Technology (VIT Bhopal)
     * Year of Graduation: 2022
     * CGPA / Score: 8.51 CGPA (85.1%)
   - Class 12th / Senior Secondary (HSC): Completed in 2018, CGPA: 8.8 (88%)
   - Class 10th / Secondary (SSC): Completed in 2016, Percentage: 70%

6. Core Technical Skills & Years of Experience:
   - Primary Backend Languages:
     * Java (Java 8, 11, 17, 21, Concurrency, Virtual Threads, Multithreading, JVM Performance Tuning, Collections): 4.2 Years
     * Python (FastAPI, Flask, Scripting, Automation): 2+ Years
     * JavaScript / TypeScript, Node.js: 2+ Years
   - Frameworks & ORM:
     * Spring Boot (2.x / 3.x), Spring Framework, Spring Data JPA, Spring Cloud, Spring Security, Hibernate: 4.2 Years
   - Distributed Systems, Messaging & Streaming:
     * Apache Kafka (Topics, Partitions, Consumer Groups, Offsets, Kafka Streams, Exactly-once processing semantics): 3+ Years
     * Apache Flink & Apache Spark (Stream Processing, Event-driven pipelines, Windowing, State Backends): 2+ Years
     * In-Memory Caching (Redis, Memcached - Distributed Caching, Cache-Aside, Write-Through, Redis Sentinel/Cluster, Key Expiration): 3+ Years
     * Microservices Architecture, RESTful APIs, gRPC, API Gateway, Service Mesh: 4.2 Years
     * Distributed Transactions & Resilience: Saga Pattern (Orchestration & Choreography), Transactional Outbox Pattern, Idempotent Consumers, Circuit Breakers (Resilience4j), Rate Limiting: 4.2 Years
   - Databases & Data Storage:
     * Relational: PostgreSQL, MySQL, SQL Server (Schema Design, B-Tree/GIN Indexing, Query Optimization, HikariCP Connection Pooling, ACID Transactions): 4.2 Years
     * NoSQL: MongoDB (Document Models, Aggregation Pipelines, Indexes), DynamoDB: 3+ Years
   - Cloud, DevOps & Infrastructure:
     * AWS Cloud (EC2, S3, RDS, Lambda, EKS, CloudWatch, IAM, SQS, SNS, ALB): 4.2 Years
     * Containerization: Docker, Docker Compose, Kubernetes (Pods, Deployments, Services, Ingress, Horizontal Pod Autoscalers / HPA): 3+ Years
     * CI/CD & Build Tools: Git, GitHub Actions, GitLab CI, Maven, Gradle, Jenkins: 4.2 Years
     * Observability: Prometheus, Grafana, OpenTelemetry, ELK / OpenSearch: 3+ Years
   - Frontend:
     * React.js, Redux, HTML5, CSS3, Modern ES6+: 3+ Years
     * Angular / TypeScript familiarity: 2+ Years

7. In-Depth Engineering Highlights & Architectural Case Studies (at Everbridge):
   - High-Scale Microservices & Java 21 Modernization:
     * Architected and maintained critical event-driven notification microservices processing over 10M+ daily events under strict SLA requirements.
     * Led the migration of core high-traffic backend services from Java 8 to Java 21 with Virtual Threads and Spring Reactive stacks, accelerating dispute processing under 2s and improving throughput by 15%.
   - Real-Time Data Streaming & Ledger Reconciliation:
     * Designed an Apache Kafka and Apache Flink pipeline to stream, process, and aggregate high-volume operational events.
     * Enhanced settlement reporting reliability by 40% and eliminated distributed ledger discrepancies by implementing transactional outbox and idempotent event processing.
   - Traffic Surge & Failure Mitigation (10x Spike Strategy):
     * Immediate stabilization: Enforce rate limiting and load shedding (Token Bucket via Redis / API Gateway) and activate Resilience4j circuit breakers with graceful fallback responses.
     * Elastic horizontal scaling: Auto-scale service pods via Kubernetes HPA on CPU/memory and Kafka consumer lag metrics; spin up PostgreSQL read replicas.
     * Buffering & Caching: Offload write surges to asynchronous Kafka message buffers and absorb read spikes with distributed Redis caching.
     * Root cause profiling: Monitor APM, Grafana, and HikariCP connection pool metrics to isolate database bottlenecks or unindexed queries.
   - URL Shortener (TinyURL) Architecture:
     * Base62 encoding over unique 64-bit distributed IDs (Snowflake/DB auto-increment); distributed Redis cache for hot redirect lookups (absorbing >90% read load); PostgreSQL/MongoDB for persistent storage with unique index on short key; 301/302 HTTP redirects; Bloom filters for quick key existence checks.
   - Distributed Data Consistency:
     * Applied Saga pattern (orchestrated workflow) for long-running multi-service transactions with compensating actions.
     * Enforced Transactional Outbox pattern with Debezium / Kafka Connect to prevent dual-write anomalies, coupled with consumer idempotency deduplication keys in Redis.
"""

SYSTEM_INSTRUCTIONS = """You are Siddhant Singh, an experienced Software Engineer (SDE-2 at Everbridge), answering recruiter questionnaire forms for job applications.

VOICE, TONE, AND HUMAN AUTHENTICITY GUIDELINES:
1. Speak in your genuine, first-person candidate voice ("I", "my team", "at Everbridge I...").
2. Write naturally, professionally, and conversationally like a skilled software engineer typing directly into a form.
3. NEVER sound like an AI assistant, a chatbot, or a textbook:
   - NEVER use AI disclosures, disclaimers, or meta-comments. Never mention or disclose that you are an AI or using an LLM. Avoid hedging, hesitation, or AI-like preamble (do NOT say "As an AI...", "Certainly!", "Sure!", "Here is my answer:", "Based on my resume...", "In conclusion...", "I hope this helps!").
   - NEVER repeat or echo the prompt or question before answering.
   - NEVER use markdown code fences, headers (###), or artificial bulleted lists for short single-paragraph responses.
4. ANSWER FORMATTING RULES BY QUESTION TYPE:
   - For Short / Numerical / Factual Fields (CTC, Experience, Notice Period, Dates, Locations, Phone, Email):
     Output ONLY the exact, standard value without conversational filler:
     * Current CTC: "23 LPA" (or "23 LPA (100% Fixed)" if breakdown requested)
     * Expected CTC: "30 LPA" (or "30 LPA (100% Fixed)" if breakdown requested)
     * Combined CTC: "Current CTC: 23 LPA, Expected CTC: 30 LPA"
     * Total Experience: "4.2 Years" (or "4.2" if numeric field)
     * Java / Spring Boot / Relevant Experience: "4.2 Years" (or "4.2" if numeric field)
     * Notice Period: "15 days" (or "15" if numeric field)
     * Last Working Day (LWD): Output the exact computed date: "{lwd_str}" (calculated as today + 15 days)
     * Combined Notice & LWD: "15 days, LWD: {lwd_str}"
     * Current Location: "Bangalore, Karnataka, India"
     * Relocation / Immediate Joiner / Open to Hybrid: "Yes"
     * Simple Yes/No questions: "Yes" or "No"
   - For Multiple Choice / Dropdown / Radio Options:
     * When options are provided, you MUST pick and output EXACTLY ONE of the provided option strings verbatim.
   - For Open-Ended Technical, Architectural, and Problem-Solving Questions (e.g. TinyURL system design, 10x traffic spikes, technical challenges, microservice communication, distributed consistency):
     * Provide a concise, highly pragmatic, 1-2 paragraph engineering response in the first person.
     * Reference your real-world experience at Everbridge using Java 21, Spring Boot, Kafka, Redis, PostgreSQL, AWS, and Kubernetes.
     * Sound like an authentic senior engineer sharing practical production decisions, trade-offs, and metrics.
5. Output ONLY your direct answer text.
"""


class GemmaLLMClient:
    """Async Google AI Studio Gemma client with dynamic discovery and fail-open resilience."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else GOOGLE_AI_API_KEY
        self._discovered_models: List[str] = []
        self._selected_model: Optional[str] = None
        self._fallback_chain: List[str] = list(DEFAULT_GEMMA_MODELS)
        self._discovery_completed: bool = False
        self._session: Optional[aiohttp.ClientSession] = None

    def is_configured(self) -> bool:
        """Check if client has a valid API key configured."""
        return bool(self.api_key and self.api_key.strip())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def verify_and_select_model(self) -> str:
        """
        Verify available Gemma model IDs via GET /v1beta/models.
        Filters Gemma IDs, logs the list, and selects primary:
        prioritizes responsive Gemma 4 models (e.g. gemma-4-26b-a4b-it or gemma-4-31b-it).
        """
        if self._discovery_completed and self._selected_model:
            return self._selected_model

        if not self.api_key:
            print("   ⚠️ [Gemma LLM] No GOOGLE_AI_API_KEY configured. Using default model chain.")
            self._selected_model = self._fallback_chain[0]
            self._discovery_completed = True
            return self._selected_model

        try:
            url = f"{self.API_BASE}/models?key={self.api_key}"
            session = await self._get_session()
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    all_models = data.get("models", [])
                    # Filter models supporting generateContent and containing gemma
                    gemma_models = []
                    for m in all_models:
                        name = m.get("name", "")
                        clean_name = name.replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "gemma" in clean_name.lower():
                            if not methods or "generateContent" in methods:
                                gemma_models.append(clean_name)

                    self._discovered_models = gemma_models
                    print(f"   🤖 [Gemma LLM] Discovered {len(gemma_models)} Gemma model(s): {gemma_models}")

                    if gemma_models:
                        # Order priority: gemma-4-26b-a4b-it, gemma-4-31b-it, gemma-3-*, gemma-2-*
                        ordered = []
                        for m in gemma_models:
                            if "26b" in m.lower() and "gemma" in m.lower():
                                ordered.append(m)
                        for m in gemma_models:
                            if "31b" in m.lower() and m not in ordered:
                                ordered.append(m)
                        for m in gemma_models:
                            if m not in ordered:
                                ordered.append(m)

                        primary = ordered[0]
                        self._selected_model = primary
                        self._fallback_chain = ordered
                        print(f"   🎯 [Gemma LLM] Selected primary model: {primary}")
                        self._discovery_completed = True
                        return primary
                else:
                    err_text = await resp.text()
                    print(f"   ⚠️ [Gemma LLM] Model discovery returned status {resp.status}: {err_text[:100]}")
        except Exception as e:
            print(f"   ⚠️ [Gemma LLM] Model discovery failed: {e}")

        # Fallback to defaults
        self._selected_model = self._fallback_chain[0]
        self._discovery_completed = True
        print(f"   ℹ️ [Gemma LLM] Using fallback model: {self._selected_model}")
        return self._selected_model

    discover_and_select_model = verify_and_select_model

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
                f"Context from your own previous answers (use for consistency where applicable):\n"
                f"{context}\n"
            )

        prompt_parts.append(f"Input Type: {input_type}\n")

        if options and len(options) > 0:
            formatted_opts = "\n".join(f"- {opt}" for opt in options)
            prompt_parts.append(
                f"Available Options (You MUST choose one of these exact strings):\n{formatted_opts}\n"
            )

        prompt_parts.append(
            f"Question: {question}\n\n"
            f"Answer:"
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

        # Return the original raw answer if no match found
        return raw_answer.strip()

    def _normalize_uniform_answer(self, answer: str, question: str) -> str:
        """Post-process short field answers to enforce strict uniformity across questionnaires."""
        if not answer:
            return answer
        
        q_lower = question.lower().strip()
        ans_trimmed = answer.strip().strip("\"'`")

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
            else:
                match = re.search(r"23\s*LPA", ans_trimmed, re.IGNORECASE)
                if match and ("fixed" in ans_trimmed.lower() or "variable" in ans_trimmed.lower() or "breakdown" in q_lower):
                    return "23 LPA (Fixed: 23 LPA, Variable: 0 LPA)"
        elif is_expected and has_ctc and not is_current:
            if "breakdown" not in q_lower and "fixed" not in q_lower and "variable" not in q_lower:
                match = re.search(r"30\s*LPA", ans_trimmed, re.IGNORECASE)
                if match:
                    return "30 LPA"
            else:
                match = re.search(r"30\s*LPA", ans_trimmed, re.IGNORECASE)
                if match:
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

        # 4. Notice Period Uniformity
        if "last working day" in q_lower and "notice period" not in q_lower and not has_ctc:
            # Extract date if present
            date_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", ans_trimmed)
            if date_match:
                return date_match.group(0)

        # 5. Clean trailing periods on short single-line values
        if len(ans_trimmed.split("\n")) == 1 and len(ans_trimmed) < 40 and ans_trimmed.endswith("."):
            ans_trimmed = ans_trimmed[:-1].strip()

        return ans_trimmed

    async def answer_question(self, question: str, options: Optional[List[str]] = None,
                              input_type: str = "text", context: Optional[str] = None) -> Optional[str]:
        """
        Answer a questionnaire question with fail-open resilience.
        Returns the answer string, or None if the API fails or no key is present.
        """
        if not question or not question.strip():
            return None

        if not self.api_key:
            print("   ⚠️ [Gemma LLM] No GOOGLE_AI_API_KEY configured. Failing open to pattern matching.")
            return None

        # Ensure model is verified
        if not self._discovery_completed:
            await self.verify_and_select_model()

        models_to_try = list(self._fallback_chain)
        prompt = self._build_prompt(question, options=options, input_type=input_type, context=context)

        session = await self._get_session()

        for model_id in models_to_try:
            clean_model = model_id.replace("models/", "")
            endpoint = f"{self.API_BASE}/models/{clean_model}:generateContent?key={self.api_key}"

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

            for attempt in range(3):
                start_time = time.time()
                try:
                    async with session.post(endpoint, json=payload, timeout=120) as resp:
                        elapsed = time.time() - start_time
                        if resp.status == 200:
                            data = await resp.json()
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
                                        # Strip <thought>...</thought> or <think>...</think> tags
                                        stripped = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", all_text, flags=re.DOTALL).strip()
                                        if stripped and not stripped.startswith(("*   Role:", "*   User wants", "*   Constraint")):
                                            raw_text = stripped

                                    if not raw_text:
                                        print(f"   ⚠️ [Gemma LLM] No non-thought answer produced by {clean_model}. Falling back...")
                                        break

                                    cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                                    cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()
                                    cleaned_text = re.sub(r"<(?:thought|think)>.*?</(?:thought|think)>", "", cleaned_text, flags=re.DOTALL).strip()
                                    cleaned_text = cleaned_text.strip("\"'` ")

                                    # Guard: if the text still looks like thinking/reasoning bullet points, reject it
                                    if cleaned_text.startswith(("*   Role:", "*   User wants", "*   Constraint", "Role: Job applicant")):
                                        print(f"   ⚠️ [Gemma LLM] Detected reasoning spillover in output from {clean_model}. Falling back...")
                                        break

                                    if options:
                                        final_answer = self._match_chosen_option(cleaned_text, options)
                                    else:
                                        final_answer = self._normalize_uniform_answer(cleaned_text, question)

                                    print(f"   🤖 [Gemma LLM] Model: {clean_model} | Latency: {elapsed:.2f}s | Q: '{question[:40]}...' -> A: '{final_answer}'")
                                    return final_answer
                        elif resp.status == 429 or resp.status >= 500:
                            backoff = min(1.0 * (2 ** attempt), 4.0)
                            print(f"   ⚠️ [Gemma LLM] {clean_model} returned {resp.status}. Retrying in {backoff:.1f}s (attempt {attempt + 1}/3)...")
                            await asyncio.sleep(backoff)
                            continue
                        elif resp.status == 404 or resp.status == 400:
                            err_msg = await resp.text()
                            print(f"   ⚠️ [Gemma LLM] {clean_model} returned {resp.status}: {err_msg[:80]}. Trying next fallback model...")
                            break
                        else:
                            err_msg = await resp.text()
                            print(f"   ⚠️ [Gemma LLM] {clean_model} returned status {resp.status}: {err_msg[:80]}")
                            break
                except asyncio.TimeoutError:
                    print(f"   ⏱️ [Gemma LLM] {clean_model} timed out after 20s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(1.0)
                except Exception as ex:
                    print(f"   ⚠️ [Gemma LLM] Request error on {clean_model}: {ex}")
                    await asyncio.sleep(1.0)

        print(f"   ❌ [Gemma LLM] All models in fallback chain failed for question: '{question[:40]}...'. Failing open to pattern matching.")
        return None
