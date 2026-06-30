import asyncio
import csv
import json
import random
import os
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple, Any

from src.sentinel.schemas import (
    SentinelState
)
from src.sentinel.prompts import NAUKRI_TASK_CONTEXT
from src.sentinel.question_classifier import (
    QuestionClassifier, QuestionCategory
)
from src.sentinel.question_fingerprint import (
    SuccessTracker, FingerprintMatcher,
    detect_expected_format, validate_answer,
    SYNONYM_MAP, STOP_WORDS
)
from src.patterns.input_aware_resolver import (
    InputAwareResolver, InputType as ResolverInputType, Option
)
from src.sentinel.self_healing import SelfHealingMatcher
from src.patterns.pattern_learner import PatternLearner
from src.patterns.pattern_matcher import create_matcher


# Patterns are now loaded from config/qa_patterns.json (single source of truth)
# The SentinelAgent uses PatternMatcher which reads from the JSON config file.

FUZZY_MATCH_THRESHOLD = 0.65
FUZZY_MATCH_THRESHOLD_FALLBACK = 0.55


class SentinelAgent:
    """
    Sentinel Agent - 100% Scripted Browser Automation.
    Operates on DOM to control a browser without LLM calls.
    """
    
    MAX_STEPS_LINKEDIN = 120  # LinkedIn tasks get more steps
    MAX_STEPS_DEFAULT = 120   # All other tasks (Naukri, etc.)
    MEMORY_CLEANUP_INTERVAL = 50  # Refresh context every N steps
    SCREENSHOT_DIR = os.path.expanduser("~/Desktop/sentinel_errors")
    UNKNOWN_QUESTIONS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/unknown_questions.log")
    ALL_QUESTIONS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/all_questions.log")
    METRICS_LOG = os.path.expanduser("~/Desktop/sentinel_errors/metrics.jsonl")
    # Single consolidated sheet of every question answered or rejected.
    # Columns: timestamp, platform, url, question, answer, input_type, options,
    # selected_option, confidence, status, error_message
    QA_RESULTS_CSV = os.path.join(SCREENSHOT_DIR, "qa_results.csv")
    QA_RESULTS_COLUMNS = [
        "timestamp", "platform", "url", "question", "answer", "input_type",
        "options", "selected_option", "confidence", "status", "error_message",
    ]
    
    def __init__(self, browser=None):
        self.browser = browser
        self._page = None  # Set by runner
        self.state = SentinelState()
        self.linkedin_applications = 0
        self.linkedin_rate_limit_until = None  # Timestamp when LinkedIn can resume
        self.naukri_rate_limit_until = None  # Timestamp when Naukri can resume
        self._linkedin_scroll_attempted = False  # Track if we tried scrolling for null cards
        self._task_context = NAUKRI_TASK_CONTEXT
        self._steps_since_cleanup = 0  # Track steps for memory cleanup
        self._logged_questions = set()  # Track already logged questions to avoid duplicates
        self._all_logged_questions = set()  # Track questions logged to all_questions.log
        self._last_result = ""  # Track last result for loop detection
        self._same_result_count = 0  # Counter for repeated results
        self._instahyre_no_action_count = 0  # Track consecutive NO_ACTION on Instahyre
        self._linkedin_stuck_count = 0  # Track consecutive LINKEDIN_FORM_STUCK in outer loop

        # Metrics tracking
        self.metrics = {
            'task_name': '',
            'start_time': None,
            'end_time': None,
            'applications_submitted': 0,
            'questions_answered': 0,
            'errors_encountered': 0,

            'login_prompts': 0,
            'steps_taken': 0,
            'success': False
        }
        
        # Question classifier for smart defaults
        self._question_classifier: Optional[QuestionClassifier] = None
        self._current_platform: str = "default"
        
        # Pattern matcher for JSON-based patterns (preferred - reads from config/qa_patterns.json)
        self._pattern_matcher = create_matcher()
        
        # Fingerprint matcher and success tracker
        self._fingerprint_matcher = FingerprintMatcher()
        # Build from JSON patterns (single source of truth)
        json_patterns = self._pattern_matcher.patterns.get('patterns', {})
        self._fingerprint_matcher.build_from_patterns(json_patterns)
        self._success_tracker = SuccessTracker()
        
        # NEW: Input-aware resolver and self-healing components
        self._input_resolver = InputAwareResolver()
        self._self_healing = SelfHealingMatcher()
        self._pattern_learner = PatternLearner()
        self._error_detector = None  # Initialized when page is available
        self._error_recovery = None
    
    def _init_error_detection(self):
        """Initialize error detection components when page is available."""
        if self._page:
            from src.sentinel.ui_error_detector import UIErrorDetector, UIErrorRecovery
            self._error_detector = UIErrorDetector(
                page=self._page,
                screenshot_dir=self.SCREENSHOT_DIR
            )
            self._error_recovery = UIErrorRecovery(
                detector=self._error_detector,
                self_healing_matcher=self._self_healing,
                input_resolver=self._input_resolver
            )
    
    def _get_patterns_for_js(self) -> Dict[str, Any]:
        """
        Get all patterns with input_type_defaults for JavaScript injection.
        
        Uses JSON config (config/qa_patterns.json) as single source of truth.
        
        Returns:
            Dictionary with 'answers' (flat key->default) and 
            'with_defaults' (key->object with default and input_type_defaults)
        """
        patterns_dict = {}
        patterns_with_defaults = {}
        
        # Load patterns from JSON config (single source of truth)
        try:
            json_patterns = self._pattern_matcher.patterns.get('patterns', {})
            for pattern_id, pattern_data in json_patterns.items():
                answer = pattern_data.get('default', '')
                if not answer:
                    continue
                
                input_type_defaults = pattern_data.get('input_type_defaults', {})
                
                # Add each pattern string as a key
                for pattern_str in pattern_data.get('patterns', []):
                    patterns_dict[pattern_str.lower()] = answer
                    patterns_with_defaults[pattern_str.lower()] = {
                        'default': answer,
                        'category': pattern_data.get('category', ''),
                        'input_type_defaults': input_type_defaults,
                        'requires_exact_match': pattern_data.get('requires_exact_match', False)
                    }
        except Exception as e:
            print(f"Warning: Could not load JSON patterns for JS: {e}")
        
        return {
            'answers': patterns_dict,
            'with_defaults': patterns_with_defaults
        }
    
    def _format_answer_for_field(self, answer: str, question: str, field_type: str = "text") -> str:
        """
        Format answer appropriately for the field type.
        
        Args:
            answer: The raw answer
            question: The question text
            field_type: Type of form field (text, number, email, etc.)
            
        Returns:
            Formatted answer
        """
        import re
        
        question_lower = question.lower()
        
        # Check if field expects numeric input
        expects_number = (
            field_type == "number" or
            "number" in question_lower or
            "decimal" in question_lower or
            "how many" in question_lower or
            "rate your" in question_lower or
            "proficiency" in question_lower or
            "confidence" in question_lower or
            "years of" in question_lower or
            "experience" in question_lower or
            "exp" in question_lower
        )
        
        if expects_number:
            # Extract numeric value from answer
            # Handle cases like "4 Years" -> "4", "8 out of 10" -> "8"
            match = re.search(r'(\d+\.?\d*)', answer)
            if match:
                numeric = match.group(1)
                # Validate it's a reasonable number
                try:
                    val = float(numeric)
                    if val > 0:
                        return numeric
                except:
                    pass
        
        # Check if field expects yes/no
        if "yes" in answer.lower() or "no" in answer.lower():
            # Check if this is actually a yes/no question
            is_yes_no_question = any(kw in question_lower for kw in [
                "would you", "are you", "do you", "can you", "will you",
                "is this", "have you", "agree", "accept", "confirm"
            ])
            
            if not is_yes_no_question and expects_number:
                # This shouldn't be yes/no, extract number instead
                # Default to 8 for ratings/confidence
                if "proficiency" in question_lower or "confidence" in question_lower or "rate" in question_lower:
                    return "8"
        
        return answer

    def _detect_platform(self) -> str:
        """Detect current platform from URL or context."""
        try:
            if self._page:
                url = self._page.url.lower()
                if 'linkedin.com' in url:
                    return 'linkedin'
                elif 'naukri.com' in url:
                    return 'naukri'
                elif 'instahyre.com' in url:
                    return 'instahyre'
        except:
            pass
        return self._current_platform

    def _detect_negation(self, question: str) -> bool:
        """Detect if question contains negation words."""
        negation_words = ['not', 'no', "n't", 'never', 'without', 'except', 'apart from', 'cannot', "can't", "won't", 'refuse', 'decline']
        question_lower = question.lower()
        return any(word in question_lower for word in negation_words)
    
    def _word_set_similarity(self, q1: str, q2: str) -> float:
        """Calculate Jaccard similarity between word sets."""
        words1 = set(q1.lower().split())
        words2 = set(q2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)
    
    def _position_similarity(self, q1: str, q2: str) -> float:
        """Calculate position-aware similarity combining sequence and word-set matching."""
        seq_sim = SequenceMatcher(None, q1, q2).ratio()
        word_sim = self._word_set_similarity(q1, q2)
        return 0.6 * seq_sim + 0.4 * word_sim
    
    def _same_keyword_category(self, q1: str, q2: str) -> bool:
        """Check if two questions belong to the same keyword category."""
        salary_keywords = ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc']
        experience_keywords = ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']
        notice_keywords = ['notice', 'serving', 'join', 'availability']
        location_keywords = ['location', 'city', 'relocate', 'preferred location']
        
        q1_lower = q1.lower()
        q2_lower = q2.lower()
        
        categories = [salary_keywords, experience_keywords, notice_keywords, location_keywords]
        for category in categories:
            q1_in_cat = any(kw in q1_lower for kw in category)
            q2_in_cat = any(kw in q2_lower for kw in category)
            if q1_in_cat and q2_in_cat:
                return True
        return False

    def _fuzzy_match_question(self, question: str) -> Tuple[Optional[str], float]:
        """Find closest known question pattern using improved keyword + fuzzy matching."""
        # Update platform detection before processing
        self._current_platform = self._detect_platform()
        
        question_lower = question.lower().strip()
        question_negated = self._detect_negation(question_lower)
        best_match = None
        best_score = 0.0
        
        # ==========================================
        # PHASE 0: Skip Patterns (highest priority)
        # ==========================================
        skip_patterns = ['skip this question', 'try again', 'restart conversation', 'no worries', 'change your input']
        if any(skip in question_lower for skip in skip_patterns):
            return '', 1.0  # Return empty string to trigger skip
        
        # ==========================================
        # PHASE 0.5: Fingerprint Matching
        # Normalize questions to match variations
        # ==========================================
        if self._fingerprint_matcher:
            fp_match = self._fingerprint_matcher.match(question)
            if fp_match:
                answer, confidence = fp_match
                # Validate answer format
                format_type = detect_expected_format(question)
                if format_type:
                    is_valid, error_msg = validate_answer(answer, format_type)
                    if not is_valid:
                        print(f"   ⚠️ Fingerprint match failed validation: {error_msg}")
                    else:
                        print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
                        return answer, confidence
                else:
                    print(f"   🔍 Fingerprint match (conf: {confidence:.2f}): {answer[:50]}...")
                    return answer, confidence
        
        # ==========================================
        # PHASE 0.6: Learned Pattern Matching
        # Check self-healing and pattern learner
        # ==========================================
        learned = self._get_learned_answer(question)
        if learned and learned[1] >= 0.5:
            print(f"   📚 Learned pattern match (conf: {learned[1]:.2f}): {learned[0][:50]}...")
            return learned
        
        # ==========================================
        # PHASE 1: Keyword-based Priority Matching
        # Prevents CTC questions matching experience patterns
        # ==========================================
        
        # Define keyword categories for priority matching
        salary_keywords = ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc']
        experience_keywords = ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']
        notice_keywords = ['notice', 'serving', 'join', 'availability']
        location_keywords = ['location', 'city', 'relocate', 'preferred location']
        
        # LWD (Last Working Day) detection - BEFORE experience keywords
        lwd_keywords = ['last working day', 'lwd', 'exact lwd', 'exact last working']
        is_lwd_question = any(kw in question_lower for kw in lwd_keywords)

        # Immediate joiners only - LinkedIn specific pattern
        immediate_joiners_keywords = ['looking for immediate joiners only', 'immediate joiners only']
        is_immediate_joiners_only = any(kw in question_lower for kw in immediate_joiners_keywords)
        
        # NP abbreviation detection (Notice Period) - special handling
        np_keywords = ['your np', 'what is your np', 'mention np', 'np?']
        is_np_abbreviation = any(kw in question_lower for kw in np_keywords)
        
        # Rating/Proficiency questions (1-10 scale) - CHECK BEFORE EXPERIENCE
        rating_keywords = ['rate proficiency', 'rate yourself', 'rate your', 'on a scale', '1-10', '1 to 10', 'proficiency in']
        is_rating_question = any(kw in question_lower for kw in rating_keywords)
        
        # Preferred position questions
        position_keywords = ['preferred position', 'frontend/backend', 'frontend or backend', 'preferred role', 'which role']
        is_position_question = any(kw in question_lower for kw in position_keywords)
        
        # Database/Knowledge questions
        db_knowledge_keywords = ['knowledge in db', 'strong knowledge', 'database knowledge', 'db knowledge']
        is_db_question = any(kw in question_lower for kw in db_knowledge_keywords)
        
        # DSA questions
        dsa_keywords = ['dsa', 'data structures', 'algorithms', 'how good are you']
        is_dsa_question = any(kw in question_lower for kw in dsa_keywords)
        
        # Tech stacks / Python libraries questions - MUST CHECK BEFORE EXPERIENCE
        tech_stack_keywords = ['tech stack', 'tech-stack', 'technologies worked', 'worked upon', 'major tech']
        python_lib_keywords = ['python libraries', 'python library', 'python libs', 'python packages', 'which python']
        is_tech_question = any(kw in question_lower for kw in tech_stack_keywords)
        is_python_lib_question = any(kw in question_lower for kw in python_lib_keywords)
        
        # Database NAME questions (not experience) - CHECK BEFORE EXPERIENCE
        db_name_keywords = ['which database', 'what database', 'database do you have', 'database have you', 'database experience working', 'database worked', 'databases do you', 'databases have you']
        is_db_name_question = any(kw in question_lower for kw in db_name_keywords)
        
        # Location specific questions - "based in X", "located in X", "from X", "stay in X"
        location_specific_keywords = ['based in', 'located in', 'from mumbai', 'from bangalore', 'from pune', 'from hyderabad', 'from chennai', 'from delhi', 'stay currently', 'where do you stay', 'which city do you', 'candidates from', 'need candidates from', 'andheri']  # Added Mumbai-specific patterns
        is_location_specific = any(kw in question_lower for kw in location_specific_keywords)
        
        # Referral questions - "referred by", "encouraged to apply"
        referral_keywords = ['referred', 'referral', 'encouraged to apply', 'employee referral', 'referred by']
        is_referral_question = any(kw in question_lower for kw in referral_keywords)
        
        # Job change reason questions
        job_change_keywords = ['reason for job change', 'reasons for job change', 'reasons for your job change', 'why are you changing', 'why job change', 'reason for leaving', 'reason for change']
        is_job_change_question = any(kw in question_lower for kw in job_change_keywords)
        
        # Total experience question (short form like "total Exp")
        total_exp_keywords = ['total exp', 'what is your total exp']
        is_total_exp_question = any(kw in question_lower for kw in total_exp_keywords) and 'ctc' not in question_lower
        
        # Project count questions
        project_count_keywords = ['how many projects', 'number of projects', 'projects you have worked', 'projects as fullstack']
        is_project_count = any(kw in question_lower for kw in project_count_keywords)
        
        # Yes/No Proficiency questions (NOT rating scale)
        yes_no_proficiency_keywords = ['strong proficiency', 'good grasp', 'do you have proficiency', 'etl concepts', 'good understanding of']
        is_yes_no_proficiency = any(kw in question_lower for kw in yes_no_proficiency_keywords)
        
        # E-commerce domain experience
        ecommerce_keywords = ['e-commerce', 'ecommerce', 'e commerce']
        is_ecommerce_question = any(kw in question_lower for kw in ecommerce_keywords) and ('experience' in question_lower or 'worked' in question_lower)
        
        # Composite HR question (CTC + ECTC + NP in one)
        is_composite_hr = ('ctc' in question_lower and ('np' in question_lower or 'notice' in question_lower or 'ectc' in question_lower))
        
        # Country/State questions
        country_keywords = ['country you currently', 'which country', 'country currently', 'state you', 'which state']
        is_country_question = any(kw in question_lower for kw in country_keywords)
        
        # ==========================================
        # COMPLIANCE & EMPLOYMENT HISTORY DETECTION
        # These questions MUST return "No" for compliance safety
        # ==========================================
        
        # List of technical/tool/programming keywords to prevent false positives in company matching
        TECH_KEYWORDS = {
            'aws', 'python', 'java', 'react', 'angular', 'vue', 'node', 'typescript', 'javascript', 
            'docker', 'kubernetes', 'gcp', 'azure', 'git', 'jenkins', 'sql', 'nosql', 'kafka', 
            'redis', 'spark', 'hadoop', 'c#', 'c++', 'go', 'rust', 'ruby', 'php', 'html', 'css', 
            'devops', 'agile', 'scrum', 'jira', 'sap', 'salesforce', 'lambda', 'ecs', 's3', 'sqs'
        }
        
        # Pattern 1: "Have you worked with/at/for [Company]" - Most common Workday pattern
        worked_with_company_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at|in)\s+(?:the\s+)?(?:past\s+)?(?:\d+\s+years?\s+)?at\s+(\w+)"
        worked_with_match = re.search(worked_with_company_pattern, question_lower)
        if worked_with_match:
            company = worked_with_match.group(1).lower()
            if company not in TECH_KEYWORDS:
                # Only answer "Yes" for current/past employer, "No" for all others
                if company == 'everbridge' or company == 'fiserv':
                    return 'Yes', 0.98
                return 'No', 0.98
        
        # Pattern 2: "Have you worked with [Company] in the past X years"
        past_years_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at)\s+(\w+)\s+(?:in\s+the\s+)?(?:past|last)\s+(\d+)"
        past_years_match = re.search(past_years_pattern, question_lower)
        if past_years_match:
            company = past_years_match.group(1).lower()
            if company not in TECH_KEYWORDS:
                if company == 'everbridge' or company == 'fiserv':
                    return 'Yes', 0.98
                return 'No', 0.98
        
        # Pattern 3: "Have you worked with Visa" or similar specific company questions
        specific_company_pattern = r"have\s+you\s+(?:worked|been\s+employed)\s+(?:with|for|at)\s+(\w+)(?:\s+in\s+the\s+)?"
        specific_company_match = re.search(specific_company_pattern, question_lower)
        if specific_company_match:
            company = specific_company_match.group(1).lower()
            if company not in TECH_KEYWORDS:
                if company == 'everbridge' or company == 'fiserv':
                    return 'Yes', 0.98
                # For Visa and other companies, return "No"
                return 'No', 0.98
        
        # Pattern 4: "Currently employed by any of the" - blanket No
        currently_employed_pattern = r"currently\s+(?:employed|an\s+employee)\s+(?:by|at|of)\s+(?:any|any\s+of\s+the)"
        if re.search(currently_employed_pattern, question_lower):
            return 'No', 0.98
        
        # Pattern 5: "Ever been employed by" or "Previously employed by"
        ever_employed_pattern = r"(?:ever\s+been\s+employed|previously\s+employed)\s+(?:by|at|with)"
        if re.search(ever_employed_pattern, question_lower):
            # Check if it's asking about Everbridge or Fiserv specifically
            if 'everbridge' in question_lower or 'fiserv' in question_lower:
                return 'Yes', 0.98
            return 'No', 0.98
        
        # Pattern 6: "Conflict of interest" or "Family member" questions
        conflict_keywords = ['conflict of interest', 'close relative', 'family member', 
                            'relative working', 'family in company', 'relatives in company']
        is_conflict_question = any(kw in question_lower for kw in conflict_keywords)
        if is_conflict_question:
            return 'No', 0.98
        
        # Pattern 7: "Worked with" + any company name not in whitelist
        # This catches variations like "worked with Navan", "worked for Reed", etc.
        generic_worked_pattern = r"worked\s+(?:with|for|at)\s+(visa|navan|reed|nielsen|mastercard|amex|american\s+express|paypal|stripe)"
        if re.search(generic_worked_pattern, question_lower):
            return 'No', 0.98
        
        # Pattern 8: Company list questions like "Have you worked with any of the following"
        company_list_pattern = r"(?:have\s+you|do\s+you)\s+(?:worked|been)\s+(?:with|for|at|employed)\s+(?:with|for|at)?\s+(?:any\s+of\s+the|any\s+of\s+these|any\s+of\s+the\s+following)"
        if re.search(company_list_pattern, question_lower):
            return 'No', 0.98
        
        # Notice period for current company in days - HIGH PRIORITY to avoid matching company name
        if 'notice period' in question_lower and 'company' in question_lower and ('days' in question_lower or 'in days' in question_lower):
            return '15', 0.99
        
        # Handle high-priority question types FIRST
        
        # Composite HR question (must check BEFORE individual NP/salary)
        if is_composite_hr:
            return 'Current CTC: 23 LPA, Expected CTC: 30 LPA, Notice Period: 15 Days (Negotiable)', 0.98
        
        # NP abbreviation (Notice Period) - after composite check
        if is_np_abbreviation:
            return '15', 0.98
        
        # LWD (Last Working Day) questions - calculate date 15 days from now
        if is_lwd_question:
            return '15', 0.98
        
        # Desired / preferred / expected start date questions - return DD/MM/YYYY (today + 15 days)
        start_date_keywords = ['desired start date', 'preferred start date', 'expected start date',
                               'when would you like to start', 'when can you start working',
                               'proposed start date']
        is_start_date_question = any(kw in question_lower for kw in start_date_keywords)
        # "start date" alone (without other noise) also qualifies
        if not is_start_date_question and 'start date' in question_lower:
            is_start_date_question = True
        if is_start_date_question:
            start_date = datetime.now() + timedelta(days=15)
            return start_date.strftime('%d/%m/%Y'), 0.99
        
        # Project count questions
        if is_project_count:
            return '5', 0.98
        
        # Yes/No Proficiency (must be BEFORE rating questions)
        if is_yes_no_proficiency:
            return 'Yes', 0.98
        
        # E-commerce experience (must be BEFORE generic experience)
        if is_ecommerce_question:
            return 'Yes, I have experience building scalable e-commerce platforms with payment gateway integration (Stripe, Razorpay), inventory management, order processing, and real-time tracking systems.', 0.98
        
        if is_rating_question:
            return '8', 0.95
        
        if is_position_question:
            return 'Backend', 0.95
        
        if is_db_question:
            return 'Yes', 0.95
        
        if is_dsa_question:
            return '8', 0.95
        
        # Handle tech stack and python library questions - BEFORE experience check
        if is_python_lib_question:
            return 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI', 0.95
        
        if is_tech_question:
            return 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis', 0.95
        
        # Handle database NAME questions - BEFORE experience check
        if is_db_name_question:
            return 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB', 0.95
        
        # Handle location-specific questions
        if is_location_specific:
            # Check for Mumbai-only/exclusivity requirements
            if ('mumbai' in question_lower or 'andheri' in question_lower) and ('need candidates from' in question_lower or 'candidates from mumbai' in question_lower or 'from mumbai itself' in question_lower):
                return 'No, I am currently based in Noida, not in Mumbai. I am open to immediate relocation to Mumbai if required.', 0.95
            # Check for specific city mentions
            if 'bangalore' in question_lower or 'bengaluru' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Bangalore.', 0.95
            if 'mumbai' in question_lower or 'andheri' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Mumbai.', 0.95
            if 'pune' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Pune.', 0.95
            if 'hyderabad' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Hyderabad.', 0.95
            if 'chennai' in question_lower:
                return 'No, I am currently based in Noida. However, I am willing to relocate to Chennai.', 0.95
            if 'delhi' in question_lower or 'ncr' in question_lower or 'noida' in question_lower or 'gurgaon' in question_lower or 'gurugram' in question_lower:
                return 'Yes, I am currently based in Noida, Delhi NCR.', 0.95
            return 'Noida, Delhi NCR', 0.95
        
        # Handle referral questions
        if is_referral_question:
            return 'No', 0.95
        
        # Handle job change reason questions
        if is_job_change_question:
            return 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals', 0.95
        
        # Handle total experience (short form) questions
        if is_total_exp_question:
            return '4 Years', 0.95
        
        # Handle country/state questions
        if is_country_question:
            return 'India', 0.95
        
        # Check which category the question falls into
        is_salary_question = any(kw in question_lower for kw in salary_keywords)
        is_experience_question = any(kw in question_lower for kw in experience_keywords) and not is_salary_question and not is_rating_question and not is_tech_question and not is_python_lib_question
        is_notice_question = any(kw in question_lower for kw in notice_keywords)
        is_location_question = any(kw in question_lower for kw in location_keywords)
        
        # Priority patterns based on detected category
        if is_salary_question:
            # Check for abbreviations CCTC (Current) and ECTC (Expected)
            if 'cctc' in question_lower:
                return '23', 0.98
            if 'ectc' in question_lower:
                return '30', 0.98
            
            # Check for expected vs current - use plain numbers
            if 'expected' in question_lower or 'expect' in question_lower:
                return '30', 0.95
            elif 'current' in question_lower or 'present' in question_lower:
                return '23', 0.95
            # Default to current CTC if unclear (which is standard for generic "CTC" questions)
            return '23', 0.90
        
        # Specific Experience Questions (Priority over generic check)
        if 'area' in question_lower and 'experience' in question_lower:
            return 'Full-stack', 0.98
            
        if 'chosen engineering field' in question_lower:
            return '4', 0.98

        if is_experience_question:
            if 'month' in question_lower:
                # Use PatternMatcher instead of KNOWN_QA_PATTERNS
                answer, confidence = self._pattern_matcher.fuzzy_match("months of experience")
                return answer or '48', max(confidence, 0.95)
            # LinkedIn requires whole numbers - return '4' for those cases
            if 'whole number' in question_lower or 'enter a number' in question_lower:
                return '4', 0.98
            # Platform-specific experience format
            if self._current_platform == 'linkedin':
                return '4', 0.95
            else:
                # Use PatternMatcher instead of KNOWN_QA_PATTERNS
                answer, confidence = self._pattern_matcher.fuzzy_match("years of experience")
                return answer or '4 Years', max(confidence, 0.95)
        
        if is_notice_question or is_immediate_joiners_only:
            if self._current_platform == 'linkedin':
                # Check if it is a yes/no question about serving notice
                is_yes_no = 'serving' in question_lower and not any(kw in question_lower for kw in ['days', 'how many', 'duration', 'lwd', 'last working'])
                if is_yes_no:
                    answer, confidence = self._pattern_matcher.fuzzy_match("serving notice")
                    return answer or 'Yes', max(confidence, 0.95)
                return '15', 0.98
            
            if 'last working day' in question_lower or 'lwd' in question_lower:
                lwd_date = datetime.now() + timedelta(days=15)
                lwd_formatted = lwd_date.strftime('%d %B %Y')
                return f'Serving 15 days notice, LWD: {lwd_formatted}', 0.95
            elif 'serving' in question_lower:
                answer, confidence = self._pattern_matcher.fuzzy_match("serving notice")
                return answer or 'Yes', max(confidence, 0.95)
            elif 'in days' in question_lower:
                return '15', 0.98
            else:
                if self._current_platform == 'naukri':
                    lwd_date = datetime.now() + timedelta(days=15)
                    lwd_formatted = lwd_date.strftime('%d %B %Y')
                    return f'15 days (LWD: {lwd_formatted})', 0.95
                else:
                    return '15 days', 0.95
        
        if is_location_question:
            if 'preferred' in question_lower:
                # Use PatternMatcher instead of KNOWN_QA_PATTERNS
                answer, confidence = self._pattern_matcher.fuzzy_match("preferred location")
                return answer or 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune', max(confidence, 0.95)
            # Use PatternMatcher instead of KNOWN_QA_PATTERNS
            answer, confidence = self._pattern_matcher.fuzzy_match("current location")
            return answer or 'Noida', max(confidence, 0.95)
        
        # ==========================================
        # PHASE 2: Fuzzy Matching for Other Questions
        # Enhanced with negation detection, word-set similarity, and position-aware scoring
        # Now uses PatternMatcher which reads from config/qa_patterns.json
        # ==========================================
        
        # First try the PatternMatcher (JSON-based patterns)
        json_answer, json_confidence = self._pattern_matcher.fuzzy_match(question)
        if json_answer and json_confidence >= FUZZY_MATCH_THRESHOLD:
            # Validate and potentially fix the answer
            validated_answer, final_confidence = self._validate_and_retry(
                question, json_answer, []
            )
            return validated_answer, final_confidence
        
        # ==========================================
        # PHASE 3: Smart Category Fallback
        # Use question classifier for intelligent defaults
        # ==========================================
        if self._question_classifier is None:
            self._question_classifier = QuestionClassifier(self._current_platform)
        
        category, cat_confidence = self._question_classifier.classify(question)
        
        # Use lower threshold for category fallback
        if category != QuestionCategory.UNKNOWN and cat_confidence >= 0.4:
            # Get platform-specific answer
            answer, ans_confidence = self._question_classifier.get_answer(question, category)
            if answer:
                combined_confidence = max(best_score, cat_confidence * 0.8)  # Slightly lower confidence for fallback
                print(f"   🤖 Smart fallback [{category.value}]: {answer[:50]}...")
                return answer, combined_confidence
        
        return None, best_score

    def _validate_and_retry(self, question: str, answer: str, 
                           validation_errors: List[str] = None) -> Tuple[str, float]:
        """
        Validate an answer and attempt to fix it if validation fails.
        
        Args:
            question: The original question
            answer: The proposed answer
            validation_errors: List of validation error messages
            
        Returns:
            Tuple of (fixed_answer, confidence_score)
        """
        if validation_errors is None:
            validation_errors = []
        
        try:
            # Detect expected format from question
            format_type = detect_expected_format(question)
            if not format_type:
                return answer, 0.95  # No validation needed
            
            # Validate the answer
            is_valid, error_msg = validate_answer(answer, format_type)
            if is_valid:
                return answer, 0.95
            
            # Attempt to fix the answer based on format type
            fixed_answer = answer
            confidence = 0.85  # Lower confidence for fixed answers
            
            if format_type == 'numeric':
                # Extract numbers from answer
                import re
                numbers = re.findall(r'\d+\.?\d*', answer.replace(',', ''))
                if numbers:
                    fixed_answer = numbers[0]
                    print(f"   🔧 Fixed numeric answer: {answer} -> {fixed_answer}")
            
            elif format_type == 'salary_lpa':
                # Extract numeric part only (no LPA suffix for LinkedIn)
                import re
                match = re.search(r'(\d+\.?\d*)', answer)
                if match:
                    fixed_answer = match.group(1)
                    print(f"   🔧 Fixed salary answer: {answer} -> {fixed_answer}")
            
            elif format_type == 'salary_inr':
                # Convert to INR format (remove decimals, ensure numeric)
                import re
                numbers = re.findall(r'\d+', answer.replace(',', ''))
                if numbers:
                    fixed_answer = ''.join(numbers)
                    print(f"   🔧 Fixed INR salary: {answer} -> {fixed_answer}")
            
            elif format_type == 'experience_years':
                # Extract years, add "Years" suffix if missing
                import re
                match = re.search(r'(\d+\.?\d*)', answer)
                if match:
                    years = float(match.group(1))
                    if 'month' in question.lower():
                        fixed_answer = str(int(years * 12))
                    else:
                        fixed_answer = f"{years} Years"
                    print(f"   🔧 Fixed experience: {answer} -> {fixed_answer}")
            
            elif format_type == 'date':
                # Try to parse and format date
                from datetime import datetime
                try:
                    # Try various date formats
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d %B %Y']:
                        try:
                            dt = datetime.strptime(answer, fmt)
                            fixed_answer = dt.strftime('%d/%m/%Y')
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            elif format_type == 'yes_no':
                # Normalize yes/no answers
                answer_lower = answer.lower().strip()
                if any(word in answer_lower for word in ['yes', 'yeah', 'yep', 'sure', 'ok', 'agree']):
                    fixed_answer = 'Yes'
                elif any(word in answer_lower for word in ['no', 'nope', 'nah', 'not']):
                    fixed_answer = 'No'
                print(f"   🔧 Fixed yes/no: {answer} -> {fixed_answer}")
            
            # Re-validate the fixed answer
            is_valid, error_msg = validate_answer(fixed_answer, format_type)
            if is_valid:
                return fixed_answer, confidence
            else:
                # Return original with lower confidence if we can't fix it
                return answer, 0.6
                
        except Exception as e:
            print(f"   ⚠️ Error in validation retry: {e}")
            return answer, 0.6

    def _match_answer_to_options(
        self,
        answer: str,
        options: List[str],
        question: str = "",
        input_type: ResolverInputType = ResolverInputType.SELECT
    ) -> Tuple[str, float]:
        """
        Match an answer to available options using the input-aware resolver.
        
        Args:
            answer: The intended answer value
            options: List of available options for select/radio/checkbox
            question: Question text for context
            input_type: Type of input (SELECT, RADIO, CHECKBOX)
            
        Returns:
            Tuple of (matched_option, confidence)
        """
        if not options:
            return answer, 0.5
        
        opt_objects = [Option(value=o, label=o, index=i) for i, o in enumerate(options)]
        
        result = self._input_resolver.resolve(
            answer=answer,
            input_type=input_type,
            options=opt_objects,
            question=question
        )
        
        if result.matched_option:
            return result.matched_option.label, result.confidence
        
        return answer, 0.3
    
    def _get_learned_answer(self, question: str) -> Optional[Tuple[str, float]]:
        """
        Get a learned answer for a question.
        
        Checks both self-healing patterns and pattern learner.
        
        Returns:
            Tuple of (answer, confidence) or None
        """
        # Check self-healing learned patterns first
        healed = self._self_healing.get_learned_answer(question)
        if healed and healed[1] >= 0.5:
            return healed
        
        # Check pattern learner
        learned = self._pattern_learner.find_answer(question)
        if learned and learned[1] >= 0.5:
            return learned
        
        return None
    
    async def _attempt_form_recovery(self) -> bool:
        """
        Attempt to recover from form errors using self-healing.
        Called AFTER existing JS error detection has found issues.
        
        Returns:
            True if recovery was successful
        """
        if not self._error_detector:
            self._init_error_detection()
        
        if not self._error_detector:
            return False
        
        # Detect current errors using Python layer
        errors = await self._error_detector.detect_errors()
        
        if not errors:
            return False
        
        for error in errors:
            healed_value = None

            # Record the failing answer in the consolidated QA results CSV sheet
            self._log_qa_result(
                question=error.field_label or "",
                answer=error.field_value or "",
                input_type="select" if error.available_options else "text",
                options=error.available_options,
                selected_option=error.field_value or "",
                confidence="",
                status="validation_error",
                error_message=error.message or "",
                url=self._page.url if self._page else "",
                platform=error.platform.value if error.platform else "",
            )

            # Try learned patterns for this field
            if error.field_label:
                learned = self._get_learned_answer(error.field_label)
                if learned and learned[1] >= 0.5:
                    print(f"   🔧 Using learned answer for '{error.field_label[:30]}...': {learned[0]}")
                    # Record success pattern
                    pattern = self._self_healing.learning_store.find_pattern_for_question(error.field_label)
                    if pattern:
                        self._self_healing.learning_store.record_success(pattern.pattern_id)
                    healed_value = learned[0]
            
            # Try option matching if options available
            if not healed_value and error.available_options and error.field_value:
                matched, confidence = self._match_answer_to_options(
                    error.field_value,
                    error.available_options,
                    error.field_label or ""
                )
                if confidence >= 0.7:
                    print(f"   🔧 Option matched: '{matched}' (conf: {confidence:.0%})")
                    healed_value = matched

            if healed_value:
                # Inject the healed value back into the DOM using the label text to find the input
                try:
                    js_inject = f"""() => {{
                        const labels = Array.from(document.querySelectorAll('label'));
                        const targetLabel = labels.find(l => l.innerText.trim().includes(`{error.field_label}`));
                        if (!targetLabel) return false;
                        
                        const container = targetLabel.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question') || targetLabel.parentElement;
                        
                        // Handle Select Dropdowns
                        const select = container.querySelector('select');
                        if (select) {{
                            const options = Array.from(select.options);
                            const targetOpt = options.find(o => o.text.trim() === `{healed_value}`);
                            if (targetOpt) {{
                                select.value = targetOpt.value;
                                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        
                        // Handle Text/Number Inputs
                        const input = container.querySelector('input:not([type="radio"]):not([type="checkbox"]), textarea');
                        if (input) {{
                            const prevVal = input.value;
                            const fill = (val) => {{
                                try {{
                                    const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                                    if (nativeSetter) nativeSetter.call(input, val);
                                    else input.value = val;
                                }} catch(e) {{ input.value = val; }}
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                            }};
                            
                            // Clear first, then set healed value
                            fill('');
                            fill(`{healed_value}`);
                            
                            // Fallback
                            if (input.value !== `{healed_value}` && Reflect.has(input, 'value')) {{
                                Reflect.set(input, 'value', `{healed_value}`);
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                            
                            return true;
                        }}
                        
                        // Handle Radio buttons (like Yes/No)
                        const radios = container.querySelectorAll('input[type="radio"]');
                        if (radios.length > 0) {{
                            for (const r of radios) {{
                                const rLabel = container.querySelector(`label[for="${{r.id}}"]`)?.innerText || r.value;
                                if (rLabel.toLowerCase().includes(`{healed_value}`.toLowerCase())) {{
                                    r.click();
                                    r.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                        }}
                        
                        return false;
                    }}"""
                    success = await self._page.evaluate(js_inject)
                    if success:
                        print(f"   ✅ Successfully injected healed value '{healed_value}'")
                        return True
                    else:
                        print(f"   ⚠️ Failed to inject healed value '{healed_value}' into DOM")
                except Exception:
                    print("   ⚠️ Error during DOM injection: {e}")
                    
        return False

    def _log_unknown_question(self, question: str, context: str = "", 
                               input_type: str = "", options: List[str] = None, 
                               selected_option: str = ""):
        """Log unrecognized questions to file for later review."""
        try:
            # Avoid duplicate logging
            q_hash = hash(question.lower().strip()[:100])
            if q_hash in self._logged_questions:
                return
            self._logged_questions.add(q_hash)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] [{context}]\n"
            log_entry += f"  Q: {question}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  Options: {', '.join(options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            with open(self.UNKNOWN_QUESTIONS_LOG, 'a', encoding='utf-8') as f:
                f.write(log_entry)

            # Also record unknown questions in the consolidated QA results CSV sheet
            self._log_qa_result(
                question=question,
                answer="",
                input_type=input_type,
                options=options,
                selected_option=selected_option,
                confidence="",
                status="unknown",
                platform=context,
            )

            print("   📝 Logged unknown question to file")
        except Exception as e:
            print(f"   ⚠️ Failed to log question: {e}")

    def _log_all_questions(self, question: str, answer: str, context: str = "", 
                           match_confidence: str = "", input_type: str = "",
                           options: List[str] = None, selected_option: str = ""):
        """Log ALL questions encountered during Naukri and LinkedIn tasks for analysis."""
        try:
            # Avoid duplicate logging (same question in same session)
            q_hash = hash((question.lower().strip()[:100], context))
            if q_hash in self._all_logged_questions:
                return
            self._all_logged_questions.add(q_hash)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            confidence_str = f" [{match_confidence}]" if match_confidence else ""
            log_entry = f"[{timestamp}] [{context}]{confidence_str}\n"
            log_entry += f"  Q: {question}\n"
            log_entry += f"  A: {answer}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  Options: {', '.join(options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            with open(self.ALL_QUESTIONS_LOG, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # Track in metrics
            self.metrics['questions_answered'] += 1
        except Exception as e:
            print(f"   ⚠️ Failed to log question: {e}")

    def _log_qa_result(self, question: str, answer: str, input_type: str = "",
                       options: List[str] = None, selected_option: str = "",
                       confidence="", status: str = "submitted",
                       error_message: str = "", url: str = "",
                       platform: str = ""):
        """
        Write a single row to the consolidated QA results CSV sheet.

        This is the ONE place that records every question, the answer given,
        the answer type, available options, and whether the form accepted it
        (status). Use status='submitted' for answered questions and
        status='validation_error' for answers rejected by the form.

        Args:
            question: Question text
            answer: Answer that was provided (or attempted)
            input_type: Type of input (text, radio, checkbox, select, number)
            options: Available options for select/radio/checkbox
            selected_option: The option that was selected
            confidence: Match confidence score (str or float)
            status: One of 'submitted', 'validation_error', 'unknown', 'recovered'
            error_message: Validation error message if status is validation_error
            url: Page URL
            platform: Platform context (linkedin, naukri, instahyre)
        """
        try:
            os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)
            row = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "platform": platform or self._current_platform or "",
                "url": url or (self._page.url if self._page else ""),
                "question": question or "",
                "answer": answer or "",
                "input_type": input_type or "",
                "options": ", ".join(str(o) for o in options) if options else "",
                "selected_option": selected_option or "",
                "confidence": str(confidence) if confidence != "" else "",
                "status": status,
                "error_message": error_message or "",
            }
            write_header = not os.path.exists(self.QA_RESULTS_CSV)
            with open(self.QA_RESULTS_CSV, "a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=self.QA_RESULTS_COLUMNS, extrasaction="ignore"
                )
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as e:
            print(f"   ⚠️ Failed to log QA result to CSV: {e}")

    def _log_question_detailed(self, question_data: Dict[str, Any]):
        """
        Log a question with complete details including options and selection.
        Called from JavaScript form handlers to capture full context.
        
        Args:
            question_data: Dict containing:
                - question: Question text
                - answer: Answer provided
                - input_type: Type of input (text, radio, checkbox, select)
                - options: List of available options
                - selected_option: The option that was selected
                - context: Platform/context (linkedin, naukri, etc.)
                - url: Page URL
                - confidence: Match confidence score
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            question = question_data.get('question', '')
            answer = question_data.get('answer', '')
            input_type = question_data.get('input_type', '')
            options = question_data.get('options', [])
            selected_option = question_data.get('selected_option', '')
            context = question_data.get('context', 'unknown')
            url = question_data.get('url', '')
            confidence = question_data.get('confidence', '')
            
            # Create structured log entry
            log_entry = f"[{timestamp}] [{context}]\n"
            log_entry += f"  URL: {url}\n"
            log_entry += f"  Q: {question}\n"
            log_entry += f"  A: {answer}\n"
            if confidence:
                log_entry += f"  Confidence: {confidence}\n"
            if input_type:
                log_entry += f"  Input Type: {input_type}\n"
            if options:
                log_entry += f"  All Options: {', '.join(str(o) for o in options)}\n"
            if selected_option:
                log_entry += f"  Selected: {selected_option}\n"
            log_entry += "  ---\n"
            
            # Also create a JSON version for structured parsing
            json_entry = {
                'timestamp': timestamp,
                'context': context,
                'url': url,
                'question': question,
                'answer': answer,
                'confidence': confidence,
                'input_type': input_type,
                'options': options,
                'selected_option': selected_option
            }
            
            # Write to detailed log
            detailed_log = os.path.join(self.SCREENSHOT_DIR, 'all_questions_detailed.log')
            with open(detailed_log, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # Write to JSON log for programmatic access
            json_log = os.path.join(self.SCREENSHOT_DIR, 'all_questions.jsonl')
            with open(json_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(json_entry) + '\n')

            # Write to the consolidated QA results CSV sheet (success row)
            self._log_qa_result(
                question=question,
                answer=answer,
                input_type=input_type,
                options=options,
                selected_option=selected_option,
                confidence=confidence,
                status="submitted",
                url=url,
                platform=context,
            )

            print(f"   📝 Logged detailed question: {question[:50]}...")
        except Exception as e:
            print(f"   ⚠️ Failed to log detailed question: {e}")

    def track_question_attempt(self, question: str, answer: str, success: bool, confidence: float = 0.0):
        """
        Track the success/failure of a question answering attempt.
        
        Args:
            question: The question that was asked
            answer: The answer that was provided
            success: Whether the answer was accepted
            confidence: Match confidence score
        """
        try:
            if self._success_tracker:
                self._success_tracker.record_attempt(question, answer, success, confidence)
                
                # Log low success patterns for review
                stats = self._success_tracker.get_stats(question, answer)
                if stats and stats.attempts >= 3 and stats.success_rate < 0.7:
                    print(f"   ⚠️ Low success pattern: {question[:50]}... (rate: {stats.success_rate:.1%})")
        except Exception as e:
            print(f"   ⚠️ Failed to track attempt: {e}")

    def get_pattern_stats(self) -> Dict:
        """Get statistics about pattern success rates."""
        if self._success_tracker:
            return self._success_tracker.get_stats_summary()
        return {}

    def _save_metrics(self):
        """Save task metrics to JSONL file for analysis."""
        try:
            os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)
            self.metrics['end_time'] = datetime.now().isoformat()
            self.metrics['steps_taken'] = self.state.step_count
            
            with open(self.METRICS_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(self.metrics) + '\n')
            
            print(f"📊 Metrics saved: {self.metrics['applications_submitted']} apps, {self.metrics['questions_answered']} Q&A, {self.metrics['errors_encountered']} errors")
        except Exception as e:
            print(f"   ⚠️ Failed to save metrics: {e}")

    async def _check_page_health(self) -> bool:
        """Verify page is responsive before actions."""
        try:
            # Quick JS evaluation to check if page responds
            result = await asyncio.wait_for(
                self._page.evaluate("() => document.readyState"),
                timeout=5.0
            )
            if result != 'complete':
                print(f"   ⚠️ Page not ready: {result}")
                await asyncio.sleep(2)
                return False
            return True
        except asyncio.TimeoutError:
            print("   ⚠️ Page health check timeout - page may be unresponsive")
            return False
        except Exception as e:
            print(f"   ⚠️ Page health check failed: {e}")
            return False

    async def _maybe_cleanup_memory(self):
        """Periodic memory cleanup by refreshing page if needed."""
        self._steps_since_cleanup += 1
        
        if self._steps_since_cleanup >= self.MEMORY_CLEANUP_INTERVAL:
            print("   🧹 Memory cleanup: Refreshing page state...")
            try:
                # Clear JS memory by running garbage collection hint
                await self._page.evaluate("""() => {
                    // Clear any stored data
                    if (window.gc) window.gc();
                    // Clear console
                    console.clear();
                    return 'CLEANUP_DONE';
                }""")
                self._steps_since_cleanup = 0
                print("   ✅ Memory cleanup complete")
            except Exception as e:
                print(f"   ⚠️ Memory cleanup failed: {e}")



    async def _check_login_state(self) -> bool:
        """Detect if session expired and need re-login. Returns True if logged in."""
        try:
            current_url = self._page.url.lower()
            
            # LinkedIn login detection
            if 'linkedin' in current_url:
                login_required = await self._page.evaluate("""() => {
                    // Check for auth wall or login prompts
                    const authWall = document.querySelector('[data-test="authwall"]');
                    const loginForm = document.querySelector('form.login-form, #session_key');
                    const signInBtn = document.querySelector('a[data-tracking-control-name="guest_homepage-basic_sign-in-button"]');
                    const bodyText = document.body?.innerText || '';
                    
                    return !!(authWall || loginForm || signInBtn || 
                             bodyText.includes('Sign in to LinkedIn'));
                }""")
                
                if login_required:
                    print("⚠️ LinkedIn session expired - waiting 60s for re-login...")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            # Naukri login detection
            elif 'naukri' in current_url:
                login_required = await self._page.evaluate("""() => {
                    // 1. Check for explicit login forms/containers
                    const loginForm = document.querySelector('#login-form, .login-container');
                    if (loginForm) return true;

                    // 2. Check for "Login" button specifically in the main header (avoiding footers/hidden menus)
                    // Naukri's top bar usually has 'naukri-header' or similar structure
                    const header = document.querySelector('.naukri-header, #naukri-header, .naukri-header-container');
                    const loginBtnInHeader = header ? header.querySelector('a[href*="login"], .login-btn') : null;
                    
                    // 3. Verify if we see profile-specific elements (e.g., 'My Naukri', 'Profile', or logout link)
                    const profileIcon = document.querySelector('.icon-profile, .nC_user-img, a[href*="logout"]');
                    const myNaukriText = document.body.innerText.includes('My Naukri') || 
                                       document.body.innerText.includes('View Profile');

                    // If profile elements exist, we are definitely logged in
                    if (profileIcon || myNaukriText) return false;

                    // If we find a login button in the header and NO profile elements, we might be logged out
                    // But common "ghost" login buttons can still exist. 
                    // Let's only trigger if we are on a page that actually REQUIRES login but shows a login prompt.
                    const bodyText = document.body.innerText;
                    const restrictedPage = bodyText.includes('Login to continue') || 
                                         bodyText.includes('Please login');

                    return !!(loginBtnInHeader && restrictedPage);
                }""")
                
                if login_required:
                    print("⚠️ Naukri session expired - waiting 60s for re-login...")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            # Instahyre login detection
            elif 'instahyre' in current_url:
                login_required = await self._page.evaluate("""() => {
                    const googleSignIn = document.querySelector('[data-google-signin], .google-signin-btn, button[id*="google"]');
                    const loginForm = document.querySelector('.login-form, #loginForm, .auth-container');
                    const signInText = document.body?.innerText || '';
                    
                    return !!(googleSignIn || loginForm || 
                             signInText.includes('Sign in with Google') ||
                             signInText.includes('Login to continue'));
                }""")
                
                if login_required:
                    print("⚠️ Instahyre session expired - waiting 60s for re-login...")
                    self.metrics['login_prompts'] += 1
                    await asyncio.sleep(60)
                    return False
            
            return True
        except Exception as e:
            print(f"   ⚠️ Login state check failed: {e}")
            return True  # Assume logged in on error


    async def _human_mouse_move(self, target_x: int = None, target_y: int = None):
        """Add random micro-movements before clicks to simulate human behavior."""
        try:
            # Get current viewport size
            viewport = await self._page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
            
            # If no target, pick random point in viewport
            if target_x is None:
                target_x = random.randint(100, viewport['w'] - 100)
            if target_y is None:
                target_y = random.randint(100, viewport['h'] - 100)
            
            # Start from random position
            start_x = random.randint(50, viewport['w'] - 50)
            start_y = random.randint(50, viewport['h'] - 50)
            
            # Move in 2-4 small steps with slight randomness
            steps = random.randint(2, 4)
            for i in range(steps):
                # Calculate intermediate position with jitter
                progress = (i + 1) / steps
                jitter_x = random.randint(-15, 15)
                jitter_y = random.randint(-10, 10)
                
                curr_x = int(start_x + (target_x - start_x) * progress + jitter_x)
                curr_y = int(start_y + (target_y - start_y) * progress + jitter_y)
                
                await self._page.mouse.move(curr_x, curr_y)
                await asyncio.sleep(random.uniform(0.02, 0.08))
            
            # Final move to target
            await self._page.mouse.move(target_x, target_y)
        except Exception:
            pass  # Silent fail - this is just for human simulation

    async def _human_scroll(self, direction: str = "down", amount: int = None):
        """Variable scroll patterns - sometimes slow, sometimes fast."""
        try:
            # Random scroll behavior type
            scroll_type = random.choice(['smooth', 'stepped', 'quick'])
            
            if amount is None:
                # Variable scroll amounts
                if scroll_type == 'smooth':
                    amount = random.randint(200, 400)
                elif scroll_type == 'stepped':
                    amount = random.randint(100, 200)
                else:  # quick
                    amount = random.randint(400, 600)
            
            scroll_y = amount if direction == "down" else -amount
            
            if scroll_type == 'smooth':
                # Smooth scroll with small increments
                steps = random.randint(5, 8)
                step_amount = scroll_y // steps
                for _ in range(steps):
                    await self._page.evaluate(f"window.scrollBy(0, {step_amount})")
                    await asyncio.sleep(random.uniform(0.03, 0.08))
            
            elif scroll_type == 'stepped':
                # Stepped scroll with pauses (like reading)
                steps = random.randint(2, 4)
                step_amount = scroll_y // steps
                for _ in range(steps):
                    await self._page.evaluate(f"window.scrollBy(0, {step_amount})")
                    await asyncio.sleep(random.uniform(0.1, 0.3))  # Reading pause
            
            else:  # quick
                # Quick single scroll
                await self._page.evaluate(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.2, 0.4))
            
            # Occasional micro-adjustment after scroll
            if random.random() < 0.3:
                micro = random.randint(-30, 30)
                await self._page.evaluate(f"window.scrollBy(0, {micro})")
                
        except Exception:
            pass  # Silent fail

    async def _human_click(self, locator):
        """Human-like click with mouse movement and slight delay."""
        try:
            # Get element position
            box = await locator.bounding_box()
            if box:
                # Calculate click position with slight randomness (not dead center)
                target_x = box['x'] + box['width'] * random.uniform(0.3, 0.7)
                target_y = box['y'] + box['height'] * random.uniform(0.3, 0.7)
                
                # Move mouse to element
                await self._human_mouse_move(int(target_x), int(target_y))
                await asyncio.sleep(random.uniform(0.05, 0.15))
                
                # Click
                await locator.click()
            else:
                # Fallback to regular click
                await locator.click()
        except Exception:
            # Fallback to regular click
            await locator.click()

    # ==========================================
    # ROBUST CLICK HELPERS - Bypass viewport issues
    # ==========================================
    
    async def _robust_click(self, locator, description: str = "element", timeout: int = 5000, retries: int = 3) -> bool:
        """
        Robust click that handles viewport issues with multiple fallback strategies.
        Returns True if click succeeded, False otherwise.
        """
        for attempt in range(retries):
            try:
                # Strategy 1: Try normal Playwright click with short timeout
                try:
                    await locator.click(timeout=min(timeout, 3000))
                    return True
                except Exception:
                    pass
                
                # Strategy 2: Scroll into view and use JS click
                try:
                    await locator.evaluate('el => { el.scrollIntoView({block: "center", behavior: "instant"}); }')
                    await asyncio.sleep(0.1)
                    await locator.evaluate('el => el.click()')
                    return True
                except Exception:
                    pass
                
                # Strategy 3: Force scroll to element and dispatch click event
                try:
                    await locator.evaluate('''el => {
                        el.scrollIntoView({block: "center"});
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    }''')
                    return True
                except Exception:
                    pass
                
                # Strategy 4: Get coordinates and click at position
                try:
                    box = await locator.bounding_box()
                    if box:
                        x = box['x'] + box['width'] / 2
                        y = box['y'] + box['height'] / 2
                        await self._page.mouse.click(x, y)
                        return True
                except Exception:
                    pass
                
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                if attempt == retries - 1:
                    print(f"   ⚠️ Robust click failed after {retries} attempts on {description}: {e}")
        
        return False

    async def _robust_js_click(self, selector: str, description: str = "element", timeout: int = 5000) -> bool:
        """
        Click element using pure JavaScript - most reliable for viewport issues.
        Returns True if click succeeded, False otherwise.
        """
        try:
            result = await self._page.evaluate("""(selector) => {
                const el = document.querySelector(selector);
                if (!el) return 'NOT_FOUND';
                
                // Scroll into view
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                
                // Try direct click
                try { el.click(); return 'CLICKED'; } catch(e) {}
                
                // Fallback: dispatch event
                try {
                    el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    return 'DISPATCHED';
                } catch(e) {
                    return 'FAILED: ' + e.message;
                }
            }""", selector)
            
            if result in ['CLICKED', 'DISPATCHED']:
                return True
            else:
                print(f"   ⚠️ JS click on {description}: {result}")
                return False
        except Exception as e:
            print(f"   ⚠️ JS click failed on {description}: {e}")
            return False

    async def _robust_click_by_text(self, text: str, tag: str = "*", exact: bool = False, timeout: int = 3000) -> bool:
        """
        Click element containing specific text, using JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate("""(text, tag, exact) => {
                const elements = document.querySelectorAll(tag);
                for (const el of elements) {
                    const elText = el.innerText || el.textContent || '';
                    const matches = exact ? elText.trim() === text : elText.toLowerCase().includes(text.toLowerCase());
                    if (matches && el.offsetParent !== null) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return 'CLICKED: ' + elText.substring(0, 50);
                    }
                }
                return 'NOT_FOUND';
            }""", text, tag, exact)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Click by text '{text}' failed: {e}")
            return False

    async def _robust_radio_click(self, value_or_text: str, fallback_index: int = None) -> bool:
        """
        Robustly click a radio button by value, id, or label text.
        Uses JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate("""(valueOrText, fallbackIndex) => {
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                if (radios.length === 0) return 'NO_RADIOS';
                
                // Try to find by value, id, or associated label
                for (const r of radios) {
                    const val = (r.value || '').toLowerCase();
                    const id = (r.id || '').toLowerCase();
                    const label = r.closest('label') || document.querySelector('label[for="' + r.id + '"]');
                    const labelText = label ? label.innerText.toLowerCase() : '';
                    
                    if (val.includes(valueOrText.toLowerCase()) || 
                        id.includes(valueOrText.toLowerCase()) || 
                        labelText.includes(valueOrText.toLowerCase())) {
                        r.scrollIntoView({block: 'center'});
                        r.click();
                        return 'CLICKED: ' + (label ? label.innerText : val);
                    }
                }
                
                // Fallback to index
                if (fallbackIndex !== null && fallbackIndex < radios.length) {
                    radios[fallbackIndex].scrollIntoView({block: 'center'});
                    radios[fallbackIndex].click();
                    return 'CLICKED_INDEX: ' + fallbackIndex;
                }
                
                return 'NOT_FOUND';
            }""", value_or_text, fallback_index)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Radio click '{value_or_text}' failed: {e}")
            return False

    async def _robust_checkbox_click(self, value_or_text: str = None, select_all: bool = False) -> bool:
        """
        Robustly click checkboxes, optionally all visible ones or by value/text.
        Uses JS to bypass viewport issues.
        """
        try:
            result = await self._page.evaluate("""(valueOrText, selectAll) => {
                const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                let clicked = 0;
                
                for (const cb of cbs) {
                    if (cb.offsetParent === null) continue;  // Skip hidden
                    if (cb.checked) continue;  // Skip already checked
                    
                    const val = (cb.value || '').toLowerCase();
                    const label = cb.closest('label') || document.querySelector('label[for="' + cb.id + '"]');
                    const labelText = label ? label.innerText.toLowerCase() : '';
                    
                    if (selectAll) {
                        cb.scrollIntoView({block: 'center'});
                        cb.click();
                        clicked++;
                    } else if (valueOrText) {
                        if (val.includes(valueOrText.toLowerCase()) || labelText.includes(valueOrText.toLowerCase())) {
                            cb.scrollIntoView({block: 'center'});
                            cb.click();
                            return 'CLICKED: ' + (label ? label.innerText : val);
                        }
                    }
                }
                
                if (selectAll) return clicked > 0 ? 'CLICKED_ALL: ' + clicked : 'NONE_TO_CLICK';
                return 'NOT_FOUND';
            }""", value_or_text, select_all)
            
            if 'CLICKED' in result:
                return True
            return False
        except Exception as e:
            print(f"   ⚠️ Checkbox click failed: {e}")
            return False

    async def _robust_button_click(self, text_patterns: list, fallback_selector: str = None) -> bool:
        """
        Click button by text pattern with JS fallback.
        text_patterns: List of text strings to look for (first match wins)
        """
        for pattern in text_patterns:
            try:
                result = await self._page.evaluate("""(pattern) => {
                    const buttons = document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], .btn, a.button');
                    for (const btn of buttons) {
                        const text = btn.innerText || btn.value || '';
                        if (text.toLowerCase().includes(pattern.toLowerCase()) && btn.offsetParent !== null) {
                            btn.scrollIntoView({block: 'center'});
                            btn.click();
                            return 'CLICKED: ' + text.substring(0, 30);
                        }
                    }
                    return 'NOT_FOUND';
                }""", pattern)
                
                if 'CLICKED' in result:
                    return True
            except Exception:
                continue
        
        # Try fallback selector
        if fallback_selector:
            return await self._robust_js_click(fallback_selector, "button fallback")
        
        return False

    async def _scroll_element_into_view(self, selector_or_locator, block: str = "center") -> bool:
        """
        Scroll element into viewport using multiple strategies.
        """
        try:
            if isinstance(selector_or_locator, str):
                await self._page.evaluate("""(selector, block) => {
                    const el = document.querySelector(selector);
                    if (el) el.scrollIntoView({block: block, behavior: 'instant'});
                }""", selector_or_locator, block)
            else:
                await selector_or_locator.evaluate(f'el => el.scrollIntoView({{block: "{block}", behavior: "instant"}})')
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False


    async def _dismiss_browser_dialogs(self):
        """Dismiss common browser dialogs like 'Restore pages?'"""
        try:
            result = await self._page.evaluate("""() => {
                // Chrome "Restore pages?" dialog - click X button
                const restoreDialog = document.querySelector('[aria-label="Restore pages?"], [aria-describedby*="restore"]');
                if (restoreDialog) {
                    const closeBtn = restoreDialog.querySelector('button[aria-label="Close"], .close-button, button:has(svg)');
                    if (closeBtn) {
                        closeBtn.click();
                        return 'CLOSED_RESTORE_DIALOG';
                    }
                }
                
                // Any dialog with "Restore" button - click X instead
                const restoreBtn = document.querySelector('button:has-text("Restore")');
                if (restoreBtn) {
                    const dialog = restoreBtn.closest('[role="dialog"], .modal, [aria-modal="true"]');
                    if (dialog) {
                        const closeBtn = dialog.querySelector('button[aria-label*="close"], button[aria-label*="dismiss"], .close');
                        if (closeBtn) {
                            closeBtn.click();
                            return 'CLOSED_DIALOG';
                        }
                    }
                }
                
                // Generic modal dismiss
                const genericModals = document.querySelectorAll('[role="dialog"], [aria-modal="true"]');
                for (let modal of genericModals) {
                    if (modal.innerText && modal.innerText.includes("didn't shut down")) {
                        const xBtn = modal.querySelector('button[aria-label*="Close"], svg, .close-button');
                        if (xBtn) {
                            xBtn.click();
                            return 'CLOSED_CRASH_DIALOG';
                        }
                    }
                }
                
                return 'NO_DIALOG';
            }""")
            
            if 'CLOSED' in result:
                print(f"   🚫 {result}")
                await asyncio.sleep(0.5)
                return True
            return False
        except Exception:
            return False


    def _log_js_msg(self, msg):
        """Helper to log JS console messages with filtering for noisy errors."""
        text = msg.text
        
        # Filter out noisy resource loading errors
        noisy_patterns = [
            'ERR_FAILED',
            'Failed to load resource',
            'the server responded with a status of',
            'visitor.publishDestinations',
            'destination publishing iframe',
            'External tag load event',
            'net::ERR_BLOCKED_BY_CLIENT',
            'net::ERR_CONNECTION_REFUSED',
        ]
        
        # Skip if message contains any noisy pattern
        if any(pattern in text for pattern in noisy_patterns):
            return
        
        # Skip tracking/analytics domains
        noisy_domains = [
            'ads.linkedin.com',
            'analytics',
            'tracking',
            'pixel',
            'google-analytics',
            'doubleclick',
            'facebook.com/tr',
        ]
        
        if any(domain in text.lower() for domain in noisy_domains):
            return
        
        # Print important messages
        print(f"   🖥️ JS: {text[:200]}")  # Limit length to prevent spam

    def _get_max_steps(self) -> int:
        """Determine max steps based on task type - LinkedIn gets 120, others get 50."""
        # Use a more specific check for LinkedIn to avoid false positives from common context
        task_desc = getattr(self, '_task_description', '')
        current_url = self._page.url.lower() if self._page else ''
        
        # Check if the task is explicitly for LinkedIn based on URL or specific LinkedIn keywords
        is_linkedin_task = (
            'linkedin.com/jobs' in current_url or 
            'linkedin.com/search' in current_url or
            ('LINKEDIN_JOB_APPLY_TASK' in task_desc and 'linkedin' in current_url)
        )
        
        if is_linkedin_task:
            return self.MAX_STEPS_LINKEDIN
        return self.MAX_STEPS_DEFAULT

    async def run(self, task_description: str = "") -> bool:
        """Main execution loop - 100% SCRIPTED (No LLM)."""
        self._task_description = task_description  # Store for use in handlers
        max_steps = self._get_max_steps()
        print(f"\n🚀 Sentinel Starting Task (Script Mode): {task_description}")
        print(f"   📊 Max Steps: {max_steps}")
        
        # Initialize metrics for this task
        self.metrics = {
            'task_name': task_description[:50] if task_description else 'Unknown',
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'applications_submitted': 0,
            'questions_answered': 0,
            'errors_encountered': 0,

            'login_prompts': 0,
            'steps_taken': 0,
            'success': False
        }
        
        # Enable console logging from browser (Safe Mode)
        if self._page and not getattr(self, '_console_listening', False):
            try:
                self._page.on("console", self._log_js_msg)
                self._console_listening = True
                print("   ✅ Browser console logging enabled")
            except Exception as e:
                print(f"   ⚠️ Could not enable browser console logging: {e}")
        
        while self.state.step_count < max_steps and not self.state.task_complete:
            self.state.step_count += 1
            print(f"\n📍 Step {self.state.step_count}/{max_steps}")
            
            try:
                # Guard: stop immediately if LinkedIn rate limit is still active
                if self.linkedin_rate_limit_until and datetime.now() < self.linkedin_rate_limit_until:
                    remaining = (self.linkedin_rate_limit_until - datetime.now()).seconds // 60
                    print(f"⏳ LinkedIn rate limited. {remaining} min remaining. Stopping task.")
                    self.state.task_complete = True
                    break

                current_url = self._page.url if self._page else ""
                
                # Periodic memory cleanup
                await self._maybe_cleanup_memory()
                
                # Page health check before actions
                if not await self._check_page_health():
                    print("   🔄 Retrying after page health issue...")
                    await asyncio.sleep(3)
                    continue
                

                
                # Login state check - pause for re-login
                if not await self._check_login_state():
                    print("   🔄 Resuming after login...")
                    continue
                
                # Dismiss any browser dialogs (Restore pages?, etc.)
                await self._dismiss_browser_dialogs()
                
                # Occasional random human behaviors (simulate natural browsing)
                if random.random() < 0.2:  # 20% chance of random mouse movement
                    await self._human_mouse_move()
                if random.random() < 0.15:  # 15% chance of random small scroll
                    await self._human_scroll(direction=random.choice(["down", "up"]))
                
                await asyncio.sleep(random.uniform(4, 8))  # Random 4-8 sec gap between actions
                
                # Run scripted fallback
                result = await self._handle_scripted_fallback()
                print(f"📜 Script Result: {result}")
                
                # Handle question data logging if present
                if result and '|' in result:
                    parts = result.split('|', 1)
                    action = parts[0]
                    if len(parts) > 1:
                        try:
                            question_data_json = parts[1]
                            question_data = json.loads(question_data_json)
                            current_url = self._page.url if self._page else ''
                            for q_data in question_data:
                                self._log_question_detailed({
                                    'question': q_data.get('question', ''),
                                    'answer': q_data.get('answer', ''),
                                    'input_type': q_data.get('inputType', ''),
                                    'match_phase': 'aggressive' if 'aggressive' in q_data.get('inputType', '') else 'pattern_match',
                                    'options': q_data.get('options', []),
                                    'selected_option': q_data.get('selectedOption', ''),
                                    'context': self._detect_platform(),
                                    'url': current_url,
                                    'confidence': 'form_filled'
                                })
                            # Update result to just the action part
                            result = action
                        except json.JSONDecodeError:
                            pass
                
                # Handle results
                if result == 'TASK_COMPLETE': 
                    print("🎉 Task Completed Successfully!")
                    self.state.task_complete = True
                    break
                
                # Naukri: Task complete after target jobs applied
                if 'NAUKRI_TASK_DONE' in result:
                    print("🎉 Naukri task complete - applied to 5 jobs successfully!")
                    self.state.task_complete = True
                    break
                
                # Naukri: Rate limit detected (error popup)
                if 'NAUKRI_RATE_LIMITED' in result:
                    self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                    print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                    self.state.task_complete = True
                    break
                
                # LinkedIn: Easy Apply daily limit detected in outer loop (before/after autopilot)
                if 'LINKEDIN_RATE_LIMITED' in result:
                    self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=3)
                    print(f"⚠️ LinkedIn Easy Apply Limit! Pausing for 3 hours until {self.linkedin_rate_limit_until.strftime('%H:%M')}")
                    self.state.task_complete = True
                    break
                
                if 'SUCCESS' in result:
                    # For LinkedIn, we want to apply to multiple jobs (up to limit)
                    if 'LinkedIn' in self._task_description:
                         print("🎉 Job application successful! Moving to next job...")
                         # Do NOT break here, let the loop continue
                    else:
                        # For other tasks (Naukri single apply), we break
                        print("🎉 Task Completed Successfully!")
                        self.state.task_complete = True
                        break
                
                # Naukri: Partial success - applied some jobs but need more
                if 'NAUKRI_SUCCESS_PARTIAL' in result:
                    print(f"📜 {result}")
                    print("🔄 Continuing to apply for more jobs...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Success detected but need to navigate to next job
                if 'LINKEDIN_SUCCESS_NEED_NAV' in result:
                    self.metrics['applications_submitted'] += 1
                    print(f"✅ LinkedIn success! Total: {self.metrics['applications_submitted']}")
                    
                    if 'LinkedIn' in self._task_description and self.metrics['applications_submitted'] >= 5:
                        print("🎉 LinkedIn limit reached (5 jobs). Stopping task.")
                        self.state.task_complete = True
                        break

                    print("   Need to navigate to next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Success modal was closed, need to navigate to next job
                if 'LINKEDIN_SUCCESS_MODAL_CLOSED' in result:
                    self.metrics['applications_submitted'] += 1
                    print(f"✅ Success modal dismissed. Total: {self.metrics['applications_submitted']}")
                    
                    if 'LinkedIn' in self._task_description and self.metrics['applications_submitted'] >= 5:
                        print("🎉 LinkedIn limit reached (5 jobs). Stopping task.")
                        self.state.task_complete = True
                        break

                    print("   Looking for next job...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # LinkedIn: Safety modal "Continue applying" button clicked
                if 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED' in result:
                    print("✅ LinkedIn safety modal dismissed, continuing application...")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: Location autocomplete dropdown needs to be clicked
                if result in ('LINKEDIN_LOCATION_RETRIGGERED', 'LINKEDIN_LOCATION_FILLED_WAITING_DROPDOWN'):
                    retrigger_count = getattr(self, '_location_retrigger_count', 0) + 1
                    self._location_retrigger_count = retrigger_count
                    
                    if retrigger_count > 2:
                        print(f"⚠️ Location dropdown not appearing after {retrigger_count} attempts. Trying fallback strategies...")
                        self._location_retrigger_count = 0
                        
                        # Strategy 1: Try clearing the location field entirely and see if that allows progress
                        print("   📝 Strategy 1: Clearing location field...")
                        try:
                            clear_result = await self._page.evaluate("""() => {
                                const inputs = document.querySelectorAll('input[type="text"], input[type="search"], textarea, input:not([type="hidden"])');
                                let locationInput = null;
                                for (const inp of inputs) {
                                    const val = inp.value || '';
                                    if (val.toLowerCase().includes('noida')) {
                                        locationInput = inp;
                                        break;
                                    }
                                }
                                
                                if (locationInput) {
                                    // Clear the field completely
                                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                    nativeInputValueSetter.call(locationInput, '');
                                    locationInput.dispatchEvent(new Event('input', { bubbles: true }));
                                    locationInput.dispatchEvent(new Event('change', { bubbles: true }));
                                    locationInput.dispatchEvent(new Event('blur', { bubbles: true }));
                                    console.log('Location field cleared');
                                    return 'CLEARED';
                                }
                                return 'NOT_FOUND';
                            }""")
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            print(f"   ⚠️ Clear failed: {e}")
                        
                        # Strategy 2: Force click the Next button even with empty/invalid location
                        print("   🔘 Strategy 2: Force-clicking Next button...")
                        try:
                            # Use Playwright's click which is more reliable
                            next_buttons = await self._page.locator('button:has-text("Next"), button:has-text("Continue"), button[aria-label*="Next"]').all()
                            clicked = False
                            for btn in next_buttons:
                                try:
                                    await btn.click(timeout=1000)
                                    print("   ✅ Next button clicked via locator")
                                    clicked = True
                                    break
                                except:
                                    pass
                            
                            if not clicked:
                                # Fallback to JavaScript click
                                await self._page.evaluate("""() => {
                                    const buttons = document.querySelectorAll('button');
                                    for (const btn of buttons) {
                                        const text = btn.innerText.toLowerCase();
                                        if ((text.includes('next') || text.includes('continue')) && btn.offsetParent !== null) {
                                            console.log('Force clicking button:', btn.innerText);
                                            btn.click();
                                            btn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                            btn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                            btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                            return 'CLICKED';
                                        }
                                    }
                                    return 'NOT_FOUND';
                                }""")
                                print("   ✅ Next button clicked via JavaScript")
                            
                            await asyncio.sleep(1)
                        except Exception as e:
                            print(f"   ⚠️ Force click failed: {e}")
                        
                        continue
                    
                    print(f"   🔍 Selecting location from dropdown (attempt {retrigger_count}/3)...")
                    try:
                        # Get diagnostic info about what's in the DOM
                        diagnostics = await self._page.evaluate("""() => {
                            const modal = document.querySelector('.jobs-easy-apply-modal, .artdeco-modal--is-open');
                            if (!modal) return { error: 'No modal found' };
                            
                            // Find the Noida input
                            const inputs = modal.querySelectorAll('input[type="text"], input[type="search"], textarea');
                            let noIdaInput = null;
                            for (const inp of inputs) {
                                if ((inp.value || '').includes('Noida')) {
                                    noIdaInput = inp;
                                    break;
                                }
                            }
                            
                            if (!noIdaInput) return { error: 'Noida input not found' };
                            
                            // Look for dropdown-related elements
                            const dropdownLists = modal.querySelectorAll('[role="listbox"], .typeahead-input__dropdown-list, .artdeco-typeahead__results-list, [data-test-typeahead-results]');
                            const dropdownItems = modal.querySelectorAll('[role="option"], .typeahead-input__dropdown-item, .artdeco-typeahead__result');
                            
                            // Look for any select elements
                            const selects = modal.querySelectorAll('select');
                            const selectOptions = selects.length > 0 ? Array.from(selects[0].querySelectorAll('option')).map(o => o.text) : [];
                            
                            // Look for buttons near the input
                            const inputContainer = noIdaInput.closest('.fb-dash-form-element') || noIdaInput.parentElement;
                            const buttonsNear = inputContainer ? inputContainer.querySelectorAll('button') : [];
                            
                            return {
                                inputId: noIdaInput.id,
                                inputValue: noIdaInput.value,
                                dropdownListsFound: dropdownLists.length,
                                dropdownItemsFound: dropdownItems.length,
                                selectsFound: selects.length,
                                selectOptions: selectOptions,
                                buttonsNear: Array.from(buttonsNear).map(b => b.innerText),
                                inputParentClass: inputContainer?.className
                            };
                        }""")
                        
                        print(f"   📋 Diagnostics: {diagnostics}")
                        
                        if diagnostics.get('error'):
                            print(f"   ⚠️ {diagnostics['error']}")
                        
                        # Try strategy 1: Keyboard navigation (ArrowDown to select first option)
                        print("   ↓ Trying keyboard navigation...")
                        keyboard_result = await self._page.evaluate("""() => {
                            const inputs = document.querySelectorAll('input[type="text"], input[type="search"], textarea, input:not([type="hidden"])');
                            let locationInput = null;
                            for (const inp of inputs) {
                                const val = inp.value || '';
                                if (val.toLowerCase().includes('noida')) {
                                    locationInput = inp;
                                    break;
                                }
                            }
                            
                            if (locationInput) {
                                locationInput.focus();
                                // Try ArrowDown to open dropdown
                                locationInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                locationInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                // Wait briefly then try another ArrowDown to select first option
                                return 'ARROW_DOWN_SENT';
                            }
                            return 'NOT_FOUND';
                        }""")
                        
                        # Wait for potential dropdown to open
                        await asyncio.sleep(0.4)
                        
                        # Step 2: Try to find and click dropdown option
                        click_result = await self._page.evaluate("""() => {
                            // First check if there are ANY visible elements that might be dropdown items
                            const allDivs = document.querySelectorAll('[role="option"], li, div[class*="dropdown"], div[class*="option"], span[class*="option"]');
                            console.log('Total potential dropdown elements:', allDivs.length);
                            
                            // Try all dropdown selectors with aggressive clicking
                            const dropdownSelectors = [
                                // Pismo-specific selectors (what we see in your form)
                                'div[class*="typeahead"] [role="option"]',
                                'div[class*="search-vertical"] [role="option"]',
                                '.gqueried-content [role="option"]',
                                '[role="option"]',
                                
                                // LinkedIn-specific selectors
                                '.typeahead-input__dropdown-item',
                                '.typeahead-input__dropdown-list li',
                                '[role="listbox"] [role="option"]',
                                '.artdeco-typeahead__result',
                                'li[class*="typeahead"]',
                                'div[class*="dropdown"] li',
                                'div[class*="option"] li'
                            ];
                            
                            let clickedAny = false;
                            for (const selector of dropdownSelectors) {
                                const options = document.querySelectorAll(selector);
                                console.log('Checking selector:', selector, '- found:', options.length);
                                for (const option of options) {
                                    // Check if option is visible and has content
                                    if (option.offsetParent !== null) {
                                        const text = (option.innerText || option.textContent || '').trim();
                                        if (text && text.toLowerCase().includes('noida')) {
                                            console.log('Found Noida option, clicking:', text);
                                            option.scrollIntoView({block: 'nearest'});
                                            option.click();
                                            option.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                            option.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                            option.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                            option.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                            clickedAny = true;
                                            break;
                                        }
                                    }
                                }
                                if (clickedAny) break;
                            }
                            
                            if (!clickedAny) {
                                // Try clicking any visible option as fallback
                                for (const selector of dropdownSelectors) {
                                    const options = document.querySelectorAll(selector);
                                    for (const option of options) {
                                        if (option.offsetParent !== null) {
                                            const text = (option.innerText || option.textContent || '').trim();
                                            if (text && text.length > 0 && !text.includes('select') && !text.includes('choose')) {
                                                console.log('Fallback: clicking first visible option:', text);
                                                option.scrollIntoView({block: 'nearest'});
                                                option.click();
                                                option.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                                option.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                                option.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                                option.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                                clickedAny = true;
                                                break;
                                            }
                                        }
                                    }
                                    if (clickedAny) break;
                                }
                            }
                            
                            return clickedAny ? 'CLICKED' : 'NOT_FOUND';
                        }""")
                        
                        if click_result == 'CLICKED':
                            print("   ✅ Dropdown option clicked")
                            self._location_retrigger_count = 0
                            await asyncio.sleep(1)
                        else:
                            # Fallback: Try using Playwright's locator to find and click the option
                            print("   📍 JavaScript click didn't work, trying Playwright locator...")
                            try:
                                # Try to find and click any option containing "Noida"
                                option_locator = self._page.locator('[role="option"]:has-text("Noida")')
                                if await option_locator.count() > 0:
                                    await option_locator.first.click(timeout=2000)
                                    print("   ✅ Clicked option via Playwright locator")
                                    self._location_retrigger_count = 0
                                    await asyncio.sleep(1)
                                else:
                                    # Try clicking any visible option
                                    any_option = self._page.locator('[role="option"]')
                                    if await any_option.count() > 0:
                                        await any_option.first.click(timeout=2000)
                                        print("   ✅ Clicked first option via Playwright")
                                        self._location_retrigger_count = 0
                                        await asyncio.sleep(1)
                                    else:
                                        print("   ⏳ No options found via Playwright either, will retry...")
                                        await asyncio.sleep(0.5)
                            except Exception as e:
                                print(f"   ⚠️ Playwright click failed: {e}")
                                await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"   ⚠️ Error during selection: {e}")
                        await asyncio.sleep(0.5)
                    continue
                
                # LinkedIn: First job opened (when no currentJobId in URL)
                if 'LINKEDIN_FIRST_JOB' in result:
                    print(f"✅ {result}")
                    await asyncio.sleep(random.uniform(4, 6))
                    continue
                
                # LinkedIn: Navigation results
                if 'LINKEDIN_NAVIGATED' in result:
                    print(f"✅ {result}")
                    if 'card null' in result.lower() or 'card None' in result:
                        if not self._linkedin_scroll_attempted:
                            print("⚠️  Null card detected - trying to scroll down first...")
                            self._linkedin_scroll_attempted = True
                            try:
                                # Scroll the job list to load more jobs
                                await self._page.evaluate("""() => {
                                    const sidebar = document.querySelector('.scaffold-layout__list') || 
                                                   document.querySelector('.jobs-search-results-list');
                                    if (sidebar) {
                                        sidebar.scrollTop += 800;
                                        return 'Scrolled job list';
                                    }
                                    window.scrollTo(0, window.scrollY + 800);
                                    return 'Scrolled window';
                                }""")
                                await asyncio.sleep(random.uniform(3, 5))
                            except Exception as e:
                                print(f"⚠️  Scroll failed: {e}")
                        else:
                            print("⚠️  Null card still detected after scroll - refreshing page...")
                            self._linkedin_scroll_attempted = False  # Reset for next time
                            try:
                                await self._page.reload(wait_until='domcontentloaded', timeout=15000)
                                await asyncio.sleep(random.uniform(5, 8))
                            except Exception as e:
                                print(f"⚠️  Refresh failed: {e}")
                    else:
                        self._linkedin_scroll_attempted = False  # Reset on successful navigation
                        await asyncio.sleep(random.uniform(4, 6))  # Wait for job details to load
                    continue
                
                # LinkedIn: Scrolled for more jobs
                if 'LINKEDIN_SCROLLED' in result:
                    print(f"📜 {result}")
                    await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    continue
                
                # LinkedIn: Skip non-Easy Apply jobs or already applied jobs
                if 'LINKEDIN_JOB_SKIPPED' in result:
                    print(f"   ℹ️ Result: {result}")  # Debug log
                    if 'SCROLLED_FOR_MORE' in result:
                        print("📜 Scrolled job list to load more jobs, waiting...")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    elif 'FOUND_UNAPPLIED' in result:
                        print("🔍 Found non-applied job, navigating to it...")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for job details to load
                    elif 'NEXT' in result:
                        print("⏭️ Skipped to next job in list")
                        await asyncio.sleep(random.uniform(4, 8))  # Wait for job details to load
                    else:
                        print("⏭️ Skipped job (already applied or not Easy Apply)")
                    continue
                
                # LinkedIn: Form stuck loop detection in outer step loop
                # When autopilot breaks after being stuck, the outer loop keeps getting
                # LINKEDIN_FORM_STUCK from _handle_scripted_fallback. After 3 consecutive
                # stuck results, force-close the modal and navigate away to escape.
                if 'LINKEDIN_FORM_STUCK' in result:
                    self._linkedin_stuck_count += 1
                    print(f"⚠️ LinkedIn form stuck ({self._linkedin_stuck_count}/3): {result}")
                    if self._linkedin_stuck_count >= 3:
                        print("⚠️ LinkedIn stuck 3x in outer loop. Force-closing modal and navigating away...")
                        closed = await self._close_linkedin_modal()
                        if not closed:
                            print("⚠️ Modal close failed — navigating to LinkedIn jobs search to escape...")
                            try:
                                await self._page.goto('https://www.linkedin.com/jobs/search/', timeout=30000)
                                await asyncio.sleep(random.uniform(4, 6))
                            except Exception as nav_e:
                                print(f"   ⚠️ Navigation fallback error: {nav_e}")
                        self._linkedin_stuck_count = 0  # Reset counter
                        await asyncio.sleep(random.uniform(2, 3))
                    else:
                        await asyncio.sleep(random.uniform(2, 4))
                    continue
                
                # Reset stuck counter on any non-stuck LinkedIn result
                if 'LINKEDIN' in result and 'LINKEDIN_FORM_STUCK' not in result:
                    self._linkedin_stuck_count = 0
                
                # LinkedIn Autopilot — triggered by APPLY_CLICKED_LINKEDIN (legacy) or LINKEDIN_EASY_APPLY_CLICKED (JS)
                if 'APPLY_CLICKED_LINKEDIN' in result or 'LINKEDIN_EASY_APPLY_CLICKED' in result:
                    # STRICT CHECK: If we've already submitted 5 applications, mark task complete
                    if self.linkedin_applications >= 5:
                        print(f"✅ LinkedIn limit reached ({self.linkedin_applications}/5). Task complete.")
                        self.state.task_complete = True
                        continue
                    
                    print("🔄 Entering LinkedIn Autopilot Mode...")
                    # Wait for the Easy Apply modal to fully open before first autopilot iteration
                    # Without this, the modal heuristics might run before the modal DOM is ready
                    await asyncio.sleep(random.uniform(3, 4))
                    same_result_count = 0
                    last_result = ""
                    submit_attempt_count = 0  # Track submit attempts without success
                    max_submit_attempts = 3   # Max retries per job before skipping
                    autopilot_iteration = 0   # Track total iterations in autopilot
                    max_autopilot_iterations = 50  # Safety limit per job
                    transitioning_count = 0   # Track consecutive modal transitioning states
                    max_transitioning_attempts = 5  # Max waits for modal to transition
                    
                    while True:
                        autopilot_iteration += 1

                        
                        # SAFETY: Exit autopilot if too many iterations (prevents infinite loop)
                        if autopilot_iteration > max_autopilot_iterations:
                            print(f"⚠️ Max iterations ({max_autopilot_iterations}) reached for this job. Skipping...")
                            # Try to close any open modal and move on (two-step close)
                            await self._close_linkedin_modal()
                            break
                        
                        await asyncio.sleep(random.uniform(4, 8))
                        
                        # Check for Easy Apply daily limit dialog or generic rate limit message
                        rate_limited = await self._page.evaluate("""() => {
                            // Primary: check for the specific Easy Apply fuse limit dialog
                            const limitDialog = (
                                document.querySelector('[data-testid="dialog-content"]') ||
                                document.querySelector('[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.EasyApplyFuseLimitDialogModal"]')
                            );
                            if (limitDialog) {
                                const dlgText = (limitDialog.innerText || '').toLowerCase();
                                if (dlgText.includes('easy apply limit') || dlgText.includes('apply tomorrow') || dlgText.includes('continue applying tomorrow')) {
                                    return true;
                                }
                            }
                            // Fallback: body-text heuristics
                            const bodyText = document.body.innerText.toLowerCase();
                            return bodyText.includes('you reached today') ||
                                   bodyText.includes('easy apply limit') ||
                                   bodyText.includes('we limit daily submissions') || 
                                   bodyText.includes('prevent bots') ||
                                   bodyText.includes('apply tomorrow');
                        }""")
                        
                        if rate_limited:
                            # Click "Got it" to dismiss the dialog before pausing
                            try:
                                await self._page.evaluate("""() => {
                                    // Try the specific Got it button inside the limit dialog
                                    const selectors = [
                                        '[data-testid="dialog-content"] button',
                                        '[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.EasyApplyFuseLimitDialogModal"] button'
                                    ];
                                    for (const sel of selectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.click();
                                            return 'GOT_IT_CLICKED';
                                        }
                                    }
                                    // Fallback: any visible button whose text is "Got it"
                                    const allBtns = document.querySelectorAll('button');
                                    for (const btn of allBtns) {
                                        if ((btn.innerText || '').trim().toLowerCase() === 'got it' && btn.offsetParent !== null) {
                                            btn.click();
                                            return 'GOT_IT_CLICKED_FALLBACK';
                                        }
                                    }
                                    return 'NO_GOT_IT_BTN';
                                }""")
                            except Exception:
                                pass
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=3)
                            print(f"⚠️ LinkedIn Easy Apply Limit Detected! Pausing for 3 hours until {self.linkedin_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        
                        # Check for application loading error ("We experienced an error loading this application")
                        app_load_error = await self._page.evaluate("""() => {
                            const errorMsg = document.querySelector('.artdeco-inline-feedback--error .artdeco-inline-feedback__message');
                            if (errorMsg) {
                                const text = (errorMsg.innerText || '').toLowerCase();
                                if (text.includes('experienced an error') || text.includes('error loading')) {
                                    return true;
                                }
                            }
                            // Also check for general error text on page
                            const bodyText = document.body.innerText.toLowerCase();
                            return bodyText.includes('we experienced an error loading this application');
                        }""")
                        
                        if app_load_error:
                            print("⚠️ LinkedIn Application Loading Error Detected! Skipping this job...")
                            # Close any open modal (two-step close)
                            await self._close_linkedin_modal()
                            break  # Skip to next job
                        
                        next_result = await self._handle_scripted_fallback()
                        print(f"   📜 Autopilot: {next_result}")
                        
                        # Check for rate limit in result
                        if 'LINKEDIN_RATE_LIMITED' in next_result:
                            self.linkedin_rate_limit_until = datetime.now() + timedelta(hours=3)
                            print(f"⚠️ LinkedIn Easy Apply Limit! Pausing for 3 hours until {self.linkedin_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        
                        # DETECT SUBMISSION FAILURE: If no modal present after submit, it likely failed
                        if 'LINKEDIN_SUBMISSION_FAILED' in next_result:
                            print(f"❌ Submission failed (attempt {submit_attempt_count + 1}/{max_submit_attempts})")
                            submit_attempt_count += 1
                            if submit_attempt_count >= max_submit_attempts:
                                print("⚠️ Max submit attempts reached. Skipping this job...")
                                break
                            continue
                        
                        # Prevent infinite loop if same result repeats
                        if next_result == last_result:
                            same_result_count += 1
                            if same_result_count >= 5:
                                print("⚠️ Stuck in loop, skipping this job...")
                                # Two-step close: X button then Discard confirmation
                                await self._close_linkedin_modal()
                                break
                        else:
                            same_result_count = 0
                            transitioning_count = 0  # Reset transitioning counter on any different result
                        last_result = next_result
                        
                        if 'LINKEDIN_SUCCESS' in next_result:
                            self.linkedin_applications += 1
                            self.metrics['applications_submitted'] += 1
                            print(f"🎉 LinkedIn Application {self.linkedin_applications}/5 Submitted!")
                            submit_attempt_count = 0  # Reset on success
                            
                            if self.linkedin_applications >= 5:
                                print("✅ LinkedIn target (5 applications) reached. Task complete!")
                                self.state.task_complete = True
                                break
                                
                            await asyncio.sleep(random.uniform(2, 4))
                            # Exit autopilot after successful submit to navigate to next job
                            break
                        # Fallback: if we clicked submit and the modal closed (signaled by no modal actions like clicking Easy Apply or selecting/scrolling jobs)
                        elif submit_attempt_count > 0 and ('LINKEDIN_EASY_APPLY_CLICKED' in next_result or 'LINKEDIN_JOB_SELECTED' in next_result or 'LINKEDIN_SCROLLED' in next_result):
                            self.linkedin_applications += 1
                            self.metrics['applications_submitted'] += 1
                            print(f"🎉 LinkedIn Application {self.linkedin_applications}/5 Submitted (modal closed after submit)!")
                            submit_attempt_count = 0
                            
                            if self.linkedin_applications >= 5:
                                print("✅ LinkedIn target (5 applications) reached. Task complete!")
                                self.state.task_complete = True
                                break
                                
                            await asyncio.sleep(random.uniform(2, 4))
                            break
                        elif 'LINKEDIN_SUBMITTED' in next_result:
                            submit_attempt_count += 1
                            print(f"✅ Clicked Submit (attempt {submit_attempt_count}/{max_submit_attempts})")
                            
                            # If we've clicked submit too many times without success, the submission is failing
                            if submit_attempt_count >= max_submit_attempts:
                                print("⚠️ Submit not working (possible 403 error). Skipping this job...")
                                # Try to close the modal (two-step close)
                                await self._close_linkedin_modal()
                                break
                            continue
                        elif 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED' in next_result:
                            print("🛡️ Acknowledged Safety Reminder")
                            continue
                        elif 'LINKEDIN_MODAL_TRANSITIONING' in next_result:
                            transitioning_count += 1
                            if transitioning_count >= max_transitioning_attempts:
                                print("⚠️ Modal stuck in transitioning state. Forcing navigation to next job...")
                                transitioning_count = 0
                                break
                            print(f"⏳ Modal is transitioning or loading ({transitioning_count}/{max_transitioning_attempts}), waiting...")
                            await asyncio.sleep(random.uniform(2, 3))
                            continue
                        elif 'LINKEDIN_NEXT_CLICKED' in next_result or 'LINKEDIN_REVIEW_CLICKED' in next_result:
                            print("➡ Clicked Next/Review")
                            # NOTE: Do NOT reset submit_attempt_count here!
                            # The 403 loop shows Next/Review buttons after failed submit
                            continue
                        elif 'LINKEDIN_FORM_FILLED' in next_result:
                            print("📝 Filled form fields")
                            submit_attempt_count = 0  # Reset when filling (progress made)
                            
                            # Parse and log Q&A data if present
                            if '|' in next_result:
                                try:
                                    qa_json = next_result.split('|', 1)[1]
                                    qa_pairs = json.loads(qa_json)
                                    for qa in qa_pairs:
                                        self._log_all_questions(
                                            qa.get('q', 'Unknown'),
                                            qa.get('a', ''),
                                            context="LinkedIn_Form",
                                            match_confidence="Keyword Match"
                                        )
                                except Exception:
                                    pass  # Silently handle parse errors
                            continue
                        elif 'LINKEDIN_AUTOCOMPLETE_OPTION_SELECTED' in next_result:
                            print("🎯 Selected autocomplete option")
                            await asyncio.sleep(0.5)  # Brief pause for selection to register
                            continue
                        elif 'LINKEDIN_CITY_TYPED' in next_result:
                            print("🏙️ Typed city, waiting for dropdown...")
                            await asyncio.sleep(1.5)  # Wait for dropdown to appear
                            continue
                        elif 'LINKEDIN_CITY_SELECTED' in next_result:
                            print("✅ Selected city from dropdown")
                            continue
                        elif 'LINKEDIN_CHECKBOX_CHECKED' in next_result:
                            print("☑️ Checked Terms/Privacy checkbox")
                            continue
                        elif 'LINKEDIN_FORM_STUCK' in next_result:
                            print("⚠️ Form stuck (button not found or validation issue). Waiting for re-render...")
                            await asyncio.sleep(random.uniform(2, 4))
                            continue
                        elif 'LINKEDIN_FORM_STEP_CONTINUED' in next_result:
                            print("➡️ Form step continued")
                            submit_attempt_count = 0  # Progress made
                            continue
                        elif 'LINKEDIN_EASY_APPLY_CLICKED' in next_result:
                            print("🔄 Easy Apply clicked inside autopilot (modal may have restarted). Waiting for modal...")
                            await asyncio.sleep(random.uniform(3, 4))
                            continue
                        elif 'NO_ACTION' in next_result or 'MODAL_OPEN_NO_ACTION' in next_result:
                            print("⚠️ Autopilot stuck, checking for form errors...")
                            recovered = await self._attempt_form_recovery()
                            if recovered:
                                print("🛠️ Self-healing resolved form errors, resuming...")
                                continue
                                
                            print("⚠️ Exiting Autopilot...")
                            break
                        elif 'LINKEDIN_JOB_SKIPPED' in next_result:
                            print("⏭️ Job skipped, moving to next...")
                            break
                
                # Naukri Profile Update - Resume Headline Toggle
                # NOTE: Only run if NOT an Employment LWD task (same URL, different task)
                # NOTE: Skip if coming from a failed application attempt (error page)
                if ('profile' in current_url and 'naukri.com' in current_url and 
                    'Employment' not in self._task_description and 
                    'myapply' not in current_url and 'saveApply' not in current_url):
                    print("📝 Naukri Profile Page - Running headline update...")
                    try:
                        update_result = await self._page.evaluate("""() => {
                            // Find the Resume Headline section
                            const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
                            if (!headlineSection) return 'NO_HEADLINE_SECTION';
                            
                            // Find the edit icon
                            const editIcon = headlineSection.querySelector('span.edit.icon, span.icon.edit, [class*="edit"][class*="icon"]');
                            if (!editIcon) return 'NO_EDIT_ICON';
                            
                            editIcon.click();
                            return 'EDIT_CLICKED';
                        }""")
                        print(f"   📜 Step 1 - Edit click: {update_result}")
                        
                        if update_result == 'EDIT_CLICKED':
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for modal to fully open
                            
                            # Step 2: Remove fullstop (using exact selector from screenshot)
                            # Step 2: Remove fullstop using Keyboard (Backpsace)
                            remove_result = await self._page.evaluate("""() => {
                                const textarea = document.querySelector('#resumeHeadline, textarea[id="resumeHeadline"]');
                                if (!textarea) return 'NO_TEXTAREA';
                                if (textarea.value.endsWith('.')) return 'HAS_FULLSTOP';
                                return 'NO_FULLSTOP';
                            }""")
                            
                            if remove_result == 'HAS_FULLSTOP':
                                # Robust Method: Select All -> Rewrite without dot
                                text_val = await self._page.evaluate("document.querySelector('#resumeHeadline').value")
                                new_text = text_val.rstrip('.')
                                
                                textarea = self._page.locator('#resumeHeadline')
                                await textarea.focus()
                                await textarea.select_text()
                                await textarea.press('Backspace')
                                await asyncio.sleep(0.5)
                                await textarea.type(new_text)
                                remove_result = 'FULLSTOP_REMOVED'
                            
                            print(f"   📜 Step 2 - Remove fullstop: {remove_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))

                            # Step 3: Click Save button and verify
                            try:
                                save_result = await self._page.evaluate("""() => {
                                    const selectors = [
                                        '.form-actions button.btn-dark-ot',
                                        '.action.s12 button.btn-dark-ot',
                                        'button.btn-dark-ot[type="submit"]',
                                        'button[type="submit"]'
                                    ];
                                    for (let sel of selectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED';
                                        }
                                    }
                                    const allBtns = document.querySelectorAll('button');
                                    for (let btn of allBtns) {
                                        if ((btn.innerText || '').trim().toLowerCase() === 'save' && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED: text-match';
                                        }
                                    }
                                    return 'NO_SAVE_BUTTON';
                                }""")
                            except Exception as e:
                                print(f"      ⚠️ Save error: {e}")
                                save_result = 'NO_SAVE_BUTTON'
                            print(f"   📜 Step 3 - First save: {save_result}")
                            
                            await asyncio.sleep(2)
                            if save_result == 'NO_SAVE_BUTTON':
                                print("      ⚠️ No Save button found, retrying edit...")
                                self.state.task_complete = True
                                break
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for save to complete
                            
                            # Navigate back to profile page explicitly to ensure clean state
                            print("   🔄 Navigating back to profile page...")
                            try:
                                await self._page.goto('https://www.naukri.com/mnjuser/profile?id=&altresid', timeout=60000)
                                await self._page.wait_for_selector('#lazyResumeHead, .resumeHeadline', timeout=30000)
                            except Exception as e:
                                print(f"      ⚠️ Navigation error: {e}")
                            await asyncio.sleep(random.uniform(4, 8))
                            
                            # Step 4: Click edit again
                            edit2_result = await self._page.evaluate("""() => {
                                const headlineSection = document.querySelector('#lazyResumeHead, .resumeHeadline');
                                if (!headlineSection) return 'NO_HEADLINE_SECTION';
                                const editIcon = headlineSection.querySelector('span.edit.icon, span.icon.edit, [class*="edit"][class*="icon"]');
                                if (!editIcon) return 'NO_EDIT_ICON';
                                editIcon.click();
                                return 'EDIT_CLICKED_2';
                            }""")
                            print(f"   📜 Step 4 - Edit again: {edit2_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait for second modal to open
                            
                            # Step 5: Add fullstop back using keyboard
                            add_result = await self._page.evaluate("""() => {
                                const textarea = document.querySelector('#resumeHeadline, textarea[id="resumeHeadline"]');
                                if (!textarea) return 'NO_TEXTAREA';
                                if (!textarea.value.endsWith('.')) return 'NEEDS_FULLSTOP';
                                return 'ALREADY_HAS_FULLSTOP';
                            }""")
                            
                            if add_result == 'NEEDS_FULLSTOP':
                                # Robust Method: Select All -> Rewrite with dot
                                text_val = await self._page.evaluate("document.querySelector('#resumeHeadline').value")
                                if not text_val.endswith('.'):
                                    new_text = text_val + '.'
                                    
                                    textarea = self._page.locator('#resumeHeadline')
                                    await textarea.focus()
                                    await textarea.select_text()
                                    await textarea.press('Backspace')
                                    await asyncio.sleep(0.5)
                                    await textarea.type(new_text)
                                    add_result = 'FULLSTOP_ADDED'
                            
                            print(f"   📜 Step 5 - Add fullstop: {add_result}")
                            
                            await asyncio.sleep(random.uniform(4, 8))  # Wait before second Save
                            
                            # Step 6: Click Save button and verify
                            try:
                                save2_result = await self._page.evaluate("""() => {
                                    const selectors = [
                                        '.form-actions button.btn-dark-ot',
                                        '.action.s12 button.btn-dark-ot',
                                        'button.btn-dark-ot[type="submit"]',
                                        'button[type="submit"]'
                                    ];
                                    for (let sel of selectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED_2';
                                        }
                                    }
                                    const allBtns = document.querySelectorAll('button');
                                    for (let btn of allBtns) {
                                        if ((btn.innerText || '').trim().toLowerCase() === 'save' && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED_2: text-match';
                                        }
                                    }
                                    return 'NO_SAVE_BUTTON';
                                }""")
                            except Exception as e:
                                print(f"      ⚠️ Save error: {e}")
                                save2_result = 'NO_SAVE_BUTTON'
                            print(f"   📜 Step 6 - Second save: {save2_result}")
                            
                            await asyncio.sleep(1)
                            print("🎉 Profile headline updated successfully!")
                            self.state.task_complete = True
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Profile update error: {e}")
                
                # Naukri Employment LWD Update - Set Expected Last Working Day
                if 'profile' in current_url and 'naukri.com' in current_url and 'Employment' in self._task_description:
                    print("📅 Naukri Employment - Running LWD update...")
                    try:
                        # Step 1: Click the Employment section's edit icon
                        edit_result = await self._page.evaluate("""() => {
                            // More robust selectors for Employment section
                            // Try multiple ways to find the Employment section's edit icon
                            
                            // Method 1: Find by lazy load ID
                            let empSection = document.querySelector('#lazyEmployment');
                            
                            // Method 2: Find by data-plugin attribute
                            if (!empSection) {
                                empSection = document.querySelector('[data-plugin="lazyload"][id*="Employment"]');
                            }
                            
                            // Method 3: Find parent containing "Employment" heading
                            if (!empSection) {
                                const headings = document.querySelectorAll('h2, h3, .widgetHead');
                                for (let h of headings) {
                                    if (h.innerText && h.innerText.trim() === 'Employment') {
                                        empSection = h.closest('.widgetContainer, [class*="widget"], .card, section');
                                        break;
                                    }
                                }
                            }
                            
                            if (empSection) {
                                // Find edit icon - try multiple selectors
                                const editSelectors = [
                                    'span.edit.icon',
                                    '.edit.icon',
                                    '[class*="edit"][class*="icon"]',
                                    'span[class*="edit"]',
                                    '.editIcon'
                                ];
                                
                                for (let sel of editSelectors) {
                                    const editIcons = empSection.querySelectorAll(sel);
                                    if (editIcons.length > 0) {
                                        editIcons[0].click();
                                        return 'EDIT_CLICKED';
                                    }
                                }
                            }
                            
                            // Last resort: Find any edit icon near text "Software Engineer" or "Everbridge"
                            const allEditIcons = document.querySelectorAll('span.edit.icon, .edit.icon');
                            for (let icon of allEditIcons) {
                                const parent = icon.closest('.row, div[class*="item"], .card');
                                if (parent) {
                                    const text = parent.innerText || '';
                                    if (text.includes('Software Engineer') || text.includes('Everbridge')) {
                                        icon.click();
                                        return 'EDIT_CLICKED';
                                    }
                                }
                            }
                            
                            return 'NO_EMPLOYMENT_SECTION';
                        }""")
                        print(f"   📜 Step 1 - Employment edit: {edit_result}")
                        
                        if edit_result == 'EDIT_CLICKED':
                            await asyncio.sleep(random.uniform(3, 5))  # Wait for modal to open
                            
                            # Step 2: LWD date — parse explicit date from task prompt GOAL line
                            # Format: "GOAL: Update 'Expected Last Working Day' in the Employment section to July 3, 2026."
                            import re as _re
                            month_map = {
                                'january': '1', 'february': '2', 'march': '3', 'april': '4',
                                'may': '5', 'june': '6', 'july': '7', 'august': '8',
                                'september': '9', 'october': '10', 'november': '11', 'december': '12'
                            }
                            month_names_rev = {v: k.capitalize() for k, v in month_map.items()}
                            date_match = _re.search(
                                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d+),\s+(\d{4})',
                                self._task_description, _re.IGNORECASE
                            )
                            if date_match:
                                month_name = date_match.group(1)
                                month_num = month_map[month_name.lower()]
                                day_val = date_match.group(2)
                                year_val = date_match.group(3)
                                month_display = month_name[:3]
                            else:
                                # Fallback: use offset-based calculation
                                offset_match = _re.search(r'LWD\s*\+(\d+)', self._task_description)
                                days_offset = int(offset_match.group(1)) if offset_match else 15
                                lwd_date = datetime.now() + timedelta(days=days_offset)
                                year_val = str(lwd_date.year)
                                month_num_val = lwd_date.month
                                month_display = month_names_rev[month_num_val][:3]
                                day_val = str(lwd_date.day)
                                month_num = str(month_num_val)
                            
                            print(f"   📅 Setting LWD to: {day_val} {month_display} {year_val}")
                            
                            # Step 3: Set dropdowns using EXACT data-id selector WITH RETRY
                            async def set_single_dropdown(name, dropdown_id, data_prefix, option_value, max_retries=3):
                                print(f"   📅 Setting {name} to {option_value}...")
                                for attempt in range(max_retries):
                                    try:
                                        # 1. Click dropdown to open (with short timeout)
                                        await self._page.click(dropdown_id, timeout=5000)
                                        await asyncio.sleep(0.8)
                                        
                                        # 2. Try data-id selector first
                                        data_id = f"{data_prefix}{option_value}"
                                        result = await self._page.evaluate("""(dataId) => {
                                            const anchor = document.querySelector('a[data-id="' + dataId + '"]');
                                            if (anchor && anchor.offsetParent !== null) {
                                                anchor.scrollIntoView({block: 'center'});
                                                anchor.click();
                                                return 'SELECTED';
                                            }
                                            // Fallback: Find by text within open dropdown
                                            const openDropdown = document.querySelector('.dropdownList[style*="display: block"], .dropdownList:not([style*="display: none"])');
                                            if (openDropdown) {
                                                const items = openDropdown.querySelectorAll('li a, li');
                                                for (let item of items) {
                                                    if ((item.innerText || '').trim() === dataId.split('_')[1]) {
                                                        item.click();
                                                        return 'SELECTED_BY_TEXT';
                                                    }
                                                }
                                            }
                                            return 'NOT_FOUND: ' + dataId;
                                        }""", data_id)
                                        
                                        if 'SELECTED' in result:
                                            # 3. Close dropdown
                                            await asyncio.sleep(0.3)
                                            await self._page.evaluate("() => document.body.click()")
                                            await asyncio.sleep(0.3)
                                            return f"{result}: {option_value}"
                                        
                                        # If not found, close dropdown and retry
                                        await self._page.evaluate("() => document.body.click()")
                                        await asyncio.sleep(0.5)
                                        
                                    except Exception as e:
                                        if attempt < max_retries - 1:
                                            print(f"      ⚠️ Retry {attempt + 1}/{max_retries} for {name}: {str(e)[:50]}")
                                            await asyncio.sleep(1)
                                        else:
                                            return f"ERROR: {e}"
                                
                                return f"FAILED_AFTER_{max_retries}_ATTEMPTS: {option_value}"

                            # Execute with data-id prefixes (month uses NAME like lwdMonth_Feb)
                            year_result = await set_single_dropdown('Year', '#lwdYearFor', 'lwdYear_', year_val)
                            # Use month_num (e.g. '3') instead of text ('Mar') to match generic data-id patterns (like lwdDay_1)
                            month_result = await set_single_dropdown('Month', '#lwdMonthFor', 'lwdMonth_', month_num)
                            day_result = await set_single_dropdown('Day', '#lwdDayFor', 'lwdDay_', day_val)
                            
                            print(f"   📜 Step 2 - Dropdowns: Year={year_result}, Month={month_result}, Day={day_result}")
                            
                            print("   ⏳ Waiting 2s for state to settle before saving...")
                            await asyncio.sleep(2)
                            
                            # Step 4: Click Save button with multiple fallback attempts
                            save_result = 'NOT_ATTEMPTED'
                            for save_attempt in range(3):
                                save_result = await self._page.evaluate("""() => {
                                    // Try multiple selectors for save button
                                    const selectors = [
                                        '#submitEmployment',
                                        'button[type="submit"]',
                                        'button.btn-dark-ot', 
                                        'button.waves-effect'
                                    ];
                                    for (let sel of selectors) {
                                        const btn = document.querySelector(sel);
                                        if (btn && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED: ' + sel;
                                        }
                                    }
                                    // Fallback: find by text
                                    const allBtns = document.querySelectorAll('button');
                                    for (let btn of allBtns) {
                                        if ((btn.innerText || '').trim().toLowerCase() === 'save' && btn.offsetParent !== null) {
                                            btn.scrollIntoView({block: 'center'});
                                            btn.click();
                                            return 'SAVE_CLICKED: text-match';
                                        }
                                    }
                                    return 'NO_SAVE_BUTTON';
                                }""")
                                
                                if 'SAVE_CLICKED' in save_result:
                                    break
                                await asyncio.sleep(1)
                            
                            print(f"   📜 Step 3 - Save: {save_result}")
                            
                            if 'SAVE_CLICKED' in save_result:
                                await asyncio.sleep(3)
                                
                                for verify_attempt in range(3):
                                    modal_gone = await self._page.evaluate("""() => {
                                        return !document.querySelector('.modal-content, .edit-container, [class*="modal"]');
                                    }""")
                                    on_profile = 'mnjuser/profile' in (self._page.url or '')
                                    
                                    if modal_gone or on_profile:
                                        print(f"🎉 Employment LWD updated to {day_val} {month_display} {year_val}!")
                                        await asyncio.sleep(1)
                                        self.state.task_complete = True
                                        break
                                    
                                    print(f"      ⚠️ Save verify {verify_attempt + 1}/3: modal still open, clicking Save again...")
                                    await asyncio.sleep(1)
                                    save_retry = await self._page.evaluate("""() => {
                                        const selectors = [
                                            '#submitEmployment',
                                            'button[type="submit"]',
                                            'button.btn-dark-ot',
                                            'button.waves-effect'
                                        ];
                                        for (let sel of selectors) {
                                            const btn = document.querySelector(sel);
                                            if (btn && btn.offsetParent !== null) {
                                                btn.scrollIntoView({block: 'center'});
                                                btn.click();
                                                return 'SAVE_RECLICKED: ' + sel;
                                            }
                                        }
                                        const allBtns = document.querySelectorAll('button');
                                        for (let btn of allBtns) {
                                            if ((btn.innerText || '').trim().toLowerCase() === 'save' && btn.offsetParent !== null) {
                                                btn.scrollIntoView({block: 'center'});
                                                btn.click();
                                                return 'SAVE_RECLICKED: text-match';
                                            }
                                        }
                                        return 'NO_SAVE_BUTTON';
                                    }""")
                                    print(f"      📜 Save retry: {save_retry}")
                                    await asyncio.sleep(3)
                                else:
                                    print("      ⚠️ Save may not have taken effect after 3 retries")
                                    self.state.task_complete = True
                                    break
                            else:
                                print(f"      ⚠️ Could not find Save button: {save_result}")
                            
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Employment LWD update error: {e}")
                
                # Naukri Early Access Jobs - Share Interest
                if 'recommended-earjobs' in current_url and 'naukri.com' in current_url:
                    print("🚀 Naukri Early Access - Clicking Share Interest...")
                    try:
                        # Click the first "Share interest" button
                        share_result = await self._page.evaluate("""() => {
                            // Try specific selector first
                            const specificBtn = document.querySelector("body > main > div > div > div > section.lp__left-section-container > div > div:nth-child(1) > div > div.row7 > div > div.tf__content > button");
                            if (specificBtn && specificBtn.offsetParent !== null) {
                                specificBtn.click();
                                return 'SHARE_CLICKED_SPECIFIC';
                            }
                            
                            // Fallback: Find any "Share interest" button
                            const allBtns = document.querySelectorAll('button');
                            for (let btn of allBtns) {
                                if (btn.innerText && btn.innerText.toLowerCase().includes('share interest')) {
                                    if (btn.offsetParent !== null) {
                                        btn.click();
                                        return 'SHARE_CLICKED';
                                    }
                                }
                            }
                            return 'NO_SHARE_BUTTON';
                        }""")
                        print(f"   📜 Share Interest: {share_result}")
                        
                        if 'SHARE_CLICKED' in share_result:
                            await asyncio.sleep(random.uniform(2, 4))
                            
                            # Verify success
                            success = await self._page.evaluate("""() => {
                                // Check for success message
                                const successMsg = document.querySelector('.apply-status-header.green .apply-message, .apply-status-header .apply-message');
                                if (successMsg && successMsg.innerText.toLowerCase().includes('interest shared')) {
                                    return true;
                                }
                                // Also check for general success text on page
                                return document.body.innerText.includes('Interest shared successfully');
                            }""")
                            
                            if success:
                                print("🎉 Interest shared successfully!")
                            else:
                                print("✅ Share Interest clicked (success not verified)")
                            
                            self.state.task_complete = True
                            break
                        else:
                            print("⚠️ No Share Interest button found")
                            self.state.task_complete = True
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Early Access error: {e}")
                
                
                # Naukri: Handle CHECKBOX_CLICKED_NEED_MORE - continue selecting more checkboxes
                if 'CHECKBOX_CLICKED_NEED_MORE' in result and 'naukri.com' in current_url:
                    # Extract count info from result (e.g., "CHECKBOX_CLICKED_NEED_MORE: 2/5")
                    try:
                        count_info = result.split(': ')[1] if ': ' in result else ''
                        print(f"📋 Selected job {count_info}, continuing to select more...")
                    except:
                        print("📋 Checkbox selected, continuing to select more...")
                    await asyncio.sleep(random.uniform(0.5, 1))
                    continue  # Continue loop to select more checkboxes
                
                # Naukri: After checkbox, try Apply immediately (only for regular CHECKBOX_CLICKED, not NEED_MORE)
                if 'CHECKBOX_CLICKED' in result and 'NEED_MORE' not in result and 'naukri.com' in current_url:
                    print("✅ Checkbox clicked, trying Apply...")
                    await asyncio.sleep(random.uniform(4, 8))
                    # Try to click apply immediately with robust logic and 2s monitoring
                    # NOTE: Using regular function expression for better Playwright compatibility
                    apply_result = await self._page.evaluate("""function() {
                        const applyBtn = document.querySelector('.multi-apply-button');
                        if (applyBtn && applyBtn.offsetParent !== null) {
                            applyBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
                            // NOTE: await removed - Python handles delays between evaluate calls

                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));

                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {
                                // NOTE: await new Promise removed - Python handles delays between evaluate calls
                                // Target the exact structure found in DOM inspection
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {
                                        // Dismiss if close button exists
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback check
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            return 'APPLY_CLICKED';
                        }
                        return 'NO_APPLY_BUTTON';
                    }""")
                    
                    # Playwright fallback if JS click didn't trigger modal (and no error detected)
                    if 'NO_APPLY_BUTTON' in apply_result or (apply_result == 'APPLY_CLICKED' and not await self._page.is_visible('.chatbot_DrawerContentWrapper')):
                        print("⚠️ JS click failed or button not found, trying Playwright native click fallback...")
                        try:
                            await self._page.click('.multi-apply-button', timeout=3000)
                            apply_result = 'APPLY_CLICKED_FALLBACK'
                        except Exception as e:
                            print(f"⚠️ Playwright fallback click also failed: {e}")
                    
                    print(f"   📜 Apply result: {apply_result}")
                    
                    if 'APPLY_CLICKED' in apply_result:
                        print("⏳ Waiting for Naukri chatbot...")
                        await asyncio.sleep(random.uniform(4, 8))
                        chatbot_done = await self._handle_chatbot_loop()
                        if chatbot_done == 'CONTINUE':
                            # MCC popup detected, continue main loop for scripted fallback
                            continue
                        elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                            # Error popup detected - set rate limit and exit
                            self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                            print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                        elif chatbot_done:
                            print("🎉 Naukri Application Completed!")
                            self.state.task_complete = True
                            break
                        else:
                            # Chatbot loop exhausted - navigate back to recommended jobs to try different jobs
                            print("🔄 Chatbot exhausted - navigating back to recommended jobs...")
                            try:
                                await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
                                await asyncio.sleep(random.uniform(4, 6))
                                continue
                            except Exception as e:
                                print(f"   ⚠️ Navigation error: {e}")
                
                # Naukri Chatbot handling (for direct APPLY_CLICKED)
                if 'APPLY_CLICKED' in result and 'LINKEDIN' not in result and 'naukri.com' in current_url:
                    print("⏳ Waiting for Naukri chatbot...")
                    await asyncio.sleep(random.uniform(4, 8))
                    chatbot_done = await self._handle_chatbot_loop()
                    if chatbot_done == 'CONTINUE':
                        continue
                    elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                        # Error popup detected - set rate limit and exit
                        self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                        print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                        self.state.task_complete = True
                        break
                    elif chatbot_done:
                        # Check if this was a partial application (less than target)
                        if 'PARTIAL' in result:
                            # Extract how many were applied (e.g., "APPLY_CLICKED_PARTIAL: 2/5" -> 2)
                            try:
                                applied_count = int(result.split(': ')[1].split('/')[0])
                                target_count = int(result.split('/')[1])
                                print(f"🔄 Applied to {applied_count}/{target_count} jobs. Looking for more on next section...")
                            except:
                                print("🔄 Partial application. Looking for more jobs on next section...")
                            
                            # Navigate to next tab to find more jobs
                            await asyncio.sleep(2)
                            next_tab_result = await self._page.evaluate("""() => {
                                // Tab IDs in order: profile -> apply -> preference -> similar_jobs -> top_candidate
                                const tabIds = ['profile', 'apply', 'preference', 'similar_jobs', 'top_candidate'];
                                const tabNames = ['Profile', 'Applies', 'Preferences', 'You might like', 'Top Candidate'];
                                
                                // Find which tab is currently active
                                let currentTabIndex = -1;
                                for (let i = 0; i < tabIds.length; i++) {
                                    const wrapper = document.querySelector('#' + tabIds[i]);
                                    if (wrapper) {
                                        const activeItem = wrapper.querySelector('.tab-list-active');
                                        if (activeItem) {
                                            currentTabIndex = i;
                                            break;
                                        }
                                    }
                                }
                                
                                // Try to click the next tab
                                const nextTabIndex = currentTabIndex + 1;
                                if (nextTabIndex < tabIds.length) {
                                    const nextTabId = tabIds[nextTabIndex];
                                    const nextTabName = tabNames[nextTabIndex];
                                    
                                    const nextWrapper = document.querySelector('#' + nextTabId);
                                    if (nextWrapper) {
                                        const tabItem = nextWrapper.querySelector('.tab-list-item');
                                        if (tabItem && tabItem.offsetParent !== null) {
                                            tabItem.click();
                                            return 'TAB_CLICKED: ' + nextTabName;
                                        }
                                        nextWrapper.click();
                                        return 'TAB_CLICKED: ' + nextTabName;
                                    }
                                }
                                
                                return 'NO_MORE_TABS';
                            }""")
                            
                            if 'TAB_CLICKED' in next_tab_result:
                                tab_name = next_tab_result.split(': ')[1] if ': ' in next_tab_result else 'Unknown'
                                print(f"📑 Switched to tab: {tab_name} to find more jobs")
                                await asyncio.sleep(random.uniform(4, 8))
                                continue  # Continue loop to find and apply to more jobs
                            else:
                                print("📭 No more tabs available. Finishing with current applications.")
                        
                        print("🎉 Naukri Application Completed!")
                        self.state.task_complete = True
                        break
                    else:
                        # Chatbot loop exhausted - navigate back to recommended jobs to try different jobs
                        print("🔄 Chatbot exhausted - navigating back to recommended jobs...")
                        try:
                            await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
                            await asyncio.sleep(random.uniform(4, 6))
                            continue
                        except Exception as e:
                            print(f"   ⚠️ Navigation error: {e}")
                
                # Naukri: Chatbot detected by scripted fallback - trigger chatbot loop
                if result == 'CHATBOT_DETECTED' and 'naukri.com' in current_url:
                    chatbot_done = await self._handle_chatbot_loop()
                    if chatbot_done == 'CONTINUE':
                        continue  # MCC popup, let scripted fallback handle it
                    elif chatbot_done:
                        print("🎉 Naukri Application Completed!")
                        self.state.task_complete = True
                        break
                
                # Naukri: Tab clicked - wait for page to load new jobs
                if 'TAB_CLICKED' in result and 'naukri.com' in current_url:
                    tab_name = result.split(': ')[1] if ': ' in result else 'Unknown'
                    if 'FOR_MORE' in result:
                        print(f"📑 Only 1 job in current section - switching to tab: {tab_name} to select 2 jobs")
                    else:
                        print(f"📑 Switched to tab: {tab_name}")
                    await asyncio.sleep(random.uniform(4, 8))  # Wait for new jobs to load
                    continue  # Continue to try finding checkboxes on new tab
                
                # Naukri: No more tabs to check
                if 'NO_MORE_TABS_NAUKRI' in result:
                    print("📭 All Naukri tabs checked. No more jobs with checkboxes.")
                    self.state.task_complete = True
                    break
                
                # Handle NO_MORE_JOBS
                if 'NO_MORE_JOBS' in result:
                    print(f"   ℹ️ Result: {result}")  # Debug log
                    if 'NO_CARDS' in result:
                        if 'linkedin.com' in current_url:
                            if not self._linkedin_scroll_attempted:
                                print("❌ No job cards found on LinkedIn - trying to scroll down first...")
                                self._linkedin_scroll_attempted = True
                                try:
                                    # Scroll the job list to load more jobs
                                    await self._page.evaluate("""() => {
                                        const sidebar = document.querySelector('.scaffold-layout__list') || 
                                                       document.querySelector('.jobs-search-results-list');
                                        if (sidebar) {
                                            sidebar.scrollTop += 800;
                                            return 'Scrolled job list';
                                        }
                                        window.scrollTo(0, window.scrollY + 800);
                                        return 'Scrolled window';
                                    }""")
                                    await asyncio.sleep(random.uniform(3, 5))
                                    continue  # Continue loop to try again after scroll
                                except Exception as e:
                                    print(f"⚠️  Scroll failed: {e}")
                            else:
                                print("❌ Still no job cards after scroll - refreshing page...")
                                self._linkedin_scroll_attempted = False
                                try:
                                    await self._page.reload(wait_until='domcontentloaded', timeout=15000)
                                    await asyncio.sleep(random.uniform(5, 8))
                                    continue  # Continue loop to try again after refresh
                                except Exception as e:
                                    print(f"⚠️  Refresh failed: {e}")
                        else:
                            print("❌ No job cards found on page! Check selectors.")
                    else:
                        print("📭 No more jobs to apply. Task complete.")
                    self.state.task_complete = True
                    break
                
                # Instahyre: Show Results clicked - continue to View/Apply phase
                if 'INSTAHYRE_SHOW_RESULTS_CLICKED' in result:
                    print("🔍 Instahyre search configured, now looking for jobs to apply...")
                    await asyncio.sleep(random.uniform(3, 5))  # Wait for results to load
                    continue  # Continue to View/Apply loop
                
                # Instahyre: Application submitted
                if 'INSTAHYRE_APPLY_CLICKED' in result:
                    if not hasattr(self, '_instahyre_apply_count'):
                        self._instahyre_apply_count = 0
                    self._instahyre_apply_count += 1
                    print(f"✅ Instahyre Application {self._instahyre_apply_count}/10 submitted!")
                    
                    if self._instahyre_apply_count >= 10:
                        print("🎉 Completed 10 Instahyre applications!")
                        self._instahyre_apply_count = 0  # Reset for next cycle
                        self.state.task_complete = True
                        break
                    
                    await asyncio.sleep(random.uniform(2, 4))  # Wait for modal to close
                    continue  # Continue to next application
                
                # Instahyre: View clicked - wait for modal
                if 'INSTAHYRE_VIEW_CLICKED' in result:
                    print("👁️ Viewing job details, looking for Apply button...")
                    await asyncio.sleep(random.uniform(2, 3))  # Wait for modal to open
                    continue
                
                # Instahyre: Modal closed (post-apply or blocked modal)
                if 'INSTAHYRE_MODAL_CLOSED' in result:
                    print("   📜 Instahyre: Modal closed, continuing...")
                    await asyncio.sleep(random.uniform(1, 2))
                    continue
                
                # Instahyre: Modal closed after success
                if 'INSTAHYRE_MODAL_CLOSED_SUCCESS' in result:
                    print("✅ Application confirmed, looking for next job...")
                    await asyncio.sleep(random.uniform(1, 2))
                    continue
                
                # Instahyre: No more jobs
                if 'INSTAHYRE_NO_MORE_JOBS' in result:
                    applied_count = getattr(self, '_instahyre_apply_count', 0)
                    print(f"📭 No more Instahyre jobs found. Applied to {applied_count} jobs.")
                    self._instahyre_apply_count = 0
                    self.state.task_complete = True
                    break
                
                # Instahyre: All visible jobs already applied — scrolling for more
                if 'INSTAHYRE_ALL_APPLIED_SCROLLING' in result:
                    print("   📜 All visible jobs already applied — scrolling for more...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
                # Instahyre: Other actions (scrolling, etc.)
                if 'INSTAHYRE_' in result and 'instahyre.com' in current_url:
                    print(f"   📜 Instahyre: {result}")
                    self._instahyre_no_action_count = 0  # Reset on any action
                    await asyncio.sleep(random.uniform(1, 2))
                    continue
                
                # Instahyre: NO_ACTION loop detection — stop task if no jobs found
                if result == 'NO_ACTION' and 'instahyre.com' in current_url:
                    self._instahyre_no_action_count += 1
                    print(f"   ⚠️ Instahyre NO_ACTION ({self._instahyre_no_action_count}/8)")
                    if self._instahyre_no_action_count >= 8:
                        applied = getattr(self, '_instahyre_apply_count', 0)
                        print(f"📭 Instahyre: No jobs available after 8 attempts. Applied to {applied} jobs. Ending task.")
                        self._instahyre_apply_count = 0
                        self.state.task_complete = True
                        break
                    continue
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                self.state.errors.append(str(e))
                self.metrics['errors_encountered'] += 1
                if len(self.state.errors) > 5:
                    print("🚨 Too many errors. Stopping.")
                    break
        
        # Save metrics at end of task
        # Success requires either applications submitted OR an explicit non-application task completion
        is_non_app_task = self.state.task_complete and self.metrics['applications_submitted'] == 0
        self.metrics['success'] = self.state.task_complete and (
            self.metrics['applications_submitted'] > 0 or is_non_app_task
        )
        self._save_metrics()
        
        return self.state.task_complete

    async def _handle_chatbot_loop(self) -> "bool | str":
        """Handle Naukri chatbot questionnaire. Returns True if done, 'CONTINUE' for MCC popup, False on failure."""
        # Use merged patterns from JSON config + legacy dict
        patterns_for_js = self._get_patterns_for_js()
        # Extract the flat answers for backward compatibility + with_defaults for input type support
        patterns_json = json.dumps(patterns_for_js.get('answers', {}))
        patterns_with_defaults_json = json.dumps(patterns_for_js.get('with_defaults', {}))
        max_iterations = 30
        previous_questions = []
        same_question_count = 0
        consecutive_waiting_count = 0  # Track consecutive CHATBOT_WAITING states
        last_action_was_answer = False  # Track if we just answered a question
        
        for iteration in range(max_iterations):
            await asyncio.sleep(random.uniform(2, 3.5))
            
            result = await self._page.evaluate(f"""async () => {{
                // Flat answers for all logic
                const KNOWN_PATTERNS = {patterns_json};
                // Full objects with input_type_defaults per pattern
                const KNOWN_PATTERNS_WITH_DEFAULTS = {patterns_with_defaults_json};
                
                // Helper: detect the input type present on the page
                const detectInputType = (chatLayer) => {{
                    if (!chatLayer) return 'text';
                    if (chatLayer.querySelector('select')) return 'select';
                    if (chatLayer.querySelectorAll('input[type="radio"]').length > 0) return 'radio';
                    if (chatLayer.querySelectorAll('input[type="checkbox"]').length > 0) return 'checkbox';
                    if (chatLayer.querySelector('input[type="date"]')) return 'date';
                    const optBtns = chatLayer.querySelectorAll('.chatbot_OptionContainer button, [class*="option"] button');
                    if (optBtns.length > 0) return 'button';
                    return 'text';
                }};
                
                // Input-type-aware fuzzy match — returns the best answer for the detected input type
                const fuzzyMatch = (question, chatLayer) => {{
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    let bestMatch = null;
                    let bestKeyLen = 0;
                    const detectedType = detectInputType(chatLayer);
                    
                    const sortedPatterns = Object.entries(KNOWN_PATTERNS).sort((a, b) => b[0].length - a[0].length);
                    
                    for (const [key, val] of sortedPatterns) {{
                        const keyLower = key.toLowerCase();
                        if (qLower === keyLower) {{
                            return getAnswerForPattern(key, detectedType, val);
                        }}
                        if (qLower.includes(keyLower) && key.length > bestKeyLen) {{
                            if (keyLower === 'years' && (qLower.includes('salary') || qLower.includes('ctc') || qLower.includes('pay') || qLower.includes('inr'))) {{
                                continue;
                            }}
                            const patternData = KNOWN_PATTERNS_WITH_DEFAULTS[key];
                            if (patternData && patternData.requires_exact_match) {{
                                continue;
                            }}
                            bestMatch = key;
                            bestKeyLen = key.length;
                        }}
                    }}
                    return bestMatch ? getAnswerForPattern(bestMatch, detectedType, KNOWN_PATTERNS[bestMatch]) : null;
                }};
                
                // Get type-aware answer for a matched pattern
                const getAnswerForPattern = (patternKey, inputType, defaultVal) => {{
                    const data = KNOWN_PATTERNS_WITH_DEFAULTS[patternKey];
                    if (!data) return defaultVal;
                    const typeDefaults = data.input_type_defaults || {{}};
                    // Use input_type_defaults if present for this type
                    if (typeDefaults[inputType]) {{
                        return typeDefaults[inputType];
                    }}
                    // Fallbacks for radio/checkbox when default is long text
                    if (inputType === 'radio' || inputType === 'button') {{
                        if (typeDefaults.radio) return typeDefaults.radio;
                        if (typeDefaults.yes_no) return typeDefaults.yes_no;
                        if (typeDefaults.checkbox) return typeDefaults.checkbox;
                        // Normalize Yes/No from long answer
                        const answerLower = defaultVal.toLowerCase();
                        if (answerLower.includes('yes') && !answerLower.includes('no')) return 'Yes';
                        if (answerLower.includes('no')) return 'No';
                    }}
                    if (inputType === 'checkbox') {{
                        if (typeDefaults.checkbox) return typeDefaults.checkbox;
                        if (typeDefaults.yes_no) return typeDefaults.yes_no;
                    }}
                    if (inputType === 'select' && typeDefaults.select) {{
                        return typeDefaults.select;
                    }}
                    return defaultVal;
                }};
                
                // LinkedIn-specific overrides for the chatbot loop
                if (window.location.hostname.includes('linkedin')) {{
                    Object.keys(KNOWN_PATTERNS).forEach(k => {{
                        const v = KNOWN_PATTERNS[k];
                        if (v === '4 Years') KNOWN_PATTERNS[k] = '4';
                        else if (v === '2 Years') KNOWN_PATTERNS[k] = '2';
                    }});
                    
                    // Category-based overrides for notice period:
                    Object.keys(KNOWN_PATTERNS).forEach(k => {{
                        const defaultObj = KNOWN_PATTERNS_WITH_DEFAULTS[k];
                        if (defaultObj && defaultObj.category === 'notice_period') {{
                            const v = KNOWN_PATTERNS[k];
                            if (v && typeof v === 'string') {{
                                if (v !== 'Yes' && v !== 'No' && v !== 'Serving Notice Period') {{
                                    const match = v.match(/(\d+)/);
                                    KNOWN_PATTERNS[k] = match ? match[1] : '15';
                                    
                                    if (defaultObj.input_type_defaults) {{
                                        Object.keys(defaultObj.input_type_defaults).forEach(type => {{
                                            const typeVal = defaultObj.input_type_defaults[type];
                                            if (typeof typeVal === 'string' && typeVal.includes('days')) {{
                                                const typeMatch = typeVal.match(/(\d+)/);
                                                defaultObj.input_type_defaults[type] = typeMatch ? typeMatch[1] : '15';
                                            }}
                                        }});
                                    }}
                                }}
                            }}
                        }}
                    }});
                    
                    const noticeKeys = [
                        'notice period', 'what is your notice period', 'notice period in days', 'notice period days',
                        'serving notice', 'serving notice period', 'are you serving notice', 'currently serving notice',
                        'if serving lwd', 'if serving lwd. looking for immediate joiners only',
                        'if serving lwd, looking for immediate joiners only', 'serving lwd',
                        'if serving notice period immediate joiner', 'last working day'
                    ];
                    noticeKeys.forEach(k => {{
                        const v = KNOWN_PATTERNS[k];
                        if (v && v !== 'Yes' && v !== 'No' && v !== 'Serving Notice Period') {{
                            const match = v.match(/(\d+)/);
                            KNOWN_PATTERNS[k] = match ? match[1] : '15';
                        }} else if (KNOWN_PATTERNS[k]) {{
                            KNOWN_PATTERNS[k] = 'Serving Notice Period';
                        }}
                    }});
                    
                    // Broader override: any pattern whose VALUE is "Yes" but key contains notice/serving/lwd
                    Object.keys(KNOWN_PATTERNS).forEach(k => {{
                        const kLower = k.toLowerCase();
                        if ((kLower.includes('notice') || kLower.includes('serving') || kLower.includes('lwd')) && 
                            KNOWN_PATTERNS[k] === 'Yes') {{
                            KNOWN_PATTERNS[k] = 'Serving Notice Period';
                        }}
                    }});
                }}
                const snackBody = document.querySelector('.ss-snackbar-body');
                if (snackBody && snackBody.offsetParent !== null) {{
                    const snackText = snackBody.innerText.toLowerCase();
                    if (snackText.includes('error') || snackText.includes('limit') || snackText.includes('reached') || snackText.includes('something went wrong')) {{
                        const closeBtn = document.querySelector('button.ss-close');
                        if (closeBtn) closeBtn.click();
                        return 'NAUKRI_RATE_LIMITED: Error popup detected at loop start';
                    }}
                }}
                
                const mccPopup = document.querySelector('.mcc-popup, [class*="update-popup"], [class*="confirmation-modal"]');
                if (mccPopup && mccPopup.offsetParent !== null) {{
                    return 'MCC_POPUP_DETECTED';
                }}
                
                const successIndicators = [
                    document.querySelector('.chatbot_SuccessMsg'),
                    document.querySelector('[class*="success"]'),
                    document.body.innerText.includes('Application submitted'),
                    document.body.innerText.includes('Successfully applied')
                ];
                if (successIndicators.some(Boolean)) {{
                    return 'CHATBOT_COMPLETE';
                }}
                
                let chatLayer = document.querySelector('.chatbot_DrawerContentWrapper');
                if (!chatLayer) {{
                    chatLayer = document.querySelector('[class*="drawer"], [class*="modal"], [role="dialog"]');
                }}
                const isVisible = (el) => {{
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && rect.top >= 0;
                }};
                if (!chatLayer || !isVisible(chatLayer)) {{
                    if (document.body.innerText.includes('applied')) {{
                        return 'CHATBOT_COMPLETE';
                    }}
                    return 'NO_CHATBOT';
                }}
                
                const qEls = chatLayer.querySelectorAll('.chatbot_QuestionContainer, .botMsg, [class*="question"]');
                let questionEl = qEls.length > 0 ? qEls[qEls.length - 1] : null;
                let qText = '';
                if (questionEl) {{
                    qText = questionEl.innerText || '';
                }} else {{
                    qText = chatLayer.innerText || '';
                }}
                
                const qLower = qText.toLowerCase();
                
                // Special pre-match: LWD date questions — must answer with a date, not years
                const isLwdDateQ = qLower.includes('when is your lwd') ||
                                   qLower.includes('what is your lwd') ||
                                   qLower.includes('lwd date') ||
                                   qLower.includes('your lwd') ||
                                   qLower.includes('your ldw') ||
                                   qLower.includes('last working day') ||
                                   qLower.includes('ldw') ||
                                   qLower.includes('lwd');
                let answer;
                if (isLwdDateQ) {{
                    const lwd = new Date();
                    lwd.setDate(lwd.getDate() + 15);
                    const dd = String(lwd.getDate()).padStart(2, '0');
                    const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][lwd.getMonth()];
                    const yyyy = lwd.getFullYear();
                    answer = dd + ' ' + mon + ' ' + yyyy;
                    console.log('Chatbot Debug - LWD date question detected, answering:', answer);
                }} else if (qLower.includes('date of birth') || qLower.includes('dob') || qLower.includes('birth date')) {{
                    answer = '17/12/2000';
                    console.log('Chatbot Debug - DOB question detected, answering:', answer);
                }} else {{
                    answer = fuzzyMatch(qText, chatLayer) || '1';
                    
                    // Yes/no question detection — override numeric/empty fallbacks
                    // Questions like "Have you worked with X?" or "Do you have experience in X?"
                    // should answer "Yes", not "1" or "4" (from generic "experience" pattern)
                    const isYesNoQuestion = (
                        qLower.startsWith('have you ') ||
                        qLower.startsWith('do you ') ||
                        qLower.startsWith('are you ') ||
                        qLower.startsWith('can you ') ||
                        qLower.startsWith('will you ') ||
                        qLower.startsWith('did you ') ||
                        qLower.startsWith('have u ') ||
                        qLower.startsWith('r u ') ||
                        qLower.startsWith('apply only ') ||
                        qLower.includes('willing') ||
                        qLower.includes('comfortable') ||
                        qLower.includes('localite') ||
                        qLower.includes('relocate') ||
                        qLower.includes('relocation') ||
                        qLower.includes('open to')
                    );
                    
                    // Exclude questions that are genuinely asking for years/numbers
                    // e.g., "Do you have 4+ years of experience?" should NOT be overridden
                    const isNumericQuestion = (
                        qLower.includes('how many years') ||
                        qLower.includes('years of experience') ||
                        qLower.includes('how much') ||
                        qLower.includes('rate your') ||
                        qLower.includes('on a scale') ||
                        qLower.includes('proficiency') ||
                        qLower.includes('salary') ||
                        qLower.includes('ctc')
                    );
                    
                    if (isYesNoQuestion && !isNumericQuestion) {{
                        // Override if answer is null, "1", starts with a digit (numeric result
                        // from generic "experience" pattern matching "Do you have experience..."),
                        // OR is a non-yes/no answer that's not a known exception
                        const isNumericResult = answer && /^\d/.test(answer.trim());
                        const answerLowerYN = answer ? answer.toLowerCase().trim() : '';
                        const hasYesOrNo = answerLowerYN.includes('yes') || answerLowerYN.includes('no');
                        const knownExceptions = ['serving notice', 'male', 'female', 'single', 'married', 'sde-', 'software developer'];
                        const isException = knownExceptions.some(e => answerLowerYN.includes(e));
                        
                        if (!answer || answer === '1' || isNumericResult || (!hasYesOrNo && !isException)) {{
                            // Check negative indicators for No vs Yes
                            const negativeIndicators = ['sponsorship', 'visa', 'referral', 'referred',
                                'conflict of interest', 'relative', 'family member', 'criminal', 'felony',
                                'convict', 'disability', 'previously employed', 'ever been employed',
                                'currently employed', 'worked at', 'worked for', 'worked with', 'backlog', 'backlogs'];
                            const isNegative = negativeIndicators.some(p => qLower.includes(p));
                            answer = isNegative ? 'No' : 'Yes';
                            console.log('Chatbot Debug - Yes/no override, answer:', answer, '| was:', answerLowerYN.substring(0, 50));
                        }}
                    }}
                }}
                
                // Special handling for Naukri salary questions - use full INR values
                const isNaukri = window.location.hostname.includes('naukri');
                const isSalaryQuestion = qText.toLowerCase().includes('salary') ||
                    qText.toLowerCase().includes('ctc') ||
                    qText.toLowerCase().includes('compensation') ||
                    qText.toLowerCase().includes('pay');

                if (isNaukri && isSalaryQuestion) {{
                    const isCurrentSalary = qText.toLowerCase().includes('current') ||
                        qText.toLowerCase().includes('cctc') ||
                        qText.toLowerCase().includes('present');
                    // Use full INR values for Naukri
                    answer = isCurrentSalary ? '2300000' : '3000000';
                }}
                
                // DEBUG: Log what we detected
                console.log('Chatbot Debug - Question:', qText.substring(0, 100), '| Answer:', answer);
                
                // DEBUG: Log all inputs found in chatLayer
                if (chatLayer) {{
                    const debugInputs = chatLayer.querySelectorAll('input:not([type="hidden"]), textarea');
                    console.log('Chatbot Debug - Inputs in chatLayer:', debugInputs.length);
                    debugInputs.forEach((inp, i) => {{
                        console.log('  Input[' + i + ']:', inp.type, inp.placeholder || inp.name || inp.id, 'visible:', inp.offsetParent !== null);
                    }});
                }}
                
                // STEP 1: DETECT all available input types on the page
                const hasSelect = chatLayer.querySelector('select') !== null;
                const hasRadio = chatLayer.querySelectorAll('input[type="radio"]').length > 0;
                const hasCheckbox = chatLayer.querySelectorAll('input[type="checkbox"]').length > 0;
                let textInput = chatLayer.querySelector('input[type="text"]:not([type="hidden"]):not([type="file"]), textarea');
                let contentEditableEarly = chatLayer.querySelector('div[contenteditable="true"]') || 
                                          document.querySelector('div[contenteditable="true"]');
                
                console.log('Chatbot Debug - Available inputs:', {{select: hasSelect, radio: hasRadio, checkbox: hasCheckbox, text: !!textInput, editable: !!contentEditableEarly}});
                
                // EARLY COMPLETION PHRASE CHECK: If the question text itself contains
                // a completion phrase, the application was submitted successfully
                if (qText) {{
                    const qLowerForCompletion = qText.toLowerCase();
                    const completionPhrases = [
                        'thank you for your response',
                        'thank you for your responses',
                        'thank you for applying',
                        'thank you for your interest',
                        'application has been submitted',
                        'we have received your application',
                        'your application has been received',
                        'your response has been recorded',
                        'thanks for your response'
                    ];
                    if (completionPhrases.some(p => qLowerForCompletion.includes(p))) {{
                        console.log('Chatbot Debug - Completion phrase detected:', qText.substring(0, 100));
                        return 'CHATBOT_COMPLETE';
                    }}
                }}
                
                // CHECK FOR COMPLETION: If chatLayer is visible but has no inputs and no real question,
                // the application was likely submitted successfully
                const hasAnyInput = hasSelect || hasRadio || hasCheckbox || !!textInput || !!contentEditableEarly;
                const isShortQuestion = qText && qText.trim().length <= 3; // "2", "4" etc are not real questions
                const hasRealQuestion = qText && qText.trim().length > 10 && qText.includes('?');
                
                if (!hasAnyInput && chatLayer && isVisible(chatLayer)) {{
                    // Check for success indicators first
                    const hasSuccessMsg = document.querySelector('.chatbot_SuccessMsg') !== null ||
                                         document.querySelector('[class*="success"]') !== null ||
                                         document.body.innerText.includes('Application submitted') ||
                                         document.body.innerText.includes('Successfully applied') ||
                                         document.body.innerText.includes('applied successfully');
                    
                    // If no inputs and either success message OR no real question, consider it complete
                    if (hasSuccessMsg || !hasRealQuestion || isShortQuestion) {{
                        console.log('Chatbot Debug - Completion detected: No inputs, success indicators or short question');
                        return 'CHATBOT_COMPLETE';
                    }}
                }}
                
                // STEP 1.5: DETECT option buttons EARLY (must be checked before text inputs)
                // Broad selector: chatbot option containers + any visible standalone buttons
                // in the chat drawer (excluding Save/Send/Upload controls)
                const optBtnSelector = '.chatbot_OptionContainer button, [class*="option"] button, ' +
                    '.chatbot_DrawerContentWrapper button, .chatbot_Drawer button, ' +
                    'li.botItem button, [class*="chatbot"] button, ' +
                    '.chatbot_Chip, .chatbot_Chips div.chipItem, [class*="Chip"] div';
                let optBtns = chatLayer ? Array.from(chatLayer.querySelectorAll(optBtnSelector)) : [];
                // Filter out Save/Send/Upload buttons
                optBtns = optBtns.filter(function(btn) {{
                    const t = (btn.innerText || '').trim().toLowerCase();
                    const cls = (btn.className || '').toLowerCase();
                    if (t === 'save' || t === 'send' || t === 'submit' || t === 'next') return false;
                    if (cls.includes('sendmsg') || cls.includes('upload') || cls.includes('file')) return false;
                    if (btn.offsetParent === null) return false;
                    return true;
                }});
                const hasOptionBtns = optBtns.length > 0;
                
                // SKIP certain tool/skill-specific experience questions that don't match our profile
                // Must be checked AFTER optBtns are populated so we can click the Skip button
                const skipQuestionPatterns = [
                    'cypress', 'playwright', 'selenium', 'appium', 'test automation',
                    'cucumber', 'bdd', 'tdd', 'katalon', 'robot framework'
                ];
                let shouldSkipQ = false;
                for (const skipPat of skipQuestionPatterns) {{
                    if (qLower.includes(skipPat)) {{
                        shouldSkipQ = true;
                        break;
                    }}
                }}
                if (shouldSkipQ) {{
                    console.log('Chatbot Debug - Skipping tool-specific question:', qText.substring(0, 80));
                    const skipOptBtn = optBtns.find(b => (b.innerText || '').toLowerCase().includes('skip'));
                    if (skipOptBtn) {{
                        skipOptBtn.click();
                        return 'CHATBOT_SKIPPED_QUESTION: ' + qText.slice(0, 50);
                    }}
                    const allSkipEls = chatLayer.querySelectorAll('button, span, div, label, a');
                    for (const skEl of allSkipEls) {{
                        const skText = (skEl.innerText || '').toLowerCase().trim();
                        if (skText === 'skip' || skText === 'skip this question' || skText === 'skip question') {{
                            if (skEl.offsetParent !== null) {{
                                skEl.click();
                                return 'CHATBOT_SKIPPED_QUESTION: ' + qText.slice(0, 50);
                            }}
                        }}
                    }}
                    return 'CHATBOT_SKIP_UNANSWERABLE: ' + qText.slice(0, 50);
                }}
                
                // STEP 2: USE the first available input type (sequential detection)
                // Order: Option Buttons -> Dropdown -> Radio -> Checkbox -> Text Input -> Contenteditable
                
                // HANDLE OPTION BUTTONS (highest priority — before text inputs to prevent typing button labels)
                if (hasOptionBtns) {{
                    console.log('Chatbot Debug - Found', optBtns.length, 'option buttons');
                    
                    const answerLower = answer.toLowerCase();
                    let clickedBtn = null;
                    
                    // Try to match answer to button text
                    for (const btn of optBtns) {{
                        const btnText = btn.innerText.trim().toLowerCase();
                        console.log('Chatbot Debug - Option button:', btnText);
                        
                        // Exact match
                        if (btnText === answerLower) {{
                            btn.click();
                            clickedBtn = btn;
                            console.log('Chatbot Debug - Clicked exact match option:', btn.innerText.trim());
                            break;
                        }}
                        // Partial match (answer contains button text or vice versa)
                        if (btnText.includes(answerLower) || answerLower.includes(btnText)) {{
                            btn.click();
                            clickedBtn = btn;
                            console.log('Chatbot Debug - Clicked partial match option:', btn.innerText.trim());
                            break;
                        }}
                        // Yes/No matching
                        if ((answerLower === 'yes' || answerLower.includes('yes')) && btnText === 'yes') {{
                            btn.click();
                            clickedBtn = btn;
                            console.log('Chatbot Debug - Clicked Yes option');
                            break;
                        }}
                        if ((answerLower === 'no' || answerLower.startsWith('no')) && btnText === 'no') {{
                            btn.click();
                            clickedBtn = btn;
                            console.log('Chatbot Debug - Clicked No option');
                            break;
                        }}
                    }}
                    
                    // If no match found, check if a contenteditable input exists before falling back to first option
                    if (!clickedBtn && optBtns.length > 0) {{
                        const hasContentEditable = chatLayer.querySelector('div[contenteditable="true"]') || 
                                                  document.querySelector('div[contenteditable="true"]');
                        const allSkip = optBtns.every(b => (b.innerText || '').toLowerCase().includes('skip'));
                        if (allSkip && hasContentEditable) {{
                            console.log('Chatbot Debug - Option buttons are all skip, falling through to contenteditable');
                        }} else {{
                            optBtns[0].click();
                            clickedBtn = optBtns[0];
                            console.log('Chatbot Debug - No match, clicked first option:', optBtns[0].innerText.trim());
                        }}
                    }}
                    
                    if (clickedBtn) {{
                        return 'CHATBOT_OPT_CLICKED: ' + clickedBtn.innerText.trim() + ' | Q: ' + qText.slice(0, 50);
                    }}
                }}
                
                // HANDLE DROPDOWN
                if (hasSelect) {{
                    const select = chatLayer.querySelector('select');
                    if (select && select.offsetParent !== null) {{
                        const selectOptions = Array.from(select.options);
                        console.log('Chatbot Debug - Found dropdown with', selectOptions.length, 'options');
                        
                        // For salary questions, look for option containing the number
                        for (const opt of selectOptions) {{
                            const optText = opt.text.toLowerCase();
                            if (isSalaryQuestion) {{
                                // Match if option contains our numeric answer
                                if (optText.includes(answer) || 
                                    (answer === '30' && (optText.includes('30') || optText.includes('25-30') || optText.includes('23-30')))) {{
                                    select.value = opt.value;
                                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                                    if (saveDiv && saveDiv.offsetParent !== null) {{
                                        saveDiv.click();
                                    }}
                                    return 'CHATBOT_DROPDOWN_SELECTED: ' + opt.text;
                                }}
                            }} else {{
                                // Non-salary: try to match by answer text
                                if (optText.includes(answer.toLowerCase())) {{
                                    select.value = opt.value;
                                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                                    if (saveDiv && saveDiv.offsetParent !== null) {{
                                        saveDiv.click();
                                    }}
                                    return 'CHATBOT_SELECTED: ' + opt.text;
                                }}
                            }}
                        }}
                        
                        // Default: select second option if available
                        if (selectOptions.length > 1) {{
                            select.selectedIndex = 1;
                            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            const saveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                            if (saveDiv && saveDiv.offsetParent !== null) {{
                                saveDiv.click();
                                return 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ' + selectOptions[1].text;
                            }}
                            return 'CHATBOT_SELECTED_DEFAULT: ' + selectOptions[1].text;
                        }}
                    }}
                }}
                
                // HANDLE RADIO BUTTONS
                if (hasRadio) {{
                    const radios = chatLayer.querySelectorAll('input[type="radio"]');
                    console.log('Chatbot Debug - Processing radio buttons:', radios.length);
                    
                    let clickedRadio = false;
                    const answerLower = answer.toLowerCase();
                    
                    // Extract numeric value from answer (e.g., "4 Years" -> 4)
                    const answerNumericMatch = answer.match(/(\d+\.?\d*)/);
                    const answerNumeric = answerNumericMatch ? parseFloat(answerNumericMatch[1]) : null;
                    console.log('Chatbot Debug - Answer:', answer, '| Numeric:', answerNumeric);
                    
                    // Try to match answer to radio label
                    for (const radio of radios) {{
                        // Improved label extraction: try label[for], aria-label, parent <label>, then fallback
                        let label = '';
                        if (radio.id) {{
                            const labelEl = chatLayer.querySelector('label[for="' + radio.id + '"]');
                            if (labelEl) label = labelEl.innerText.trim();
                        }}
                        if (!label && radio.getAttribute('aria-label')) {{
                            label = radio.getAttribute('aria-label');
                        }}
                        if (!label) {{
                            let parent = radio.parentElement;
                            while (parent && parent.tagName !== 'LABEL' && parent !== chatLayer) {{
                                parent = parent.parentElement;
                            }}
                            if (parent && parent.tagName === 'LABEL') {{
                                label = parent.innerText.trim();
                            }}
                        }}
                        if (!label) {{
                            label = radio.parentElement?.innerText || radio.nextSibling?.textContent || '';
                        }}
                        const labelLower = label.toLowerCase();
                        
                        // TEXT MATCH: for non-numeric answers, find best text overlap
                        if (!answerNumeric) {{
                            const words = answerLower.split(/\s+/).filter(w => w.length > 2);
                            let matchCount = 0;
                            for (const w of words) {{
                                if (labelLower.includes(w)) matchCount++;
                            }}
                            if (matchCount > 0 && matchCount >= words.length * 0.5) {{
                                if (!radio.checked) {{
                                    radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked text-match radio:', label, '| words matched:', matchCount, '/', words.length);
                                }}
                                break;
                            }}
                        }}
                        
                        // Match Yes/Serving for positive answers
                        if ((answerLower.includes('yes') || answerLower.includes('true')) && 
                            (labelLower.includes('yes') || labelLower.includes('serving'))) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked Yes radio:', label);
                            }}
                            break;
                        }}
                        // Match No for negative answers — guard: skip if label also contains "yes"
                        if ((answerLower.includes('no') || answerLower.includes('false')) && 
                            (labelLower === 'no' || /(\bno\b|^no\b|\bno$)/.test(labelLower)) &&
                            !labelLower.includes('yes')) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked No radio:', label);
                            }}
                            break;
                        }}
                        
                        // Match numeric answers to experience ranges
                        if (answerNumeric !== null) {{
                            // Extract numbers from label (e.g., "3-5 years" -> [3, 5])
                            const labelNumbers = labelLower.match(/(\d+\.?\d*)/g);
                            if (labelNumbers) {{
                                const nums = labelNumbers.map(n => parseFloat(n));
                                // Check if answer falls within range
                                if (nums.length >= 2) {{
                                    if (answerNumeric >= nums[0] && answerNumeric <= nums[1]) {{
                                        if (!radio.checked) {{
                                            radio.click();
                                            clickedRadio = true;
                                            console.log('Chatbot Debug - Clicked numeric range radio:', label);
                                        }}
                                        break;
                                    }}
                                }} else if (nums.length === 1) {{
                                    // Single number match — detect direction (text + symbol prefixes)
                                    const isLess = /less\s+than|under|up\s+to|^<\s*\d/i.test(labelLower);
                                    const isMore = /more\s+than|over|above|plus|^>\s*\d/i.test(labelLower);
                                    if (isLess) {{
                                        // "Less than X" → answer must be below X
                                        if (answerNumeric < nums[0]) {{
                                            if (!radio.checked) {{
                                                radio.click();
                                                clickedRadio = true;
                                                console.log('Chatbot Debug - Clicked numeric upper-bound radio:', label);
                                            }}
                                            break;
                                        }}
                                    }} else if (isMore) {{
                                        // "More than X" → answer must be at least X
                                        if (answerNumeric >= nums[0]) {{
                                            if (!radio.checked) {{
                                                radio.click();
                                                clickedRadio = true;
                                                console.log('Chatbot Debug - Clicked numeric threshold radio:', label);
                                            }}
                                            break;
                                        }}
                                    }} else {{
                                        // No prefix — assume lower bound (e.g., "5+ years", "X years")
                                        if (answerNumeric >= nums[0]) {{
                                            if (!radio.checked) {{
                                                radio.click();
                                                clickedRadio = true;
                                                console.log('Chatbot Debug - Clicked numeric threshold radio:', label);
                                            }}
                                            break;
                                        }}
                                    }}
                                }}
                            }}
                            
                            // Also try to match by looking for the number in the label
                            if (labelLower.includes(String(answerNumeric))) {{
                                if (!radio.checked) {{
                                    radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked exact numeric match radio:', label);
                                }}
                                break;
                            }}
                        }}
                    }}
                    
                    // Education-specific radio matching (before proficiency handler to prevent false matches)
                    const isEducationQ = qLower.includes('education') || qLower.includes('degree') ||
                        qLower.includes('qualification') || qLower.includes('academic') ||
                        qLower.includes('graduate') || qLower.includes('college') ||
                        qLower.includes('university') || qLower.includes('diploma') ||
                        qLower.includes('bachelor') || qLower.includes('master') ||
                        qLower.includes('doctorate') || qLower.includes('school');
                    if (!clickedRadio && isEducationQ) {{
                        // Map answer keywords to radio label keywords for education-level questions
                        const eduAnswerMap = [
                            {{answerKws: ['b.tech', 'bachelor', 'b.e', 'b.sc', 'bca', 'undergraduate'], labelKws: ['bachelor']}},
                            {{answerKws: ['m.tech', 'master', 'm.sc', 'mca', 'mba', 'post graduate', 'postgraduate'], labelKws: ['master']}},
                            {{answerKws: ['phd', 'doctorate', 'doctoral', 'ph.d'], labelKws: ['phd', 'doctorate', 'doctoral']}},
                            {{answerKws: ['diploma', 'advanced diploma'], labelKws: ['diploma']}},
                            {{answerKws: ['10th', 'ssc', 'matric', 'matriculation', 'high school'], labelKws: ['10th', 'ssc', 'high school', 'secondary', 'matric']}},
                            {{answerKws: ['12th', 'hsc', 'intermediate', 'higher secondary'], labelKws: ['12th', 'hsc', 'higher secondary', 'intermediate']}},
                            {{answerKws: ['associate'], labelKws: ['associate']}}
                        ];
                        for (const mapping of eduAnswerMap) {{
                            if (clickedRadio) break;
                            const hasAnswerKeyword = mapping.answerKws.some(kw => answerLower.includes(kw));
                            if (!hasAnswerKeyword) continue;
                            for (const radio of radios) {{
                                const label = (radio.parentElement?.innerText || radio.nextSibling?.textContent || '').toLowerCase();
                                if (mapping.labelKws.some(kw => label.includes(kw))) {{
                                    if (!radio.checked) {{
                                        radio.click();
                                        clickedRadio = true;
                                        console.log('Chatbot Debug - Clicked education radio:', label.trim());
                                    }}
                                    break;
                                }}
                            }}
                        }}
                    }}
                    
                    // Map numeric rating to proficiency levels (Beginner/Intermediate/Advanced)
                    if (!clickedRadio && answerNumeric !== null && !isEducationQ) {{
                        const radioLabels = Array.from(radios).map(r =>
                            (r.parentElement?.innerText || r.nextSibling?.textContent || '').toLowerCase().trim()
                        );
                        const profLevels = ['beginner', 'intermediate', 'advanced'];
                        const hasProfLevels = profLevels.some(level =>
                            radioLabels.some(label => label.includes(level))
                        );
                        if (hasProfLevels) {{
                            let targetLevel;
                            if (answerNumeric >= 7) targetLevel = 'advanced';
                            else if (answerNumeric >= 4) targetLevel = 'intermediate';
                            else targetLevel = 'beginner';
                            for (const radio of radios) {{
                                const label = (radio.parentElement?.innerText || radio.nextSibling?.textContent || '').toLowerCase();
                                if (label.includes(targetLevel)) {{
                                    if (!radio.checked) {{
                                        radio.click();
                                        clickedRadio = true;
                                        console.log('Chatbot Debug - Clicked proficiency radio:', label.trim(), 'for rating', answerNumeric);
                                    }}
                                    break;
                                }}
                            }}
                        }}
                    }}
                    
                    // If no match found, click first non-"No experience" radio
                    if (!clickedRadio) {{
                        for (const radio of radios) {{
                            if (!radio.checked) {{
                                const label = radio.parentElement?.innerText || radio.nextSibling?.textContent || '';
                                const labelLower = label.toLowerCase();
                                // Skip "No experience" option
                                if (labelLower.includes('no experience') || labelLower.includes('0 years')) {{
                                    console.log('Chatbot Debug - Skipping "No experience" option');
                                    continue;
                                }}
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked default radio:', label);
                                break;
                            }}
                        }}
                    }}
                    
                    // After selecting radio, click Save/Submit button
                    if (clickedRadio) {{
                        await new Promise(r => setTimeout(r, 300));
                        
                        const naukSaveDiv = document.querySelector('.sendMsg[tabindex], div.sendMsg, #sendMsg__vjhkrpzhhInputBox .sendMsg');
                        if (naukSaveDiv && naukSaveDiv.offsetParent !== null) {{
                            naukSaveDiv.click();
                            console.log('Chatbot Debug - Save clicked after radio');
                            return 'CHATBOT_RADIO_AND_SAVE: ' + qText.slice(0, 50);
                        }}
                        
                        const allButtons = chatLayer ? 
                            Array.from(chatLayer.querySelectorAll('button, div[tabindex], span[tabindex]')) : 
                            Array.from(document.querySelectorAll('[role="dialog"] button, [class*="modal"] button'));
                        
                        for (const btn of allButtons) {{
                            const btnText = btn.innerText.toLowerCase().trim();
                            if ((btnText === 'save' || btnText === 'submit' || btnText === 'next') 
                                && btn.offsetParent !== null) {{
                                btn.click();
                                console.log('Chatbot Debug - Save clicked after radio (fallback)');
                                return 'CHATBOT_RADIO_AND_SAVE: ' + qText.slice(0, 50);
                            }}
                        }}
                        
                        return 'CHATBOT_RADIO_CLICKED: ' + qText.slice(0, 50);
                    }}
                }}
                
                // HANDLE CHECKBOXES
                if (hasCheckbox) {{
                    const checkboxes = chatLayer.querySelectorAll('input[type="checkbox"]');
                    console.log('Chatbot Debug - Processing checkboxes:', checkboxes.length);
                    
                    let clickedCheckbox = false;
                    const answerStr = typeof answer === 'string' ? answer : String(answer);
                    const answerLower = answerStr.toLowerCase();
                    
                    // Try to match answer to checkbox label
                    for (const checkbox of checkboxes) {{
                        const label = checkbox.parentElement?.innerText || checkbox.nextSibling?.textContent || '';
                        const labelLower = label.toLowerCase();
                        
                        // Check if answer matches this option
                        if (answerLower.includes(labelLower) || labelLower.includes(answerLower)) {{
                            if (!checkbox.checked) {{
                                checkbox.click();
                                clickedCheckbox = true;
                                console.log('Chatbot Debug - Clicked checkbox:', label);
                            }}
                        }}
                    }}
                    
                    // If no specific match but answer is "Yes" or positive, check ALL options
                    // except "Skip this question" (user wants to select all available locations)
                    // BUT skip "No" if this is a Yes/No pair (don't select both)
                    if (!clickedCheckbox && (answerLower.includes('yes') || answerLower.includes('true'))) {{
                        const visLabels = Array.from(checkboxes).map(c => (c.parentElement?.innerText || c.nextSibling?.textContent || '').toLowerCase().trim());
                        const visIsYesNoPair = visLabels.some(l => l === 'yes') && visLabels.some(l => l === 'no');
                        for (const checkbox of checkboxes) {{
                            const lbl = (checkbox.parentElement?.innerText || checkbox.nextSibling?.textContent || '').toLowerCase();
                            // Skip the "skip" option
                            if (lbl.includes('skip')) continue;
                            // For Yes/No pairs, skip "no" — only select "yes"
                            if (visIsYesNoPair && lbl.trim() === 'no') continue;
                            if (!checkbox.checked) {{
                                checkbox.click();
                                clickedCheckbox = true;
                                console.log('Chatbot Debug - Clicked checkbox:', lbl.trim());
                            }}
                        }}
                    }}
                    
                    // After selecting checkbox(es), click Save/Submit button
                    if (clickedCheckbox) {{
                        // Find and click Save button
                        const saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg') ||
                                       Array.from(document.querySelectorAll('button')).find(el => 
                                           el.innerText.toLowerCase().includes('save'));
                        
                        if (saveBtn && saveBtn.offsetParent !== null) {{
                            saveBtn.click();
                            console.log('Chatbot Debug - Save clicked after checkbox');
                            return 'CHATBOT_CHECKBOX_AND_SAVE: ' + qText.slice(0, 50);
                        }}
                        
                        return 'CHATBOT_CHECKBOX_CLICKED: ' + qText.slice(0, 50);
                    }}
                    
                    // Naukri fallback: hidden input[type="checkbox"] exist inside .mcc__checkbox divs
                    // but parentElement.innerText doesn't expose the visible label.
                    // The inputs have name="Pune" etc but are NOT inside .mcc__checkbox.
                    // Dump full DOM structure to understand relationship.
                    const mccCheckboxes = chatLayer.querySelectorAll('.mcc__checkbox');
                    const namedInputs = chatLayer.querySelectorAll('input[type="checkbox"][name]');
                    console.log('Chatbot Debug - Naukri .mcc__checkbox fallback:', mccCheckboxes.length, '| named inputs:', namedInputs.length);
                    
                    // Dump structure of first mcc and first input
                    if (mccCheckboxes.length > 0) {{
                        console.log('Chatbot Debug - MCC[0] tag:', mccCheckboxes[0].tagName, 'class:', mccCheckboxes[0].className, 'children:', mccCheckboxes[0].children.length, 'innerHTML[:200]:', mccCheckboxes[0].innerHTML.substring(0, 200));
                        console.log('Chatbot Debug - MCC[0] parent tag:', mccCheckboxes[0].parentElement?.tagName, 'class:', mccCheckboxes[0].parentElement?.className);
                        console.log('Chatbot Debug - MCC[0] outerHTML[:300]:', mccCheckboxes[0].outerHTML.substring(0, 300));
                    }}
                    if (namedInputs.length > 0) {{
                        console.log('Chatbot Debug - Input[0] name:', namedInputs[0].name, 'parent:', namedInputs[0].parentElement?.tagName, 'class:', namedInputs[0].parentElement?.className);
                        console.log('Chatbot Debug - Input[0] grandparent:', namedInputs[0].parentElement?.parentElement?.tagName, 'class:', namedInputs[0].parentElement?.parentElement?.className);
                        // Check if input is inside or next to any .mcc__checkbox
                        const closestMcc = namedInputs[0].closest('.mcc__checkbox');
                        console.log('Chatbot Debug - Input[0] closest .mcc__checkbox:', closestMcc ? 'FOUND' : 'NOT FOUND');
                        // Check siblings
                        const siblings = namedInputs[0].parentElement?.children;
                        if (siblings) {{
                            console.log('Chatbot Debug - Input[0] sibling tags:', Array.from(siblings).map(s => s.tagName + '.' + s.className.substring(0, 30)).join(', '));
                        }}
                    }}
                    
                    // Strategy: use the named inputs to get labels, click corresponding .mcc__checkbox by index
                    // Detect Yes/No pair: if both "yes" and "no" are options, only click "yes"
                    const mccInputNames = Array.from(namedInputs).map(n => (n.name || '').toLowerCase().trim());
                    const mccHasYes = mccInputNames.some(n => n === 'yes');
                    const mccHasNo = mccInputNames.some(n => n === 'no');
                    const mccIsYesNoPair = mccHasYes && mccHasNo;
                    if (mccIsYesNoPair) {{
                        console.log('Chatbot Debug - MCC Yes/No pair detected, will only click Yes');
                    }}
                    let mccClicked = 0;
                    const skipNames = [];
                    for (let i = 0; i < namedInputs.length && i < mccCheckboxes.length; i++) {{
                        const inputName = (namedInputs[i].name || '').toLowerCase().trim();
                        const isSkip = inputName.includes('skip') || inputName.includes('skip this');
                        // For Yes/No pairs, skip "no" — only select "yes"
                        const isNoInPair = mccIsYesNoPair && inputName === 'no';
                        console.log('Chatbot Debug - Pair[' + i + '] input name:', inputName, 'isSkip:', isSkip, 'isNoInPair:', isNoInPair);
                        if (isSkip || isNoInPair) {{
                            skipNames.push(inputName);
                            continue;
                        }}
                        mccCheckboxes[i].click();
                        mccClicked++;
                        console.log('Chatbot Debug - MCC clicked index:', i, 'name:', inputName);
                    }}
                    
                    if (mccClicked > 0) {{
                        await new Promise(r => setTimeout(r, 300));
                        const saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg:not(.disabled)') ||
                                       document.querySelector('.sendMsgbtn_container .sendMsg');
                        if (saveBtn) {{
                            saveBtn.click();
                            console.log('Chatbot Debug - Save clicked after MCC checkboxes');
                        }}
                        return 'CHATBOT_MCC_CHECKBOX_SAVED: Selected ' + mccClicked + ' options';
                    }}
                }}
                
                // ─── THREE-FIELD DATE PICKER (DD / MM / YYYY) ──────────────────────
                // Naukri's date picker uses three separate input[type="number"] fields.
                // The generic handler below would only fill DD with "30" and break.
                // Detect this pattern first and fill all three fields correctly.
                const ddInput = chatLayer ? chatLayer.querySelector('input[placeholder="DD"]') : null;
                const mmInput = chatLayer ? chatLayer.querySelector('input[placeholder="MM"]') : null;
                const yyInput = chatLayer ? chatLayer.querySelector('input[placeholder="YYYY"]') : null;
                if (ddInput && mmInput && yyInput) {{
                    // Check if this is a DOB question or LWD question
                    const isDobQ = qLower.includes('date of birth') || qLower.includes('dob') || qLower.includes('birth date');
                    let dd, mm, yyyy;
                    if (isDobQ) {{
                        dd = '17'; mm = '12'; yyyy = '2000';
                    }} else {{
                        const targetDate = new Date();
                        targetDate.setDate(targetDate.getDate() + 30);
                        dd = String(targetDate.getDate()).padStart(2, '0');
                        mm = String(targetDate.getMonth() + 1).padStart(2, '0');
                        yyyy = String(targetDate.getFullYear());
                    }}
                    
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    
                    [[ddInput, dd], [mmInput, mm], [yyInput, yyyy]].forEach(function(pair) {{
                        const el = pair[0], val = pair[1];
                        if (nativeSetter) nativeSetter.call(el, val);
                        el.dispatchEvent(new Event('input',  {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                    }});
                    
                    console.log('Chatbot Debug - Date filled: ' + dd + '/' + mm + '/' + yyyy);
                    
                    const saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg') ||
                                   chatLayer.querySelector('button');
                    if (saveBtn && !saveBtn.disabled) {{
                        saveBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.dispatchEvent(new MouseEvent('mouseup',   {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.click();
                        console.log('Chatbot Debug - Save clicked after date fill');
                        return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                    }}
                    return 'CHATBOT_DATE_FILLED: ' + dd + '/' + mm + '/' + yyyy;
                }}
                // ───────────────────────────────────────────────────────────────────
                
                // HANDLE TRADITIONAL TEXT INPUTS

                let input = null;
                if (chatLayer) {{
                    input = chatLayer.querySelector('input[type="text"][placeholder*="Type"], input[placeholder*="type"], input[placeholder*="Enter"]');
                    if (!input) {{
                        input = chatLayer.querySelector('input[type="text"]:not([type="hidden"]):not([type="file"])');
                    }}
                    if (!input) {{
                        input = chatLayer.querySelector('textarea');
                    }}
                    if (!input) {{
                        const chatInputs = chatLayer.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="file"]), textarea');
                        for (const inp of chatInputs) {{
                            const rect = inp.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0 && chatLayer.contains(inp)) {{
                                input = inp;
                                break;
                            }}
                        }}
                    }}
                }}
                
                if (!input) {{
                    input = document.querySelector('[role="dialog"] input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="file"]), [class*="modal"] input:not([type="hidden"]):not([type="file"]), textarea');
                }}
                
                // HANDLE CONTENTEDITABLE (Naukri chat-style inputs)
                let contentEditable = null;
                if (!input) {{
                    contentEditable = chatLayer.querySelector('div[contenteditable="true"]') || 
                                     document.querySelector('div[contenteditable="true"]');
                }}
                
                if (contentEditable) {{
                    console.log('Chatbot Debug - Found contenteditable div:', contentEditable.className);
                    
                    // Clear existing content
                    contentEditable.innerHTML = '';
                    
                    // Insert text as text node
                    const textNode = document.createTextNode(answer);
                    contentEditable.appendChild(textNode);
                    
                    // Trigger input event
                    contentEditable.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    contentEditable.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    // Focus the element
                    contentEditable.focus();
                    
                    // Place cursor at end
                    const range = document.createRange();
                    range.selectNodeContents(contentEditable);
                    range.collapse(false);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    
                    console.log('Chatbot Debug - Contenteditable set to:', contentEditable.innerText);
                    
                    // Wait for UI to update
                    await new Promise(r => setTimeout(r, 500));
                    
                    let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                        el.innerText.toLowerCase().trim() === 'save');
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                    }}
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('[id^="sendMsgbtn_container"]');
                    }}
                    if (!saveBtn && chatLayer) {{
                        saveBtn = chatLayer.querySelector('button');
                    }}
                    if (!saveBtn) {{
                        saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                            el.innerText.toLowerCase().includes('save'));
                    }}
                    
                    console.log('Chatbot Debug - Save button found:', !!saveBtn, saveBtn ? saveBtn.innerText : 'none');
                    
                    if (saveBtn) {{
                        if (saveBtn.disabled) {{
                            console.log('Chatbot Debug - Save button is disabled');
                            return 'CHATBOT_SAVE_DISABLED: ' + qText.slice(0, 50);
                        }}
                        
                        // ROBUST CLICK: Dispatch multiple events
                        saveBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.click();
                        
                        console.log('Chatbot Debug - Save button clicked');
                        
                        // Wait for UI to process
                        await new Promise(r => setTimeout(r, 300));
                        
                        // Check for error text after click (validation error)
                        const errorSelectors = [
                            '.error', '.err', '[class*="error"]',
                            '.chatbot_error', '.errorMsg', '.validation-error',
                            '[class*="invalid"]', '.red-text', '.warning'
                        ];
                        for (const sel of errorSelectors) {{
                            const errorMsg = document.querySelector(sel);
                            if (errorMsg && errorMsg.offsetParent !== null && errorMsg.innerText.trim()) {{
                                const errText = errorMsg.innerText.trim();
                                if (errText.length > 0 && errText.length < 200) {{
                                    console.log('Chatbot Debug - Error found:', errText);
                                    return 'CHATBOT_SUBMISSION_ERROR: ' + errText;
                                }}
                            }}
                        }}
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                    }}
                    return 'CHATBOT_ANSWERED: ' + qText.slice(0, 50);
                }}
                
                if (input && input.type !== 'file') {{
                    const isNumericInput = input.type === 'number' || 
                        input.getAttribute('inputmode') === 'numeric' ||
                        input.getAttribute('inputmode') === 'decimal' ||
                        (input.className && (
                            input.className.toLowerCase().includes('number') ||
                            input.className.toLowerCase().includes('decimal') ||
                            input.className.toLowerCase().includes('numeric')
                        )) ||
                        qText.toLowerCase().includes('in lakhs') ||
                        qText.toLowerCase().includes('in lacs');
                    
                    console.log('Chatbot Debug - Found input:', input.type, input.placeholder, 'Numeric:', isNumericInput);
                    
                    if (isNumericInput && answer) {{
                        const numericMatch = answer.match(/(\\d+\\.?\\d*)/);
                        if (numericMatch) {{
                            answer = numericMatch[1];
                            console.log('Chatbot Debug - Extracted numeric:', answer);
                        }}
                    }}
                    
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    if (setter) setter.call(input, answer);
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    console.log('Chatbot Debug - Input value set to:', input.value);
                    
                    // Verify the value was set correctly
                    if (input.value !== answer) {{
                        // Try again with focus and blur
                        input.focus();
                        if (setter) setter.call(input, answer);
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.blur();
                    }}
                    
                    // FALLBACK: Try hitting Enter on the input
                    input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
                    
                    // Wait a moment for UI to respond
                    await new Promise(r => setTimeout(r, 500));
                    
                    let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                        el.innerText.toLowerCase().trim() === 'save');
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('.sendMsg[tabindex], div.sendMsg');
                    }}
                    if (!saveBtn) {{
                        saveBtn = document.querySelector('[id^="sendMsgbtn_container"]');
                    }}
                    if (!saveBtn && chatLayer) {{
                        saveBtn = chatLayer.querySelector('button');
                    }}
                    if (!saveBtn) {{
                        saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                            el.innerText.toLowerCase().includes('save'));
                    }}
                    
                    console.log('Chatbot Debug - Save button found:', !!saveBtn, saveBtn ? saveBtn.innerText : 'none');
                    
                    if (saveBtn) {{
                        if (saveBtn.disabled) {{
                            console.log('Chatbot Debug - Save button is disabled');
                            return 'CHATBOT_SAVE_DISABLED: ' + qText.slice(0, 50);
                        }}
                        
                        // ROBUST CLICK: Dispatch multiple events
                        saveBtn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true, view: window }}));
                        saveBtn.click();
                        
                        console.log('Chatbot Debug - Save button clicked');
                        
                        // Wait for UI to process
                        await new Promise(r => setTimeout(r, 300));
                        
                        // Check for error text after click (validation error)
                        const errorSelectors = [
                            '.error', '.err', '[class*="error"]',
                            '.chatbot_error', '.errorMsg', '.validation-error',
                            '[class*="invalid"]', '.red-text', '.warning'
                        ];
                        for (const sel of errorSelectors) {{
                            const errorMsg = document.querySelector(sel);
                            if (errorMsg && errorMsg.offsetParent !== null && errorMsg.innerText.trim()) {{
                                const errText = errorMsg.innerText.trim();
                                if (errText.length > 0 && errText.length < 200) {{
                                    console.log('Chatbot Debug - Error found:', errText);
                                    return 'CHATBOT_SUBMISSION_ERROR: ' + errText;
                                }}
                            }}
                        }}
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE: ' + qText.slice(0, 50);
                    }}
                    return 'CHATBOT_ANSWERED: ' + qText.slice(0, 50);
                }}
                
                // Option buttons are now handled at the top of STEP 2 (before dropdowns/radios)
                // This fallback only runs if the early handler somehow missed them
                const lateOptionBtns = chatLayer.querySelectorAll('.chatbot_OptionContainer button, [class*="option"] button');
                if (lateOptionBtns.length > 0) {{
                    lateOptionBtns[0].click();
                    return 'CHATBOT_OPT_CLICKED_FALLBACK';
                }}
                
                // Try to click Send/Submit/Next button
                const sendBtns = chatLayer.querySelectorAll('.chatbot_sendBtn, button.send, button[class*="send"], button[class*="submit"], button[class*="next"]');
                for (const btn of sendBtns) {{
                    if (btn.offsetParent !== null && !btn.disabled) {{
                        btn.click();
                        return 'CHATBOT_SENT';
                    }}
                }}
                
                // Check for any clickable button
                const anyBtn = chatLayer.querySelector('button:not([disabled])');
                if (anyBtn && anyBtn.offsetParent !== null) {{
                    anyBtn.click();
                    return 'CHATBOT_BTN_CLICKED';
                }}
                
                return 'CHATBOT_WAITING';
            }}""")
            
            # Extract question text from result for tracking
            current_question = None
            if 'CHATBOT_ANSWERED_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_ANSWERED_AND_SAVE: ')[1] if 'CHATBOT_ANSWERED_AND_SAVE: ' in result else None
            elif 'CHATBOT_ANSWERED:' in result:
                current_question = result.split('CHATBOT_ANSWERED: ')[1] if 'CHATBOT_ANSWERED: ' in result else None
            elif 'CHATBOT_SUBMISSION_ERROR:' in result:
                current_question = result.split('CHATBOT_SUBMISSION_ERROR: ')[1] if 'CHATBOT_SUBMISSION_ERROR: ' in result else None
            elif 'CHATBOT_DROPDOWN_SELECTED:' in result:
                current_question = result.split('CHATBOT_DROPDOWN_SELECTED: ')[1] if 'CHATBOT_DROPDOWN_SELECTED: ' in result else None
            elif 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ')[1] if 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE: ' in result else None
            elif 'CHATBOT_SAVE_DISABLED:' in result:
                current_question = result.split('CHATBOT_SAVE_DISABLED: ')[1] if 'CHATBOT_SAVE_DISABLED: ' in result else None
            elif 'CHATBOT_RADIO_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_RADIO_AND_SAVE: ')[1] if 'CHATBOT_RADIO_AND_SAVE: ' in result else None
            elif 'CHATBOT_RADIO_CLICKED:' in result:
                current_question = result.split('CHATBOT_RADIO_CLICKED: ')[1] if 'CHATBOT_RADIO_CLICKED: ' in result else None
            elif 'CHATBOT_CHECKBOX_AND_SAVE:' in result:
                current_question = result.split('CHATBOT_CHECKBOX_AND_SAVE: ')[1] if 'CHATBOT_CHECKBOX_AND_SAVE: ' in result else None
            elif 'CHATBOT_CHECKBOX_CLICKED:' in result:
                current_question = result.split('CHATBOT_CHECKBOX_CLICKED: ')[1] if 'CHATBOT_CHECKBOX_CLICKED: ' in result else None
            
            # Check if stuck on same question
            if current_question:
                if previous_questions and previous_questions[-1] == current_question:
                    same_question_count += 1
                    if same_question_count >= 3:
                        print(f"⚠️ Stuck on same question ({same_question_count}x): {current_question}")
                        # Take screenshot for debugging
                        return False
                else:
                    same_question_count = 0
                previous_questions.append(current_question)
            
            # Only log CHATBOT_WAITING every 5th iteration to reduce noise
            if result != 'CHATBOT_WAITING' or iteration % 5 == 0:
                print(f"   📜 Chatbot[{iteration}]: {result}")
            
            if result == 'CHATBOT_COMPLETE':
                self.metrics['applications_submitted'] += 1
                return True
            elif result == 'MCC_POPUP_DETECTED':
                return 'CONTINUE'  # Signal main loop to handle MCC
            elif 'NAUKRI_RATE_LIMITED' in result:
                # Error popup detected - return to main loop for rate limiting
                return result
            elif 'CHATBOT_SUBMISSION_ERROR' in result:
                # Validation error - wait longer and try again
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_SAVE_DISABLED' in result:
                # Button not ready yet - wait
                await asyncio.sleep(random.uniform(1, 2))
                continue
            elif result == 'NO_CHATBOT':
                # Check if maybe we're done
                if iteration > 3:
                    return True
                continue
            elif 'CHATBOT_ANSWERED_AND_SAVE' in result:
                # Wait longer after successful save to let UI update
                last_action_was_answer = True
                consecutive_waiting_count = 0  # Reset waiting counter after successful action
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_RADIO_AND_SAVE' in result:
                # Wait longer after successful radio selection
                last_action_was_answer = True
                consecutive_waiting_count = 0
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_CHECKBOX_AND_SAVE' in result:
                # Wait longer after successful checkbox selection
                last_action_was_answer = True
                consecutive_waiting_count = 0
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_DROPDOWN_SELECTED' in result or 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE' in result:
                # Wait longer after dropdown selection
                last_action_was_answer = True
                consecutive_waiting_count = 0
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_OPT_CLICKED' in result:
                # Option button clicked - wait for chatbot to process and show next question
                last_action_was_answer = True
                consecutive_waiting_count = 0
                await asyncio.sleep(random.uniform(2, 3))
                continue
            elif 'CHATBOT_WAITING' in result:
                # Nothing to do, wait
                consecutive_waiting_count += 1
                # If we've been waiting for several iterations after answering questions,
                # the chatbot is likely done but just hasn't closed yet
                if consecutive_waiting_count >= 3 and last_action_was_answer:
                    print(f"   📜 Chatbot completed after {consecutive_waiting_count} waiting iterations post-answer")
                    self.metrics['applications_submitted'] += 1
                    return True
                continue
        
        print("⚠️ Chatbot loop exhausted")
        # If we answered at least one question before exhausting, consider it a success
        if last_action_was_answer:
            print("   📜 Chatbot likely completed - answered questions before exhausting")
            self.metrics['applications_submitted'] += 1
            return True
        return False

    async def _close_linkedin_modal(self) -> bool:
        """
        Close the LinkedIn Easy Apply modal with a two-step close:
        1) Click the X/Dismiss button (opens 'Discard application?' confirmation dialog)
        2) Wait for the Discard dialog, then click the Discard confirmation button
        
        Returns True if the modal was closed (no visible modal remains), False otherwise.
        """
        if not self._page:
            return False
        try:
            # Step 1: Click the dismiss/close (X) button
            step1 = await self._page.evaluate("""() => {
                const closeSelectors = [
                    'button[aria-label*="Dismiss"]',
                    'button[aria-label*="dismiss"]',
                    'button[aria-label*="Close"]',
                    'button[aria-label*="close"]',
                    'button[data-test-modal-close-btn]',
                    '.artdeco-modal__dismiss',
                    '.artdeco-button--circle[aria-label]',
                    'button[aria-label*="Discard"]'
                ];
                for (let sel of closeSelectors) {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return 'CLICKED';
                    }
                }
                return 'NO_CLOSE_BTN';
            }""")
            if step1 == 'NO_CLOSE_BTN':
                # Maybe already closed, or a Discard dialog is already open
                pass
            await asyncio.sleep(1)
            
            # Step 2: Click the "Discard application" confirmation button (appears after step 1)
            step2 = await self._page.evaluate("""() => {
                // The Discard confirmation dialog has a primary button with text "Discard application"
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if ((text === 'discard' || text === 'discard application' || text.includes('discard application')) && btn.offsetParent !== null) {
                        btn.click();
                        return 'DISCARDED';
                    }
                }
                // Fallback: aria-label based
                const discardBtn = document.querySelector('button[data-test-dialog-primary-button], button.artdeco-button--primary');
                if (discardBtn && discardBtn.offsetParent !== null) {
                    const t = (discardBtn.innerText || '').toLowerCase();
                    if (t.includes('discard')) {
                        discardBtn.click();
                        return 'DISCARDED';
                    }
                }
                return 'NO_DISCARD_BTN';
            }""")
            await asyncio.sleep(1)
            
            # Step 3: Verify modal is actually closed
            modal_still_open = await self._page.evaluate("""() => {
                const modal = document.querySelector('.artdeco-modal--is-open, .jobs-easy-apply-modal');
                return !!(modal && modal.offsetParent !== null);
            }""")
            
            if not modal_still_open:
                print("✅ LinkedIn modal closed successfully (two-step close)")
                return True
            print("⚠️ LinkedIn modal still open after two-step close attempt")
            return False
        except Exception as e:
            print(f"⚠️ _close_linkedin_modal error: {e}")
            return False

    async def _handle_scripted_fallback(self) -> str:
        """Execute the scripted JavaScript fallback logic and return the result string."""
        # Serialize patterns, synonyms, and stop words for JS injection
        # Use merged patterns from JSON config + legacy dict
        patterns_for_js = self._get_patterns_for_js()
        patterns_json = json.dumps(patterns_for_js.get('answers', {}))
        patterns_with_defaults_json = json.dumps(patterns_for_js.get('with_defaults', {}))
        synonyms_json = json.dumps(SYNONYM_MAP)
        stopwords_json = json.dumps(list(STOP_WORDS))
        exact_match_keys = [k for k, v in patterns_for_js.get('with_defaults', {}).items() if v.get('requires_exact_match')]
        exact_match_keys_json = json.dumps(exact_match_keys)
        
        try:
            # We use a formatted string to inject the JSON, but we must escape braces for the JS function
            # NOTE: This function must NOT use async/await - Playwright's evaluate handles timing via Python asyncio
            # Using a function expression (wrapped in parens) - function statements require a name in JS
            js_code = """(function() {
                // 1. INJECTED KNOWLEDGE
                const KNOWN_PATTERNS = __PATTERNS__;
                const KNOWN_PATTERNS_WITH_DEFAULTS = __PATTERNS_WITH_DEFAULTS__;
                const SYNONYMS = __SYNONYMS__;
                const STOP_WORDS_SET = new Set(__STOPWORDS__);
                const EXACT_MATCH_KEYS = new Set(__EXACT_MATCH_KEYS__);
                
                // Platform-specific overrides
                if (window.location.hostname.includes('linkedin')) {
                    // Override ALL experience values for LinkedIn (numeric-only fields)
                    // Instead of maintaining a list, scan all values generically
                    Object.keys(KNOWN_PATTERNS).forEach(k => {
                        const v = KNOWN_PATTERNS[k];
                        if (v === '4 Years') KNOWN_PATTERNS[k] = '4';
                        else if (v === '2 Years') KNOWN_PATTERNS[k] = '2';
                    });
                    
                    // Override salary/CTC to numeric values for LinkedIn text inputs
                    const salaryKeys = [
                        'salary range', 'current salary range', 'expected salary range',
                        'annual salary', 'ctc range', 'current ctc', 'expected ctc',
                        'expected annual ctc in inr', 'expected annual ctc', 'expected ctc in inr', 'expected ctc inr',
                        'current salary', 'expected salary', 'current annual salary',
                        'what is your current annual salary', 'what is your current annual salary?',
                        'expected annual salary', 'what is your expected annual salary', 'what is your expected annual salary?',
                        'what is your current salary?', 'what is your expected salary?',
                        'what is your current ctc', 'what is your current ctc?',
                        'gross salary', 'gross current salary', 'gross expected salary', 'salary expectations'
                    ];
                    salaryKeys.forEach(k => {
                        if (KNOWN_PATTERNS[k]) {
                            // Use full INR values for LinkedIn text inputs
                            if (k.includes('expected') || k.includes('ectc') || k.includes('expect')) {
                                KNOWN_PATTERNS[k] = '3000000';
                            } else {
                                KNOWN_PATTERNS[k] = '2300000';
                            }
                        }
                    });
                    
                    // Override notice period keys to numeric days for LinkedIn
                    Object.keys(KNOWN_PATTERNS).forEach(k => {
                        const defaultObj = KNOWN_PATTERNS_WITH_DEFAULTS[k];
                        if (defaultObj && defaultObj.category === 'notice_period') {
                            const v = KNOWN_PATTERNS[k];
                            if (v && typeof v === 'string') {
                                if (v !== 'Yes' && v !== 'No' && v !== 'Serving Notice Period') {
                                    const match = v.match(/(\d+)/);
                                    KNOWN_PATTERNS[k] = match ? match[1] : '15';
                                    
                                    // Also override the input_type_defaults if present
                                    if (defaultObj.input_type_defaults) {
                                        Object.keys(defaultObj.input_type_defaults).forEach(type => {
                                            const typeVal = defaultObj.input_type_defaults[type];
                                            if (typeof typeVal === 'string' && typeVal.includes('days')) {
                                                const typeMatch = typeVal.match(/(\d+)/);
                                                defaultObj.input_type_defaults[type] = typeMatch ? typeMatch[1] : '15';
                                            }
                                        });
                                    }
                                }
                            }
                        }
                    });
                    
                    // Fallback to noticeKeys list just in case some keys aren't in defaults
                    const noticeKeys = [
                        'notice period', 'what is your notice period', 'what is your notice period?',
                        'what is your notice period ?', 'notice period in days', 'notice period days',
                        'serving notice', 'serving notice period', 'are you serving notice', 'currently serving notice',
                        'if serving lwd', 'if serving lwd. looking for immediate joiners only',
                        'if serving lwd, looking for immediate joiners only', 'serving lwd',
                        'if serving notice period immediate joiner',
                        'official notice period', 'what is your official notice period',
                        'official notice period if serving lwd', 'notice period if serving lwd',
                        'official notice period lwd', 'official notice',
                        'how many days you can join',
                        'in how many days can you join',
                        'if selected, in how many days can you join',
                        'how soon can you join us', 'how soon you can join us',
                        'how soon can you join if gets selected',
                        'how soon can you join', 'when can you join',
                        'earliest joining date', 'tentative joining date',
                        'joining date', 'joining', 'availability',
                        'when are you available', 'available from',
                        'days required for notice', 'how immediate can you join',
                        'please mention your notice period',
                        'please select your notice period with your current employer',
                        'please select your notice period',
                        'how many days will you be able to join',
                        'within how many days will you be able to join',
                        'join us', 'joining time', 'joining availability',
                        'last working day'
                    ];
                    noticeKeys.forEach(k => {
                        const v = KNOWN_PATTERNS[k];
                        if (v && v !== 'Yes' && v !== 'No' && v !== 'Serving Notice Period') {
                            const match = v.match(/(\d+)/);
                            KNOWN_PATTERNS[k] = match ? match[1] : '15';
                        }
                    });
                    
                    // Override cloud/AWS/GCP experience keys to numeric years for LinkedIn number inputs
                    // These fields ask for years (decimal), not platform names
                    const cloudKeys = [
                        'cloud experience', 'what cloud experience', 'cloud experience you are having',
                        'aws azure gcp', 'aws azure or gcp', 'aws gcp azure',
                        'cloud platform', 'cloud computing', 'cloud services',
                        'which cloud', 'cloud provider', 'cloud infrastructure',
                        'aws experience', 'devops experience', 'kubernetes experience',
                        'docker experience'
                    ];
                    cloudKeys.forEach(k => {
                        if (KNOWN_PATTERNS[k]) KNOWN_PATTERNS[k] = '4';
                    });
                }

                const MAX_RETRIES = 3;
                
                // 2. SHARED UTILS (Restored from Legacy)
                // NOTE: sleep removed - use Python's asyncio.sleep() between evaluate calls instead
                // const sleep = (ms) => new Promise(r => setTimeout(r, ms));  // REMOVED - causes SyntaxError
                const isVisible = (elem) => !!(elem && (elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length));

                // Keyword extraction: normalize synonyms, strip stop words
                const extractKeywords = (text) => {
                    const words = text.replace(/[^\w\s]/g, ' ').toLowerCase().split(/\s+/);
                    const normalized = words.map(w => SYNONYMS[w] || w);
                    return new Set(normalized.filter(w => !STOP_WORDS_SET.has(w) && w.length > 1));
                };
                
                // Set intersection helper
                const setIntersect = (a, b) => {
                    const result = new Set();
                    for (const item of a) { if (b.has(item)) result.add(item); }
                    return result;
                };

                // Multi-pass Fuzzy Matcher implementation with robust pattern matching
                const fuzzyMatch = (question) => {
                    if (!question) return null;
                    const qLower = question.toLowerCase().trim();
                    let bestMatch = null;
                    let bestKeyLen = 0;
                    let bestScore = 0;
                    
                    // Sort patterns by key length (descending) to prioritize longer, more specific matches
                    const sortedPatterns = Object.entries(KNOWN_PATTERNS).sort((a, b) => b[0].length - a[0].length);
                    
                    // --- PASS 1: Exact match (highest priority) ---
                    for (const [key, val] of sortedPatterns) {
                        const keyLower = key.toLowerCase();
                        if (qLower === keyLower) return val;
                    }
                    
                    // --- PASS 2: Substring match (question contains entire pattern key) ---
                    for (const [key, val] of sortedPatterns) {
                        const keyLower = key.toLowerCase();
                        if (qLower.includes(keyLower)) {
                            // Anti-collision for generic words
                            if (keyLower === 'years' && (qLower.includes('salary') || qLower.includes('ctc') || qLower.includes('pay') || qLower.includes('inr'))) continue;
                            if (keyLower === 'no' && qLower.length > 20 && !qLower.includes('non-') && !qLower.includes('notice')) continue;
                            if (EXACT_MATCH_KEYS.has(keyLower)) continue;
                            if (key.length > bestKeyLen) {
                                bestMatch = val;
                                bestKeyLen = key.length;
                            }
                        }
                    }
                    
                    // --- PASS 3: Contains-words match (all significant pattern words exist in question) ---
                    // This handles: "owned backend architecture end to end" pattern vs "Have you owned backend architecture end to end, from design to production deployment?"
                    if (!bestMatch) {
                        const qWords = new Set(qLower.split(/\s+/));
                        for (const [key, val] of sortedPatterns) {
                            const keyLower = key.toLowerCase();
                            if (EXACT_MATCH_KEYS.has(keyLower)) continue;
                            const keyWords = keyLower.split(/\s+/).filter(w => w.length > 2);
                            if (keyWords.length < 2) continue; // Only for multi-word patterns
                            
                            // Check if ALL significant words from pattern exist in question
                            const allWordsFound = keyWords.every(word => qWords.has(word) || qLower.includes(word));
                            if (allWordsFound) {
                                // Score based on coverage ratio
                                const score = keyWords.length / Math.max(qLower.split(/\s+/).length, keyWords.length);
                                if (score > bestScore || (score === bestScore && key.length > bestKeyLen)) {
                                    bestMatch = val;
                                    bestKeyLen = key.length;
                                    bestScore = score;
                                }
                            }
                        }
                    }
                    
                    // --- PASS 4: Keyword overlap (fallback with lower threshold) ---
                    if (!bestMatch) {
                        const qKeywords = extractKeywords(qLower);
                        if (qKeywords.size > 0) {
                            let bestKeywordScore = 0;
                            for (const [key, val] of sortedPatterns) {
                                const kKeywords = extractKeywords(key);
                                if (kKeywords.size === 0) continue;
                                if (EXACT_MATCH_KEYS.has(key.toLowerCase())) continue;
                                const overlap = setIntersect(qKeywords, kKeywords);
                                const score = overlap.size / Math.max(qKeywords.size, kKeywords.size);
                                // Lower threshold (0.3) for better matching on complex questions
                                if (score > bestKeywordScore && score >= 0.3) {
                                    bestKeywordScore = score;
                                    bestMatch = val;
                                }
                            }
                        }
                    }
                    
                    // --- PASS 5: Smart type-based defaults (safety net) ---
                    if (!bestMatch) {
                        const isSalaryQ = /salary|ctc|pay|compensation|package|remuneration/.test(qLower);
                        const isExpQ = /experience|years|\byear\b|months|exp\.?\b/.test(qLower) && !isSalaryQ;
                        const isNoticeQ = /notice\s*period|serving\s*notice|lwd/.test(qLower);
                        const isYearsQ = /years\b/.test(qLower) && !isSalaryQ;
                        
                        if (isYearsQ) {
                            bestMatch = '4'; // Default years
                        } else if (isNoticeQ) {
                            bestMatch = '15'; // Default notice period
                        } else if (isSalaryQ) {
                            bestMatch = (qLower.includes('expected') || qLower.includes('ectc') || qLower.includes('expect')) ? '3000000' : '2300000';
                        } else if (isExpQ) {
                            bestMatch = '4 Years';
                        }
                    }
                    
                    // --- PASS 6: Platform-specific overrides (post-match disambiguation) ---
                    if (bestMatch) {
                        const isSalaryQ = /salary|ctc|pay|compensation|package|remuneration/.test(qLower);
                        const isExpQ = /experience|years|\byear\b|months|exp\.?\b/.test(qLower) && !isSalaryQ;
                        const isNoticeQ = /notice\s*period|serving\s*notice|lwd/.test(qLower);
                        
                        if (isSalaryQ) {
                            bestMatch = (qLower.includes('expected') || qLower.includes('ectc') || qLower.includes('expect')) ? '3000000' : '2300000';
                        } else if (isExpQ && !/\d/.test(bestMatch)) {
                            if (/how many|years|months|\bexp\b/i.test(qLower)) {
                                bestMatch = '4';
                            }
                        } else if (isNoticeQ && !/\d/.test(bestMatch)) {
                            bestMatch = '15';
                        }
                    }
                    
                    return bestMatch;
                };               
                
                // Helper: Find best matching option
                const findBestMatch = (answer, options) => {
                    if (!answer || !options) return null;
                    const ans = answer.toLowerCase().trim();
                    
                    // Extract numeric value from answer for range matching
                    const numMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    const answerNum = numMatch ? parseFloat(numMatch[1]) : 0;
                    // Extract the integer part for exact matching (e.g., "4" -> 4)
                    const answerInt = Math.floor(answerNum);                    let bestOpt = null;
                    let bestScore = -1;
                    
                    for (const opt of options) {
                        const text = (opt.text || opt.label || '').toLowerCase().trim();
                        if (!text || text.includes('select')) continue;
                        let score = 0;
                        
                        // Extract number from option text for numeric comparison
                        const optNumMatch = text.match(/^(\d+(?:\.\d+)?)/);
                        const optNum = optNumMatch ? parseFloat(optNumMatch[1]) : -1;
                        const hasAnswerNum = numMatch !== null; // true if answer contains any number (including 0)
                        
                        // PRIORITY 1: Exact number match (e.g., answer="4" matches option="4 years" exactly)
                        if (optNum >= 0 && hasAnswerNum && optNum === answerNum) {
                            score = 120; // Highest priority for exact number match
                        }
                        // PRIORITY 2a: Rounded match (e.g., answer="4.2" matches "4" by rounding)
                        else if (optNum >= 0 && hasAnswerNum && answerNum > 0 && optNum === Math.round(answerNum)) {
                            score = 112;
                        }
                        // PRIORITY 2b: Floor match (e.g., answer="4.2" matches "4" by flooring)
                        else if (optNum >= 0 && hasAnswerNum && answerNum > 0 && optNum === answerInt) {
                            score = 110;
                        }
                        // PRIORITY 3: Exact full text match
                        else if (text === ans) {
                            score = 105;
                        }
                        // PRIORITY 4: Text contains answer OR answer contains text
                        // BUT protect against "4 years".includes("4 years") false positive
                        else if (text.includes(ans) || ans.includes(text)) {
                            // Guard: if both are numeric-like, verify the numbers actually match
                            if (optNum >= 0 && hasAnswerNum) {
                                // Only count as match if the numbers are close
                                if (Math.abs(optNum - answerNum) <= 0.5) {
                                    score = 100;
                                } else {
                                    // Substring match but numbers are far apart — likely a false positive
                                    score = 10;
                                }
                            } else {
                                score = 100;
                            }
                        }
                        // PRIORITY 5: Numeric range matching (e.g., answer='4' matches option='3 to 6 years')
                        else if (answerNum > 0) {
                            const rangeMatch = text.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                            if (rangeMatch) {
                                const min = parseFloat(rangeMatch[1]);
                                const max = parseFloat(rangeMatch[2]);
                                if (answerNum >= min && answerNum <= max) {
                                    score = 80;
                                }
                            }
                            // Match "X+" patterns (e.g., answer='4' matches option='3+ years')
                            else {
                                const plusMatch = text.match(/(\d+(?:\.\d+)?)\s*\+/);
                                if (plusMatch && answerNum >= parseFloat(plusMatch[1])) {
                                    score = 75;
                                }
                            }
                        }
                        
                        if (score > bestScore) {
                            bestScore = score;
                            bestOpt = opt;
                        }
                    }
                    
                    console.log('findBestMatch: answer=', answer, '-> selected:', bestOpt?.text, 'score:', bestScore);
                    return bestOpt;
                };
                
// Helper: Find best matching radio button for experience ranges
                const findBestRadioMatch = (answer, radios) => {
                    if (!answer || !radios || radios.length === 0) return null;
                    
                    const ans = answer.toLowerCase();
                    let bestRadio = null;
                    let bestScore = -1;
                    
                    const numMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    const answerNum = numMatch ? parseFloat(numMatch[1]) : 0;
                    
                    for (const radio of radios) {
                        const label = radio.closest('label')?.innerText || radio.parentElement?.innerText || '';
                        const lowerLabel = label.toLowerCase();
                        let score = 0;
                        
                        if (lowerLabel.includes(ans) || ans.includes(lowerLabel)) {
                            score = 100;
                        }
                        else if ((/\byes\b/i.test(lowerLabel) || lowerLabel.includes('serving')) &&
                                (/\byes\b/i.test(ans) || ans.includes('serving'))) {
                            score = 90;
                        }
                        else if (/\bno\b/i.test(lowerLabel) && /\bno\b/i.test(ans)) {
                            score = 90;
                        }
                        else if (answerNum > 0) {
                            // Day-based matching (notice period questions)
                            const dayRangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)\s*days/i);
                            const weekMatch = lowerLabel.match(/(?:within|less\s+than|under|up\s+to)\s+(\d+(?:\.\d+)?)\s*weeks/i);
                            const dayLessMatch = lowerLabel.match(/(?:within|less\s+than|under|up\s+to)\s+(\d+(?:\.\d+)?)\s*days/i);
                            const dayMoreMatch = lowerLabel.match(/(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)\s*days/i);
                            
                            if (dayRangeMatch) {
                                const min = parseFloat(dayRangeMatch[1]);
                                const max = parseFloat(dayRangeMatch[2]);
                                if (answerNum >= min && answerNum <= max) {
                                    const rangeSize = max - min;
                                    const offset = Math.abs(answerNum - (min + max) / 2);
                                    score = Math.max(0, 85 - (offset / Math.max(rangeSize, 1) * 20));
                                } else {
                                    const diff = Math.min(Math.abs(answerNum - min), Math.abs(answerNum - max));
                                    score = Math.max(0, 60 - diff * 2);
                                }
                            } else if (weekMatch) {
                                const boundDays = parseFloat(weekMatch[1]) * 7;
                                if (answerNum < boundDays) {
                                    score = 85;
                                } else {
                                    score = Math.max(0, 60 - (answerNum - boundDays) * 2);
                                }
                            } else if (dayLessMatch) {
                                const bound = parseFloat(dayLessMatch[1]);
                                if (answerNum < bound) score = 85;
                                else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 2);
                            } else if (dayMoreMatch) {
                                const bound = parseFloat(dayMoreMatch[1]);
                                if (answerNum >= bound) score = 85;
                                else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 2);
                            }
                            
                            // Year-based range matching
                            if (score === 0) {
                                const rangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                                if (rangeMatch) {
                                    const min = parseFloat(rangeMatch[1]);
                                    const max = parseFloat(rangeMatch[2]);
                                    if (answerNum >= min && answerNum <= max) {
                                        const rangeSize = max - min;
                                        const offset = Math.abs(answerNum - (min + max) / 2);
                                        score = Math.max(0, 80 - (offset / Math.max(rangeSize, 1) * 20));
                                    }
                                }
                            }
                            
                            // Prefix-based range matching
                            if (score === 0) {
                                const lessMatch = lowerLabel.match(/(?:less\s+than|under|up\s+to|within)\s+(\d+(?:\.\d+)?)/i);
                                const moreMatch = lowerLabel.match(/(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)/i);
                                if (lessMatch) {
                                    const bound = parseFloat(lessMatch[1]);
                                    if (answerNum < bound) {
                                        const rangeSize = Math.max(bound, 1);
                                        const offset = Math.abs(answerNum - 0);
                                        score = Math.max(0, 85 - (offset / rangeSize * 20));
                                    } else {
                                        const diff = Math.abs(answerNum - bound);
                                        score = Math.max(0, 60 - diff * 10);
                                    }
                                } else if (moreMatch) {
                                    const bound = parseFloat(moreMatch[1]);
                                    if (answerNum >= bound) {
                                        score = 85;
                                    } else {
                                        const diff = Math.abs(answerNum - bound);
                                        score = Math.max(0, 60 - diff * 10);
                                    }
                                }
                            }
                            
                            // Single year/number match
                            if (score === 0) {
                                const plusMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*\+/);
                                if (plusMatch) {
                                    const radioVal = parseFloat(plusMatch[1]);
                                    if (answerNum >= radioVal) {
                                        score = 90;
                                    } else {
                                        const diff = Math.abs(answerNum - radioVal);
                                        score = Math.max(0, 85 - diff * 10);
                                    }
                                } else {
                                    const singleNumMatch = lowerLabel.match(/(\d+(?:\.\d+)?)/);
                                    if (singleNumMatch) {
                                        const radioVal = parseFloat(singleNumMatch[1]);
                                        const diff = Math.abs(answerNum - radioVal);
                                        score = Math.max(0, 90 - diff * 10);
                                    }
                                }
                            }
                        }
                        
                        if (score > bestScore) {
                            bestScore = score;
                            bestRadio = radio;
                        }
                    }
                    
                    return bestRadio;
                };
                
                const findBestCustomRadioMatch = (answer, radios) => {
                    if (!answer || !radios || radios.length === 0) return null;
                    
                    const ans = answer.toLowerCase();
                    let bestRadio = null;
                    let bestScore = -1;
                    
                    const numMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    const answerNum = numMatch ? parseFloat(numMatch[1]) : 0;
                    
                    for (const radio of radios) {
                        const textEl = radio.querySelector('p, span');
                        const label = textEl?.innerText || radio.getAttribute('aria-label') || radio.innerText || radio.textContent || '';
                        const lowerLabel = label.toLowerCase().trim();
                        let score = 0;
                        
                        if (lowerLabel.includes(ans) || ans.includes(lowerLabel)) {
                            score = 100;
                        }
                        else if ((lowerLabel.includes('yes') || lowerLabel.includes('serving')) &&
                                (ans.includes('yes') || ans.includes('serving'))) {
                            score = 90;
                        }
                        else if (lowerLabel.includes('no') && ans.includes('no')) {
                            score = 90;
                        }
                        else if (answerNum > 0) {
                            // Convert label to numeric value (days or years)
                            let radioNum = 0;
                            let radioMin = 0;
                            let radioMax = 0;
                            let isRange = false;
                            let unit = 'years';
                            
                            // Check for day-based labels first (notice period questions)
                            const dayRangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)\s*days/i);
                            const weekMatch = lowerLabel.match(/(?:within|less\s+than|under|up\s+to)\s+(\d+(?:\.\d+)?)\s*weeks/i);
                            const dayLessMatch = lowerLabel.match(/(?:within|less\s+than|under|up\s+to)\s+(\d+(?:\.\d+)?)\s*days/i);
                            const dayMoreMatch = lowerLabel.match(/(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)\s*days/i);
                            const immediateMatch = lowerLabel.match(/immediate|right away|0\s*days/i);
                            
                            if (dayRangeMatch) {
                                radioMin = parseFloat(dayRangeMatch[1]);
                                radioMax = parseFloat(dayRangeMatch[2]);
                                isRange = true;
                                unit = 'days';
                            } else if (weekMatch) {
                                const weeks = parseFloat(weekMatch[1]);
                                radioMax = weeks * 7;
                                radioMin = 0;
                                isRange = true;
                                unit = 'days';
                            } else if (dayLessMatch) {
                                radioMax = parseFloat(dayLessMatch[1]);
                                radioMin = 0;
                                isRange = true;
                                unit = 'days';
                            } else if (dayMoreMatch) {
                                radioMin = parseFloat(dayMoreMatch[1]);
                                radioMax = 999;
                                isRange = true;
                                unit = 'days';
                            } else if (immediateMatch) {
                                radioNum = 0;
                                unit = 'days';
                            } else {
                                // Year-based range matching (experience questions)
                                const yearRangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                                if (yearRangeMatch) {
                                    radioMin = parseFloat(yearRangeMatch[1]);
                                    radioMax = parseFloat(yearRangeMatch[2]);
                                    isRange = true;
                                    unit = 'years';
                                }
                            }
                            
                            if (isRange) {
                                if (unit === 'days') {
                                    // For notice period: answer "7" means 7 days
                                    if (answerNum >= radioMin && answerNum <= radioMax) {
                                        const rangeSize = Math.max(radioMax - radioMin, 1);
                                        const offset = Math.abs(answerNum - (radioMin + radioMax) / 2);
                                        score = Math.max(0, 85 - (offset / rangeSize * 20));
                                    } else {
                                        const diff = Math.min(Math.abs(answerNum - radioMin), Math.abs(answerNum - radioMax));
                                        score = Math.max(0, 60 - diff * 2);
                                    }
                                } else {
                                    if (answerNum >= radioMin && answerNum <= radioMax) {
                                        const rangeSize = radioMax - radioMin;
                                        const offset = Math.abs(answerNum - (radioMin + radioMax) / 2);
                                        score = Math.max(0, 80 - (offset / Math.max(rangeSize, 1) * 20));
                                    }
                                }
                            }
                            
                            if (score === 0 && !isRange) {
                                // Prefix-based matching for day units
                                const lessDaysMatch = lowerLabel.match(/(?:less\s+than|under|up\s+to|within)\s+(\d+(?:\.\d+)?)/i);
                                const moreDaysMatch = lowerLabel.match(/(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)/i);
                                const lessWeeksMatch = lowerLabel.match(/(?:less\s+than|under|up\s+to|within)\s+(\d+(?:\.\d+)?)\s*weeks/i);
                                
                                if (lessWeeksMatch) {
                                    const boundDays = parseFloat(lessWeeksMatch[1]) * 7;
                                    if (answerNum < boundDays) score = 85;
                                    else score = Math.max(0, 60 - (answerNum - boundDays) * 2);
                                } else if (lessDaysMatch) {
                                    const bound = parseFloat(lessDaysMatch[1]);
                                    if (answerNum < bound) score = 85;
                                    else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 2);
                                } else if (moreDaysMatch) {
                                    const bound = parseFloat(moreDaysMatch[1]);
                                    if (answerNum >= bound) score = 85;
                                    else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 2);
                                }
                                
                                // Year-based prefix matching
                                if (score === 0) {
                                    const lessYearMatch = lowerLabel.match(/(?:less\s+than|under|up\s+to)\s+(\d+(?:\.\d+)?)/i);
                                    const moreYearMatch = lowerLabel.match(/(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)/i);
                                    if (lessYearMatch) {
                                        const bound = parseFloat(lessYearMatch[1]);
                                        if (answerNum < bound) score = 85;
                                        else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 10);
                                    } else if (moreYearMatch) {
                                        const bound = parseFloat(moreYearMatch[1]);
                                        if (answerNum >= bound) score = 85;
                                        else score = Math.max(0, 60 - Math.abs(answerNum - bound) * 10);
                                    }
                                }
                            }
                            
                            if (score === 0) {
                                const plusMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*\+/);
                                if (plusMatch) {
                                    const radioVal = parseFloat(plusMatch[1]);
                                    if (answerNum >= radioVal) score = 90;
                                    else score = Math.max(0, 85 - Math.abs(answerNum - radioVal) * 10);
                                } else {
                                    const singleNumMatch = lowerLabel.match(/(\d+(?:\.\d+)?)/);
                                    if (singleNumMatch) {
                                        const radioVal = parseFloat(singleNumMatch[1]);
                                        const diff = Math.abs(answerNum - radioVal);
                                        score = Math.max(0, 90 - diff * 10);
                                    }
                                }
                            }
                        }
                        
                        if (score > bestScore) {
                            bestScore = score;
                            bestRadio = radio;
                        }
                    }
                    
                    return bestRadio;
                };
                
                const clickCustomRadio = (element) => {
                    if (!element) return;
                    element.scrollIntoView({ block: 'center' });
                    element.click();
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new Event('click', { bubbles: true }));
                    const roleInput = element.querySelector('input[type="radio"]');
                    if (roleInput) {
                        roleInput.checked = true;
                        roleInput.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                };
                
                // Helper: Find salary range match for range-based options
                const findSalaryRangeMatch = (answer, options, isCurrentSalary) => {
                    if (!answer || !options || options.length === 0) return null;
                    
                    // Extract numeric salary from answer (e.g., "15.3 LPA" → 15.3)
                    const salaryMatch = answer.match(/(\d+(?:\.\d+)?)/);
                    if (!salaryMatch) return null;
                    const salary = parseFloat(salaryMatch[1]);
                    
                    let bestMatch = null;
                    let bestScore = -1;
                    
                    for (const opt of options) {
                        const text = (opt.text || opt.label || '').toLowerCase();
                        
                        // Match patterns like "0-5 Lacs", "10-15 Lacs Per Annum", "5 to 10 LPA"
                        const rangeMatch = text.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                        if (rangeMatch) {
                            const min = parseFloat(rangeMatch[1]);
                            const max = parseFloat(rangeMatch[2]);
                            
                            // Check if salary falls within this range
                            if (salary >= min && salary <= max) {
                                // Score based on how centered the salary is in the range
                                const rangeCenter = (min + max) / 2;
                                const score = 1 - Math.abs(salary - rangeCenter) / (max - min);
                                
                                if (score > bestScore) {
                                    bestScore = score;
                                    bestMatch = opt;
                                }
                            }
                        }
                    }
                    
                    return bestMatch;
                };                
                
                // Helper: Check if answer is affirmative
                const isYes = (ans) => ans && ['yes', 'true', 'agree'].some(w => ans.toLowerCase().includes(w));
                const isNo = (ans) => ans && ['no', 'false'].some(w => ans.toLowerCase().includes(w));

                // Helper: Detect if question text is a Yes/No question
                const isLikelyYesNoQuestion = (text) => {
                    if (!text) return false;
                    const t = text.replace(/[*?]/g, '').trim().toLowerCase();
                    return /^(have you|do you|are you|will you|can you|did you|is your|are your|does your|would you|could you|should you|don't you|doesn't|isn't|aren't|wasn't|weren't|haven't|hasn't|had you|own you|owned you)\b/.test(t) ||
                           t.startsWith('apply only ') ||
                           t.includes('willing') ||
                           t.includes('comfortable') ||
                           t.includes('localite') ||
                           t.includes('relocate') ||
                           t.includes('relocation') ||
                           t.includes('open to');
                };

                const isLinkedIn = document.title.includes('LinkedIn') || window.location.href.includes('linkedin.com');
                const isNaukri = document.title.includes('Naukri') || window.location.href.includes('naukri.com');
                const isInstahyre = document.title.includes('Instahyre') || window.location.href.includes('instahyre.com');

                // Helper: Query selector that can penetrate Shadow DOM
                const queryDeep = (selector, root = document) => {
                    let match = root.querySelector(selector);
                    if (match) return match;
                    const hosts = root.querySelectorAll('*');
                    for (const host of hosts) {
                        if (host.shadowRoot) {
                            match = queryDeep(selector, host.shadowRoot);
                            if (match) return match;
                        }
                    }
                    return null;
                };

                const queryAllDeep = (selector, root = document, results = []) => {
                    root.querySelectorAll(selector).forEach(el => results.push(el));
                    root.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) queryAllDeep(selector, el.shadowRoot, results);
                    });
                    return results;
                };

                // ============================================================
                // LINKEDIN LOGIC (CLEAN REWRITE FOR 2025-2026)
                // Handles obfuscated classes and dynamic DOM structure
                // ============================================================
                if (isLinkedIn) {
                    console.log('=== LINKEDIN AUTOMATION STARTED ===');
                    
                    // Helper: Find elements by text content (Shadow aware)
                    const findByText = (selector, text, exact = false, root = document) => {
                        const elements = queryAllDeep(selector, root);
                        const searchText = text.toLowerCase();
                        return Array.from(elements).find(el => {
                            const elText = el.innerText.toLowerCase();
                            return exact ? elText === searchText : elText.includes(searchText);
                        });
                    };
                    
                    // Helper: Find Easy Apply button on job details page
                    const findEasyApplyButton = () => {
                        console.log('Looking for Easy Apply button...');
                        // 1. By class and id (most reliable - verified 2026)
                        let btn = queryDeep('button.jobs-apply-button') || queryDeep('#jobs-apply-button-id');
                        if (btn && isVisible(btn)) return btn;
                        
                        // 2. By aria-label (found during inspection)
                        btn = queryDeep('button[aria-label*="Easy Apply"], a[aria-label*="Easy Apply"]');
                        if (btn && isVisible(btn)) return btn;
                        
                        // 3. By data-view-name (LinkedIn uses <button> not <a> as of 2026)
                        btn = queryDeep('button[data-view-name="job-apply-button"], button.top-card-layout__cta--primary');
                        if (btn && isVisible(btn)) return btn;

                        // 4. By text search (broadest fallback)
                        btn = findByText('button', 'easy apply') || findByText('a', 'easy apply');
                        if (btn && isVisible(btn)) return btn;

                        return null;
                    };

                    // Helper: Fill LinkedIn form fields
                    const handleLinkedInForm = (modal) => {
                        console.log('Filling LinkedIn form fields (Shadow aware)...');

                        // ──────────────────────────────────────────────────
                        // SAFETY GUARD: If this modal is actually a safety
                        // reminder popup (mislabeled as 'form' by checkModals),
                        // click "Continue applying" and return immediately.
                        // This is the last line of defense.
                        // ──────────────────────────────────────────────────
                        {
                            const modalText = (modal.innerText || '').toLowerCase();
                            // Also check ancestor dialog text (modal may be a sub-container)
                            const dialogAncestor = modal.closest('[role="dialog"], .artdeco-modal, [class*="modal"]');
                            const ancestorText = dialogAncestor ? (dialogAncestor.innerText || '').toLowerCase() : '';
                            const combinedText = modalText + ' ' + ancestorText;
                            const safetyKeywords = ['safety reminder', 'job search safety', 'research the company', 'report suspicious', 'review job post', 'continue applying'];
                            if (safetyKeywords.some(kw => combinedText.includes(kw))) {
                                console.log('SAFETY GUARD (form handler): Modal is a safety reminder popup. Looking for "Continue applying" button...');
                                const btns = Array.from(queryAllDeep('button, span[role="button"]', modal));
                                const allBtns = dialogAncestor ? btns.concat(Array.from(queryAllDeep('button, span[role="button"]', dialogAncestor))) : btns;
                                const continueBtn = allBtns.find(b => (b.innerText || '').toLowerCase().includes('continue applying')) ||
                                                   allBtns.find(b => (b.innerText || '').toLowerCase().trim() === 'continue') ||
                                                   allBtns[allBtns.length - 1];  // fallback: last button
                                if (continueBtn) {
                                    console.log('SAFETY GUARD: Clicking "Continue applying":', continueBtn.innerText);
                                    continueBtn.scrollIntoView({block: 'center'});
                                    continueBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                    continueBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                    continueBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                    continueBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                    continueBtn.click();
                                    return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                                }
                                console.log('SAFETY GUARD: Safety modal detected but no "Continue applying" button found.');
                                return 'LINKEDIN_FORM_STUCK: Safety modal detected, no continue button';
                            }
                        }

                        const formResults = [];

                        // Helper: Get label text associated with input (radio/checkbox)
                        const getInputLabelText = (input) => {
                            if (!input) return '';
                            let labelText = '';
                            if (input.id) {
                                const labelEl = document.querySelector(`label[for="${input.id}"]`);
                                if (labelEl) labelText = labelEl.innerText || labelEl.textContent;
                            }
                            if (!labelText) {
                                const labelEl = input.closest('label');
                                if (labelEl) labelText = labelEl.innerText || labelEl.textContent;
                            }
                            if (!labelText && input.parentElement) {
                                const siblingLabel = input.parentElement.querySelector('label');
                                if (siblingLabel) labelText = siblingLabel.innerText || siblingLabel.textContent;
                                else labelText = input.parentElement.innerText || input.parentElement.textContent;
                            }
                            // LinkedIn: text is in <p> inside <div role="radio">
                            if (!labelText) {
                                const roleRadioParent = input.closest('[role="radio"]');
                                if (roleRadioParent) {
                                    const textEl = roleRadioParent.querySelector('p, span');
                                    if (textEl) labelText = textEl.innerText || textEl.textContent;
                                }
                            }
                            return (labelText || '').trim().toLowerCase();
                        };

                        // Helper: Robust click on input (clicks label if input is hidden)
                        const clickInput = (input) => {
                            if (!input) return;
                            
                            // LinkedIn: click the <div role="radio"> container
                            const roleRadioParent = input.closest('[role="radio"]');
                            if (roleRadioParent) {
                                console.log('Clicking role=radio container:', roleRadioParent.innerText);
                                roleRadioParent.scrollIntoView({ block: 'center' });
                                roleRadioParent.click();
                                input.checked = true;
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                                return;
                            }
                            
                            let label = null;
                            if (input.id) {
                                label = document.querySelector(`label[for="${input.id}"]`);
                            }
                            if (!label) {
                                label = input.closest('label');
                            }
                            if (!label && input.parentElement) {
                                label = input.parentElement.querySelector('label');
                            }
                            
                            if (label) {
                                console.log('Clicking input label:', label.innerText || label.textContent);
                                label.scrollIntoView({ block: 'center' });
                                label.click();
                            } else {
                                console.log('Clicking input directly:', input.id || input.name);
                                input.scrollIntoView({ block: 'center' });
                                input.click();
                            }
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            input.dispatchEvent(new Event('click', { bubbles: true }));
                        };
                        
                        // Helper: Check if a field is already filled
                        const isFieldPreFilled = (element) => {
                            if (!element) return false;
                            if (element.disabled) return true;
                            // For checkboxes/radios, readOnly is not an applicable check for filled state

                            const tagName = element.tagName.toLowerCase();
                            const value = element.value ? element.value.trim() : "";

                            if (tagName === 'input' || tagName === 'textarea') {
                                // if it's radio or checkbox, it's prefilled if checked
                                if (element.type === 'radio' || element.type === 'checkbox') return element.checked;
                                return value.length > 0;
                            }

                            if (tagName === 'select') {
                                // LinkedIn uses "Select an option" as placeholder.
                                const isPlaceholder = !value || value === "" || value.toLowerCase().includes("select an option") || element.options[element.selectedIndex]?.text.toLowerCase().includes("select");
                                return !isPlaceholder;
                            }
                            
                            // Custom elements with aria-valuenow or aria-checked
                            if (element.hasAttribute('aria-valuenow')) {
                                return element.getAttribute('aria-valuenow').trim().length > 0;
                            }
                            if (element.hasAttribute('aria-checked')) {
                                return element.getAttribute('aria-checked') === 'true';
                            }
                            
                            return false;
                        };
                        
                        // Helper: Safely fill React controlled inputs
                        const fillReactInput = (element, value) => {
                            if (!element) return false;
                            const previousValue = element.value;
                            
                            // 1. Try React native setter
                            try {
                                const proto = element.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                                if (nativeSetter) {
                                    nativeSetter.call(element, value);
                                } else {
                                    element.value = value;
                                }
                            } catch(e) {
                                element.value = value;
                            }
                            
                            // 2. Dispatch events
                            element.dispatchEvent(new Event('input', { bubbles: true }));
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                            element.dispatchEvent(new Event('blur', { bubbles: true }));
                            
                            // 3. Fallback for stubborn frameworks
                            if (element.value !== value && Reflect.has(element, 'value')) {
                                Reflect.set(element, 'value', value);
                                element.dispatchEvent(new Event('input', { bubbles: true }));
                            }
                            
                            return element.value !== previousValue || element.value === value;
                        };

                        // 0. FIRST: Check for visible autocomplete/typeahead dropdown options
                        // LinkedIn renders these in portals outside the modal, so search entire document
                        // This MUST run before anything else to select from already-open dropdowns
                        {
                            const dropdownSelectors = '.typeahead-input__dropdown-item, [role="option"], .artdeco-typeahead__result, [data-test-typeahead-item], li[class*="typeahead"], .basic-typeahead__selectable';
                            const allDropdownOpts = document.querySelectorAll(dropdownSelectors);
                            console.log('Pre-check: scanning for visible autocomplete options:', allDropdownOpts.length);
                            
                            for (const option of allDropdownOpts) {
                                if (option.offsetParent !== null) {
                                    const text = option.innerText.trim();
                                    if (text && text.length > 2 && !text.toLowerCase().includes('select')) {
                                        console.log('CLICKING VISIBLE AUTOCOMPLETE OPTION:', text);
                                        option.click();
                                        return 'LINKEDIN_AUTOCOMPLETE_SELECTED|' + JSON.stringify([{question: 'autocomplete', answer: text, inputType: 'typeahead'}]);
                                    }
                                }
                            }
                        }

                        // 1. Handle text/numeric inputs
                        const textInputs = queryAllDeep('input[type="text"], input[type="number"], input:not([type]), textarea', modal);
                        for (const input of textInputs) {
                            // ROBUST LABEL DETECTION: Try multiple methods to find the label
                            let labelText = '';
                            
                            // Method 1: .fb-dash-form-element parent (LinkedIn's newer structure)
                            if (!labelText) {
                                const fbParent = input.closest('.fb-dash-form-element');
                                if (fbParent) {
                                    const lbl = fbParent.querySelector('label');
                                    if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                                }
                            }
                            
                            // Method 2: label[for] by input id
                            if (!labelText && input.id) {
                                const lbl = queryDeep(`label[for="${input.id}"]`, modal);
                                if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                            }
                            
                            // Method 3: aria-label attribute
                            if (!labelText) {
                                labelText = input.getAttribute('aria-label') || '';
                            }
                            
                            // Method 4: aria-labelledby attribute
                            if (!labelText) {
                                const labelledBy = input.getAttribute('aria-labelledby');
                                if (labelledBy) {
                                    const lbl = document.getElementById(labelledBy);
                                    if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                                }
                            }
                            
                            // Method 5: Walk up parent tree looking for label siblings
                            if (!labelText) {
                                let parent = input.parentElement;
                                for (let i = 0; i < 5 && parent && parent !== modal; i++) {
                                    // Check for label element in the same container
                                    const lbl = parent.querySelector('label');
                                    if (lbl && lbl.innerText && lbl.innerText.trim().length > 2) {
                                        labelText = lbl.innerText.trim();
                                        break;
                                    }
                                    // Check previous sibling for label
                                    let prevSib = parent.previousElementSibling;
                                    while (prevSib) {
                                        if (prevSib.tagName === 'LABEL' || prevSib.querySelector?.('label')) {
                                            const found = prevSib.tagName === 'LABEL' ? prevSib : prevSib.querySelector('label');
                                            if (found && found.innerText && found.innerText.trim().length > 2) {
                                                labelText = found.innerText.trim();
                                                break;
                                            }
                                        }
                                        // Also check for span/div that acts as label
                                        if (prevSib.innerText && prevSib.innerText.trim().length > 2 && prevSib.innerText.trim().length < 100) {
                                            const text = prevSib.innerText.trim();
                                            if (!text.includes('Select') && !text.includes('select')) {
                                                labelText = text;
                                                break;
                                            }
                                        }
                                        prevSib = prevSib.previousElementSibling;
                                    }
                                    if (labelText) break;
                                    parent = parent.parentElement;
                                }
                            }
                            
                            // Method 6: Look in form group containers (LinkedIn Easy Apply sections)
                            if (!labelText) {
                                const formGroup = input.closest('.jobs-easy-apply-form-section__question, [data-test-form-element], fieldset, .artdeco-form-field, .jobs-easy-apply-form-element');
                                if (formGroup) {
                                    const legend = formGroup.querySelector('legend, .artdeco-form-field__label');
                                    if (legend) {
                                        labelText = legend.innerText || legend.textContent || '';
                                    }
                                    if (!labelText) {
                                        const spans = formGroup.querySelectorAll('span, div, p, label');
                                        for (const el of spans) {
                                            const t = (el.innerText || el.textContent || '').trim();
                                            if (t.length > 2 && t.length < 200 && !t.includes('Select an option') && !t.includes('select an option')) {
                                                // Make sure this element is not inside the input itself
                                                if (!input.contains(el)) {
                                                    labelText = t;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Method 7: Placeholder as last resort
                            if (!labelText) {
                                labelText = input.placeholder || '';
                            }
                            
                            // Clean up the label text (remove asterisks, "required" text, etc.)
                            labelText = labelText.replace(/\*+$/g, '').replace(/\s*This field is required/gi, '').trim();
                            
                            console.log('LABEL DETECTION for input:', input.tagName, input.type || 'textarea', '| Detected label:', JSON.stringify(labelText));
                            
                            const lowerLabel = labelText.toLowerCase();
                            const isLocationField = lowerLabel.includes('location') || lowerLabel.includes('city');
                            
                            // Special handling: Location fields that have text but show validation errors
                            // LinkedIn requires selecting from autocomplete dropdown, not just text
                            if (isLocationField && isFieldPreFilled(input) && isVisible(input)) {
                                // Check if there's a visible validation error on this field
                                const parentContainer = input.closest('.fb-dash-form-element') || input.closest('.jobs-easy-apply-form-section__question') || input.parentElement?.parentElement;
                                const hasError = parentContainer && (parentContainer.querySelector('.artdeco-inline-feedback--error') || parentContainer.querySelector('.fb-dash-form-element__error-field'));
                                const globalError = queryDeep('.artdeco-inline-feedback--error', modal);
                                
                                if (hasError || globalError) {
                                    console.log('Location field has text but validation error — re-triggering autocomplete for:', labelText, 'current value:', input.value);
                                    const currentVal = input.value;
                                    
                                    // Try a different strategy: click the input field multiple times to open dropdown
                                    input.click();
                                    
                                    // Dispatch multiple events to trigger dropdown
                                    input.focus();
                                    input.dispatchEvent(new Event('click', { bubbles: true }));
                                    input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('focus', { bubbles: true }));
                                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                    input.dispatchEvent(new KeyboardEvent('keyup', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
                                    
                                    return 'LINKEDIN_LOCATION_RETRIGGERED';
                                }
                                continue;  // location pre-filled and no error — skip
                            }
                            
                            if (!isVisible(input)) continue;
                            
                            // Check if this field has a validation error — if so, clear and refill
                            const inputParent = input.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question, [class*="form-element"]');
                            let hasError = !!(inputParent && inputParent.querySelector('.artdeco-inline-feedback--error'));
                            if (!hasError && inputParent) {
                                const helperPs = inputParent.querySelectorAll('[data-testid*="helper-text"] p, [data-testid*="error"] p');
                                for (const hp of helperPs) {
                                    const t = (hp.innerText || '').toLowerCase();
                                    if (t.includes('invalid') || t.includes('required') || t.includes('enter a valid') || t.includes('please enter')) {
                                        hasError = true;
                                        break;
                                    }
                                }
                            }
                            if (isFieldPreFilled(input) && !hasError) continue;
                            
                            // Clear invalid field before refilling
                            if (hasError) {
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                if (nativeSetter) nativeSetter.call(input, '');
                                else input.value = '';
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                                console.log('Cleared invalid field:', labelText);
                            }
                            
                            // Check if input expects numeric values only
                            const isNumericInput = input.type === 'number' || 
                                                  input.getAttribute('inputmode') === 'numeric' ||
                                                  input.getAttribute('pattern')?.includes('\\d') ||
                                                  input.className?.toLowerCase().includes('number') ||
                                                  input.className?.toLowerCase().includes('decimal') ||
                                                  (labelText && /how many years|total years|relevant experience|experience with|decimal number|numeric|experience you are having|years of experience|experience in years|enter a decimal/i.test(labelText));
                            
                            // Try to get answer from fuzzyMatch first
                            let answer = labelText ? fuzzyMatch(labelText) : null;
                            
                            // If the answer is notice period-related and we are filling a text input,
                            // we must use a numeric value (e.g. '15')
                            if (answer && (answer === 'Serving Notice Period' || /notice|np|lwd|days/i.test(labelText))) {
                                const defaultObj = KNOWN_PATTERNS_WITH_DEFAULTS[labelText.toLowerCase()];
                                if (defaultObj && defaultObj.category === 'notice_period') {
                                    const match = answer.match(/(\d+)/);
                                    answer = match ? match[1] : '15';
                                } else if (/np|notice/i.test(labelText)) {
                                    const match = answer.match(/(\d+)/);
                                    answer = match ? match[1] : '15';
                                }
                            }
                            
                            // If it's a numeric input, extract just the number from the answer
                            if (answer && isNumericInput) {
                                const numericMatch = answer.match(/(\d+\.?\d*)/);
                                if (numericMatch) {
                                    let numVal = parseFloat(numericMatch[1]);
                                    // LinkedIn rejects decimals in experience fields — round up
                                    if (numVal % 1 !== 0 && /experience|years/i.test(labelText)) {
                                        numVal = Math.ceil(numVal);
                                        console.log('Rounded up experience:', numericMatch[1], '->', numVal);
                                    }
                                    answer = String(numVal);
                                    console.log('Extracted numeric value for number field:', answer);
                                } else {
                                    // Fallback if answer contained no numbers but input expects numeric/years
                                    answer = /notice|lwd/i.test(labelText) ? '15' : '4';
                                    console.log('Fallback numeric value for number field:', answer);
                                }
                            }
                            
                            // Yes/no question override — if fuzzyMatch returned nothing or a numeric answer,
                            // and the question is a yes/no question, answer "Yes" (or "No" for negative indicators)
                            if (!answer || /^\d+$/.test(answer.trim())) {
                                if (labelText && isLikelyYesNoQuestion(labelText)) {
                                    const ynNegativeIndicators = ['sponsorship', 'visa', 'referral', 'referred',
                                        'conflict of interest', 'relative', 'family member', 'criminal', 'felony',
                                        'convict', 'disability', 'previously employed', 'ever been employed',
                                        'currently employed', 'worked at', 'worked for', 'worked with'];
                                    const lowerQ = labelText.toLowerCase();
                                    const isNeg = ynNegativeIndicators.some(p => lowerQ.includes(p));
                                    answer = isNeg ? 'No' : 'Yes';
                                    console.log('LinkedIn form: Yes/no override, answer:', answer, '| question:', labelText.substring(0, 80));
                                }
                            }
                            
                            // KEYWORD-BASED FALLBACK: If fuzzyMatch returned nothing, try common field patterns
                            if (!answer) {
                                const combinedText = (lowerLabel + ' ' + (input.placeholder || '').toLowerCase()).trim();
                                
                                // Yes/no phrasing safety net — catch questions that don't start with
                                // standard yes/no prefixes but contain yes/no phrasing keywords
                                if (combinedText.includes('willing') || combinedText.includes('comfortable') ||
                                    combinedText.includes('relocate') || combinedText.includes('able to') ||
                                    combinedText.includes('authorized') || combinedText.includes('eligible') ||
                                    combinedText.includes('require sponsorship') || combinedText.includes('work on site') ||
                                    combinedText.includes('work onsite')) {
                                    const ynNegInd = ['sponsorship', 'visa', 'require sponsorship'];
                                    const isNeg = ynNegInd.some(p => combinedText.includes(p));
                                    answer = isNeg ? 'No' : 'Yes';
                                    console.log('LinkedIn form: Yes/no keyword fallback, answer:', answer, '| text:', combinedText.substring(0, 80));
                                } else if (combinedText.includes('skill') || combinedText.includes('expertise') || combinedText.includes('technologies') || combinedText.includes('tech stack')) {
                                    answer = 'Java, JavaScript, HTML, CSS, ReactJS, NodeJS, Python, Spring Boot, Hibernate, AWS, SQL, Docker, Kubernetes';
                                    console.log('Fallback: Filling skill set field');
                                } else if (combinedText.includes('location') || (combinedText.includes('city') && !combinedText.includes('street'))) {
                                    answer = 'Noida';
                                    console.log('Fallback: Filling location/city field');
                                } else if (combinedText.includes('street') || combinedText.includes('address line')) {
                                    answer = 'Sector 137';
                                    console.log('Fallback: Filling street address');
                                } else if (combinedText.includes('zip') || combinedText.includes('postal') || combinedText.includes('pincode') || combinedText.includes('pin code')) {
                                    answer = '201301';
                                    console.log('Fallback: Filling zip/postal code');
                                } else if (combinedText.match(/\bcity\b/) || combinedText.includes('town')) {
                                    answer = 'Noida';
                                    console.log('Fallback: Filling city');
                                } else if (combinedText.includes('state') || combinedText.includes('province')) {
                                    answer = 'Uttar Pradesh';
                                    console.log('Fallback: Filling state/province');
                                } else if (combinedText.includes('country') || combinedText.includes('nation')) {
                                    answer = 'India';
                                    console.log('Fallback: Filling country');
                                } else if (combinedText.includes('phone') || combinedText.includes('mobile') || combinedText.includes('contact number')) {
                                    answer = '7905828880';
                                    console.log('Fallback: Filling phone/mobile');
                                } else if (combinedText.includes('email')) {
                                    answer = 'siddhant3646@gmail.com';
                                    console.log('Fallback: Filling email');
                                } else if (combinedText.includes('full name') || combinedText.includes('your name') || combinedText.includes('candidate name')) {
                                    answer = 'Siddhant Singh';
                                    console.log('Fallback: Filling name field');
                                } else if (combinedText.includes('summary') || combinedText.includes('cover letter') || combinedText.includes('about yourself') || combinedText.includes('why should') || combinedText.includes('why do you want') || combinedText.includes('tell us about') || combinedText.includes('anything else')) {
                                    answer = 'I am a Java Full Stack Developer with 4 years of experience in building scalable applications using Java, Spring Boot, React.js, and cloud technologies. I am eager to contribute my skills to your team.';
                                    console.log('Fallback: Filling summary/cover letter');
                                } else if (combinedText.includes('notice') || combinedText.includes('lwd') || combinedText.includes('how soon')) {
                                    answer = '7';
                                    console.log('Fallback: Filling notice/join period');
                                } else if (combinedText.includes('linkedin') || combinedText.includes('profile url')) {
                                    answer = 'https://www.linkedin.com/in/siddhant-singh';
                                    console.log('Fallback: Filling LinkedIn URL');
                                } else if (combinedText.includes('github') || combinedText.includes('portfolio')) {
                                    answer = 'https://github.com/siddhant3646';
                                    console.log('Fallback: Filling GitHub/portfolio URL');
                                } else if (combinedText.includes('certification') || combinedText.includes('certificate')) {
                                    answer = 'AWS Certified, Java Certified';
                                    console.log('Fallback: Filling certifications');
                                } else if (combinedText.includes('reason') || combinedText.includes('seeking') || combinedText.includes('looking for a change')) {
                                    answer = 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals';
                                    console.log('Fallback: Filling reason for change');
                                }
                            }
                            
                            if (answer) {
                                console.log('Filling text field:', labelText || '(unlabeled)', 'with:', answer);
                                
                                if (input.hasAttribute('maxlength')) {
                                    const maxLen = parseInt(input.getAttribute('maxlength'), 10);
                                    if (!isNaN(maxLen) && answer.length > maxLen) {
                                        console.log(`Truncating answer from ${answer.length} to maxlength ${maxLen}`);
                                        answer = answer.substring(0, maxLen);
                                    }
                                }
                                
                                fillReactInput(input, answer);
                                
                                formResults.push({ question: labelText || '(unlabeled)', answer: answer, inputType: input.tagName === 'TEXTAREA' ? 'textarea' : 'text' });
                                
                                // If this is a location field, trigger autocomplete dropdown
                                if (isLocationField) {
                                    console.log('Location field filled — triggering autocomplete dropdown...');
                                    input.focus();
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('focus', { bubbles: true }));
                                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
                                    
                                    // Keep the input visible and focused for dropdown to appear
                                    input.scrollIntoView({block: 'center', behavior: 'instant'});
                                    
                                    return 'LINKEDIN_LOCATION_FILLED_WAITING_DROPDOWN';
                                }
                            } else if (!labelText && isVisible(input) && !isFieldPreFilled(input)) {
                                // LAST RESORT: Completely unlabeled field — log it for debugging
                                console.log('WARNING: Completely unlabeled empty input found, tag:', input.tagName, 'type:', input.type, 'placeholder:', input.placeholder, 'class:', (input.className || '').substring(0, 80));
                            }
                        }

                        // 2. Handle Select elements (native and custom LinkedIn dropdowns)
                        const nativeSelects = queryAllDeep('select', modal);
                        const customDropdowns = queryAllDeep('[role="combobox"], .jobs-easy-apply-form-section__dropdown, button[aria-expanded], [data-test-text-entity-list-form-select]', modal);
                        
                        // Process native <select> elements
                        for (const select of nativeSelects) {
                            if (!isVisible(select) || isFieldPreFilled(select)) continue;
                            
                            // ROBUST LABEL DETECTION for selects (same as text inputs)
                            let labelText = '';
                            
                            // Method 1: .fb-dash-form-element parent
                            if (!labelText) {
                                const fbParent = select.closest('.fb-dash-form-element');
                                if (fbParent) {
                                    const lbl = fbParent.querySelector('label');
                                    if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                                }
                            }
                            // Method 2: label[for]
                            if (!labelText && select.id) {
                                const lbl = queryDeep(`label[for="${select.id}"]`, modal);
                                if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                            }
                            // Method 3: aria-label
                            if (!labelText) {
                                labelText = select.getAttribute('aria-label') || '';
                            }
                            // Method 4: aria-labelledby
                            if (!labelText) {
                                const labelledBy = select.getAttribute('aria-labelledby');
                                if (labelledBy) {
                                    const lbl = document.getElementById(labelledBy);
                                    if (lbl) labelText = lbl.innerText || lbl.textContent || '';
                                }
                            }
                            // Method 5: Walk up parent tree
                            if (!labelText) {
                                let parent = select.parentElement;
                                for (let i = 0; i < 5 && parent && parent !== modal; i++) {
                                    const lbl = parent.querySelector('label');
                                    if (lbl && lbl.innerText && lbl.innerText.trim().length > 2) {
                                        labelText = lbl.innerText.trim();
                                        break;
                                    }
                                    let prevSib = parent.previousElementSibling;
                                    while (prevSib) {
                                        if (prevSib.tagName === 'LABEL' || prevSib.querySelector?.('label')) {
                                            const found = prevSib.tagName === 'LABEL' ? prevSib : prevSib.querySelector('label');
                                            if (found && found.innerText && found.innerText.trim().length > 2) {
                                                labelText = found.innerText.trim();
                                                break;
                                            }
                                        }
                                        if (prevSib.innerText && prevSib.innerText.trim().length > 2 && prevSib.innerText.trim().length < 200) {
                                            const text = prevSib.innerText.trim();
                                            if (!text.includes('Select') && !text.includes('select')) {
                                                labelText = text;
                                                break;
                                            }
                                        }
                                        prevSib = prevSib.previousElementSibling;
                                    }
                                    if (labelText) break;
                                    parent = parent.parentElement;
                                }
                            }
                            // Method 6: Form group containers
                            if (!labelText) {
                                const formGroup = select.closest('.jobs-easy-apply-form-section__question, [data-test-form-element], fieldset, .artdeco-form-field, .jobs-easy-apply-form-element');
                                if (formGroup) {
                                    const legend = formGroup.querySelector('legend, .artdeco-form-field__label');
                                    if (legend) labelText = legend.innerText || legend.textContent || '';
                                    if (!labelText) {
                                        const spans = formGroup.querySelectorAll('span, div, p, label');
                                        for (const el of spans) {
                                            const t = (el.innerText || el.textContent || '').trim();
                                            if (t.length > 2 && t.length < 200 && !t.includes('Select an option') && !t.includes('select an option')) {
                                                if (!select.contains(el)) {
                                                    labelText = t;
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Clean up
                            labelText = labelText.replace(/\*+$/g, '').replace(/\s*This field is required/gi, '').trim();
                            
                            console.log('SELECT LABEL DETECTION:', JSON.stringify(labelText), '| current value:', select.value);
                            
                            const lowerLabel = labelText.toLowerCase();
                            
                            // SPECIAL CASE: For "learn about" / "hear about" / "source" questions, select ANY first option
                            const isLearnAboutQuestion = lowerLabel.includes('learn about') || 
                                                        lowerLabel.includes('hear about') || 
                                                        lowerLabel.includes('how did you') ||
                                                        lowerLabel.includes('where did you') ||
                                                        lowerLabel.includes('source');
                            
                            if (isLearnAboutQuestion) {
                                console.log('Learn about question detected in native select - selecting first non-placeholder option');
                                const options = Array.from(select.options);
                                // Skip first option if it's a placeholder
                                const firstRealOption = options.find(o => {
                                    const text = o.text.toLowerCase();
                                    return !text.includes('select') && !text.includes('choose') && text.trim().length > 0;
                                });
                                
                                if (firstRealOption) {
                                    select.value = firstRealOption.value;
                                    select.selectedIndex = firstRealOption.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    console.log('Selected first option:', firstRealOption.text);
                                    formResults.push({ question: labelText, answer: firstRealOption.text, inputType: 'select' });
                                }
                                continue;
                            }
                            
                            {
                                let answer = labelText ? fuzzyMatch(labelText) : null;
                                
                                // KEYWORD-BASED FALLBACK for select when fuzzyMatch returned nothing
                                if (!answer && lowerLabel) {
                                    if (lowerLabel.includes('total years') || lowerLabel.includes('years of professional') || lowerLabel.includes('years of experience') || lowerLabel.includes('years of work')) {
                                        answer = '4';
                                        console.log('Fallback: Using 4 for years of experience select');
                                    } else if (lowerLabel.includes('additional months') || lowerLabel.includes('months of experience')) {
                                        answer = '0';
                                        console.log('Fallback: Using 0 for months of experience select');
                                    } else if (lowerLabel.includes('notice') && (lowerLabel.includes('period') || lowerLabel.includes('day'))) {
                                        answer = '15';
                                        console.log('Fallback: Using 15 for notice period select');
                                    }
                                }
                                
                                // Determine if we should attempt to select "Yes" based on keywords
                                const isYesNoQuestion = lowerLabel.includes('experience') || 
                                                      lowerLabel.includes('developer') ||
                                                      lowerLabel.includes('comfortable') ||
                                                      lowerLabel.includes('willing');
                                
                                if (answer || isYesNoQuestion) {
                                    const options = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                    let bestOpt = findBestMatch(answer, options);
                                    
                                    // Fallback: If answer is numeric (e.g. "4 Years") but options are Yes/No
                                    if ((!bestOpt && answer) && (lowerLabel.includes('experience') || lowerLabel.includes('year'))) {
                                        const isYesNo = options.some(o => o.text.toLowerCase().includes('yes')) && 
                                                      options.some(o => o.text.toLowerCase().includes('no'));
                                        
                                        if (isYesNo) {
                                            // Extract required years from question
                                            // Matches "3+ years", "minimum 3 years", "at least 3 years"
                                            const reqMatch = labelText.match(/(\d+)\+?\s*(?:years|yrs)/i);
                                            const reqYears = reqMatch ? parseFloat(reqMatch[1]) : 0;
                                            
                                            // Extract users years from answer
                                            const ansMatch = answer.match(/(\d+(?:\.\d+)?)/);
                                            const ansYears = ansMatch ? parseFloat(ansMatch[1]) : 0;
                                            
                                            console.log(`Experience Logic: Required ${reqYears}, User ${ansYears}`);
                                            
                                            if (ansYears >= reqYears) {
                                                bestOpt = options.find(o => o.text.toLowerCase().includes('yes'));
                                            } else {
                                                // If user has less experience, we might want to lie (aggressive) or be honest
                                                // For now, let's be aggressive if it's close, or default Yes if parsing failed
                                                bestOpt = options.find(o => o.text.toLowerCase().includes('yes')); 
                                            }
                                        }
                                    }
                                    
                                    // Fallback 2: Implicit Yes/No for Developer/Experience questions where fuzzyMatch returned null
                                    if (!bestOpt && !answer && isYesNoQuestion) {
                                         bestOpt = options.find(o => o.text.toLowerCase().includes('yes'));
                                         if (bestOpt) console.log('Defaulting native select to Yes for:', labelText);
                                    }

                                    if (bestOpt) {
                                        console.log('Selecting native dropdown:', labelText, 'with:', bestOpt.text);
                                        
                                        // Robust selection logic
                                        select.value = bestOpt.value;
                                        if (select.value !== bestOpt.value) {
                                            select.selectedIndex = bestOpt.index;
                                        }
                                        
                                        select.dispatchEvent(new Event('input', { bubbles: true }));
                                        select.dispatchEvent(new Event('change', { bubbles: true }));
                                        select.dispatchEvent(new Event('blur', { bubbles: true }));
                                        
                                        formResults.push({ question: labelText, answer: bestOpt.text, inputType: 'select' });
                                    }
                                }
                                
                                // AGGRESSIVE FALLBACK 3: If select still not filled and has Yes/No options, default to Yes
                                // SAFETY: Blacklist dangerous questions that should NOT default to Yes
                                const dangerousYesPatterns = ['visa', 'sponsorship', 'citizenship', 'disability', 'gender', 'race', 'ethnicity', 'veteran', 'military', 'convict', 'felony', 'bankrupt', 'credit check', 'lie detector', 'polygraph', 'genetic', 'relative', 'family member'];
                                const isDangerousYes = dangerousYesPatterns.some(p => lowerLabel.includes(p));
                                
                                if (!isFieldPreFilled(select) && !isDangerousYes) {
                                    const options = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                    const hasYesNo = options.some(o => o.text.toLowerCase().includes('yes')) && 
                                                     options.some(o => o.text.toLowerCase().includes('no'));
                                    
                                    if (hasYesNo) {
                                        const yesOption = options.find(o => o.text.toLowerCase().includes('yes'));
                                        if (yesOption) {
                                            console.log('AGGRESSIVE FALLBACK: Defaulting to Yes for unfilled select:', labelText);
                                            select.value = yesOption.value;
                                            if (select.value !== yesOption.value) {
                                                select.selectedIndex = yesOption.index;
                                            }
                                            
                                            select.dispatchEvent(new Event('input', { bubbles: true }));
                                            select.dispatchEvent(new Event('change', { bubbles: true }));
                                            select.dispatchEvent(new Event('blur', { bubbles: true }));
                                            
                                            formResults.push({ question: labelText, answer: yesOption.text, inputType: 'select-aggressive' });
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Process custom LinkedIn dropdowns (comboboxes)
                        for (const dropdown of customDropdowns) {
                            if (!isVisible(dropdown) || dropdown.tagName === 'SELECT') continue;
                            
                            // Check if dropdown needs filling
                            const dropdownText = dropdown.innerText || dropdown.textContent || '';
                            const isUnselected = dropdownText.toLowerCase().includes('select an option') || 
                                               dropdownText.toLowerCase().includes('select') ||
                                               !dropdown.getAttribute('aria-expanded');
                            
                            if (!isUnselected) {
                                // console.log('Skipping pre-filled custom dropdown:', dropdownText);
                                continue;
                            }
                            
                            // Get label text from parent element
                            const labelText = dropdown.closest('.fb-dash-form-element')?.querySelector('label')?.innerText || 
                                            dropdown.closest('.jobs-easy-apply-form-section__question')?.querySelector('label')?.innerText ||
                                            dropdown.getAttribute('aria-label') || 
                                            dropdown.closest('div')?.querySelector('label')?.innerText || '';
                            
                            const lowerLabel = labelText.toLowerCase();
                            
                            // SPECIAL CASE: For "learn about" / "hear about" / "source" questions, select ANY first option
                            const isLearnAboutQuestion = lowerLabel.includes('learn about') || 
                                                        lowerLabel.includes('hear about') || 
                                                        lowerLabel.includes('how did you') ||
                                                        lowerLabel.includes('where did you') ||
                                                        lowerLabel.includes('source');
                            
                            if (isLearnAboutQuestion) {
                                console.log('Learn about question detected - selecting first available option');
                                dropdown.click();
                                
                                setTimeout(() => {
                                    const allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, .jobs-easy-apply-form-element__dropdown-option, li');
                                    for (const option of allOptions) {
                                        const text = option.innerText.trim();
                                        const lowerText = text.toLowerCase();
                                        if (text && !lowerText.includes('select') && !lowerText.includes('choose') && text.length > 2) {
                                            console.log('Selected first option for learn about question:', text);
                                            option.click();
                                            formResults.push({ question: labelText, answer: text, inputType: 'custom-dropdown' });
                                            break;
                                        }
                                    }
                                }, 200);
                                
                                return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN';
                            }
                            
                            if (labelText) {
                                const answer = fuzzyMatch(labelText);
                                // For Yes/No questions, default to "Yes" if no specific answer found
                                const isYesNoQuestion = lowerLabel.includes('experience') || 
                                                      lowerLabel.includes('developer');
                                
                                // SMART EXPERIENCE CHECK
                                let calculatedShouldSelectYes = false;
                                if (answer && (lowerLabel.includes('experience') || lowerLabel.includes('year'))) {
                                    const reqMatch = labelText.match(/(\d+)\+?\s*(?:years|yrs)/i);
                                    const reqYears = reqMatch ? parseFloat(reqMatch[1]) : 0;
                                    const ansMatch = answer.match(/(\d+(?:\.\d+)?)/);
                                    const ansYears = ansMatch ? parseFloat(ansMatch[1]) : 0;
                                    if (ansYears >= reqYears) calculatedShouldSelectYes = true;
                                }

                                const shouldSelectYes = calculatedShouldSelectYes || (isYesNoQuestion && (!answer || answer.toLowerCase().includes('yes')));
                                
                                if (answer || shouldSelectYes) {
                                    console.log('Clicking custom dropdown:', labelText);
                                    dropdown.click();
                                    
                                    // Wait briefly for dropdown options to appear
                                    setTimeout(() => {
                                        const yesOption = findByText('[role="option"], li', 'yes', true) ||
                                                        findByText('span', 'yes', true);
                                        const noOption = findByText('[role="option"], li', 'no', true) ||
                                                        findByText('span', 'no', true);
                                        
                                        if (shouldSelectYes && yesOption) {
                                            console.log('Selecting Yes for:', labelText);
                                            yesOption.click();
                                            formResults.push({ question: labelText, answer: 'Yes', inputType: 'custom-dropdown' });
                                        } else if (!shouldSelectYes && answer && answer.toLowerCase().includes('no') && noOption) {
                                            console.log('Selecting No for:', labelText);
                                            noOption.click();
                                            formResults.push({ question: labelText, answer: 'No', inputType: 'custom-dropdown' });
                                        } else if (yesOption) {
                                            console.log('Defaulting to Yes for:', labelText);
                                            yesOption.click();
                                            formResults.push({ question: labelText, answer: 'Yes', inputType: 'custom-dropdown' });
                                        }
                                    }, 100);
                                    
                                    return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN';
                                }
                            }
                            
                            // AGGRESSIVE FALLBACK: For unfilled custom dropdowns with Yes/No options
                            // SAFETY: Blacklist dangerous questions that should NOT default to Yes
                            const customDangerousPatterns = ['visa', 'sponsorship', 'citizenship', 'disability', 'gender', 'race', 'ethnicity', 'veteran', 'military', 'convict', 'felony', 'bankrupt', 'credit check', 'lie detector', 'polygraph', 'genetic', 'relative', 'family member'];
                            const isCustomDangerousYes = customDangerousPatterns.some(p => lowerLabel.includes(p));
                            
                            if (stillUnselected && labelText && !isCustomDangerousYes) {
                                console.log('AGGRESSIVE FALLBACK: Checking custom dropdown for Yes/No:', labelText);
                                dropdown.click();
                                
                                setTimeout(() => {
                                    const allOptions = document.querySelectorAll('[role="option"], .artdeco-dropdown__item, li');
                                    let hasYes = false;
                                    let hasNo = false;
                                    let yesOption = null;
                                    
                                    for (const option of allOptions) {
                                        const text = option.innerText.trim().toLowerCase();
                                        if (text === 'yes' || text.includes('yes')) {
                                            hasYes = true;
                                            yesOption = option;
                                        }
                                        if (text === 'no' || text.includes('no')) hasNo = true;
                                    }
                                    
                                    if (hasYes && hasNo && yesOption) {
                                        console.log('AGGRESSIVE FALLBACK: Selecting Yes for custom dropdown:', labelText);
                                        yesOption.click();
                                        formResults.push({ question: labelText, answer: 'Yes', inputType: 'custom-dropdown-aggressive' });
                                    }
                                }, 150);
                                
                                return 'LINKEDIN_FORM_FILLING_CUSTOM_DROPDOWN_AGGRESSIVE';
                            }
                        }

                        // 3. Handle Radio buttons (e.g., Yes/No questions)
                        const fieldsets = queryAllDeep('fieldset, [role="radiogroup"]', modal);
                        for (const fieldset of fieldsets) {
                            let legend = fieldset.querySelector('legend')?.innerText || '';
                            
                            // Fallback: get question text from parent section if no legend
                            if (!legend) {
                                const parentSection = fieldset.closest('.jobs-easy-apply-form-section__question, .fb-dash-form-element, [data-test-form-element]');
                                if (parentSection) {
                                    const sectionLabel = parentSection.querySelector('label, span, p');
                                    if (sectionLabel) legend = sectionLabel.innerText || '';
                                }
                                // Walk up parent tree
                                if (!legend) {
                                    let parent = fieldset.parentElement;
                                    for (let i = 0; i < 4 && parent && parent !== modal; i++) {
                                        const labelEl = parent.querySelector('label');
                                        if (labelEl && labelEl.innerText && labelEl.innerText.trim().length > 5) {
                                            legend = labelEl.innerText.trim();
                                            break;
                                        }
                                        parent = parent.parentElement;
                                    }
                                }
                            }
                            
                            legend = legend.replace(/\*+$/g, '').replace(/\s*This field is required/gi, '').trim();
                            const radios = Array.from(fieldset.querySelectorAll('input[type="radio"]'));
                            
                            // Check if any radio is already checked (standard or LinkedIn aria-checked)
                            const hasCheckedRadio = radios.some(r => r.checked) || 
                                Array.from(fieldset.querySelectorAll('[role="radio"]')).some(el => el.getAttribute('aria-checked') === 'true');
                            
                            if (radios.length > 0 && !hasCheckedRadio) {
                                const answer = legend ? fuzzyMatch(legend) : null;
                                if (answer) {
                                    let bestRadio = findBestRadioMatch(answer, radios);
                                    if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(legend)) {
                                        bestRadio = findSalaryRangeMatch(answer, radios);
                                    }
                                    if (bestRadio) {
                                        console.log('Clicking radio:', legend, 'with:', bestRadio.id);
                                        clickInput(bestRadio);
                                        formResults.push({ question: legend, answer: answer, inputType: 'radio' });
                                    } else {
                                        // Default to Yes if it's a Yes/No question
                                        // Check: (1) has yes+no radio options with few radios, OR (2) question text is a Yes/No question pattern
                                        const hasYes = radios.some(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        const hasNo = radios.some(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'no' || labelText === 'no' || labelText.includes('no');
                                        });
                                        const isYesNoFromRadios = radios.length <= 4 && hasYes && hasNo;
                                        const isYesNoFromText = isLikelyYesNoQuestion(legend);
                                        if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                            const yesRadio = radios.find(r => {
                                                const val = (r.value || '').toLowerCase();
                                                const labelText = getInputLabelText(r);
                                                return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                            });
                                            if (yesRadio) {
                                                console.log('Defaulting to Yes for Yes/No question:', legend.substring(0, 50));
                                                clickInput(yesRadio);
                                                formResults.push({ question: legend.substring(0, 100), answer: 'Yes', inputType: 'radio' });
                                            }
                                        }
                                    }
                                } else {
                                    // No fuzzy match - check if it's a Yes/No question and default to Yes
                                    const hasYes = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    const hasNo = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'no' || labelText === 'no' || labelText.includes('no');
                                    });
                                    const isYesNo = radios.length <= 4 && hasYes && hasNo;
                                    const isYesNoQ = isLikelyYesNoQuestion(legend);
                                    
                                    if (isYesNo || (isYesNoQ && hasYes)) {
                                        const yesRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        if (yesRadio) {
                                            console.log('Defaulting Yes/No question to Yes in fieldset:', legend.substring(0, 50));
                                            clickInput(yesRadio);
                                            formResults.push({ question: legend.substring(0, 100), answer: 'Yes', inputType: 'radio' });
                                        }
                                    }
                                }
                            }
                        }
                        
                        // 3.1a Handle LinkedIn custom radio groups (div-based, not fieldset/input)
                        // LinkedIn screening questions use div containers with role="radio" or label elements
                        // that have no <fieldset> wrapper and no <input type="radio">
                        let customRadioContainers = queryAllDeep(
                            '[data-test-form-builder-radio-button-group]:not(fieldset), ' +
                            '[role="radiogroup"]:not(fieldset)',
                            modal
                        );
                        
                        // Also find .fb-dash-form-element containers that contain custom radios
                        const fbElements = queryAllDeep('.fb-dash-form-element', modal);
                        for (const fb of fbElements) {
                            if (fb.tagName === 'FIELDSET') continue;
                            if (customRadioContainers.includes(fb)) continue;
                            const hasRoleRadio = fb.querySelector('[role="radio"]');
                            const hasLabelRadio = fb.querySelector('label[data-test-radio-button], div[data-test-radio-button]');
                            if (hasRoleRadio || hasLabelRadio) {
                                customRadioContainers.push(fb);
                            }
                        }
                        
                        for (const container of customRadioContainers) {
                            let questionText = '';
                            
                            const labelEl = container.querySelector('label, span, p, legend');
                            if (labelEl) {
                                const labelText = (labelEl.innerText || labelEl.textContent || '').trim();
                                if (labelText.length > 3) questionText = labelText;
                            }
                            
                            if (!questionText) {
                                const parentSection = container.closest('.jobs-easy-apply-form-section__question, [data-test-form-element]');
                                if (parentSection) {
                                    const sectionLabel = parentSection.querySelector('label, span, p');
                                    if (sectionLabel) questionText = (sectionLabel.innerText || sectionLabel.textContent || '').trim();
                                }
                            }
                            
                            if (!questionText) {
                                let parent = container.parentElement;
                                for (let i = 0; i < 4 && parent && parent !== modal; i++) {
                                    const labelEl2 = parent.querySelector('label');
                                    if (labelEl2 && labelEl2.innerText && labelEl2.innerText.trim().length > 5) {
                                        questionText = labelEl2.innerText.trim();
                                        break;
                                    }
                                    parent = parent.parentElement;
                                }
                            }
                            
                            questionText = questionText.replace(/\*+$/g, '').replace(/\s*This field is required/gi, '').trim();
                            
                            const customRadios = Array.from(container.querySelectorAll(
                                '[role="radio"], label[data-test-radio-button], div[data-test-radio-button], button[role="radio"]'
                            ));
                            
                            const hasSelected = customRadios.some(el =>
                                el.getAttribute('aria-checked') === 'true' ||
                                el.classList.contains('selected') ||
                                el.classList.contains('checked') ||
                                el.getAttribute('aria-selected') === 'true'
                            );
                            
                            if (customRadios.length > 0 && !hasSelected) {
                                const answer = questionText ? fuzzyMatch(questionText) : null;
                                console.log('Custom radio group:', questionText.substring(0, 60), '| answer:', answer, '| options:', customRadios.length);
                                
                                if (answer) {
                                    let bestRadio = findBestCustomRadioMatch(answer, customRadios);
                                    if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(questionText)) {
                                        bestRadio = findSalaryRangeMatch(answer, customRadios);
                                    }
                                    if (bestRadio) {
                                        console.log('Clicking custom radio:', questionText.substring(0, 50), '| match:', bestRadio.innerText?.substring(0, 30));
                                        clickCustomRadio(bestRadio);
                                        formResults.push({ question: questionText.substring(0, 100), answer: answer, inputType: 'radio' });
                                    } else {
                                        const hasYes = customRadios.some(r => {
                                            const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                            return t === 'yes' || t.includes('yes');
                                        });
                                        const hasNo = customRadios.some(r => {
                                            const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                            return t === 'no' || t.includes('no');
                                        });
                                        const isYesNoFromRadios = customRadios.length <= 4 && hasYes && hasNo;
                                        const isYesNoFromText = isLikelyYesNoQuestion(questionText);
                                        if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                            const yesRadio = customRadios.find(r => {
                                                const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                                return t === 'yes' || t.includes('yes');
                                            });
                                            if (yesRadio) {
                                                console.log('Defaulting custom radio to Yes:', questionText.substring(0, 50));
                                                clickCustomRadio(yesRadio);
                                                formResults.push({ question: questionText.substring(0, 100), answer: 'Yes', inputType: 'radio' });
                                            }
                                        }
                                    }
                                } else {
                                    const hasYes = customRadios.some(r => {
                                        const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                        return t === 'yes' || t.includes('yes');
                                    });
                                    const hasNo = customRadios.some(r => {
                                        const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                        return t === 'no' || t.includes('no');
                                    });
                                    const isYesNo = customRadios.length <= 4 && hasYes && hasNo;
                                    const isYesNoQ = isLikelyYesNoQuestion(questionText);
                                    
                                    if (isYesNo || (isYesNoQ && hasYes)) {
                                        const yesRadio = customRadios.find(r => {
                                            const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                            return t === 'yes' || t.includes('yes');
                                        });
                                        if (yesRadio) {
                                            console.log('Defaulting custom Yes/No to Yes:', questionText.substring(0, 50));
                                            clickCustomRadio(yesRadio);
                                            formResults.push({ question: questionText.substring(0, 100) || 'Yes/No question', answer: 'Yes', inputType: 'radio' });
                                        }
                                    }
                                }
                            }
                        }
                        
                        // 3.1b Handle standalone Radio buttons (not inside fieldsets)
                        // Many forms have radio buttons directly in divs or other containers
                        const allRadios = queryAllDeep('input[type="radio"]', modal);
                        const radioGroups = {};
                        
                        // Group radios by name attribute
                        for (const radio of allRadios) {
                            const name = radio.name;
                            if (!name) continue;  // Skip radios without names
                            if (!radioGroups[name]) {
                                radioGroups[name] = [];
                            }
                            radioGroups[name].push(radio);
                        }
                        
                        // Process each radio group
                        for (const [name, radios] of Object.entries(radioGroups)) {
                            // Skip if any radio in group is already checked
                            if (radios.some(r => r.checked)) continue;
                            
                            // Find label/question text for this group
                            let questionText = '';
                            const firstRadio = radios[0];
                            
                            // Try .fb-dash-form-element parent label (LinkedIn's structure)
                            if (!questionText) {
                                const fbParent = firstRadio.closest('.fb-dash-form-element');
                                if (fbParent) {
                                    const lbl = fbParent.querySelector('label');
                                    if (lbl) questionText = lbl.innerText || lbl.textContent || '';
                                }
                            }
                            
                            // Try to find label text
                            const parentLabel = firstRadio.closest('label');
                            if (!questionText && parentLabel) {
                                questionText = parentLabel.innerText;
                            }
                            if (!questionText) {
                                // Look for preceding text or parent container text
                                const container = firstRadio.closest('.jobs-easy-apply-form-section__question, [data-test-form-element], .artdeco-form-field, .jobs-easy-apply-form-element, .fb-dash-form-element');
                                if (container) {
                                    // Get text from the container (include label elements — question label is often a <label>)
                                    const textNodes = Array.from(container.childNodes)
                                        .filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'INPUT'))
                                        .map(n => n.textContent || n.innerText)
                                        .join(' ')
                                        .trim();
                                    questionText = textNodes;
                                }
                            }
                            
                            // Also try to get text from aria-label or aria-labelledby
                            if (!questionText && firstRadio.getAttribute('aria-labelledby')) {
                                const labelEl = document.getElementById(firstRadio.getAttribute('aria-labelledby'));
                                if (labelEl) questionText = labelEl.innerText;
                            }
                            
                            if (!questionText && firstRadio.getAttribute('aria-label')) {
                                questionText = firstRadio.getAttribute('aria-label');
                            }
                            
                            // Try to get text from name attribute if all else fails
                            if (!questionText && name && !name.match(/^[0-9]+$/)) {
                                questionText = name.replace(/[_-]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
                                console.log('Inferred question text from radio name:', questionText);
                            }
                            
                            // Try to find answer for this question
                            if (questionText) {
                                const answer = fuzzyMatch(questionText);
                                if (answer) {
                                    let bestRadio = findBestRadioMatch(answer, radios);
                                    if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(questionText)) {
                                        bestRadio = findSalaryRangeMatch(answer, radios);
                                    }
                                    if (bestRadio) {
                                        console.log('Clicking standalone radio:', questionText.substring(0, 50), 'with:', bestRadio.value || bestRadio.id);
                                        clickInput(bestRadio);
                                        formResults.push({ question: questionText.substring(0, 100), answer: answer, inputType: 'radio' });
                                    } else {
                                        // Default to Yes if it's a Yes/No question
                                        const hasYes = radios.some(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        const hasNo = radios.some(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'no' || labelText === 'no' || labelText.includes('no');
                                        });
                                        const isYesNoFromRadios = radios.length <= 4 && hasYes && hasNo;
                                        const isYesNoFromText = isLikelyYesNoQuestion(questionText);
                                        if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                            const yesRadio = radios.find(r => {
                                                const val = (r.value || '').toLowerCase();
                                                const labelText = getInputLabelText(r);
                                                return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                            });
                                            if (yesRadio) {
                                                console.log('Defaulting to Yes for Yes/No question:', questionText.substring(0, 50));
                                                clickInput(yesRadio);
                                                formResults.push({ question: questionText.substring(0, 100), answer: 'Yes', inputType: 'radio' });
                                            }
                                        }
                                    }
                                } else {
                                    // No fuzzy match - check if it's a Yes/No question and default to Yes
                                    const hasYes = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    const hasNo = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'no' || labelText === 'no' || labelText.includes('no');
                                    });
                                    const isYesNo = radios.length <= 4 && hasYes && hasNo;
                                    const isYesNoQ = isLikelyYesNoQuestion(questionText);
                                    
                                    if (isYesNo || (isYesNoQ && hasYes)) {
                                        const yesRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        if (yesRadio) {
                                            console.log('Defaulting Yes/No question to Yes:', questionText.substring(0, 50) || 'Unknown question');
                                            clickInput(yesRadio);
                                            formResults.push({ question: questionText.substring(0, 100) || 'Yes/No question', answer: 'Yes', inputType: 'radio' });
                                        }
                                    }
                                }
                            } else {
                                // No question text found - check if it's a Yes/No and default to Yes
                                const hasYes = radios.some(r => {
                                    const val = (r.value || '').toLowerCase();
                                    const labelText = getInputLabelText(r);
                                    return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                });
                                const hasNo = radios.some(r => {
                                    const val = (r.value || '').toLowerCase();
                                    const labelText = getInputLabelText(r);
                                    return val === 'no' || labelText === 'no' || labelText.includes('no');
                                });
                                const isYesNo = radios.length <= 4 && hasYes && hasNo;
                                
                                if (isYesNo) {
                                    const yesRadio = radios.find(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    if (yesRadio && !yesRadio.checked) {
                                        console.log('Selecting Yes for unlabeled Yes/No question');
                                        clickInput(yesRadio);
                                        formResults.push({ question: 'Yes/No question (no label found)', answer: 'Yes', inputType: 'radio' });
                                    }
                                }
                            }
                        }
                        
                        // 3.2 Handle Checkboxes - TWO PHASE:
                        // Phase 1 (Group): Multi-checkbox fieldsets → look up parent question → check matching options only
                        // Phase 2 (Singleton): Remaining single consent/privacy checkboxes → old logic
                        const checkboxes = queryAllDeep('input[type="checkbox"], .fb-form-element__checkbox', modal);
                        console.log('Found', checkboxes.length, 'checkboxes in modal');

                        // Helper: get the question text for a group/fieldset (legend or heading)
                        function getGroupQuestionText(fieldset) {
                            const legend = fieldset.querySelector('legend');
                            if (legend && legend.innerText.trim().length > 3) return legend.innerText.trim();
                            const heading = fieldset.querySelector('[class*="label"], [class*="header"], [class*="question"], .artdeco-form-field__label, [data-test-form-element-label]');
                            if (heading && heading.innerText.trim().length > 3) return heading.innerText.trim();
                            return '';
                        }

                        // Helper: get only the per-option label for a single checkbox (NOT the whole fieldset)
                        function getOptionLabel(cb) {
                            // aria-labelledby
                            const lby = cb.getAttribute('aria-labelledby');
                            if (lby) { const el = document.getElementById(lby); if (el) return el.innerText.trim(); }
                            // aria-label
                            const al = cb.getAttribute('aria-label');
                            if (al) return al.trim();
                            // id → label[for]
                            if (cb.id) { const lbl = queryDeep('label[for="' + cb.id + '"]', modal); if (lbl) return lbl.innerText.trim(); }
                            // sibling label (immediate parent)
                            const parent = cb.parentElement;
                            if (parent) {
                                const sibling = parent.querySelector('label');
                                if (sibling) return sibling.innerText.trim();
                                // data-test option label
                                const optLabel = parent.querySelector('[data-test-text-selectable-option__label]');
                                if (optLabel) return optLabel.innerText.trim();
                            }
                            return '';
                        }

                        // Phase 1: Handle multi-checkbox fieldsets group-by-group
                        const handledCheckboxes = new Set();
                        const multiCheckboxFieldsets = Array.from(
                            modal.querySelectorAll('fieldset, .fb-dash-form-element, .jobs-easy-apply-form-section__question, [data-test-form-element], .artdeco-form-field')
                        ).filter(el => el.querySelectorAll('input[type="checkbox"]').length > 1);

                        console.log('Found', multiCheckboxFieldsets.length, 'multi-checkbox fieldsets');

                        for (const fieldset of multiCheckboxFieldsets) {
                            const groupQuestion = getGroupQuestionText(fieldset);
                            console.log('Checkbox group question:', groupQuestion.substring(0, 80));

                            const groupAnswer = groupQuestion ? fuzzyMatch(groupQuestion) : null;
                            console.log('Checkbox group answer:', groupAnswer);

                            const groupCbs = fieldset.querySelectorAll('input[type="checkbox"]');
                            for (const cb of groupCbs) {
                                handledCheckboxes.add(cb);
                                if (!isVisible(cb) || cb.checked) continue;

                                const optLabel = getOptionLabel(cb);
                                console.log('Checkbox option label:', optLabel || '(none)');

                                let shouldCheck = false;

                                if (groupAnswer) {
                                    const answerLower = groupAnswer.toLowerCase();
                                    const optLower = optLabel.toLowerCase();
                                    // Check if this option is explicitly listed in the answer
                                    // e.g. answer="Full-stack" matches option "Full-stack"
                                    // answer="Yes" on a Yes/No group ticks the Yes checkbox
                                    shouldCheck = optLower.length > 0 && (
                                        answerLower.includes(optLower) ||
                                        optLower.includes(answerLower) ||
                                        answerLower === 'yes' && (optLower === 'yes' || optLower.startsWith('yes'))
                                    );
                                }

                                if (shouldCheck) {
                                    console.log('Checking group checkbox option:', optLabel, 'for group:', groupQuestion.substring(0, 50));
                                    clickInput(cb);
                                    formResults.push({ question: groupQuestion || optLabel, answer: optLabel, inputType: 'checkbox' });
                                } else {
                                    console.log('Skipping group checkbox option:', optLabel, '(answer:', groupAnswer, ')');
                                }
                            }
                        }

                        // Phase 2: Remaining singleton/consent checkboxes
                        for (const checkbox of checkboxes) {
                            if (handledCheckboxes.has(checkbox)) continue;
                            if (!isVisible(checkbox) || checkbox.checked) continue;
                            
                            // Get label text for the checkbox - try multiple methods
                            let labelText = '';
                            
                            // Method 1: Check for aria-labelledby
                            const labelledBy = checkbox.getAttribute('aria-labelledby');
                            if (labelledBy) {
                                const labelEl = document.getElementById(labelledBy);
                                if (labelEl) labelText = labelEl.innerText;
                            }
                            
                            // Method 2: Check for aria-label
                            if (!labelText) {
                                labelText = checkbox.getAttribute('aria-label') || '';
                            }
                            
                            // Method 3: Check for id and find matching label
                            if (!labelText && checkbox.id) {
                                const label = queryDeep(`label[for="${checkbox.id}"]`, modal);
                                if (label) labelText = label.innerText;
                            }
                            
                            // Method 4: Look for label in parent fieldset (LinkedIn specific structure)
                            if (!labelText) {
                                const fieldset = checkbox.closest('fieldset');
                                if (fieldset) {
                                    const legend = fieldset.querySelector('legend');
                                    if (legend) {
                                        labelText = legend.innerText;
                                    } else {
                                        labelText = fieldset.innerText.substring(0, 300);
                                    }
                                }
                            }
                            
                            // Method 5: Try to find label by data-test attribute (LinkedIn specific)
                            if (!labelText) {
                                const parent = checkbox.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question, [data-test-form-element]');
                                if (parent) {
                                    const label = parent.querySelector('[data-test-text-selectable-option__label], label');
                                    if (label) {
                                        labelText = label.innerText || label.getAttribute('data-test-text-selectable-option__label') || '';
                                    }
                                    if (!labelText) {
                                        labelText = parent.innerText.substring(0, 300);
                                    }
                                }
                            }
                            
                            // Method 6: Check sibling labels
                            if (!labelText) {
                                const parent = checkbox.parentElement;
                                if (parent) {
                                    const siblingLabel = parent.querySelector('label');
                                    if (siblingLabel) {
                                        labelText = siblingLabel.innerText;
                                    }
                                }
                            }
                            
                            console.log('Checkbox label text found:', labelText.substring(0, 100));
                            const lowerLabel = labelText.toLowerCase();
                            
                            // Check if this is a privacy/consent/acknowledge checkbox
                            const isConsentCheckbox = lowerLabel.includes('consent') || 
                                                     lowerLabel.includes('privacy') || 
                                                     lowerLabel.includes('agree') ||
                                                     lowerLabel.includes('declare') ||
                                                     lowerLabel.includes('i consent') ||
                                                     lowerLabel.includes('has my consent') ||
                                                     lowerLabel.includes('read and agree') ||
                                                     lowerLabel.includes('collect, store') ||
                                                     lowerLabel.includes('collect store and process') ||
                                                     lowerLabel.includes('for employment') ||
                                                     lowerLabel.includes('days thereafter') ||
                                                     lowerLabel.includes('365 days') ||
                                                     lowerLabel.includes('730 days') ||
                                                     lowerLabel.includes('1825 days') ||
                                                     lowerLabel.includes('considering me for employment') ||
                                                     lowerLabel.includes('acknowledge') ||
                                                     lowerLabel.includes('i acknowledge') ||
                                                     lowerLabel.includes('hereby acknowledge') ||
                                                     lowerLabel.includes('i certify') ||
                                                     lowerLabel.includes('hereby certify') ||
                                                     lowerLabel.includes('i confirm') ||
                                                     lowerLabel.includes('i understand and agree') ||
                                                     lowerLabel.includes('i have read and') ||
                                                     lowerLabel.includes('read and understood') ||
                                                     lowerLabel.includes('read and acknowledge') ||
                                                     lowerLabel.includes('data privacy notice') ||
                                                     lowerLabel.includes('privacy notice') ||
                                                     lowerLabel.includes('applicant data privacy') ||
                                                     lowerLabel.includes('job applicant data');
                            
                            let shouldCheck = isConsentCheckbox;
                            
                            if (!shouldCheck && labelText) {
                                const skillMatch = fuzzyMatch(labelText);
                                if (skillMatch && (
                                    skillMatch.toLowerCase() === 'yes' ||
                                    skillMatch.toLowerCase().includes(labelText.toLowerCase())
                                )) {
                                    shouldCheck = true;
                                    console.log('Skill found for checkbox:', labelText, 'matched as:', skillMatch);
                                }
                            }
                            
                            if (shouldCheck) {
                                console.log('Checking checkbox:', labelText.substring(0, 50));
                                clickInput(checkbox);
                                formResults.push({ question: labelText, answer: 'Checked', inputType: 'checkbox' });
                            } else {
                                console.log('Skipping checkbox - not consent/privacy related or no matching skill:', labelText.substring(0, 50));
                            }
                        }
                        
                        // 3.5 Check for any visible autocomplete dropdown options (post-fill catch)
                        // This handles cases where filling a field triggered a dropdown that needs selection
                        {
                            const dropdownSelectors = '.typeahead-input__dropdown-item, [role="option"], .artdeco-typeahead__result, [data-test-typeahead-item], li[class*="typeahead"], .basic-typeahead__selectable, .artdeco-typeahead__results-list li';
                            const postFillOptions = document.querySelectorAll(dropdownSelectors);
                            for (const option of postFillOptions) {
                                if (option.offsetParent !== null) {
                                    const text = option.innerText.trim();
                                    if (text && text.length > 2 && !text.toLowerCase().includes('select')) {
                                        console.log('Post-fill: clicking autocomplete option:', text);
                                        option.click();
                                        return 'LINKEDIN_AUTOCOMPLETE_SELECTED|' + JSON.stringify([{question: 'autocomplete', answer: text, inputType: 'typeahead'}]);
                                    }
                                }
                            }
                        }
                        
                        // 4. Form Validation Check: Are we missing anything required?
                        const checkForErrors = () => {
                            const requiredInputs = queryAllDeep('input[required], input[aria-required="true"], textarea[required], textarea[aria-required="true"]', modal);
                            const requiredSelects = queryAllDeep('select[required], select[aria-required="true"]', modal);
                            const radioGroups = queryAllDeep(
                                'fieldset[data-test-form-builder-radio-button-group], fieldset.fb-dash-form-element, ' +
                                '[data-test-form-builder-radio-button-group], [role="radiogroup"], ' +
                                '.fb-dash-form-element',
                                modal
                            );
                            
                            const hasEmptyInput = requiredInputs.some(i => isVisible(i) && !i.value.trim());
                            
                            // Check for empty/placeholder selects without assuming index 0 is invalid
                            const hasEmptySelect = requiredSelects.some(s => {
                                if (!isVisible(s)) return false;
                                const val = (s.value || '').trim();
                                const opt = s.options[s.selectedIndex];
                                const optVal = opt ? (opt.value || '').trim() : '';
                                const optText = opt ? (opt.text || '').trim().toLowerCase() : '';
                                
                                return !val || 
                                       val.toLowerCase().includes('select') || 
                                       val === '--' || 
                                       optText.includes('select') || 
                                       optText.includes('choose') || 
                                       optText === '--';
                            });
                            
                            const hasEmptyRadio = radioGroups.some(g => {
                                const rs = Array.from(g.querySelectorAll('input[type="radio"]'));
                                const roleRadios = Array.from(g.querySelectorAll('[role="radio"], label[data-test-radio-button], div[data-test-radio-button]'));
                                const hasCheckedInput = rs.some(r => r.checked);
                                const hasAriaChecked = roleRadios.some(r => r.getAttribute('aria-checked') === 'true' || r.getAttribute('aria-selected') === 'true');
                                const hasSelectedClass = roleRadios.some(r => r.classList.contains('selected') || r.classList.contains('checked'));
                                const hasRadios = rs.length > 0 || roleRadios.length > 0;
                                if (!hasRadios && !g.classList.contains('fb-dash-form-element')) return false;
                                if (!hasRadios && g.classList.contains('fb-dash-form-element')) return false;
                                return isVisible(g) && !hasCheckedInput && !hasAriaChecked && !hasSelectedClass;
                            });
                            
                            // Check for unchecked required checkboxes (privacy/consent)
                            const requiredCheckboxes = queryAllDeep('input[type="checkbox"][required], input[type="checkbox"][aria-required="true"]', modal);
                            const uncheckedCheckboxes = requiredCheckboxes.filter(cb => isVisible(cb) && !cb.checked);
                            const hasUncheckedCheckbox = uncheckedCheckboxes.length > 0;
                            
                            let hasVisibleError = !!queryDeep('.artdeco-inline-feedback--error, .fb-dash-form-element__error-field', modal);
                             
                            // Detect LinkedIn inline errors like "Invalid input" in helper-text elements
                            const helperTexts = queryAllDeep('[data-testid*="helper-text"] p, [data-testid*="error"] p, [class*="error"] p', modal);
                            for (const ht of helperTexts) {
                                const t = (ht.innerText || '').toLowerCase();
                                if ((t.includes('invalid') || t.includes('required') || t.includes('enter a valid') || t.includes('please enter')) && ht.offsetParent !== null) {
                                    hasVisibleError = true;
                                    break;
                                }
                            }
                            
                            // DEBUG: Log error details and all filled field values
                            if (hasVisibleError) {
                                const errorEls = queryAllDeep('.artdeco-inline-feedback--error, .fb-dash-form-element__error-field', modal);
                                errorEls.forEach((el, i) => {
                                    console.log('ERROR[' + i + '] text:', el.innerText, '| id:', el.id, '| class:', el.className);
                                    const errorParent = el.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question');
                                    if (errorParent) {
                                        const label = errorParent.querySelector('label, legend');
                                        const input = errorParent.querySelector('input, select, textarea');
                                        console.log('ERROR[' + i + '] field label:', label?.innerText?.substring(0, 100));
                                        console.log('ERROR[' + i + '] field value:', input?.value, input?.type);
                                    }
                                });
                            }
                            
                            // DEBUG: Log ALL filled fields and their values
                            const allInputs = queryAllDeep('input[type="text"], input[type="number"], textarea, select', modal);
                            allInputs.forEach((inp, i) => {
                                if (isVisible(inp) && inp.value) {
                                    const lbl = inp.closest('.fb-dash-form-element')?.querySelector('label')?.innerText || inp.getAttribute('aria-label') || '';
                                    console.log('FIELD[' + i + ']:', inp.type, '| label:', lbl.substring(0, 60), '| value:', inp.value);
                                }
                            });
                            
                            if (hasEmptyInput || hasEmptySelect || hasEmptyRadio || hasUncheckedCheckbox || hasVisibleError) {
                                console.log('Validation Error detected:', { hasEmptyInput, hasEmptySelect, hasEmptyRadio, hasUncheckedCheckbox, hasVisibleError });
                                return true;
                            }
                            return false;
                        };
                        
                        // Scroll modal content to bottom so lazy-rendered buttons are in DOM
                        const scrollableContent = modal.querySelector('[class*="body"], [class*="content"], form, div[style*="overflow"]') || modal;
                        if (scrollableContent && scrollableContent.scrollHeight > scrollableContent.clientHeight) {
                            scrollableContent.scrollTop = scrollableContent.scrollHeight;
                        }
                        
                        // Find action buttons (Review, Next, Submit)
                        // NOTE: 'review your application' (not just 'review') to avoid
                        // matching "Review job post" on the safety reminder modal.
                        console.log('Searching for primary action button...');
                        const primaryBtn = queryDeep('button[aria-label*="Review your application"]', modal) ||
                                         queryDeep('button[aria-label*="Continue to next step"]', modal) ||
                                         queryDeep('button[aria-label*="next step"]', modal) ||
                                         queryDeep('button[aria-label*="Submit application"]', modal) ||
                                         queryDeep('.jobs-apply-button--primary', modal) ||
                                         findByText('button', 'submit application', false, modal) ||
                                         findByText('button', 'review your application', false, modal) ||
                                         findByText('button', 'next', false, modal);

                        if (primaryBtn) {
                            // Only click if form is valid
                            if (checkForErrors()) {
                                console.log('Form has errors or missing required fields. Waiting for resolution...');
                                return 'LINKEDIN_FORM_STUCK: Validation errors or required fields missing';
                            }
                            
                            console.log('Clicking modal primary button:', primaryBtn.innerText || primaryBtn.getAttribute('aria-label'));
                            primaryBtn.click();
                            const btnText = (primaryBtn.innerText || primaryBtn.textContent || '').toLowerCase();
                            const btnAria = (primaryBtn.getAttribute('aria-label') || '').toLowerCase();
                            const isSubmit = btnText.includes('submit') || btnAria.includes('submit');
                            const actionResult = isSubmit ? 'LINKEDIN_SUBMITTED' : 'LINKEDIN_FORM_STEP_CONTINUED';
                            return actionResult + (formResults.length > 0 ? '|' + JSON.stringify(formResults) : '');
                        }

                        // Fallback: try searching entire page for primary buttons if modal-scoped failed
                        console.log('No button found in modal, trying global fallback...');
                        const globalPrimaryBtn = findByText('button', 'submit application') ||
                                                findByText('button', 'review your application') ||
                                                findByText('button', 'next');
                        if (globalPrimaryBtn && isVisible(globalPrimaryBtn)) {
                            if (checkForErrors()) {
                                console.log('Form has errors. Waiting...');
                                return 'LINKEDIN_FORM_STUCK: Validation errors';
                            }
                            console.log('Found button via global fallback:', globalPrimaryBtn.innerText);
                            globalPrimaryBtn.click();
                            const btnText = (globalPrimaryBtn.innerText || '').toLowerCase();
                            const isSubmit = btnText.includes('submit');
                            return isSubmit ? 'LINKEDIN_SUBMITTED' : 'LINKEDIN_FORM_STEP_CONTINUED';
                        }

                        return 'LINKEDIN_FORM_STUCK: No button found';
                    };

                    // Helper: Check if element is a messaging overlay (NOT an Easy Apply modal)
                    const isMessagingOverlay = (el) => {
                        const cls = (el.className || '').toLowerCase();
                        return cls.includes('msg-overlay') || cls.includes('msg-convo') || 
                               cls.includes('msg-form') || cls.includes('messaging') ||
                               cls.includes('msg-s-message-list') || cls.includes('msg-thread');
                    };

                    // ──────────────────────────────────────────────────
                    // FIRST-PASS: Safety reminder modal intercept
                    // This runs BEFORE checkModals() because LinkedIn
                    // sometimes renders the popup with non-standard
                    // modal classes that the deep query misses.
                    // We look for a visible "Continue applying" button
                    // anywhere on the page — very robust.
                    // Uses queryAllDeep to penetrate Shadow DOM.
                    // ──────────────────────────────────────────────────
                    {
                        const safetyKeywords = ['safety reminder', 'job search safety', 'research the company', 'report suspicious', 'review job post'];
                        const allBtns = queryAllDeep('button, span[role="button"]');
                        let scanned = 0;
                        for (const btn of allBtns) {
                            scanned++;
                            const txt = (btn.innerText || '').toLowerCase().trim();
                            // Match "Continue applying" button directly
                            if (txt.includes('continue applying') && isVisible(btn)) {
                                console.log('FIRST-PASS SAFETY INTERCEPT: Found "Continue applying" button, clicking...');
                                btn.scrollIntoView({block: 'center'});
                                btn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                btn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                btn.click();
                                return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                            }
                            // Also match any button inside a safety dialog context
                            if (isVisible(btn)) {
                                const dialogAncestor = btn.closest('[role="dialog"], .artdeco-modal, [class*="modal"]');
                                if (dialogAncestor) {
                                    const dialogText = (dialogAncestor.innerText || '').toLowerCase();
                                    if (safetyKeywords.some(kw => dialogText.includes(kw)) && txt.includes('continue')) {
                                        console.log('FIRST-PASS SAFETY INTERCEPT: Found continue button inside safety dialog, clicking...');
                                        btn.scrollIntoView({block: 'center'});
                                        btn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                        btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                        btn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                        btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                        btn.click();
                                        return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                                    }
                                }
                            }
                        }
                        console.log('FIRST-PASS SAFETY INTERCEPT: Scanned', scanned, 'buttons, no "Continue applying" found.');
                    }

                    // Helper: Check if LinkedIn Easy Apply modal is visible (heuristic-based)
                    // LinkedIn's new UI uses fully obfuscated CSS class names — we can't rely on
                    // class selectors. These heuristics detect the modal by its content/structure.
                    const checkEasyApplyModalOpen = () => {
                        // Heuristic 1: visible SVG role="progressbar" with aria-valuenow (% complete bar)
                        const pb = document.querySelector('svg[role="progressbar"][aria-valuenow]');
                        if (pb && isVisible(pb)) {
                            console.log('Modal detected via progressbar heuristic');
                            return true;
                        }
                        // Heuristic 2: "X of Y pages" text visible anywhere
                        const allSpans = document.querySelectorAll('p, span, div');
                        for (const el of allSpans) {
                            if (/\\d+\\s*\\/\\s*\\d+\\s*pages?/i.test(el.innerText) && isVisible(el)) {
                                console.log('Modal detected via pages-text heuristic:', el.innerText.trim().substring(0, 30));
                                return true;
                            }
                        }
                        // Heuristic 3: componentkey attribute + form inputs (LinkedIn Easy Apply root div)
                        const compKeyEl = document.querySelector('[componentkey]');
                        if (compKeyEl && isVisible(compKeyEl) && compKeyEl.querySelector('input, select, textarea, button')) {
                            console.log('Modal detected via componentkey+inputs heuristic');
                            return true;
                        }
                        return false;
                    };

                    // Helper: Get the modal element for form handling
                    const findEasyApplyModalEl = () => {
                        // Strategy 1: Walk up from progress bar if found (Guaranteed correct modal container)
                        const pb = document.querySelector('svg[role="progressbar"][aria-valuenow]');
                        if (pb) {
                            let el = pb.parentElement;
                            while (el && el !== document.body) {
                                const cls = typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '');
                                const lowerCls = cls.toLowerCase();
                                const isBlacklisted = lowerCls.includes('dropdown-to-modal') || 
                                                      lowerCls.includes('msg-overlay') || 
                                                      lowerCls.includes('msg-convo') || 
                                                      lowerCls.includes('messaging') ||
                                                      lowerCls.includes('filter__dropdown');
                                                      
                                if (!isBlacklisted) {
                                    if (el.tagName === 'FORM' || 
                                        el.hasAttribute('componentkey') || 
                                        (el.matches && (el.matches('.artdeco-modal') || el.matches('[role="dialog"]') || el.classList.contains('jobs-easy-apply-modal')))) {
                                        return el;
                                    }
                                }
                                el = el.parentElement;
                            }
                        }

                        // Strategy 2: Check standard modal container selectors next
                        // Skip messaging overlays and background filter dropdowns
                        const selectors = [
                            '.artdeco-modal',
                            '.jobs-easy-apply-modal',
                            '[role="dialog"]',
                            '[class*="easy-apply-modal"]',
                            '[class*="modal-container"]'
                        ];
                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                if (el && isVisible(el)) {
                                    const cls = typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '');
                                    const lowerCls = cls.toLowerCase();
                                    if (lowerCls.includes('msg-overlay') || lowerCls.includes('msg-convo') || 
                                        lowerCls.includes('msg-form') || lowerCls.includes('messaging') ||
                                        lowerCls.includes('dropdown-to-modal') || lowerCls.includes('filter__dropdown')) {
                                        continue;
                                    }
                                    return el;
                                }
                            }
                        }

                        // Strategy 3: Try componentkey element
                        const compKeyEl = document.querySelector('[componentkey]');
                        if (compKeyEl && isVisible(compKeyEl)) return compKeyEl;

                        // Strategy 4: Walk up from pages text element
                        const allSpans = document.querySelectorAll('p, span, div');
                        for (const el of allSpans) {
                            if (/\\d+\\s*\\/\\s*\\d+\\s*pages?/i.test(el.innerText) && isVisible(el)) {
                                let parent = el.parentElement;
                                while (parent && parent !== document.body) {
                                    const cls = typeof parent.className === 'string' ? parent.className : (parent.getAttribute('class') || '');
                                    const lowerCls = cls.toLowerCase();
                                    const isBlacklisted = lowerCls.includes('dropdown-to-modal') || 
                                                          lowerCls.includes('msg-overlay') || 
                                                          lowerCls.includes('msg-convo') || 
                                                          lowerCls.includes('messaging') ||
                                                          lowerCls.includes('filter__dropdown');
                                                          
                                    if (!isBlacklisted) {
                                        if (parent.tagName === 'FORM' || 
                                            parent.hasAttribute('componentkey') || 
                                            (parent.matches && (parent.matches('.artdeco-modal') || parent.matches('[role="dialog"]') || parent.classList.contains('jobs-easy-apply-modal')))) {
                                            return parent;
                                        }
                                    }
                                    parent = parent.parentElement;
                                }
                            }
                        }

                        // Strategy 5: Look for any visible form element
                        const form = document.querySelector('form');
                        if (form && isVisible(form)) {
                            const formId = form.getAttribute('data-id') || '';
                            const formClass = form.className || '';
                            if (!formId.includes('sign-in') && !formClass.includes('search') && !formClass.includes('sign-in')) {
                                return form;
                            }
                        }

                        // Fallback: Use dummy element rather than document.body to isolate queries
                        console.warn('Easy Apply modal container not found, using dummy fallback to prevent background interactions');
                        return document.createElement('div');
                    };

                    // Check for modals (safety FIRST, then success, limit, then Easy Apply form)
                    const checkModals = () => {
                        console.log('Checking for active Easy Apply modal (heuristic-based)...');

                        // PRIORITY 1: Scan all visible dialogs for safety/success/limit modals
                        // This runs BEFORE the Easy Apply heuristic to prevent the componentkey
                        // heuristic from misclassifying a safety modal as a form modal.
                        const dialogs = queryAllDeep('.artdeco-modal, [role="dialog"], .jobs-easy-apply-modal, [class*="modal-container"], [class*="modal"]');
                        for (const dialog of dialogs) {
                            if (!isVisible(dialog)) continue;
                            if (isMessagingOverlay(dialog)) continue;
                            const text = (dialog.innerText || '').toLowerCase();
                            // Safety reminder modal — check FIRST (broad keyword set)
                            if (text.includes('safety reminder') || text.includes('job search safety') ||
                                text.includes('research the company') || text.includes('report suspicious') ||
                                text.includes('review job post') || text.includes('continue applying')) {
                                return { type: 'safety', element: dialog };
                            }
                            // Success modal
                            if (text.includes('application sent') || text.includes('application submitted') || text.includes('success')) {
                                return { type: 'success', element: dialog };
                            }
                            // Easy Apply daily limit
                            if (dialog.querySelector('[data-testid="dialog-content"]') ||
                                text.includes('easy apply limit') || text.includes('you reached today') ||
                                (text.includes('apply tomorrow') && text.includes('limit'))) {
                                return { type: 'easy_apply_limit', element: dialog };
                            }
                        }

                        // PRIORITY 2: Easy Apply form — heuristic check
                        if (checkEasyApplyModalOpen()) {
                            const modalEl = findEasyApplyModalEl();
                            const text = (modalEl.innerText || '').toLowerCase();
                            // Double-check it's not a safety/success dialog (defense-in-depth)
                            if (text.includes('safety reminder') || text.includes('job search safety') ||
                                text.includes('research the company') || text.includes('report suspicious') ||
                                text.includes('review job post') || text.includes('continue applying')) {
                                return { type: 'safety', element: modalEl };
                            }
                            if (text.includes('application sent') || text.includes('application submitted')) {
                                return { type: 'success', element: modalEl };
                            }
                            return { type: 'form', element: modalEl };
                        }

                        // PRIORITY 3: Legacy Easy Apply form detection via dialog text
                        for (const dialog of dialogs) {
                            if (!isVisible(dialog)) continue;
                            if (isMessagingOverlay(dialog)) continue;
                            const text = (dialog.innerText || '').toLowerCase();
                            if (text.includes('apply to') || dialog.querySelector('.jobs-easy-apply-content') ||
                                dialog.querySelector('form') || text.includes('contact info') ||
                                text.includes('resume') || text.includes('additional questions')) {
                                return { type: 'form', element: dialog };
                            }
                        }
                        return null;
                    };
                    
                    // ──────────────────────────────────────────────────
                    // INTERCEPT 2: Safety/Reminder popup ("Job search safety reminder")
                    // Runs BEFORE checkModals() so safety modals are caught
                    // even if checkModals() would misclassify them as 'form'.
                    // ──────────────────────────────────────────────────
                    {
                        const allVisibleDialogs = queryAllDeep('.artdeco-modal, [role="dialog"], [class*="modal"]');
                        for (const d of allVisibleDialogs) {
                            if (!isVisible(d) || isMessagingOverlay(d)) continue;
                            const dText = (d.innerText || '').toLowerCase();

                            // Easy Apply limit check on any visible dialog
                            if (dText.includes('easy apply limit') || dText.includes('you reached today') ||
                                (dText.includes('apply tomorrow') && dText.includes('limit'))) {
                                console.log('LINKEDIN: Easy Apply limit popup detected via dialog scan. Clicking Got it...');
                                const btns = Array.from(queryAllDeep('button', d));
                                const gotItBtn = btns.find(b => (b.innerText || '').trim().toLowerCase() === 'got it') || btns[btns.length - 1];
                                if (gotItBtn) {
                                    gotItBtn.scrollIntoView({block: 'center'});
                                    gotItBtn.click();
                                }
                                return 'LINKEDIN_RATE_LIMITED: Easy Apply daily limit reached (scan)';
                            }

                            if (dText.includes('safety reminder') || dText.includes('job search safety') ||
                                dText.includes('research the company') || dText.includes('report suspicious') ||
                                dText.includes('review job post') || dText.includes('continue applying')) {
                                console.log('LINKEDIN: Safety reminder popup detected via intercept (pre-checkModals).');
                                // Find "Continue applying" button inside this element (shadow-DOM aware)
                                const btns = Array.from(queryAllDeep('button, span[role="button"]', d));
                                const continueBtn = btns.find(b => (b.innerText || '').toLowerCase().includes('continue applying')) ||
                                                   btns.find(b => (b.innerText || '').toLowerCase().includes('continue')) ||
                                                   btns[btns.length - 1];  // fallback: last button
                                if (continueBtn) {
                                    console.log('LINKEDIN: Clicking "Continue applying" (intercept path):', continueBtn.innerText);
                                    continueBtn.scrollIntoView({block: 'center'});
                                    continueBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                    continueBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                    continueBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                    continueBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                    continueBtn.click();
                                    return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                                }
                            }
                        }
                    }

                    const modal = checkModals();
                    if (modal) {
                        console.log('Active Modal detected:', modal.type);
                        if (modal.type === 'success') {
                            const closeBtn = modal.element.querySelector('button[aria-label="Dismiss"]') || 
                                           modal.element.querySelector('.artdeco-modal__dismiss') || 
                                           modal.element.querySelector('button');
                            if (closeBtn) {
                                console.log('Closing success modal...');
                                closeBtn.click();
                                return 'LINKEDIN_SUCCESS_MODAL_CLOSED';
                            }
                        }
                        
                        // Easy Apply Daily Limit — click "Got it" and signal rate limit
                        if (modal.type === 'easy_apply_limit') {
                            console.log('LINKEDIN: Easy Apply daily limit dialog detected. Clicking Got it...');
                            const gotItBtn = findByText('button', 'got it', true) ||
                                            findByText('button', 'got it') ||
                                            modal.element.querySelector('[data-testid="dialog-content"] button') ||
                                            modal.element.querySelector('[data-sdui-screen*="EasyApplyFuse"] button') ||
                                            modal.element.querySelector('button');
                            if (gotItBtn) {
                                gotItBtn.scrollIntoView({block: 'center'});
                                gotItBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                gotItBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                gotItBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                gotItBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                gotItBtn.click();
                            }
                            return 'LINKEDIN_RATE_LIMITED: Easy Apply daily limit reached';
                        }
                        
                        if (modal.type === 'safety') {
                            // Look for "Continue applying" button — try by text first, then last button
                            const continueBtn = findByText('button', 'continue applying', true) ||
                                               findByText('button', 'continue applying') ||
                                               findByText('button', 'continue') ||
                                               modal.element.querySelector('button:last-child') ||
                                               modal.element.querySelector('.artdeco-button--primary');
                            if (continueBtn) {
                                console.log('LINKEDIN: Clicking "Continue applying" on safety reminder popup');
                                continueBtn.scrollIntoView({block: 'center'});
                                continueBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                continueBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                                continueBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                continueBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                                continueBtn.click();
                                return 'LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED';
                            }
                        }
                        
                        if (modal.type === 'form') {
                            return handleLinkedInForm(modal.element);
                        }
                    }

                    // INTERCEPT 1: Easy Apply daily limit dialog (catches cases checkModals() may miss)
                    // Matches both the data-testid selector and the SDUI screen attribute
                    const easyApplyLimitDlg = (
                        document.querySelector('[data-testid="dialog-content"]') ||
                        document.querySelector('[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.EasyApplyFuseLimitDialogModal"]')
                    );
                    if (easyApplyLimitDlg && isVisible(easyApplyLimitDlg)) {
                        const dlgText = (easyApplyLimitDlg.innerText || '').toLowerCase();
                        if (dlgText.includes('easy apply limit') || dlgText.includes('you reached today') || dlgText.includes('apply tomorrow')) {
                            console.log('LINKEDIN: Easy Apply limit dialog detected via intercept. Clicking Got it...');
                            const btns = Array.from(easyApplyLimitDlg.querySelectorAll('button'));
                            const gotItBtn = btns.find(b => (b.innerText || '').trim().toLowerCase() === 'got it') || btns[btns.length - 1];
                            if (gotItBtn) {
                                gotItBtn.scrollIntoView({block: 'center'});
                                gotItBtn.click();
                            }
                            return 'LINKEDIN_RATE_LIMITED: Easy Apply daily limit reached (intercept)';
                        }
                    }

                    // INTERCEPT 2 was moved BEFORE checkModals() for safety-first detection

                    // CRITICAL: If a REAL modal is present in DOM (even if loading/transitioning), do NOT click Easy Apply
                    // Must exclude messaging overlays which also match [role="dialog"]
                    // IMPROVED: Also check if it's actually an Easy Apply modal by checking for specific indicators
                    const modals = queryAllDeep('.artdeco-modal, [role="dialog"], .jobs-easy-apply-modal, [class*="easy-apply-modal"]');
                    const anyModal = Array.from(modals).find(m => !isMessagingOverlay(m));
                    if (anyModal) {
                        const hasInteractiveElements = queryDeep('input, select, textarea, button', anyModal) !== null;
                        
                        // IMPROVED: Check for Easy Apply specific indicators
                        const hasProgressBar = anyModal.querySelector('svg[role="progressbar"][aria-valuenow]') !== null;
                        const hasPageIndicator = /\\d+\\s*\\/\\s*\\d+\\s*pages?/i.test(anyModal.innerText || '');
                        const hasEasyApplyContent = (anyModal.innerText || '').toLowerCase().includes('easy apply') ||
                                                    (anyModal.innerText || '').toLowerCase().includes('apply to') ||
                                                    (anyModal.innerText || '').toLowerCase().includes('contact info') ||
                                                    (anyModal.innerText || '').toLowerCase().includes('resume');
                        
                        // Only wait for transitioning if it looks like an actual Easy Apply modal
                        const isLikelyEasyApplyModal = hasProgressBar || hasPageIndicator || hasEasyApplyContent;
                        
                        if (isVisible(anyModal) && hasInteractiveElements) {
                            console.log('Unknown modal detected via deep query. Handling as generic form...');
                            return handleLinkedInForm(anyModal);
                        } else if (isLikelyEasyApplyModal && (isVisible(anyModal) || hasInteractiveElements)) {
                            console.log('Easy Apply modal is loading or transitioning. Waiting...');
                            return 'LINKEDIN_MODAL_TRANSITIONING';
                        } else {
                            // Not an Easy Apply modal or it's stale - proceed to look for Easy Apply button
                            console.log('Modal found but not an Easy Apply modal. Proceeding to look for Easy Apply button...');
                        }
                    }

                    // No modal open - handle job selection and clicking Easy Apply
                    console.log('No modal detected. Checking for Easy Apply button...');
                    const easyApplyBtn = findEasyApplyButton();
                    if (easyApplyBtn) {
                        console.log('Easy Apply button found, clicking...');
                        easyApplyBtn.click();
                        return 'LINKEDIN_EASY_APPLY_CLICKED';
                    }

                    // Navigation logic if needed
                    console.log('Looking for jobs in list...');
                    // 3. If no Easy Apply button and no modal, we might be on the search page
                    // We need to select the next job from the list
                    console.log('Looking for jobs in list...');
                    
                    // Find the sidebar with extreme robust fallbacks
                    // Priority 1: .jobs-search-results-list (standard)
                    // Priority 2: div[scrollable="true"] on the left side
                    // Priority 3: Geometry-based fallback (widest scrollable div on the left half)
                    let sidebar = queryDeep('.scaffold-layout__list') || 
                                  queryDeep('.jobs-search-results-list') ||
                                  queryDeep('div[scrollable="true"] > ul');
                    
                    if (!sidebar) {
                         const scrollables = Array.from(queryAllDeep('div[scrollable="true"], .jobs-search-results-list, .scaffold-layout__list'));
                         // Find the one that is on the left side and has decent height
                         sidebar = scrollables.find(el => {
                             const rect = el.getBoundingClientRect();
                             return rect.left < window.innerWidth / 2 && rect.height > 300;
                         });
                    }
                    
                    if (!sidebar) {
                         console.log('Sidebar not found by selector, trying geometry...');
                         // Find any div that is scrollable and on the left
                         const allDivs = queryAllDeep('div');
                         for (const div of allDivs) {
                             const rect = div.getBoundingClientRect();
                             if (rect.left < window.innerWidth / 2 && rect.width > 200 && rect.height > 400) {
                                 if (div.scrollHeight > div.clientHeight || div.style.overflowY === 'auto' || div.style.overflow === 'auto') {
                                     sidebar = div;
                                     break;
                                 }
                             }
                         }
                    }

                    if (!sidebar) {
                        console.log('Sidebar ABSOLUTELY not found, attempting global scroll...');
                        window.scrollBy(0, 800);
                        return 'LINKEDIN_SCROLLED: No jobs found (Legacy)';
                    }

                    // Find job cards within the sidebar
                    // Priority: .job-card-container (verified 2026), [data-job-id], .scaffold-layout__list-item
                    // NOTE: .jobs-search-results-list__list-item is DEAD as of 2026 LinkedIn update
                    let jobCards = Array.from(queryAllDeep('.job-card-container, [data-job-id], [data-occludable-job-id], .scaffold-layout__list-item', sidebar));
                    
                    // Deduplicate: a .job-card-container inside a .scaffold-layout__list-item would match twice
                    // Keep the most specific (deepest) element for each job
                    const seen = new Set();
                    jobCards = jobCards.filter(card => {
                        const jobId = card.getAttribute('data-job-id') || card.querySelector('[data-job-id]')?.getAttribute('data-job-id') || card.innerText.substring(0, 60);
                        if (seen.has(jobId)) return false;
                        seen.add(jobId);
                        return true;
                    });
                    
                    // Fallback to role="button" logic
                    if (jobCards.length === 0) {
                        jobCards = Array.from(queryAllDeep('div[role="button"]', sidebar)).filter(el => 
                            el.innerText.includes('\\n') && el.innerText.length > 50 
                        );
                    }

                    // Filter valid candidates
                    // 1. Must be visible
                    // 2. Must NOT be "Applied"
                    // 3. Must have "Easy Apply" text
                    // 4. Must not be the currently active card
                    const candidates = jobCards.filter(card => {
                        const text = card.innerText.toLowerCase();
                        // Active class may be on card itself OR on a parent <li> element
                        // LinkedIn puts --active on the <li> wrapper, not on .job-card-container
                        const isActive = card.classList.contains('jobs-search-results-list__list-item--active') ||
                                        card.closest('.jobs-search-results-list__list-item--active') !== null ||
                                        card.closest('[aria-current="true"]') !== null ||
                                        card.getAttribute('aria-current') === 'true';
                        
                        if (isActive) return false;
                        if (!isVisible(card)) return false;
                        
                        // Check explicit "Applied" status
                        if (text.includes('applied')) {
                            // console.log('Skipping applied job:', text.split('\\n')[0]);
                            return false;
                        }
                        
                        // User requirement: Must be "Easy Apply"
                        // Note: Some cards might say "Easy Apply" in hidden text, so strict check is good
                        if (!text.includes('easy apply')) {
                            // console.log('Skipping non-Easy Apply job:', text.split('\\n')[0]);
                            return false;
                        }
                        
                        return true;
                    });

                    if (candidates.length > 0) {
                        const nextJob = candidates[0];
                        console.log('Clicking next job:', nextJob.innerText.split('\\n')[0]);
                        nextJob.click();
                        nextJob.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        return 'LINKEDIN_JOB_SELECTED';
                    }

                    console.log('No eligible jobs visible in sidebar, scrolling sidebar...');
                    sidebar.scrollBy(0, 800);
                    return 'LINKEDIN_SCROLLED: No jobs found';
                }
            // NAUKRI LOGIC (Enhanced with proper selectors and tab navigation)
            // ============================================================
            if (isNaukri) {
                    const TARGET_JOBS = 5;
                    
                    // Reset tab cycle tracker on first visit
                    if (!sessionStorage.getItem('naukri_tab_idx')) {
                        sessionStorage.setItem('naukri_tab_idx', '-1');
                    }
                    
                    // 0. Dismiss any feedback modals (non-blocking)
                    const feedbackSection = Array.from(document.querySelectorAll('div, section')).find(
                        el => el.innerText && el.innerText.includes('Are these jobs relevant') && 
                              el.innerText.length < 1000 && el.offsetParent !== null
                    );
                        if (feedbackSection) {
                        const yesBtn = feedbackSection.querySelector('button');
                        if (yesBtn && yesBtn.innerText.toLowerCase().includes('yes')) {
                            yesBtn.click();
                            // NOTE: await removed - Python handles delays between evaluate calls
                        } else {
                            const anyBtn = feedbackSection.querySelector('button');
                            if (anyBtn) {
                                anyBtn.click();
                                // NOTE: await removed - Python handles delays between evaluate calls
                            }
                        }
                        // No early return! Proceed with job application
                    }
                    
                    // Check for error popup - "There was some error processing your request"
                    // Uses specific Naukri selector: div.ss-snackbar-body
                    const snackbarBody = document.querySelector('div.ss-snackbar-body');
                    if (snackbarBody) {
                        const snackText = snackbarBody.innerText.toLowerCase();
                        if (snackText.includes('error processing') || snackText.includes('some error')) {
                            const closeBtn = document.querySelector('button.ss-close');
                            if (closeBtn) closeBtn.click();
                            return 'NAUKRI_RATE_LIMITED: Error popup detected during fallback start';
                        }
                    }
                    
                    // 0. Check for success page (URL pattern or message)
                    const isSuccessPage = window.location.href.includes('/myapply/saveApply');
                    const successMsg = document.querySelector('span.apply-message');
                    if (isSuccessPage || (successMsg && successMsg.innerText.includes('successful'))) {
                        const bodyText = document.body.innerText || '';
                        const match = bodyText.match(/(\d+)\s*out\s*of\s*(\d+)/);
                        if (match) {
                            const appliedThisRound = parseInt(match[1]);
                            // Get cumulative count from sessionStorage
                            const prevTotal = parseInt(sessionStorage.getItem('naukri_total_applied') || '0');
                            const newTotal = prevTotal + appliedThisRound;
                            sessionStorage.setItem('naukri_total_applied', newTotal.toString());
                            
                            const remaining = TARGET_JOBS - newTotal;
                            
                            if (remaining <= 0) {
                                sessionStorage.removeItem('naukri_total_applied');
                                sessionStorage.removeItem('naukri_remaining');
                                // Task complete - do NOT navigate, signal done
                                return 'NAUKRI_TASK_DONE: Applied to ' + newTotal + ' jobs total. Task complete.';
                            }
                            
                            // Need more jobs - store remaining and navigate back to recommended jobs
                            sessionStorage.setItem('naukri_remaining', remaining.toString());
                            window.location.href = 'https://www.naukri.com/mnjuser/recommendedjobs';
                            return 'NAUKRI_SUCCESS_PARTIAL: Applied ' + newTotal + ' total, need ' + remaining + ' more - navigating back';
                        }
                    }
                    
                    // 1. Handle chatbot modal if open
                    const chatBotContainer = document.querySelector('[class*="ChatbotContainer"], [class*="chatBotContainer"], ._chatBotContainer');
                    const chatLayer = document.querySelector('.chatbot_DrawerContentWrapper, .chatbot_Drawer');
                    const chatIsVisible = (chatBotContainer && chatBotContainer.offsetParent !== null) || 
                                         (chatLayer && chatLayer.offsetParent !== null) ||
                                         document.querySelector('.chatbot_Overlay.show') !== null;
                    
                    if (chatIsVisible) {
                        // Find the question
                        const questionEl = document.querySelector('.chatbot_MessageContainer li.botItem:last-of-type .botMsg') ||
                                          document.querySelector('.botMsg.msg') ||
                                          document.querySelector('li.botItem .botMsg');
                        
                        // Find the input - DOM inspection found: div.textArea[contenteditable="true"]
                        // Parent is .textAreaWrapper, placeholder is "Type message here..."
                        const inputDiv = document.querySelector('div.textArea[contenteditable="true"]') ||
                                        document.querySelector('.textAreaWrapper div[contenteditable="true"]') ||
                                        document.querySelector('[id*="userInput"][contenteditable="true"]') ||
                                        document.querySelector('div[contenteditable="true"][data-placeholder*="Type message"]');
                        
                        const qText = questionEl?.innerText || 'Unknown question';
                        const qLower = qText.toLowerCase();
                        
                        // Pre-match: LWD date questions
                        const isLwdQ = qLower.includes('ldw') || qLower.includes('lwd') || 
                                        qLower.includes('last working day');
                        let answer;
                        if (isLwdQ) {{
                            const lwd = new Date();
                            lwd.setDate(lwd.getDate() + 15);
                            const dd = String(lwd.getDate()).padStart(2, '0');
                            const mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][lwd.getMonth()];
                            const yyyy = lwd.getFullYear();
                            answer = dd + ' ' + mon + ' ' + yyyy;
                            console.log('NAUKRI DEBUG: LWD question detected:', qText, '->', answer);
                        }} else {{
                            answer = fuzzyMatch(qText) || "4 Years";
                        }}

                        // ─── THREE-FIELD DATE PICKER (DD / MM / YYYY) ─────────────────────
                        // Naukri's date picker uses 3 separate input[type="number"] fields.
                        // Detect by placeholder and fill each with computed today+15.
                        const nkDD = document.querySelector('input[placeholder="DD"]');
                        const nkMM = document.querySelector('input[placeholder="MM"]');
                        const nkYY = document.querySelector('input[placeholder="YYYY"]');
                        if (nkDD && nkMM && nkYY && nkDD.offsetParent !== null) {
                            const tgt = new Date();
                            tgt.setDate(tgt.getDate() + 15);
                            const dv = String(tgt.getDate()).padStart(2, '0');
                            const mv = String(tgt.getMonth() + 1).padStart(2, '0');
                            const yv = String(tgt.getFullYear());
                            const setter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            [[nkDD, dv], [nkMM, mv], [nkYY, yv]].forEach(function(pair) {
                                const el = pair[0], val = pair[1];
                                if (setter) setter.call(el, val);
                                el.dispatchEvent(new Event('input',  { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                            });
                            console.log('NAUKRI DEBUG: date filled', dv + '/' + mv + '/' + yv);
                            const sendBtn = document.querySelector('div.sendMsg') ||
                                           document.querySelector('.sendMsgbtn_container .sendMsg') ||
                                           document.querySelector('[class*="sendMsg"]');
                            console.log('NAUKRI DEBUG: sendBtn found=', !!sendBtn, sendBtn?.outerHTML?.slice(0, 80));
                            if (sendBtn && !sendBtn.disabled) {
                                sendBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                                sendBtn.dispatchEvent(new MouseEvent('mouseup',   { bubbles: true, cancelable: true }));
                                sendBtn.click();
                                return 'NAUKRI_CHAT_ANSWERED_AND_SAVED: ' + qText.slice(0, 40);
                            }
                            return 'NAUKRI_CHAT_DATE_FILLED: ' + dv + '/' + mv + '/' + yv;
                        }
                        // ─────────────────────────────────────────────────────────────────────

                        // Try contenteditable div (Naukri's actual implementation)
                        if (inputDiv) {
                            const currentText = inputDiv.textContent || inputDiv.innerText || '';
                            if (!currentText.trim()) {
                                inputDiv.focus();
                                // Clear and set
                                inputDiv.innerHTML = '';
                                inputDiv.textContent = answer;
                                inputDiv.dispatchEvent(new Event('input', { bubbles: true }));
                                inputDiv.dispatchEvent(new Event('change', { bubbles: true }));
                                inputDiv.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                                
                                // CRITICAL: Save button is div.sendMsg, NOT a button element!
                                // Structure: .sendMsgbtn_container > div.send > div.sendMsg
                                const sendBtn = document.querySelector('div.sendMsg') ||
                                               document.querySelector('.sendMsgbtn_container .sendMsg') ||
                                               document.querySelector('[class*="sendMsg"]');
                                
                                console.log('NAUKRI DEBUG: sendBtn found=', !!sendBtn, sendBtn?.outerHTML?.slice(0, 100));
                                
                                if (sendBtn) { 
                                    sendBtn.click(); 
                                    return 'NAUKRI_CHAT_ANSWERED_AND_SAVED: ' + qText.slice(0, 40); 
                                }
                                
                                // Fallback: try pressing Enter to submit
                                inputDiv.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
                                inputDiv.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', keyCode: 13, bubbles: true }));
                                return 'NAUKRI_CHAT_ANSWERED: ' + qText.slice(0, 40);
                            }
                        }
                        
                        // Try dropdown
                        const select = document.querySelector('select');
                        if (select && select.offsetParent !== null && select.selectedIndex <= 0 && select.options.length > 1) {
                            select.selectedIndex = 1;
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                            const saveBtn = document.querySelector('div.sendMsg') || document.querySelector('.sendMsgbtn_container .sendMsg');
                            if (saveBtn) { saveBtn.click(); return 'NAUKRI_CHAT_DROPDOWN_SAVED'; }
                        }
                        
                        // Try radio buttons - enhanced logic with better matching
                        const radios = document.querySelectorAll('input[type="radio"]');
                        if (radios.length > 0) {
                            let clicked = false;
                            const qText = (document.querySelector('.chatbot_MessageContainer li.botItem:last-of-type .botMsg') ||
                                         document.querySelector('.botMsg.msg') ||
                                         document.querySelector('li.botItem .botMsg'))?.innerText || 'Unknown question';
                            
                            // First try fuzzy matching for radio button questions
                            const fuzzyAnswer = fuzzyMatch(qText);
                            let bestRadio = null;
                            
                            if (fuzzyAnswer) {
                                // Use the enhanced matching function
                                bestRadio = findBestRadioMatch(fuzzyAnswer, radios);
                                // Try salary range matching for CTC/salary questions
                                if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(qText)) {
                                    bestRadio = findSalaryRangeMatch(fuzzyAnswer, radios);
                                }
                            }
                            
                            // If no fuzzy match found, only default to Yes if it's actually a Yes/No question
                            if (!bestRadio) {
                                const hasYes = Array.from(radios).some(r => {
                                    const label = (r.closest('label')?.innerText || r.parentElement?.innerText || '').toLowerCase();
                                    return label.includes('yes') || label.includes('serving') || label.includes('currently');
                                });
                                const hasNo = Array.from(radios).some(r => {
                                    const label = (r.closest('label')?.innerText || r.parentElement?.innerText || '').toLowerCase();
                                    return label === 'no' || label.includes('no');
                                });
                                const isYesNo = radios.length <= 4 && hasYes && hasNo;
                                
                                if (isYesNo) {
                                    for (const radio of radios) {
                                        const label = radio.closest('label')?.innerText || radio.parentElement?.innerText || '';
                                        if (label.toLowerCase().includes('yes') || 
                                            label.toLowerCase().includes('serving') ||
                                            label.toLowerCase().includes('currently')) {
                                            bestRadio = radio;
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            // Click the selected radio button
                            if (bestRadio && !bestRadio.checked) { 
                                bestRadio.click(); 
                                clicked = true; 
                            }
                            
                            if (clicked) {
                                // Save button is div.sendMsg, not button element!
                                const saveBtn = document.querySelector('div.sendMsg') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                if (saveBtn) { saveBtn.click(); return 'NAUKRI_CHAT_RADIO_SAVED'; }
                            }
                        }
                        
                        // Try Checkboxes - Handle both standard checkboxes and Naukri's mcc__checkbox elements
                        // First try the specific mcc__checkbox (used for city selection, etc.)
                        let allCheckboxes = Array.from(document.querySelectorAll('.mcc__checkbox'));
                        
                        // Fallback to standard checkbox selector if mcc not found
                        if (allCheckboxes.length === 0) {
                            const cbContainer = document.querySelector('.chatbot_MessageContainer li:last-child') || document.body;
                            allCheckboxes = Array.from(cbContainer.querySelectorAll('input[type="checkbox"]'));
                        }

                        // Debug log 
                        const debugLog = [];

                        if (allCheckboxes.length > 0) {
                            let clickedCount = 0;
                            
                            // City preference order (check qText to see if it's a city question)
                            const qTextLower = qText.toLowerCase();
                            const isCityQuestion = qTextLower.includes('city') || qTextLower.includes('relocate') || qTextLower.includes('location');
                            const isNoticePeriodQuestion = qTextLower.includes('notice period');
                            const isProgrammingLanguageQuestion = qTextLower.includes('programming language') || qTextLower.includes('programming lang') || qTextLower.includes('coding language') || (qTextLower.includes('language') && (qTextLower.includes('experienced') || qTextLower.includes('proficient') || qTextLower.includes('skilled')));
                            const isExperienceQuestion = !isProgrammingLanguageQuestion && (qTextLower.includes('experience') || qTextLower.includes('years'));
                            const preferredCities = ['bengaluru', 'bangalore', 'hyderabad', 'pune', 'mumbai', 'chennai', 'delhi', 'noida', 'gurgaon'];
                            
                            // FIRST: Check if this is a binary Yes/No question
                            // Build label map first for all checkboxes
                            const checkboxLabels = allCheckboxes.map(cb => {
                                let label = cb.closest('label') || document.querySelector(`label.mcc__label[for="${cb.id}"]`);
                                if (!label && cb.id) {
                                    label = document.querySelector(`label[for="${cb.id}"]`);
                                }
                                if (!label) {
                                    label = cb.parentElement; 
                                }
                                const labelText = label ? (label.innerText || cb.id || '') : (cb.id || '');
                                return { cb, labelText, lowerLabel: labelText.toLowerCase() };
                            });
                            
                            // Check if binary (exactly 2 checkboxes with Yes/No labels)
                            const isBinaryYesNo = allCheckboxes.length === 2 && 
                                checkboxLabels.every((item) => 
                                    item.lowerLabel.includes('yes') || item.lowerLabel.includes('no')
                                );
                            
                            if (isBinaryYesNo) {
                                // Find the Yes checkbox
                                const yesCheckbox = checkboxLabels.find((item) => 
                                    item.lowerLabel.includes('yes') && !item.lowerLabel.includes('not')
                                );
                                
                                if (yesCheckbox && !yesCheckbox.cb.checked) {
                                    yesCheckbox.cb.click();
                                    if (!yesCheckbox.cb.checked) {
                                        yesCheckbox.cb.checked = true;
                                        yesCheckbox.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    clickedCount = 1;
                                    debugLog.push("CB: " + yesCheckbox.labelText);
                                } else if (yesCheckbox && yesCheckbox.cb.checked) {
                                    clickedCount = 1;
                                    debugLog.push("CB: " + yesCheckbox.labelText + " (already checked)");
                                }
                            } else if (isCityQuestion) {
                                // Check if these are actual city checkboxes (not Yes/No)
                                const cityNames = ['pune', 'mumbai', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'delhi', 'noida', 'gurgaon', 'gurugram', 'kolkata', 'ahmedabad'];
                                const containsCities = checkboxLabels.some(item => 
                                    cityNames.some(city => item.lowerLabel.includes(city))
                                );
                                
                                if (containsCities) {
                                    // This is a city selection question - select ALL options except "Skip"
                                    for (const item of checkboxLabels) {
                                        // Skip the "Skip this question" option
                                        if (item.lowerLabel.includes('skip')) {
                                            debugLog.push("CITY_SKIP: " + item.labelText);
                                            continue;
                                        }
                                        
                                        // Select any non-skip option (city names, locations, etc.)
                                        if (!item.cb.checked) {
                                            item.cb.click();
                                            if (!item.cb.checked) {
                                                item.cb.checked = true;
                                                item.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                            }
                                            clickedCount++;
                                            debugLog.push("CITY_ALL: " + item.labelText);
                                        } else if (item.cb.checked) {
                                            clickedCount++;
                                            debugLog.push("CITY_ALL: " + item.labelText + " (already checked)");
                                        }
                                    }
                                    
                                    // Click save button after selecting all cities
                                    if (clickedCount > 0) {
                                        const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                        if (saveBtn) { 
                                            saveBtn.click(); 
                                            return 'NAUKRI_CHAT_CHECKBOX_SAVED: Selected all ' + clickedCount + ' cities | DBG: ' + debugLog.join(', '); 
                                        }
                                    }
                                } else {
                                    // For relocation questions with few checkboxes, select Yes if available
                                    let yesCheckbox = checkboxLabels.find((item) => 
                                        item.lowerLabel.includes('yes') && !item.lowerLabel.includes('no')
                                    );
                                    
                                    // If no exact Yes found, look for positive indicators
                                    if (!yesCheckbox) {
                                        yesCheckbox = checkboxLabels.find((item) => 
                                            item.lowerLabel.includes('willing') || 
                                            item.lowerLabel.includes('agree') ||
                                            item.lowerLabel.includes('confirm')
                                        );
                                    }
                                    
                                    if (yesCheckbox && !yesCheckbox.cb.checked) {
                                        yesCheckbox.cb.click();
                                        if (!yesCheckbox.cb.checked) {
                                            yesCheckbox.cb.checked = true;
                                            yesCheckbox.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        clickedCount = 1;
                                        debugLog.push("RELOC_CB: " + yesCheckbox.labelText);
                                    } else if (yesCheckbox && yesCheckbox.cb.checked) {
                                        clickedCount = 1;
                                        debugLog.push("RELOC_CB: " + yesCheckbox.labelText + " (already checked)");
                                    }
                                }
                            } else if (isNoticePeriodQuestion) {
                                // For notice period questions, select "Serving Notice Period" option
                                let bestCheckbox = null;
                                let bestScore = -1;
                                let allLabels = []; // Debug: store all found labels
                                
                                for (const item of checkboxLabels) {
                                    allLabels.push(item.labelText);
                                    let score = 0;
                                    const labelLower = item.lowerLabel;
                                    
                                    // Highest priority: "Serving Notice Period" option
                                    if (labelLower.includes('serving notice period')) {
                                        score = 100;
                                    }
                                    // Secondary: any option with "serving" in it
                                    else if (labelLower.includes('serving')) {
                                        score = 90;
                                    }
                                    // Third: "Serving Notice" (without "Period")
                                    else if (labelLower.includes('serving notice')) {
                                        score = 85;
                                    }
                                    
                                    if (score > bestScore) {
                                        bestScore = score;
                                        bestCheckbox = item;
                                    }
                                }
                                
                                // Click only the "Serving Notice Period" checkbox
                                if (bestCheckbox && bestScore >= 85 && !bestCheckbox.cb.checked) {
                                    bestCheckbox.cb.click();
                                    if (!bestCheckbox.cb.checked) {
                                        bestCheckbox.cb.checked = true;
                                        bestCheckbox.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    clickedCount = 1;
                                    debugLog.push("NOTICE_CB: " + bestCheckbox.labelText + " (score: " + bestScore + ")");
                                } else if (bestCheckbox && bestScore >= 85 && bestCheckbox.cb.checked) {
                                    clickedCount = 1;
                                    debugLog.push("NOTICE_CB: " + bestCheckbox.labelText + " (already checked)");
                                } else {
                                    // Serving Notice Period not found - select next best option
                                    // Priority: 15 days or less / 0-15 days > 7 days > 1 month > 2 month > 3 month > first available
                                    const fallbackPriority = [
                                        (l) => l.includes('0-15 day') || l.includes('0-15day'),
                                        (l) => l.includes('15 day') || l.includes('15days') || l.includes('less'),
                                        (l) => l.includes('7 day') || l.includes('7day'),
                                        (l) => l.includes('1 month') || l === '1month',
                                        (l) => l.includes('2 month') || l === '2month',
                                        (l) => l.includes('3 month') || l === '3month',
                                    ];
                                    let fallbackCheckbox = null;
                                    for (const matcher of fallbackPriority) {
                                        fallbackCheckbox = checkboxLabels.find(item => matcher(item.lowerLabel));
                                        if (fallbackCheckbox) break;
                                    }
                                    // Last resort: first available option
                                    if (!fallbackCheckbox && checkboxLabels.length > 0) {
                                        fallbackCheckbox = checkboxLabels[0];
                                    }
                                    if (fallbackCheckbox && !fallbackCheckbox.cb.checked) {
                                        fallbackCheckbox.cb.click();
                                        if (!fallbackCheckbox.cb.checked) {
                                            fallbackCheckbox.cb.checked = true;
                                            fallbackCheckbox.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        clickedCount = 1;
                                        debugLog.push("NOTICE_CB_FALLBACK: " + fallbackCheckbox.labelText + " (Serving Notice Period not found)");
                                    } else if (fallbackCheckbox && fallbackCheckbox.cb.checked) {
                                        clickedCount = 1;
                                        debugLog.push("NOTICE_CB_FALLBACK: " + fallbackCheckbox.labelText + " (already checked)");
                                    } else {
                                        debugLog.push("NOTICE_CB_ERROR: No options found. Available: " + allLabels.join(", "));
                                    }
                                }
                            } else if (isExperienceQuestion) {
                                // For experience questions with checkboxes, select only the best matching range
                                // Target: 4 years experience -> select "3 - 5 years"
                                let bestCheckbox = null;
                                let bestScore = -1;
                                let allLabels = []; // Debug: store all found labels
                                const targetExperience = 4; // Years of experience
                                
                                for (const item of checkboxLabels) {
                                    allLabels.push(item.labelText);
                                    let score = 0;
                                    const labelLower = item.lowerLabel;
                                    
                                    // Look for year ranges like "3 - 5 years", "1-2 years", "5-6 years", etc.
                                    const rangeMatch = labelLower.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                                    if (rangeMatch) {
                                        const min = parseFloat(rangeMatch[1]);
                                        const max = parseFloat(rangeMatch[2]);
                                        
                                        // If target falls within range, highest score
                                        if (targetExperience >= min && targetExperience <= max) {
                                            score = 100;
                                        }
                                        // Within 1 year of either bound
                                        else if (Math.abs(targetExperience - max) <= 1 || Math.abs(targetExperience - min) <= 1) {
                                            score = 80;
                                        }
                                        // Within 2 years of either bound (catches "5-6 years" when target=4)
                                        else if (Math.abs(targetExperience - max) <= 2 || Math.abs(targetExperience - min) <= 2) {
                                            score = 60;
                                        }
                                        // Further away — score inversely proportional to distance from lower bound
                                        else {
                                            score = Math.max(1, 40 - Math.floor(Math.abs(targetExperience - min)));
                                        }
                                    }
                                    // Handle open-ended formats: ">7 years", "7+ years", "more than 7", "above 7"
                                    else if (labelLower.match(/[>+]|more than|above|over/)) {
                                        const numMatch = labelLower.match(/(\d+(?:\.\d+)?)/);
                                        if (numMatch) {
                                            const threshold = parseFloat(numMatch[1]);
                                            // Target exceeds threshold — exact match
                                            if (targetExperience > threshold) {
                                                score = 100;
                                            }
                                            // Target close below threshold — decent fallback
                                            else if (threshold - targetExperience <= 2) {
                                                score = 45;
                                            }
                                            // Further below — low but non-zero so it can still win
                                            else {
                                                score = Math.max(1, 20 - Math.floor(threshold - targetExperience));
                                            }
                                        }
                                    }
                                    // Look for single year values like "3 years", "5 years"
                                    else {
                                        const yearMatch = labelLower.match(/(\d+(?:\.\d+)?)/);
                                        if (yearMatch) {
                                            const year = parseFloat(yearMatch[1]);
                                            const diff = Math.abs(targetExperience - year);
                                            if (diff <= 0.5) score = 90;
                                            else if (diff <= 1) score = 70;
                                            else if (diff <= 2) score = 50;
                                            else score = Math.max(1, 30 - Math.floor(diff));
                                        }
                                    }
                                    
                                    if (score > bestScore) {
                                        bestScore = score;
                                        bestCheckbox = item;
                                    }
                                }
                                
                                // Click the best matching checkbox (threshold lowered — always pick closest)
                                if (bestCheckbox && bestScore >= 50 && !bestCheckbox.cb.checked) {
                                    bestCheckbox.cb.click();
                                    if (!bestCheckbox.cb.checked) {
                                        bestCheckbox.cb.checked = true;
                                        bestCheckbox.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    clickedCount = 1;
                                    debugLog.push("EXP_CB: " + bestCheckbox.labelText + " (score: " + bestScore + ")");
                                } else if (bestCheckbox && bestScore >= 50 && bestCheckbox.cb.checked) {
                                    clickedCount = 1;
                                    debugLog.push("EXP_CB: " + bestCheckbox.labelText + " (already checked)");
                                } else {
                                    // No option met threshold — fall back to closest available (never loop)
                                    const fallbackCb = bestCheckbox || (checkboxLabels.length > 0 ? checkboxLabels[0] : null);
                                    if (fallbackCb && !fallbackCb.cb.checked) {
                                        fallbackCb.cb.click();
                                        if (!fallbackCb.cb.checked) {
                                            fallbackCb.cb.checked = true;
                                            fallbackCb.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        clickedCount = 1;
                                        debugLog.push("EXP_CB_FALLBACK: " + fallbackCb.labelText + " (best available, score: " + bestScore + ")");
                                    } else if (fallbackCb && fallbackCb.cb.checked) {
                                        clickedCount = 1;
                                        debugLog.push("EXP_CB_FALLBACK: " + fallbackCb.labelText + " (already checked)");
                                    } else {
                                        debugLog.push("EXP_CB_ERROR: No options found. Available: " + allLabels.join(", "));
                                    }
                                }
                            } else if (isProgrammingLanguageQuestion) {
                                // For programming language questions, select ALL options except "Other" and "Skip"
                                for (const item of checkboxLabels) {
                                    const labelLower = item.lowerLabel.trim();
                                    
                                    // Skip "Other" and "Skip" options
                                    if (labelLower === 'other' || labelLower.includes('skip') || labelLower === 'others' || labelLower.startsWith('other ')) {
                                        debugLog.push("LANG_SKIP: " + item.labelText);
                                        continue;
                                    }
                                    
                                    if (!item.cb.checked) {
                                        item.cb.click();
                                        if (!item.cb.checked) {
                                            item.cb.checked = true;
                                            item.cb.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                        clickedCount++;
                                        debugLog.push("LANG_CB: " + item.labelText);
                                    } else {
                                        clickedCount++;
                                        debugLog.push("LANG_CB: " + item.labelText + " (already checked)");
                                    }
                                }
                            } else {
                                // Not binary - process normally
                                for (const cb of allCheckboxes) {
                                    let label = cb.closest('label') || document.querySelector(`label.mcc__label[for="${cb.id}"]`);
                                    if (!label && cb.id) {
                                        label = document.querySelector(`label[for="${cb.id}"]`);
                                    }
                                    if (!label) {
                                        label = cb.parentElement; 
                                    }
                                    
                                    const labelText = label ? (label.innerText || cb.id || '') : (cb.id || '');
                                    const lowerLabel = labelText.toLowerCase();

                                    debugLog.push("CB: " + labelText);
                                    
                                    // Ignore job list checkboxes
                                    if (cb.closest('.naukicon-ot-checkbox')) continue;

                                    // ALWAYS ignore "Skip"
                                    if (lowerLabel.includes('skip')) continue;
                                    
                                    // If already checked, count but don't re-click
                                    if (cb.checked) {
                                        clickedCount++;
                                        continue;
                                    }

                                    // For city questions, prefer "Both" or "All" option first
                                    if (isCityQuestion) {
                                        if (lowerLabel.includes('both') || lowerLabel.includes('all')) {
                                            cb.click();
                                            if (!cb.checked) {
                                                cb.checked = true;
                                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                            }
                                            // Click save and return immediately
                                            const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                            if (saveBtn) { 
                                                saveBtn.click(); 
                                                return 'NAUKRI_CHAT_CHECKBOX_SAVED: Selected Both/All locations'; 
                                            }
                                        }
                                        // Continue to select all cities
                                    }

                                    // ACTION: Click the checkbox (for non-binary questions)
                                    cb.click();
                                    
                                    // Verification & Fallback
                                    if (!cb.checked) {
                                         cb.checked = true;
                                         cb.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    
                                    clickedCount++;
                                }
                            }
                            
                            if (clickedCount > 0) {
                                const saveBtn = document.querySelector('div.sendMsg:not(.disabled)') || document.querySelector('.sendMsgbtn_container .sendMsg');
                                if (saveBtn) { 
                                    saveBtn.click(); 
                                    return 'NAUKRI_CHAT_CHECKBOX_SAVED: ' + clickedCount + ' | DBG: ' + debugLog.join(', '); 
                                }
                            }
                        }

                        // Try option buttons (with answer-aware matching)
                        const optionBtns = document.querySelectorAll('.chatbot_OptionContainer button');
                        if (optionBtns.length > 0) {
                            // Get question text for answer matching
                            const optQEl = document.querySelector('.chatbot_QuestionContainer, .botMsg, [class*="question"]');
                            const optQText = optQEl ? optQEl.innerText || '' : '';
                            const optAnswer = fuzzyMatch(optQText) || '';
                            const optAnsLower = optAnswer.toLowerCase();
                            
                            let clickedOpt = false;
                            for (const btn of optionBtns) {
                                const btnText = btn.innerText.trim().toLowerCase();
                                if (btnText === optAnsLower || 
                                    btnText.includes(optAnsLower) || 
                                    optAnsLower.includes(btnText) ||
                                    ((optAnsLower === 'yes' || optAnsLower.includes('yes')) && btnText === 'yes') ||
                                    ((optAnsLower === 'no' || optAnsLower.startsWith('no')) && btnText === 'no')) {
                                    btn.click();
                                    clickedOpt = true;
                                    return 'NAUKRI_CHAT_OPT_CLICKED: ' + btn.innerText.trim();
                                }
                            }
                            // Fallback: only click first option if it's not just "skip" and no contenteditable exists
                            if (!clickedOpt) {
                                const hasCE = document.querySelector('div[contenteditable="true"]');
                                const allSkipBtns = Array.from(optionBtns).every(b => (b.innerText || '').toLowerCase().includes('skip'));
                                if (allSkipBtns && hasCE) {
                                    console.log('Naukri chat - Options are all skip, falling through to contenteditable');
                                } else {
                                    optionBtns[0].click();
                                    return 'NAUKRI_CHAT_OPT_CLICKED: ' + optionBtns[0].innerText.trim() + ' (fallback)';
                                }
                            }
                        }
                        
                        // DOM INSPECTION on Wait
                        const activeMsg = document.querySelector('.chatbot_MessageContainer li:last-child') || document.querySelector('.chatbot_MessageContainer');
                        const dump = activeMsg ? activeMsg.innerHTML.slice(0, 800) : 'No active msg';
                        
                        return 'NAUKRI_CHAT_WAITING | DOM: ' + dump + ' | CBs: ' + debugLog.join(', ');
                    }
                    
                    // 2. Check if we're on the recommended jobs page
                    const applyBtn = document.querySelector('button.multi-apply-button');
                    if (applyBtn) {
                        const remaining = parseInt(sessionStorage.getItem('naukri_remaining') || TARGET_JOBS);
                        let clickedCount = 0;
                        
                        // Use the EXACT Naukri checkbox selector from DOM inspection
                        // Unchecked: i.dspIB.naukicon.naukicon-ot-checkbox (without Checked class)
                        // Checked: i.dspIB.naukicon.naukicon-ot-Checked
                        const uncheckedBoxes = document.querySelectorAll(
                            'i.naukicon.naukicon-ot-checkbox:not(.naukicon-ot-Checked)'
                        );
                        
                        // If no unchecked boxes in current section, navigate to next tab
                        if (uncheckedBoxes.length === 0) {
                            // Tab cycle: Applies -> Preferences -> You might like -> Profile -> Top Candidate
                            const tabOrder = ['apply', 'preference', 'similar_jobs', 'profile', 'top_candidate'];
                            
                            // Use sessionStorage tracker to follow the fixed cycle order
                            let nextIdx = parseInt(sessionStorage.getItem('naukri_tab_idx') || '-1');
                            nextIdx = (nextIdx + 1) % tabOrder.length;
                            sessionStorage.setItem('naukri_tab_idx', nextIdx);
                            
                            // If we've cycled all the way back to index 0, we've checked all tabs
                            if (nextIdx === 0) {
                                return 'NAUKRI_NO_JOBS_LEFT: All tabs exhausted';
                            }
                            
                            const nextTabId = tabOrder[nextIdx];
                            console.log('NAUKRI DEBUG: Cycle step', nextIdx, '- navigating to:', nextTabId);
                            
                            // Try multiple selectors to find the tab
                            let nextTab = document.querySelector(`#${nextTabId} .tab-list-item`);
                            
                            if (!nextTab) {
                                const allTabs = document.querySelectorAll('.tab-list-item');
                                for (const tab of allTabs) {
                                    const tabText = tab.innerText.toLowerCase();
                                    if (tabText.includes(nextTabId.replace('_', ' ')) || 
                                        tabText.includes(nextTabId.replace('_', ''))) {
                                        nextTab = tab;
                                        console.log('NAUKRI DEBUG: Found tab by text match:', tabText);
                                        break;
                                    }
                                }
                            }
                            
                            if (nextTab) {
                                console.log('NAUKRI DEBUG: Clicking tab:', nextTab.innerText?.substring(0, 30));
                                nextTab.click();
                                return 'NAUKRI_NAVIGATING_TO_TAB (0 jobs): ' + nextTabId;
                            } else {
                                console.log('NAUKRI DEBUG: Could not find tab element for:', nextTabId);
                                return 'NAUKRI_NO_JOBS_LEFT: All tabs exhausted';
                            }
                        }
                        
                        // Apply to WHATEVER jobs are available (even if < 5)
                        // The remaining counter will be updated after successful application
                        
                        for (const checkbox of uncheckedBoxes) {
                            if (clickedCount >= remaining) break;
                            if (checkbox.offsetParent !== null) {
                                checkbox.scrollIntoView({ block: 'center' });
                                checkbox.click();
                                clickedCount++;
                            }
                        }
                        
                        // Fallback: Try article-based approach
                        if (clickedCount === 0) {
                            const articles = document.querySelectorAll('article.jobTuple, .sim-jobs article, .list article');
                            for (const article of articles) {
                                if (clickedCount >= remaining) break;
                                const checkbox = article.querySelector('i.naukicon-ot-checkbox:not(.naukicon-ot-Checked)') ||
                                                article.querySelector('.tuple-check-box i:not(.checked)') ||
                                                article.querySelector('input[type="checkbox"]:not(:checked)');
                                if (checkbox && checkbox.offsetParent !== null) {
                                    checkbox.scrollIntoView({ block: 'center' });
                                    checkbox.click();
                                    clickedCount++;
                                }
                            }
                        }
                        
                        // If we selected some jobs, click Apply with robustness
                        if (clickedCount > 0) {
                            applyBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
                            // NOTE: await removed - Python handles delays between evaluate calls
                            
                            // Robust click sequence
                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            
                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {
                                // NOTE: await sleep(500) removed - Python handles delays between evaluate calls
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + clickedCount + ' jobs selected';
                        }
                        
                        // Check if there are already some checked
                        const alreadyChecked = document.querySelectorAll('i.naukicon-ot-Checked, .tuple-check-box i.checked, input[type="checkbox"]:checked').length;
                        if (alreadyChecked > 0) {
                            applyBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
                            // NOTE: await removed - Python handles delays between evaluate calls
                            
                            applyBtn.click();
                            applyBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            applyBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            
                            // MONITOR: Check for error snackbar
                            // NOTE: Loop-based await removed - single check only, Python handles polling
                            for (let i = 0; i < 1; i++) {
                                // NOTE: await sleep(500) removed - Python handles delays between evaluate calls
                                const snackBody = document.querySelector('.ss-snackbar-body');
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong')) {
                                        const closeBtn = document.querySelector('button.ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"]');
                                if (genericSnack && genericSnack.innerText.toLowerCase().includes('error')) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + alreadyChecked + ' jobs already selected';
                        }
                        
                        // No checkboxes in current section - navigate to next tab in order
                        // Tab cycle: Applies -> Preferences -> You might like -> Profile -> Top Candidate
                        const tabOrder = ['apply', 'preference', 'similar_jobs', 'profile', 'top_candidate'];
                        
                        // Use sessionStorage tracker to follow the fixed cycle order
                        let nextIdx = parseInt(sessionStorage.getItem('naukri_tab_idx') || '-1');
                        nextIdx = (nextIdx + 1) % tabOrder.length;
                        sessionStorage.setItem('naukri_tab_idx', nextIdx);
                        
                        // If we've cycled all the way back to index 0, we've checked all tabs
                        if (nextIdx === 0) {
                            return 'NAUKRI_NO_CHECKBOX_IN_SECTION: All tabs exhausted';
                        }
                        
                        const nextTabId = tabOrder[nextIdx];
                        console.log('NAUKRI DEBUG: Cycle step', nextIdx, '- navigating to:', nextTabId);
                        
                        // Try multiple selectors to find the tab
                        let nextTab = document.querySelector(`#${nextTabId} .tab-list-item`);
                        
                        if (!nextTab) {
                            const allTabs = document.querySelectorAll('.tab-list-item');
                            for (const tab of allTabs) {
                                const tabText = tab.innerText.toLowerCase();
                                if (tabText.includes(nextTabId.replace('_', ' ')) || 
                                    tabText.includes(nextTabId.replace('_', ''))) {
                                    nextTab = tab;
                                    console.log('NAUKRI DEBUG: Found tab by text match:', tabText);
                                    break;
                                }
                            }
                        }
                        
                        if (nextTab) {
                            console.log('NAUKRI DEBUG: Clicking tab:', nextTab.innerText?.substring(0, 30));
                            nextTab.click();
                            return 'NAUKRI_NAVIGATING_TO_TAB: ' + nextTabId;
                        } else {
                            console.log('NAUKRI DEBUG: Could not find tab element for:', nextTabId);
                            return 'NAUKRI_NO_CHECKBOX_IN_SECTION: All tabs exhausted';
                        }
                    }
                }

                // ============================================================
                // INSTAHYRE LOGIC (Fully Restored & Robust)
                // ============================================================
                if (isInstahyre) {
                    // Helper function to add items to selectize dropdowns
                    const addSelectizeItem = (containerSelector, inputSelector, itemText) => {
                        const container = document.querySelector(containerSelector);
                        const input = document.querySelector(inputSelector);
                        if (!container || !input) return false;
                        
                        // Check if item already exists
                        const existingItems = container.querySelectorAll('.item');
                        for (const item of existingItems) {
                            if (item.textContent && item.textContent.toLowerCase().includes(itemText.toLowerCase())) {
                                return false; // Already added
                            }
                        }
                        
                        // Focus the input to open dropdown
                        input.focus();
                        input.click();
                        
                        // Type the text
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        if (setter) setter.call(input, itemText);
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
                        
                        return true;
                    };
                    
                    // 1. Navigation: Ensure "Search other jobs" (Filter Panel) is OPEN
                    if (window.location.href.includes('opportunities')) {
                        
                        // IMPORTANT: If URL has search params, we're already on results - skip filter config
                        const urlParams = new URLSearchParams(window.location.search);
                        const hasSearchParams = urlParams.has('job_functions') || urlParams.has('skills');
                        
                        // Check if filters panel is OPEN using the filters container (more reliable)
                        const filtersPanel = document.querySelector('div.job-search-filters');
                        const expInput = document.querySelector('input#years');
                        const isPanelOpen = (filtersPanel && filtersPanel.offsetParent !== null) || 
                                           (expInput && expInput.offsetParent !== null);
                        
                        // Check for collapsed state indicator (chevron pointing down)
                        const chevronDown = document.querySelector('.job-search-heading .fa-angle-down');
                        const isPanelCollapsed = chevronDown && chevronDown.offsetParent !== null;
                        
                        // Skip filter configuration if we already have search results
                        // If Panel is CLOSED (or collapsed) and NOT on search results, we must Open it
                        if ((!isPanelOpen || isPanelCollapsed) && !hasSearchParams) {
                            // PRIORITY 1: Target the exact Instahyre class for "Search other jobs"
                            const jobSearchHeading = document.querySelector('.job-search-heading');
                            if (jobSearchHeading) {
                                console.log('Clicking job-search-heading:', jobSearchHeading.innerText);
                                // Use MouseEvent dispatch for Angular ng-click compatibility
                                const clickEvent = new MouseEvent('click', {
                                    bubbles: true, cancelable: true, view: window
                                });
                                jobSearchHeading.dispatchEvent(clickEvent);
                                return 'INSTAHYRE_OPENING_PANEL';
                            }
                            
                            // PRIORITY 2: Try the sidebar section container
                            const sidebarSection = document.querySelector('.sidebar-section.job-search-section');
                            if (sidebarSection) {
                                const heading = sidebarSection.querySelector('div[ng-click]');
                                if (heading) {
                                    console.log('Clicking sidebar section heading');
                                    const clickEvent = new MouseEvent('click', {
                                        bubbles: true, cancelable: true, view: window
                                    });
                                    heading.dispatchEvent(clickEvent);
                                    return 'INSTAHYRE_OPENING_PANEL';
                                }
                            }
                            
                            // PRIORITY 3: Fallback - text match with MouseEvent
                            const searchTriggers = Array.from(document.querySelectorAll('div, span, h4, h5')).filter(el => 
                                el.innerText && el.innerText.trim().toLowerCase() === 'search other jobs'
                            );
                            for (const trigger of searchTriggers) {
                                if (trigger && trigger.offsetParent !== null) {
                                    console.log('Clicking Search Trigger (text match):', trigger);
                                    const clickEvent = new MouseEvent('click', {
                                        bubbles: true, cancelable: true, view: window
                                    });
                                    trigger.dispatchEvent(clickEvent);
                                    return 'INSTAHYRE_OPENING_PANEL';
                                }
                            }
                        }
                        
                        // 2. Fill Details (Configuration) - One step at a time for reliability
                        // ORDER: Skills -> Job Functions -> Location -> Experience
                        
                        // Helper function to get selectize instance
                        // NOTE: Instahyre uses custom <selectize> tags, NOT <select> tags
                        const getSelectize = (fieldId) => {
                            const selectizeEl = document.querySelector('selectize#' + fieldId);
                            return selectizeEl && selectizeEl.selectize ? selectizeEl.selectize : null;
                        };
                        
                        // Check for pending operations (prevents rapid re-invocations)
                        const pendingOp = sessionStorage.getItem('instahyre_pending');
                        if (pendingOp) {
                            const [op, timestamp] = pendingOp.split('|');
                            const elapsed = Date.now() - parseInt(timestamp);
                            if (elapsed < 800) {
                                // Still waiting for previous operation
                                return 'INSTAHYRE_WAITING: ' + op;
                            } else {
                                // Timeout expired, clear pending
                                sessionStorage.removeItem('instahyre_pending');
                            }
                        }
                        
                        // A. Skills - Add one skill at a time (FIRST)
                        const skillsToAdd = ['Java', 'JavaScript', 'HTML', 'CSS', 'SpringBoot', 'ReactJS', 'AWS'];
                        const skillsSelectize = getSelectize('skills');
                        const skillsInput = document.querySelector('input#skills-selectized');
                        if (skillsInput) {
                            const skillsControl = skillsInput.closest('.selectize-control');
                            const skillsContainer = skillsControl ? skillsControl.querySelector('.selectize-input') : null;
                            if (skillsContainer) {
                                // Check existing skills using Selectize API
                                let existingSkills = [];
                                if (skillsSelectize) {
                                    existingSkills = skillsSelectize.items.map(key => {
                                        const opt = skillsSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    });
                                } else {
                                    // Fallback: DOM parsing with × removal
                                    existingSkills = Array.from(skillsContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }
                                
                                for (const skill of skillsToAdd) {
                                    if (!existingSkills.some(s => s.includes(skill.toLowerCase()))) {
                                        // Try Selectize API first
                                        if (skillsSelectize) {
                                            // Use addItem if option exists, else createItem
                                            if (skillsSelectize.options[skill]) {
                                                skillsSelectize.addItem(skill);
                                            } else {
                                                skillsSelectize.createItem(skill);
                                            }
                                            return 'INSTAHYRE_ADDED_SKILL: ' + skill;
                                        }
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'skill_' + skill + '|' + Date.now());
                                        skillsInput.focus();
                                        skillsInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(skillsInput, skill);
                                        skillsInput.dispatchEvent(new Event('input', { bubbles: true }));
                                        // Schedule click with longer delay
                                        setTimeout(() => {
                                            const dropdown = skillsControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }
                                            }
                                        }, 500);
                                        return 'INSTAHYRE_ADDING_SKILL: ' + skill;
                                    }
                                }
                            }
                        }
                        
                        // B. Job Functions - Use Selectize API (SECOND)
                        const jobFuncsToAdd = ['Backend Development', 'Frontend Development', 'Full-Stack Development'];
                        const jobFuncSelectize = getSelectize('job-functions');
                        const jobFuncInput = document.querySelector('input#job-functions-selectized');
                        if (jobFuncInput) {
                            const jobFuncControl = jobFuncInput.closest('.selectize-control');
                            const jobFuncContainer = jobFuncControl ? jobFuncControl.querySelector('.selectize-input') : null;
                            if (jobFuncContainer) {
                                // Use Selectize API for accurate check of existing items
                                let existingTexts = [];
                                if (jobFuncSelectize) {
                                    existingTexts = jobFuncSelectize.items.map(key => {
                                        const opt = jobFuncSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    });
                                } else {
                                    // Fallback: DOM parsing with × removal
                                    existingTexts = Array.from(jobFuncContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }
                                
                                for (const func of jobFuncsToAdd) {
                                    const funcKeyword = func.split(' ')[0].toLowerCase(); // "backend", "frontend", "full-stack"
                                    if (!existingTexts.some(f => f.includes(funcKeyword))) {
                                        // Try Selectize API first
                                        if (jobFuncSelectize) {
                                            // Find the option key by matching text
                                            const options = jobFuncSelectize.options;
                                            let foundKey = null;
                                            for (const key in options) {
                                                const optText = (options[key].text || options[key].name || '').toLowerCase();
                                                if (optText.includes(funcKeyword)) {
                                                    foundKey = key;
                                                    break;
                                                }
                                            }
                                            if (foundKey) {
                                                jobFuncSelectize.addItem(foundKey);
                                                return 'INSTAHYRE_ADDED_JOB_FUNC: ' + func;
                                            }
                                        }
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'jobfunc_' + func + '|' + Date.now());
                                        jobFuncInput.focus();
                                        jobFuncInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(jobFuncInput, funcKeyword);
                                        jobFuncInput.dispatchEvent(new Event('input', { bubbles: true }));
                                        setTimeout(() => {
                                            const dropdown = jobFuncControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }
                                            }
                                        }, 500);
                                        return 'INSTAHYRE_ADDING_JOB_FUNC: ' + func;
                                    }
                                }
                            }
                        }
                        
                        // C. Location - Add all locations one by one (same logic as skills)
                        const locationsToAdd = ['Anywhere in India', 'Work from home / Remote', 'Bangalore', 'Noida', 'Gurgaon', 'Pune', 'Delhi', 'Delhi / NCR', 'Mumbai', 'Hyderabad'];
                        const locationSelectize = getSelectize('locations');
                        const locationInput = document.querySelector('input#locations-selectized');
                        if (locationInput) {
                            const locControl = locationInput.closest('.selectize-control');
                            const locationContainer = locControl ? locControl.querySelector('.selectize-input') : null;
                            if (locationContainer) {
                                // Check existing locations using Selectize API
                                let existingLocations = [];
                                if (locationSelectize) {
                                    existingLocations = locationSelectize.items.map(key => {
                                        const opt = locationSelectize.options[key];
                                        return opt ? (opt.text || opt.name || key).toLowerCase() : key.toLowerCase();
                                    });
                                } else {
                                    // Fallback: DOM parsing with × removal
                                    existingLocations = Array.from(locationContainer.querySelectorAll('.item'))
                                        .map(item => (item.textContent || '').replace(/×/g, '').toLowerCase().trim());
                                }
                                
                                for (const location of locationsToAdd) {
                                    // Use a keyword from each location for matching
                                    const locKeyword = location.toLowerCase().split('/')[0].trim().split(' ').pop();
                                    if (!existingLocations.some(l => l.includes(locKeyword))) {
                                        // Try Selectize API first
                                        if (locationSelectize) {
                                            const options = locationSelectize.options;
                                            let foundKey = null;
                                            for (const key in options) {
                                                const optText = (options[key].text || options[key].name || '').toLowerCase();
                                                if (optText.includes(location.toLowerCase()) || optText.includes(locKeyword)) {
                                                    foundKey = key;
                                                    break;
                                                }
                                            }
                                            if (foundKey) {
                                                locationSelectize.addItem(foundKey);
                                                return 'INSTAHYRE_ADDED_LOCATION: ' + location;
                                            }
                                        }
                                        // Fallback: Set pending state, trigger input, schedule click
                                        sessionStorage.setItem('instahyre_pending', 'location_' + location + '|' + Date.now());
                                        locationInput.focus();
                                        locationInput.click();
                                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                                        if (setter) setter.call(locationInput, location);
                                        locationInput.dispatchEvent(new Event('input', { bubbles: true }));
                                        setTimeout(() => {
                                            const dropdown = locControl.querySelector('.selectize-dropdown-content');
                                            if (dropdown) {
                                                const option = dropdown.querySelector('.option.active, .option:first-child');
                                                if (option) {
                                                    option.click();
                                                    sessionStorage.removeItem('instahyre_pending');
                                                }
                                            }
                                        }, 500);
                                        return 'INSTAHYRE_ADDING_LOCATION: ' + location;
                                    }
                                }
                            }
                        }
                        
                        // D. Experience (LAST - after all selectize fields)
                        if (expInput && expInput.value !== '4') {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            if (setter) setter.call(expInput, '4');
                            expInput.dispatchEvent(new Event('input', { bubbles: true }));
                            expInput.dispatchEvent(new Event('change', { bubbles: true }));
                            return 'INSTAHYRE_SET_EXPERIENCE';
                        }

                        // 3. Click "Show Results" - Only after ALL fields are configured AND not already on results
                        // Use exact selector from DOM: button#show-results.btn.btn-primary.show-results
                        const showResultsBtn = document.querySelector('button#show-results.btn-primary.show-results') ||
                                              document.querySelector('button#show-results');
                        if (showResultsBtn && showResultsBtn.offsetParent !== null && isPanelOpen && !hasSearchParams) {
                            // Verify ALL fields are configured before clicking
                            const hasExp = expInput && expInput.value === '4';
                            
                            // Check location - use correct plural selector
                            const locInput = document.querySelector('input#locations-selectized');
                            const locCtrl = locInput ? locInput.closest('.selectize-control') : null;
                            const locContainer = locCtrl ? locCtrl.querySelector('.selectize-input') : null;
                            const hasLocation = locContainer && locContainer.querySelectorAll('.item').length >= 3;
                            
                            // Check skills (need at least 3 skills)
                            const skillsInp = document.querySelector('input#skills-selectized');
                            const skillsCtrl = skillsInp ? skillsInp.closest('.selectize-control') : null;
                            const skillsContainerCheck = skillsCtrl ? skillsCtrl.querySelector('.selectize-input') : null;
                            const hasSkills = skillsContainerCheck && skillsContainerCheck.querySelectorAll('.item').length >= 3;
                            
                            // Check job functions (need at least 1)
                            const jobFuncInp = document.querySelector('input#job-functions-selectized');
                            const jobFuncCtrl = jobFuncInp ? jobFuncInp.closest('.selectize-control') : null;
                            const jobFuncContainerCheck = jobFuncCtrl ? jobFuncCtrl.querySelector('.selectize-input') : null;
                            const hasJobFuncs = jobFuncContainerCheck && jobFuncContainerCheck.querySelectorAll('.item').length >= 1;
                            
                            console.log('Config check: Exp=' + hasExp + ', Loc=' + hasLocation + ', Skills=' + hasSkills + ', JobFuncs=' + hasJobFuncs);
                            
                            // Only click Show Results if ALL fields are configured
                            if (hasExp && hasLocation && hasSkills && hasJobFuncs) {
                                showResultsBtn.scrollIntoView({ block: 'center' });
                                showResultsBtn.click();
                                return 'INSTAHYRE_SHOW_RESULTS_CLICKED';
                            } else {
                                // Return status indicating which field is pending
                                if (!hasSkills) return 'INSTAHYRE_PENDING_SKILLS';
                                if (!hasJobFuncs) return 'INSTAHYRE_PENDING_JOB_FUNCS';
                                if (!hasLocation) return 'INSTAHYRE_PENDING_LOCATION';
                                if (!hasExp) return 'INSTAHYRE_PENDING_EXPERIENCE';
                            }
                        }
                    }

                    // 4. View & Apply (The Main Loop)
                    
                    // A. Handle Modal - Look for Apply button in any modal
                    const modalApplyBtns = document.querySelectorAll('.modal button.btn-primary, .application-modal button, [class*="modal"] button.btn-primary');
                    for (const btn of modalApplyBtns) {
                        if (btn && btn.offsetParent !== null && (btn.innerText || '').toLowerCase().includes('apply')) {
                            btn.click();
                            return 'INSTAHYRE_APPLY_CLICKED';
                        }
                    }
                    
                    // A2. Close ANY visible modal/overlay that blocks interaction
                    // This handles post-apply confirmation dialogs, "already applied" modals, etc.
                    const allModals = document.querySelectorAll('.modal[style*="display: block"], .modal.show, .modal.fade.in, [class*="modal"].show, .modal-backdrop, [class*="overlay"][class*="show"]');
                    for (const modal of allModals) {
                        if (modal.offsetParent !== null || modal.classList.contains('modal-backdrop')) {
                            // Try close button first
                            const closeBtn = modal.querySelector('button.close, .close, [data-dismiss="modal"], button[aria-label="Close"], button[aria-label*="close"]');
                            if (closeBtn) {
                                closeBtn.click();
                                return 'INSTAHYRE_MODAL_CLOSED';
                            }
                        }
                    }
                    // Also try closing via Bootstrap jQuery if available
                    const openModal = document.querySelector('.modal.show, .modal.in');
                    if (openModal && openModal.offsetParent !== null) {
                        // Click the modal backdrop to dismiss
                        const backdrop = document.querySelector('.modal-backdrop');
                        if (backdrop) {
                            backdrop.click();
                            return 'INSTAHYRE_MODAL_CLOSED';
                        }
                        // Last resort: press Escape
                        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
                        return 'INSTAHYRE_MODAL_CLOSED';
                    }
                    
                    // B. Close success modals / alerts
                    const successIndicators = document.querySelectorAll('.alert-success, .success-message, [class*="success"], .alert-info');
                    for (const indicator of successIndicators) {
                        if (indicator && indicator.offsetParent !== null) {
                            const closeBtn = indicator.querySelector('button.close, .close, [data-dismiss="modal"], [data-dismiss="alert"]') ||
                                            document.querySelector('.modal button.close, .modal .close');
                            if (closeBtn) {
                                closeBtn.click();
                                return 'INSTAHYRE_MODAL_CLOSED_SUCCESS';
                            }
                        }
                    }
                    
                    // C. Click "View" on Job Cards - prioritized selector patterns from DOM inspection
                    // Skip buttons that say "Applied" or "Already Applied"
                    const primaryViewBtn = document.querySelector('button#interested-btn.btn-success:not([disabled])');
                    if (primaryViewBtn && primaryViewBtn.offsetParent !== null) {
                        const pText = (primaryViewBtn.innerText || '').toLowerCase();
                        if (!pText.includes('applied') && !pText.includes('saved')) {
                            primaryViewBtn.scrollIntoView({ block: 'center' });
                            primaryViewBtn.click();
                            return 'INSTAHYRE_VIEW_CLICKED';
                        }
                    }
                    
                    // Secondary: Multiple fallback patterns
                    const viewBtnSelectors = [
                        'button#interested-btn',
                        'button.button-interested.btn-success',
                        'button[ng-click*="openApplyModal"]',
                        '.opportunity-action-links button.btn-success',
                        'button.button-interested',
                        'button.btn-success',
                        'a.view-job',
                        '[class*="interested"] button'
                    ];
                    for (const sel of viewBtnSelectors) {
                        const btns = document.querySelectorAll(sel);
                        for (const btn of btns) {
                            const btnText = (btn.innerText || '').toLowerCase();
                            if ((btnText.includes('view') || btnText.includes('interested')) && !btn.disabled && btn.offsetParent !== null && !btnText.includes('applied')) {
                                btn.scrollIntoView({ block: 'center' });
                                btn.click();
                                return 'INSTAHYRE_VIEW_CLICKED';
                            }
                        }
                    }
                    
                    // C2. All visible view buttons say "Applied" — scroll down for fresh jobs
                    const allViewBtns = document.querySelectorAll('button#interested-btn, button.button-interested, .opportunity-action-links button.btn-success');
                    let allApplied = true;
                    let visibleCount = 0;
                    for (const btn of allViewBtns) {
                        if (btn.offsetParent !== null) {
                            visibleCount++;
                            const t = (btn.innerText || '').toLowerCase();
                            if (!t.includes('applied') && !t.includes('saved') && !btn.disabled) {
                                allApplied = false;
                                break;
                            }
                        }
                    }
                    if (visibleCount > 0 && allApplied) {
                        window.scrollBy(0, 800);
                        return 'INSTAHYRE_ALL_APPLIED_SCROLLING';
                    }
                    
                    // D. Check if no more jobs available — broad detection
                    const bodyText = document.body.innerText || '';
                    const noJobsIndicators = [
                        document.querySelector('.no-jobs, .no-results, [class*="empty-state"]'),
                        bodyText.includes('No matching jobs'),
                        bodyText.includes('No jobs found'),
                        bodyText.includes('No opportunities'),
                        bodyText.includes('No results found'),
                        bodyText.includes('0 opportunities'),
                    ];
                    if (noJobsIndicators.some(Boolean)) {
                        return 'INSTAHYRE_NO_MORE_JOBS';
                    }
                    
                    // D2. Check if results page has zero actual job cards (not generic .card elements)
                    const jobCards = document.querySelectorAll('.job-card, [class*="opportunity-card"], [class*="job-listing"], .opportunity-card');
                    const viewBtnsExist = document.querySelectorAll('button#interested-btn, button.button-interested').length > 0;
                    if (jobCards.length === 0 && !viewBtnsExist) {
                        // On the results page but no job cards at all — no jobs match
                        return 'INSTAHYRE_NO_MORE_JOBS';
                    }
                    
                    // E. Scroll to load more jobs if needed
                    if (jobCards.length > 0) {
                        const lastCard = jobCards[jobCards.length - 1];
                        lastCard.scrollIntoView({ block: 'end' });
                        return 'INSTAHYRE_SCROLLING_FOR_MORE';
                    }
                }

                // ============================================================
                // GENERIC FALLBACK - Handle forms on unrecognized platforms (TCS, etc.)
                // Reuses the same helpers: fuzzyMatch, findBestRadioMatch, findSalaryRangeMatch, etc.
                // ============================================================
                if (!isLinkedIn && !isNaukri && !isInstahyre) {
                    console.log('=== GENERIC PLATFORM FORM FILLING ===');
                    const genericResults = [];
                    
                    // 1. Handle text/number/textarea inputs
                    const allTextInputs = Array.from(document.querySelectorAll('input[type="text"], input[type="number"], input[type="tel"], input[type="email"], textarea')).filter(isVisible);
                    for (const input of allTextInputs) {
                        const label = input.closest('label')?.innerText || 
                                      input.closest('.form-group, .field, [class*="field"]')?.querySelector('label, span, p')?.innerText ||
                                      document.querySelector(`label[for="${input.id}"]`)?.innerText ||
                                      input.getAttribute('placeholder') || 
                                      input.getAttribute('aria-label') || 
                                      input.name?.replace(/[_-]/g, ' ') || '';
                        if (!label || label.length < 2) continue;
                        
                        const answer = fuzzyMatch(label);
                        if (answer && !input.value.trim()) {
                            fillReactInput(input, answer);
                            console.log('GENERIC: Filled input', label.substring(0, 40), 'with:', answer.substring(0, 30));
                            genericResults.push({ question: label.substring(0, 80), answer: answer, inputType: 'text' });
                        }
                    }
                    
                    // 2. Handle select dropdowns
                    const allSelects = Array.from(document.querySelectorAll('select')).filter(isVisible);
                    for (const select of allSelects) {
                        const label = select.closest('label')?.innerText || 
                                      select.closest('.form-group, .field, [class*="field"]')?.querySelector('label, span, p')?.innerText ||
                                      document.querySelector(`label[for="${select.id}"]`)?.innerText ||
                                      select.getAttribute('aria-label') || '';
                        if (!label || label.length < 2) continue;
                        
                        const answer = fuzzyMatch(label);
                        if (answer && select.selectedIndex <= 0) {
                            const options = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                            const bestOpt = options.find(o => o.text.toLowerCase().includes(answer.toLowerCase())) ||
                                            options.find(o => answer.toLowerCase().includes(o.text.toLowerCase()));
                            if (bestOpt) {
                                select.value = bestOpt.value;
                                if (select.value !== bestOpt.value) select.selectedIndex = bestOpt.index;
                                select.dispatchEvent(new Event('change', { bubbles: true }));
                                select.dispatchEvent(new Event('blur', { bubbles: true }));
                                console.log('GENERIC: Selected dropdown', label.substring(0, 40), ':', bestOpt.text);
                                genericResults.push({ question: label.substring(0, 80), answer: bestOpt.text, inputType: 'select' });
                            }
                        }
                    }
                    
                    // 3. Handle fieldset radio buttons
                    const allFieldsets = document.querySelectorAll('fieldset');
                    for (const fieldset of allFieldsets) {
                        const legend = fieldset.querySelector('legend')?.innerText || '';
                        const radios = Array.from(fieldset.querySelectorAll('input[type="radio"]')).filter(isVisible);
                        
                        if (legend && radios.length > 0 && !radios.some(r => r.checked)) {
                            const answer = fuzzyMatch(legend);
                            if (answer) {
                                let bestRadio = findBestRadioMatch(answer, radios);
                                if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(legend)) {
                                    bestRadio = findSalaryRangeMatch(answer, radios);
                                }
                                if (bestRadio) {
                                    clickInput(bestRadio);
                                    console.log('GENERIC: Clicked fieldset radio', legend.substring(0, 40), ':', answer);
                                    genericResults.push({ question: legend.substring(0, 80), answer: answer, inputType: 'radio' });
                                } else {
                                    const hasYes = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    const hasNo = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'no' || labelText === 'no' || labelText.includes('no');
                                    });
                                    const isYesNoFromRadios = radios.length <= 4 && hasYes && hasNo;
                                    const isYesNoFromText = isLikelyYesNoQuestion(legend);
                                    if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                        const yesRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        if (yesRadio) {
                                            clickInput(yesRadio);
                                            console.log('GENERIC: Selected Yes for Yes/No question:', legend.substring(0, 40));
                                            genericResults.push({ question: legend.substring(0, 80), answer: 'Yes', inputType: 'radio' });
                                        }
                                    }
                                }
                            } else {
                                const hasYes = radios.some(r => {
                                    const val = (r.value || '').toLowerCase();
                                    const labelText = getInputLabelText(r);
                                    return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                });
                                const hasNo = radios.some(r => {
                                    const val = (r.value || '').toLowerCase();
                                    const labelText = getInputLabelText(r);
                                    return val === 'no' || labelText === 'no' || labelText.includes('no');
                                    });
                                    const isYesNoFromRadios = radios.length <= 4 && hasYes && hasNo;
                                    const isYesNoFromText = isLikelyYesNoQuestion(legend);
                                    if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                        const yesRadio = radios.find(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    if (yesRadio) {
                                        clickInput(yesRadio);
                                        console.log('GENERIC: Selected Yes for unlabeled Yes/No question');
                                        genericResults.push({ question: 'Yes/No question (no label)', answer: 'Yes', inputType: 'radio' });
                                    }
                                }
                            }
                        }
                    }
                    
                    // 3b. Handle standalone radio buttons (grouped by name)
                    const genericAllRadios = Array.from(document.querySelectorAll('input[type="radio"]')).filter(isVisible);
                    const genericRadioGroups = {};
                    for (const radio of genericAllRadios) {
                        const name = radio.name;
                        if (!name || radio.checked) continue;
                        if (!genericRadioGroups[name]) genericRadioGroups[name] = [];
                        genericRadioGroups[name].push(radio);
                    }
                    
                    for (const [name, radios] of Object.entries(genericRadioGroups)) {
                        let questionText = '';
                        const firstRadio = radios[0];
                        
                        const parentLabel = firstRadio.closest('label');
                        if (parentLabel) {
                            questionText = parentLabel.innerText;
                        } else {
                            const container = firstRadio.closest('div[class*="question"], div[class*="field"], .form-group');
                            if (container) {
                                const textNodes = Array.from(container.childNodes)
                                    .filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'INPUT' && n.tagName !== 'LABEL'))
                                    .map(n => n.textContent || n.innerText)
                                    .join(' ').trim();
                                questionText = textNodes;
                            }
                        }
                        
                        if (!questionText && name && !name.match(/^[0-9]+$/)) {
                            questionText = name.replace(/[_-]/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase();
                        }
                        
                        // Try aria-labelledby
                        if (!questionText && firstRadio.id) {
                            const labelEl = document.getElementById(firstRadio.getAttribute('aria-labelledby') || '');
                            if (labelEl) questionText = labelEl.innerText;
                        }
                        
                        if (questionText) {
                            const answer = fuzzyMatch(questionText);
                            if (answer) {
                                let bestRadio = findBestRadioMatch(answer, radios);
                                if (!bestRadio && /salary|ctc|pay|lpa|lacs|compensation|annual/i.test(questionText)) {
                                    bestRadio = findSalaryRangeMatch(answer, radios);
                                }
                                if (bestRadio) {
                                    clickInput(bestRadio);
                                    console.log('GENERIC: Clicked standalone radio', questionText.substring(0, 40), ':', answer);
                                    genericResults.push({ question: questionText.substring(0, 80), answer: answer, inputType: 'radio' });
                                } else {
                                    const hasYes = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                    });
                                    const hasNo = radios.some(r => {
                                        const val = (r.value || '').toLowerCase();
                                        const labelText = getInputLabelText(r);
                                        return val === 'no' || labelText === 'no' || labelText.includes('no');
                                    });
                                    const isYesNoFromRadios = radios.length <= 4 && hasYes && hasNo;
                                    const isYesNoFromText = isLikelyYesNoQuestion(questionText);
                                    if (isYesNoFromRadios || (isYesNoFromText && hasYes)) {
                                        const yesRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === 'yes' || labelText === 'yes' || labelText.includes('yes');
                                        });
                                        if (yesRadio) {
                                            clickInput(yesRadio);
                                            console.log('GENERIC: Selected Yes for Yes/No:', questionText.substring(0, 40));
                                            genericResults.push({ question: questionText.substring(0, 80), answer: 'Yes', inputType: 'radio' });
                                        }
                                    }
                                }
                            }
                        }
                    }
                    
                    // 4. Handle checkboxes (consent, privacy policy)
                    const genericCheckboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).filter(isVisible);
                    for (const cb of genericCheckboxes) {
                        if (cb.checked) continue;
                        const label = cb.closest('label')?.innerText || 
                                      document.querySelector(`label[for="${cb.id}"]`)?.innerText || 
                                      cb.getAttribute('aria-label') || '';
                        const lowerLabel = label.toLowerCase();
                        if (lowerLabel.includes('consent') || lowerLabel.includes('privacy') || lowerLabel.includes('terms') || 
                            lowerLabel.includes('agree') || lowerLabel.includes('accept') || lowerLabel.includes('policy') ||
                            lowerLabel.includes('declaration') || lowerLabel.includes('confirm')) {
                            cb.click();
                            cb.dispatchEvent(new Event('change', { bubbles: true }));
                            console.log('GENERIC: Checked consent checkbox:', label.substring(0, 40));
                            genericResults.push({ question: label.substring(0, 80), answer: 'Checked', inputType: 'checkbox' });
                        }
                    }
                    
                    if (genericResults.length > 0) {
                        console.log('GENERIC: Filled', genericResults.length, 'fields');
                        return 'GENERIC_FORM_FILLED: ' + JSON.stringify(genericResults);
                    }
                }

                return 'NO_ACTION';
            })""".replace("__PATTERNS__", patterns_json).replace("__PATTERNS_WITH_DEFAULTS__", patterns_with_defaults_json).replace("__SYNONYMS__", synonyms_json).replace("__STOPWORDS__", stopwords_json).replace("__EXACT_MATCH_KEYS__", exact_match_keys_json)

            
            # Playwright automatically invokes the function expression
            result = await self._page.evaluate(js_code)
            return result
            

            
        except Exception as e:
            print(f"Error in scripted fallback: {e}")
            return "ERROR"


def create_agent():
    return SentinelAgent()


