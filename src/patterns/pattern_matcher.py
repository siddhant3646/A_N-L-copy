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
    'location': ['location', 'city', 'relocate', 'preferred location', 'based in', 'located in', 'commute', 'relocation'],
    'skills': ['proficiency', 'rate', 'scale', 'tech stack', 'libraries', 'database', 'dsa', 'algorithms', 'knowledge', 'framework'],
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
            is_usd = bool(re.search(r'\b(usd|dollars?|\$)\b', ql))
            is_in_lakhs = bool(re.search(r'\b(lakhs?|lacs?|lpa)\b', ql))
            is_current = bool(re.search(r'\b(current|present|cctc)\b', ql))
            if is_usd:
                return ('40000' if is_current else '60000'), max(score, 0.98)
            elif is_in_lakhs:
                return ('23' if is_current else '30'), max(score, 0.98)
            elif ('expectation' in ql or 'expected' in ql or 'requirement' in ql):
                lpa_m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*lpa', al, re.IGNORECASE)
                if lpa_m:
                    return lpa_m.group(1), max(score, 0.98)

        # 5. Textarea Technical Essay & Conceptual Architecture Handling (avoid short digits like 4.2 or 5 in essays)
        is_conceptual_q = bool(re.search(r'\b(explain|architecture|design an?|how does|what steps|stabilize and scale|internal working|trade-offs)\b', ql))
        is_textarea_essay = (input_type == 'textarea' or is_conceptual_q or bool(re.search(r'\b(describe your|tell us about|walk through|hands-on experience working with|experience taking over)\b', ql)))
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
                           not re.search(r'\b(relative|family|experience|years|how many|early release|resign|notice|buy ?out|negotiable|equity|stock|shares|esop|bonus|holding|hold)\b', ql))
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
            r'\b(how many years|how many yrs|years of experience|yrs of experience|relevant years|total years|experience in years|how long have you|number of years|no\.?\s*of\s*years|years of exp)\b',
            ql
        ))

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