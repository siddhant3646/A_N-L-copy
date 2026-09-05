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

import aiohttp

from src.core.config import GOOGLE_AI_API_KEY

logger = logging.getLogger(__name__)

# Default fallback models if discovery API is unavailable
DEFAULT_GEMMA_MODELS = [
    "gemma-3-27b-it",
    "gemma-2-27b-it",
    "gemma-2-9b-it",
    "gemma-2-2b-it"
]

CANDIDATE_FACTS = """Candidate Profile:
- Name: Siddhant Singh
- Email: siddhant3646@gmail.com
- Phone: 7905828880
- Current Role: Software Engineer 2 at Everbridge
- Total Experience: 4 Years (48 months total)
- Key Skills: Java, JavaScript, HTML, CSS, ReactJS, NodeJS, Python, Spring Boot, Hibernate, AWS, SQL, Docker, Kubernetes, Microservices, REST APIs, System Design, CI/CD
- Current CTC / Salary: 23 LPA (23,00,000 INR per annum, ~1,91,667 INR/month)
- Expected CTC / Salary: 30 LPA (30,00,000 INR per annum, ~2,50,000 INR/month)
- Notice Period: 15 days (Serving Notice Period)
- Last Working Day (LWD): Feb 03, 2026 (03/02/2026)
- Immediate Joiner: Yes, can join immediately or within 15 days
- Current Location: Bangalore, Karnataka, India
- Relocation: Willing to relocate (Yes)
- Preferred Locations: Bangalore, Delhi/NCR, Hyderabad, Remote, Mumbai, Pune, Gurgaon, Noida, Chennai, Kolkata, Ahmedabad
- Work Mode: Comfortable with On-site, Hybrid, or Remote
- Education: B.Tech in Computer Science and Engineering from VIT Bhopal (2022), CGPA: 8.51 (85.1%)
- 12th / HSC: Completed in 2018, CGPA: 8.8 (88%)
- 10th / SSC: Completed in 2016, Percentage: 70%
- Citizenship: Indian (Citizen and Resident of India)
- Visa / Sponsorship: Authorized to work in India; do not require visa sponsorship
"""

SYSTEM_INSTRUCTIONS = """You are answering job application questions on behalf of yourself as a job applicant.
Strict rules:
1. Always speak in the first-person candidate voice ("I", "my").
2. NEVER mention or disclose that you are an AI, a language model, Gemma, an assistant, or automation.
3. NEVER include any hedging, disclaimers, explanations, or meta-commentary (e.g., do NOT say "Based on my background", "Here is my answer", "As a candidate", "I would select").
4. If options are provided (Multiple Choice, Radio, Select, Checkbox): You MUST output ONLY the EXACT string of one of the options verbatim. Do not alter casing, do not add prefixes like "Option A:" or quotes.
5. If the question asks for a numeric value (e.g. years of experience, notice period in days, salary in LPA or INR), output ONLY the concise numeric or unit answer (e.g. "4", "4 Years", "23", "23 LPA", "15", "03/02/2026").
6. If the question is Yes/No, answer with "Yes" or "No".
7. Output ONLY the final answer text and nothing else.
"""


class GemmaLLMClient:
    """Async Google AI Studio Gemma client with dynamic discovery and fail-open resilience."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GOOGLE_AI_API_KEY
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
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def verify_and_select_model(self) -> str:
        """
        Verify available Gemma model IDs via GET /v1beta/models.
        Filters Gemma IDs, logs the list, and selects primary:
        dense 31B if present, else 26B MoE, else gemma-3-27b-it.
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
                        # Select primary based on spec:
                        # 31B dense if present, else 26B MoE, else gemma-3-27b-it
                        primary = None
                        # Check dense 31B
                        for m in gemma_models:
                            m_lower = m.lower()
                            if "31b" in m_lower and "moe" not in m_lower:
                                primary = m
                                break
                        if not primary:
                            # Check 26B MoE
                            for m in gemma_models:
                                m_lower = m.lower()
                                if "26b" in m_lower:
                                    primary = m
                                    break
                        if not primary:
                            # Check gemma-3-27b-it
                            for m in gemma_models:
                                if "gemma-3-27b-it" in m.lower():
                                    primary = m
                                    break
                        if not primary:
                            # Check any 27b
                            for m in gemma_models:
                                if "27b" in m.lower():
                                    primary = m
                                    break
                        if not primary:
                            primary = gemma_models[0]

                        self._selected_model = primary
                        # Build fallback chain with remaining models
                        self._fallback_chain = [primary] + [m for m in gemma_models if m != primary]
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
        prompt_parts = [
            f"{SYSTEM_INSTRUCTIONS}\n",
            f"{CANDIDATE_FACTS}\n",
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
                    "maxOutputTokens": 256,
                    "topK": 20,
                    "topP": 0.8
                }
            }

            for attempt in range(3):
                start_time = time.time()
                try:
                    async with session.post(endpoint, json=payload, timeout=20) as resp:
                        elapsed = time.time() - start_time
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and len(candidates) > 0:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts and len(parts) > 0:
                                    raw_text = parts[0].get("text", "").strip()
                                    cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                                    cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()
                                    cleaned_text = cleaned_text.strip("\"'` ")

                                    final_answer = self._match_chosen_option(cleaned_text, options) if options else cleaned_text

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
