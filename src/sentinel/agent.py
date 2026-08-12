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
from src.sentinel.rate_limiter import RateLimiter
from src.sentinel.form_state_validator import FormStateValidator
from src.sentinel.session_manager import SessionManager
from src.patterns.enhanced_answer_validator import EnhancedAnswerValidator


# Patterns are now loaded from config/qa_patterns.json (single source of truth)
# The SentinelAgent uses PatternMatcher which reads from the JSON config file.

FUZZY_MATCH_THRESHOLD = 0.65
FUZZY_MATCH_THRESHOLD_FALLBACK = 0.55


# Module-level keyword constants - single definition used by all methods.
# Previously these were duplicated in _same_keyword_category() and _fuzzy_match_question().
SALARY_KEYWORDS = ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc']
EXPERIENCE_KEYWORDS = ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp']
NOTICE_KEYWORDS = ['notice', 'serving', 'join', 'np', 'lwd', 'last working']
LOCATION_KEYWORDS = ['location', 'city', 'relocate', 'preferred location']
ASYNC_JOB_KEYWORDS = [
    'asynchronous programming', 'celery', 'asyncio', 'async io', 'background job',
    'background task', 'task queue', 'message queue', 'rabbitmq', 'kafka',
    'redis queue', 'bull queue', 'agenda', 'node cron', 'scheduler', 'job processing',
]


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
        self._linkedin_no_jobs_scroll_count = 0  # Track consecutive 'No jobs found' scrolls for pagination
        self._naukri_no_progress_count = 0  # Track consecutive chatbot completions with no count progress
        self._naukri_no_progress_max = 3  # Max no-progress rounds before stopping the task
        self._naukri_last_batch_size = 0  # Jobs selected in the last apply batch (for close-enough logic)

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
        
        # Resilience components
        self._rate_limiter = RateLimiter()
        self._form_validator = FormStateValidator()
        self._session_manager = SessionManager()
        self._enhanced_validator = EnhancedAnswerValidator()
    
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
        q1_lower = q1.lower()
        q2_lower = q2.lower()
        
        categories = [SALARY_KEYWORDS, EXPERIENCE_KEYWORDS, NOTICE_KEYWORDS, LOCATION_KEYWORDS]
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
        
        # Use module-level keyword constants (defined at top of file)
        salary_keywords = SALARY_KEYWORDS
        experience_keywords = EXPERIENCE_KEYWORDS
        notice_keywords = NOTICE_KEYWORDS
        location_keywords = LOCATION_KEYWORDS
        
        # LWD (Last Working Day) detection - BEFORE experience keywords
        lwd_keywords = ['last working day', 'lwd', 'exact lwd', 'exact last working', 'official last working day']
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
        
        # Async/Background job questions - MUST BE BEFORE generic experience check
        is_async_job_question = any(kw in question_lower for kw in ASYNC_JOB_KEYWORDS)
        
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
        
        # React/Angular version questions - MUST be checked BEFORE total_exp
        version_keywords = ['version of react', 'react version', 'version of angular', 'angular version',
                           'which version of react', 'which version of angular', 'which react version',
                           'which angular version', 'react version have you been', 'angular version you are working']
        is_version_question = any(kw in question_lower for kw in version_keywords)
        
        # Expertise questions ("Expertise with React.js?") - NOT years of experience
        expertise_keywords = ['expertise with', 'expertise level', 'proficiency level',
                              'level of proficiency', 'level of expertise',
                              'how proficient are you', 'your expertise in', 'your proficiency in']
        is_expertise_question = any(kw in question_lower for kw in expertise_keywords)
        
        # Rating scale short ("Rate your experience (1-5)") - without "on a scale"
        rating_scale_short_keywords = ['rate your experience', 'rate your proficiency', 'rate your skills',
                                       'rate your communication', 'rate your stakeholder']
        is_rating_scale_short = any(kw in question_lower for kw in rating_scale_short_keywords)
        
        # Last Working Date in specific format ("dd-mmm-yy format")
        lwd_format_keywords = ['last working date in dd-mmm', 'lwd in dd-mmm', 'last working date format']
        is_lwd_format_question = any(kw in question_lower for kw in lwd_format_keywords)
        
        # Class vs Functional components
        class_vs_functional_keywords = ['class components or functional', 'functional components vs class',
                                        'prefer writing class components', 'class component or functional']
        is_class_vs_functional = any(kw in question_lower for kw in class_vs_functional_keywords)
        
        # Technologies worked question
        technologies_worked_keywords = ['front-end and back-end technologies', 'technologies have you worked',
                                        'backend languages have you used', 'which frontend and backend']
        is_technologies_worked = any(kw in question_lower for kw in technologies_worked_keywords)
        
        # Joining availability ("How soon you can join us?")
        joining_availability_keywords = ['how soon you can join', 'how soon you will be able to join',
                                         'how soon can you join', 'when can you join us']
        is_joining_availability = any(kw in question_lower for kw in joining_availability_keywords)
        
        # ==========================================
        # COMPLIANCE & EMPLOYMENT HISTORY DETECTION
        # These questions MUST return "No" for compliance safety
        # ==========================================
        
        # List of technical/tool/programming keywords to prevent false positives in company matching
        TECH_KEYWORDS = {
            'aws', 'python', 'java', 'react', 'angular', 'vue', 'node', 'typescript', 'javascript', 
            'docker', 'kubernetes', 'gcp', 'azure', 'git', 'jenkins', 'sql', 'nosql', 'kafka', 
            'redis', 'spark', 'hadoop', 'c#', 'c++', 'go', 'rust', 'ruby', 'php', 'html', 'css', 
            'devops', 'agile', 'scrum', 'jira', 'sap', 'salesforce', 'lambda', 'ecs', 's3', 'sqs',
            'celery', 'asyncio', 'async', 'asynchronous', 'background', 'rabbitmq', 'logging'
        }
        
        # Pattern: Async/Celery/Background job questions - MUST be before company patterns
        is_async_job_question = any(kw in question_lower for kw in ASYNC_JOB_KEYWORDS)
        if is_async_job_question:
            return 'Yes, I have extensive experience with asynchronous programming using Celery, AsyncIO, and background job processing. I have designed and implemented task queues, scheduled jobs, and message-driven architectures using RabbitMQ, Redis, and logging frameworks to handle high-throughput event processing.', 0.98
        
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
        
        # LWD (Last Working Day) questions - calculate actual date 15 days from now
        if is_lwd_question:
            lwd_date = datetime.now() + timedelta(days=15)
            # Format: DD MMM YYYY (e.g., "25 Jul 2026")
            return lwd_date.strftime('%d %b %Y'), 0.98
        
        # LWD in specific dd-mmm-yy format ("Last Working Date in dd-mmm-yy format")
        if is_lwd_format_question:
            lwd_date = datetime.now() + timedelta(days=15)
            return lwd_date.strftime('%d-%b-%y'), 0.98
        
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
            return '9', 0.95
        
        # Rating scale short ("Rate your experience (1-5)") - different scale than 1-10
        if is_rating_scale_short:
            return '4', 0.95
        
        if is_position_question:
            return 'Backend', 0.95
        
        if is_db_question:
            return 'Yes', 0.95
        
        if is_dsa_question:
            return '9', 0.95
        
        # Handle tech stack and python library questions - BEFORE experience check
        if is_python_lib_question:
            return 'NumPy, Pandas, FastAPI, Flask, SQLAlchemy, Celery, PyTorch, TensorFlow, Scikit-learn, LangChain, OpenAI', 0.95
        
        if is_tech_question:
            return 'Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis', 0.95
        
        # Handle technologies worked question ("Which front-end and back-end technologies have you worked on?")
        if is_technologies_worked:
            return 'React, Node.js, Python, Java, Spring Boot, PostgreSQL, MongoDB, Docker, AWS', 0.95
        
        # Handle expertise questions ("Expertise with React.js?") - NOT years of experience
        if is_expertise_question:
            return 'Strong proficiency - 4+ years hands-on experience building production applications', 0.95
        
        # Handle class vs functional components question
        if is_class_vs_functional:
            return 'Functional Components', 0.95
        
        # Handle database NAME questions - BEFORE experience check
        if is_db_name_question:
            return 'PostgreSQL, MySQL, MongoDB, Redis, Elasticsearch, DynamoDB', 0.95
        
        # Handle location-specific questions
        if is_location_specific:
            # Check for Mumbai-only/exclusivity requirements
            if ('mumbai' in question_lower or 'andheri' in question_lower) and ('need candidates from' in question_lower or 'candidates from mumbai' in question_lower or 'from mumbai itself' in question_lower):
                return 'No, I am currently based in Bangalore, not in Mumbai. I am open to immediate relocation to Mumbai if required.', 0.95
            # Check for specific city mentions
            if 'bangalore' in question_lower or 'bengaluru' in question_lower:
                return 'Yes, I am currently based in Bangalore.', 0.95
            if 'mumbai' in question_lower or 'andheri' in question_lower:
                return 'No, I am currently based in Bangalore. However, I am willing to relocate to Mumbai.', 0.95
            if 'pune' in question_lower:
                return 'No, I am currently based in Bangalore. However, I am willing to relocate to Pune.', 0.95
            if 'hyderabad' in question_lower:
                return 'No, I am currently based in Bangalore. However, I am willing to relocate to Hyderabad.', 0.95
            if 'chennai' in question_lower:
                return 'No, I am currently based in Bangalore. However, I am willing to relocate to Chennai.', 0.95
            if 'delhi' in question_lower or 'ncr' in question_lower or 'noida' in question_lower or 'gurgaon' in question_lower or 'gurugram' in question_lower:
                return 'No, I am currently based in Bangalore. However, I am willing to relocate to Delhi/NCR.', 0.95
            return 'Bangalore', 0.95
        
        # Handle referral questions
        if is_referral_question:
            return 'No', 0.95
        
        # Handle job change reason questions
        if is_job_change_question:
            return 'Seeking new challenges and opportunities for professional growth in a dynamic environment that aligns with my career goals', 0.95
        
        # Handle version questions - MUST be BEFORE total_exp (compound questions like
        # "What is total experience? Which Angular version you are working currently?")
        if is_version_question:
            if 'react' in question_lower:
                return '18.x', 0.98
            if 'angular' in question_lower:
                return '18', 0.98
        
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
            # Monthly salary - MUST check before generic CTC handling
            # Annual CTC 2300000 / 3000000 -> monthly ~191667 / ~250000
            if 'monthly' in question_lower:
                if 'expected' in question_lower or 'expect' in question_lower:
                    return '250000', 0.98
                return '191667', 0.98

            # LPA (Lakhs Per Annum) questions - return LPA value, not annual INR
            # "CTC in LPA", "salary in LPA", "CTC in lakhs per annum" -> "23" or "30"
            if 'lpa' in question_lower or 'lakh' in question_lower or 'per annum' in question_lower:
                if 'expected' in question_lower or 'expect' in question_lower or 'ectc' in question_lower or 'desired' in question_lower:
                    return '30', 0.98
                return '23', 0.98

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
        
        # Handle joining availability ("How soon you can join us?") - BEFORE notice check
        # since "join" is in notice_keywords and would otherwise return NP days
        if is_joining_availability:
            return 'Can join within 15 days', 0.95
        
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
                return answer or 'Bangalore, Delhi NCR, Hyderabad, Mumbai, Pune, Noida', max(confidence, 0.95)
            # Use PatternMatcher instead of KNOWN_QA_PATTERNS
            answer, confidence = self._pattern_matcher.fuzzy_match("current location")
            return answer or 'Bangalore', max(confidence, 0.95)
        
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

            # Desync-first try: if the field already has a visible value but is
            # flagged invalid, the framework's internal state likely never
            # received the input/change/blur events. Run the backspace+retype+blur
            # protocol to sync state before attempting heavier recovery.
            if error.field_value and error.field_value.strip():
                try:
                    from src.sentinel.human_behavior import resync_input_state

                    field_label = error.field_label or ""
                    resync_element = None
                    try:
                        resync_element = await self._page.query_selector(
                            'input[aria-invalid="true"], textarea[aria-invalid="true"], select[aria-invalid="true"]'
                        )
                    except Exception:
                        pass

                    if not resync_element and field_label:
                        try:
                            resync_element = await self._page.evaluate_handle(
                                """() => {
                                    const labels = Array.from(document.querySelectorAll('label'));
                                    const target = labels.find(l => l.innerText.trim().includes('""" + field_label.replace("'", "\\'") + """'));
                                    if (!target) return null;
                                    const container = target.closest('.fb-dash-form-element, .jobs-easy-apply-form-section__question, .form-group, .input-field') || target.parentElement;
                                    return container ? container.querySelector('input:not([type="radio"]):not([type="checkbox"]), textarea, select') : null;
                                }"""
                            )
                        except Exception:
                            pass

                    if resync_element:
                        print(f"   🔧 Attempting state resync for '{(field_label or 'field')[:30]}...'")
                        ok = await resync_input_state(self._page, resync_element)
                        if ok:
                            await asyncio.sleep(0.5)
                            remaining = await self._error_detector.detect_errors()
                            still_bad = any(
                                (e.field_label or "") == (error.field_label or "")
                                for e in remaining
                            )
                            if not still_bad:
                                print(f"   ✅ State resync cleared error for '{(field_label or 'field')[:30]}...'")
                                continue
                            print("   ⚠️ State resync did not clear error, trying heavier recovery")
                except Exception as e:
                    print(f"   ⚠️ State resync attempt failed: {e}")

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
                # Enhance/fix the answer using platform-aware validation before injecting
                try:
                    from src.sentinel.ui_error_detector import Platform
                    category = "yes_no"
                    if error.category:
                        category = error.category.value.lower()
                    input_type = "select" if error.available_options else "text"
                    platform = self._detect_platform()
                    healed_value = self._enhanced_validator.fix(
                        healed_value, category, input_type, platform, error.available_options
                    )
                except Exception as e:
                    print(f"   ⚠️ Enhanced validation failed during recovery: {e}")
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
                           options: List[str] = None, selected_option: str = "",
                           prefilled: bool = False):
        """Log ALL questions encountered during Naukri and LinkedIn tasks for analysis."""
        try:
            # Avoid duplicate logging (same question in same session)
            q_hash = hash((question.lower().strip()[:100], context))
            if q_hash in self._all_logged_questions:
                return
            self._all_logged_questions.add(q_hash)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            prefixed_tag = " [PREFILLED]" if prefilled else ""
            confidence_str = f" [{match_confidence}]" if match_confidence else ""
            log_entry = f"[{timestamp}] [{context}]{confidence_str}{prefixed_tag}\n"
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
            
            # Also write to consolidated CSV sheet
            status = "prefilled" if prefilled else "submitted"
            self._log_qa_result(
                question=question,
                answer=answer,
                input_type=input_type,
                options=options or [],
                selected_option=selected_option,
                confidence=match_confidence if match_confidence else "",
                status=status,
                url=self._page.url if self._page else "",
                platform=context or self._current_platform or "",
            )
            
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
        # Session-level health check (crashes, inactivity)
        health = await self._session_manager.check_health(self._page)
        if not health["healthy"]:
            print(f"   ⚠️ Session health check failed: {health['reason']}")
            if self._session_manager.should_stop():
                print("   🛑 Too many session crashes. Stopping task.")
                self.state.task_complete = True
                return False
            recovered = await self._session_manager.recover(self._page)
            if recovered:
                print("   ✅ Session recovered via reload")
            else:
                return False

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
            # Record successful activity for session manager
            try:
                current_url = self._page.url
                current_title = await self._page.title()
                self._session_manager.record_activity(url=current_url, title=current_title)
            except Exception:
                pass
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
            
            # Rate limiting and session health
            platform = self._detect_platform() or "default"
            await self._rate_limiter.wait_if_needed(platform)
            health = await self._session_manager.check_health(self._page)
            if not health["healthy"]:
                print(f"   ⚠️ Session issue: {health['reason']}")
                if self._session_manager.should_stop():
                    self.state.task_complete = True
                    break
                recovered = await self._session_manager.recover(self._page)
                if not recovered:
                    print("   🛑 Session recovery failed. Stopping.")
                    self.state.task_complete = True
                    break
                print("   ✅ Session recovered")
            
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
                
                # Snapshot form state before filling
                try:
                    before_snapshot = await self._form_validator.snapshot(self._page)
                except Exception:
                    before_snapshot = {}

                # Run scripted fallback
                result = await self._handle_scripted_fallback()
                print(f"📜 Script Result: {result}")

                # Validate form state if a form was filled
                if result and 'FORM_FILLED' in result:
                    try:
                        after_snapshot = await self._form_validator.snapshot(self._page)
                        validation = self._form_validator.validate_change(before_snapshot, after_snapshot)
                        if not validation['valid']:
                            print(f"   ⚠️ Form validation issues: {validation['errors']}")
                        else:
                            print(f"   ✅ Form changes validated ({len(validation['changed'])} fields)")
                    except Exception as e:
                        print(f"   ⚠️ Form validation snapshot failed: {e}")
                
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
                                    if (val.toLowerCase().includes('bangalore') || val.toLowerCase().includes('bengaluru')) {
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
                            
                            // Find the Bangalore input
                            const inputs = modal.querySelectorAll('input[type="text"], input[type="search"], textarea');
                            let bangaloreInput = null;
                            for (const inp of inputs) {
                                const val = inp.value || '';
                                if (val.includes('Bangalore') || val.includes('Bengaluru') || val.toLowerCase().includes('bangalore') || val.toLowerCase().includes('bengaluru')) {
                                    bangaloreInput = inp;
                                    break;
                                }
                            }
                            
                            if (!bangaloreInput) return { error: 'Bangalore input not found' };
                            
                            // Look for dropdown-related elements
                            const dropdownLists = modal.querySelectorAll('[role="listbox"], .typeahead-input__dropdown-list, .artdeco-typeahead__results-list, [data-test-typeahead-results]');
                            const dropdownItems = modal.querySelectorAll('[role="option"], .typeahead-input__dropdown-item, .artdeco-typeahead__result');
                            
                            // Look for any select elements
                            const selects = modal.querySelectorAll('select');
                            const selectOptions = selects.length > 0 ? Array.from(selects[0].querySelectorAll('option')).map(o => o.text) : [];
                            
                            // Look for buttons near the input
                            const inputContainer = bangaloreInput.closest('.fb-dash-form-element') || bangaloreInput.parentElement;
                            const buttonsNear = inputContainer ? inputContainer.querySelectorAll('button') : [];
                            
                            return {
                                inputId: bangaloreInput.id,
                                inputValue: bangaloreInput.value,
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
                                if (val.toLowerCase().includes('bangalore') || val.toLowerCase().includes('bengaluru')) {
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
                                        if (text && (text.toLowerCase().includes('bangalore') || text.toLowerCase().includes('bengaluru'))) {
                                            console.log('Found Bangalore option, clicking:', text);
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
                                # Try to find and click any option containing "Bangalore"
                                option_locator = self._page.locator('[role="option"]:has-text("Bangalore")')
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
                    
                    # Track consecutive 'No jobs found' scrolls for pagination
                    if 'No jobs found' in result:
                        self._linkedin_no_jobs_scroll_count += 1
                        print(f"   📊 No jobs scroll count: {self._linkedin_no_jobs_scroll_count}/3")
                        
                        # If JS already clicked next page, reset counter
                        if 'NEXT_PAGE_CLICKED' in result:
                            print("📄 JS clicked next page pagination button!")
                            self._linkedin_no_jobs_scroll_count = 0
                            await asyncio.sleep(random.uniform(5, 8))  # Wait for new page to load
                            continue
                        
                        # Safety net: After 3 consecutive no-jobs scrolls, try clicking next page via Playwright
                        if self._linkedin_no_jobs_scroll_count >= 3:
                            print("📄 3 consecutive no-jobs scrolls — attempting pagination via Playwright...")
                            try:
                                # Try clicking the "Next" button or next page number
                                next_page_clicked = False
                                
                                # Strategy 1: Click the visible "Next" pagination button
                                next_btn = self._page.locator('button[data-testid="pagination-controls-next-button-visible"]')
                                if await next_btn.count() > 0:
                                    await next_btn.first.click()
                                    next_page_clicked = True
                                    print("   ✅ Clicked 'Next' pagination button (data-testid)")
                                
                                # Strategy 2: Find the next page number button (aria-current="false" after aria-current="true")
                                if not next_page_clicked:
                                    current_page = self._page.locator('button[aria-current="true"][aria-label^="Page"]')
                                    if await current_page.count() > 0:
                                        current_label = await current_page.first.get_attribute('aria-label')
                                        if current_label:
                                            import re
                                            page_match = re.search(r'Page (\d+)', current_label)
                                            if page_match:
                                                current_num = int(page_match.group(1))
                                                next_num = current_num + 1
                                                next_page_btn = self._page.locator(f'button[aria-label="Page {next_num}"]')
                                                if await next_page_btn.count() > 0:
                                                    await next_page_btn.first.click()
                                                    next_page_clicked = True
                                                    print(f"   ✅ Clicked page {next_num} pagination button")
                                
                                # Strategy 3: Generic "Next" button text match
                                if not next_page_clicked:
                                    next_text_btn = self._page.locator('button:has-text("Next")').filter(has=self._page.locator('svg[id*="chevron-right"]'))
                                    if await next_text_btn.count() > 0:
                                        await next_text_btn.first.click()
                                        next_page_clicked = True
                                        print("   ✅ Clicked 'Next' button (text + chevron match)")
                                
                                if next_page_clicked:
                                    self._linkedin_no_jobs_scroll_count = 0
                                    await asyncio.sleep(random.uniform(5, 8))  # Wait for new page to load
                                else:
                                    print("   ⚠️ No pagination button found — may be on last page")
                                    self._linkedin_no_jobs_scroll_count = 0  # Reset to avoid infinite loop
                            except Exception as e:
                                print(f"   ⚠️ Pagination click failed: {e}")
                                self._linkedin_no_jobs_scroll_count = 0
                    else:
                        # Reset counter on successful scroll (jobs were found)
                        self._linkedin_no_jobs_scroll_count = 0
                    
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
                    elif 'No Easy Apply' in result:
                        print("⏭️ Job has no Easy Apply button (closed/expired), moving on...")
                        await asyncio.sleep(random.uniform(2, 4))  # Short wait before selecting next
                    else:
                        print("⏭️ Skipped job (already applied or not Easy Apply)")
                    continue
                
                # LinkedIn: Job card selected from sidebar — wait for details pane to load
                if 'LINKEDIN_JOB_SELECTED' in result:
                    print(f"📋 Selected job from list, waiting for details to load...")
                    # Infinite loop guard: if we get JOB_SELECTED repeatedly without any other
                    # result in between, the JS is stuck re-selecting the same job.
                    # After 5 consecutive JOB_SELECTED results, force a page navigation to escape.
                    if not hasattr(self, '_job_selected_streak'):
                        self._job_selected_streak = 0
                    self._job_selected_streak += 1
                    if self._job_selected_streak >= 5:
                        print(f"⚠️ JOB_SELECTED loop detected ({self._job_selected_streak}x consecutive). Force-navigating to escape...")
                        self._job_selected_streak = 0
                        try:
                            current_url = self._page.url
                            # Navigate to the search page (strip currentJobId to reset selection)
                            from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
                            parsed = urlparse(current_url)
                            params = parse_qs(parsed.query, keep_blank_values=True)
                            params.pop('currentJobId', None)
                            new_query = urlencode({k: v[0] for k, v in params.items()})
                            escape_url = urlunparse(parsed._replace(query=new_query))
                            await self._page.goto(escape_url, timeout=30000)
                            await asyncio.sleep(random.uniform(4, 6))
                        except Exception as escape_e:
                            print(f"   ⚠️ Escape navigation error: {escape_e}")
                            await asyncio.sleep(random.uniform(3, 5))
                        continue
                    await asyncio.sleep(random.uniform(3, 5))  # Wait for job detail pane to render
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
                
                # Reset JOB_SELECTED streak counter on any non-selection result
                if 'LINKEDIN' in result and 'LINKEDIN_JOB_SELECTED' not in result:
                    if hasattr(self, '_job_selected_streak'):
                        self._job_selected_streak = 0
                
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
                    easy_apply_restart_count = 0  # Track Easy Apply re-clicks inside autopilot (modal restarted)
                    
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
                            
                            # Parse and log Q&A data from the submission payload
                            if '|' in next_result:
                                try:
                                    qa_json = next_result.split('|', 1)[1]
                                    qa_pairs = json.loads(qa_json)
                                    for qa in qa_pairs:
                                        self._log_all_questions(
                                            qa.get('q', qa.get('question', 'Unknown')),
                                            qa.get('a', qa.get('answer', '')),
                                            context="LinkedIn_Form",
                                            match_confidence="Keyword Match",
                                            input_type=qa.get('inputType', qa.get('t', '')) or '',
                                            selected_option=qa.get('answer', '') or '',
                                            prefilled=qa.get('prefilled', False) or False,
                                        )
                                except Exception:
                                    pass  # Silently handle parse errors
                            
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
                                            match_confidence="Keyword Match",
                                            input_type=qa.get('inputType', '') or '',
                                            selected_option=qa.get('answer', '') or '',
                                            prefilled=qa.get('prefilled', False) or False,
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
                            # Parse and log Q&A data if present
                            if '|' in next_result:
                                try:
                                    qa_json = next_result.split('|', 1)[1]
                                    qa_pairs = json.loads(qa_json)
                                    for qa in qa_pairs:
                                        self._log_all_questions(
                                            qa.get('q', qa.get('question', 'Unknown')),
                                            qa.get('a', qa.get('answer', '')),
                                            context="LinkedIn_Form",
                                            match_confidence="Keyword Match",
                                            input_type=qa.get('inputType', qa.get('t', '')) or '',
                                            selected_option=qa.get('answer', '') or '',
                                            prefilled=qa.get('prefilled', False) or False,
                                        )
                                except Exception:
                                    pass  # Silently handle parse errors
                            print("➡️ Form step continued")
                            submit_attempt_count = 0  # Progress made
                            continue
                        elif 'LINKEDIN_EASY_APPLY_CLICKED' in next_result:
                            easy_apply_restart_count += 1
                            print(f"🔄 Easy Apply re-clicked inside autopilot (restart {easy_apply_restart_count}/2)...")
                            if easy_apply_restart_count >= 2:
                                print("⚠️ Modal restarted twice — application likely submitted or stuck. Moving to next job...")
                                await self._close_linkedin_modal()
                                # Mark the current job as skipped so it's not re-selected in an
                                # infinite loop. The job ID is extracted from the URL (preferred)
                                # or from the active card in the DOM (fallback).
                                try:
                                    await self._page.evaluate("""() => {
                                        if (!window.__skippedJobIds) window.__skippedJobIds = new Set();
                                        const urlParams = new URLSearchParams(window.location.search);
                                        let currentJobId = urlParams.get('currentJobId');
                                        if (!currentJobId) {
                                            const activeCard = document.querySelector(
                                                '.jobs-search-results-list__list-item--active [data-job-id]') ||
                                                document.querySelector('[aria-current="true"] [data-job-id]') ||
                                                document.querySelector('.job-card-list__list-item--active [data-job-id]') ||
                                                document.querySelector('.active [data-job-id]');
                                            if (activeCard) {
                                                currentJobId = activeCard.getAttribute('data-job-id') ||
                                                               activeCard.getAttribute('data-occludable-job-id');
                                            }
                                        }
                                        if (currentJobId) {
                                            window.__skippedJobIds.add(currentJobId);
                                            console.log('Marked job as skipped after modal restart failure:', currentJobId);
                                        }
                                    }""")
                                except Exception as e:
                                    print(f"   ⚠️ Failed to mark job as skipped: {e}")
                                break
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
                    # Parse batch size from result (e.g., "CHECKBOX_CLICKED: 5/5")
                    self._naukri_last_batch_size = self._parse_naukri_batch_size(result)
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
                            // Hybrid selector: real DOM is div.ss-snackbar.ss-snackbar-error.ss-snackbar-active
                            // (no -body suffix), but keep legacy + attribute fallbacks.
                            for (let i = 0; i < 1; i++) {
                                // NOTE: await new Promise removed - Python handles delays between evaluate calls
                                const snackBody = document.querySelector(
                                    '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                                    + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                                );
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong') || text.includes('processing') || text.includes('some error')) {
                                        // Dismiss if close button exists
                                        const closeBtn = document.querySelector('button.ss-close, .ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback check
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                                if (genericSnack && genericSnack.offsetParent !== null
                                    && (genericSnack.innerText.toLowerCase().includes('error')
                                        || genericSnack.innerText.toLowerCase().includes('processing'))) {
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
                    
                    # Poll for async error toast that surfaces AFTER the click returned.
                    if 'APPLY_CLICKED' in apply_result:
                        waited = await self._poll_naukri_error_snackbar()
                        if 'NAUKRI_RATE_LIMITED' in waited:
                            self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                            print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                            self.state.task_complete = True
                            break
                    
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
                            # Check if 0 jobs applied — might be error toast, poll again
                            if isinstance(chatbot_done, str) and (
                                'CHATBOT_COMPLETE: 0/' in chatbot_done
                                or 'CHATBOT_NO_PROGRESS: 0/' in chatbot_done
                            ):
                                snackbar_final = await self._poll_naukri_error_snackbar(attempts=3, interval=1.0)
                                if 'NAUKRI_RATE_LIMITED' in snackbar_final:
                                    self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                                    print(f"⚠️ Naukri Rate Limit Detected after chatbot! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                                    self.state.task_complete = True
                                    break
                            # Success - decide whether to continue (need more jobs) or stop (target reached)
                            should_continue = await self._handle_naukri_post_apply(chatbot_done)
                            if not should_continue:
                                break
                            continue
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
                    # Parse batch size from result (e.g., "NAUKRI_APPLY_CLICKED: 5 jobs selected")
                    self._naukri_last_batch_size = self._parse_naukri_batch_size(result)
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
                        # Check if 0 jobs applied — might be error toast, poll again
                        if isinstance(chatbot_done, str) and (
                            'CHATBOT_COMPLETE: 0/' in chatbot_done
                            or 'CHATBOT_NO_PROGRESS: 0/' in chatbot_done
                        ):
                            snackbar_final = await self._poll_naukri_error_snackbar(attempts=3, interval=1.0)
                            if 'NAUKRI_RATE_LIMITED' in snackbar_final:
                                self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                                print(f"⚠️ Naukri Rate Limit Detected after chatbot! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                                self.state.task_complete = True
                                break
                        # Success - decide whether to continue (need more jobs) or stop (target reached)
                        should_continue = await self._handle_naukri_post_apply(chatbot_done)
                        if not should_continue:
                            break
                        continue
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
                    elif isinstance(chatbot_done, str) and 'NAUKRI_RATE_LIMITED' in chatbot_done:
                        # Error popup detected - set rate limit and exit
                        self.naukri_rate_limit_until = datetime.now() + timedelta(hours=9)
                        print(f"⚠️ Naukri Rate Limit Detected! Pausing until {self.naukri_rate_limit_until.strftime('%H:%M')}")
                        self.state.task_complete = True
                        break
                    elif chatbot_done:
                        # Success - decide whether to continue (need more jobs) or stop (target reached)
                        should_continue = await self._handle_naukri_post_apply(chatbot_done)
                        if not should_continue:
                            break
                        continue
                
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
                
                # Instahyre: Waiting for results to load (grace period after Show Results)
                if 'INSTAHYRE_WAITING_FOR_RESULTS' in result:
                    print("   ⏳ Instahyre: Waiting for results to load...")
                    await asyncio.sleep(random.uniform(2, 3))
                    continue
                
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
                try:
                    platform = self._detect_platform() or "default"
                    self._rate_limiter.record_error(platform)
                except Exception:
                    pass
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

    async def _resolve_naukri_completion(self) -> str:
        """
        Resolve how many Naukri jobs have been applied to cumulatively.

        Called when the chatbot loop detects a successful application. Parses the
        "X out of Y" text on the Naukri success page, updates the cumulative
        counter in sessionStorage (naukri_total_applied / naukri_remaining), and
        returns a string of the form 'CHATBOT_COMPLETE: <newTotal>/5' so callers
        can branch on whether the 5-job target has been reached.

        If no "X out of Y" text is found, returns 'CHATBOT_NO_PROGRESS: <prevTotal>/5'
        (NOT 'CHATBOT_COMPLETE') so the caller can distinguish a real completion
        from a stale-state false positive and break out of an infinite loop.

        RETRY LOGIC: The success text may take a few seconds to appear on the
        page after the chatbot modal closes. This method retries up to 3 times
        with a 2-second delay between attempts before giving up and returning
        CHATBOT_NO_PROGRESS.
        """
        if not self._page:
            return 'CHATBOT_NO_PROGRESS: 0/5'

        check_js = """() => {
            const TARGET_JOBS = 5;
            const bodyText = document.body.innerText || '';
            const match = bodyText.match(/(\\d+)\\s*out\\s*of\\s*(\\d+)/);
            const prevTotal = parseInt(sessionStorage.getItem('naukri_total_applied') || '0');
            if (!match) {
                return 'CHATBOT_NO_PROGRESS: ' + prevTotal + '/' + TARGET_JOBS;
            }
            const appliedThisRound = parseInt(match[1]);
            const newTotal = prevTotal + appliedThisRound;
            sessionStorage.setItem('naukri_total_applied', newTotal.toString());
            const remaining = Math.max(0, TARGET_JOBS - newTotal);
            sessionStorage.setItem('naukri_remaining', remaining.toString());
            return 'CHATBOT_COMPLETE: ' + newTotal + '/' + TARGET_JOBS;
        }"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await self._page.evaluate(check_js)
                if isinstance(result, str) and 'CHATBOT_COMPLETE' in result:
                    return result
                # If not found and we have retries left, wait and try again
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"   ⚠️ _resolve_naukri_completion attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)

        # All retries exhausted — return the last result or safe default
        try:
            result = await self._page.evaluate(check_js)
            return result if isinstance(result, str) else 'CHATBOT_NO_PROGRESS: 0/5'
        except Exception:
            return 'CHATBOT_NO_PROGRESS: 0/5'

    async def _poll_naukri_error_snackbar(self, attempts: int = 4, interval: float = 1.5) -> str:
        """
        Poll the page for the Naukri error snackbar that appears after clicking Apply.

        The toast (``div.ss-snackbar.ss-snackbar-error.ss-snackbar-active``) is
        rendered asynchronously AFTER the click handler returns, so the single
        in-JS check inside ``evaluate`` often misses it. This helper re-checks
        from Python a few times with a short delay and returns the
        ``NAUKRI_RATE_LIMITED`` signal string the moment the toast surfaces.
        """
        # Hybrid selector (Options A+B+C): matches the real DOM structure
        # (.ss-snackbar-error / .ss-snackbar.ss-snackbar-active) while keeping
        # the legacy .ss-snackbar-body + attribute fallbacks for resilience.
        check_js = """
        () => {
            const snack = document.querySelector(
                '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
            );
            if (!snack || snack.offsetParent === null) return null;
            const text = (snack.innerText || '').toLowerCase();
            const hit = text.includes('error') || text.includes('limit')
                || text.includes('reached') || text.includes('something went wrong')
                || text.includes('processing') || text.includes('some error');
            if (hit) {
                const closeBtn = document.querySelector('button.ss-close, .ss-close');
                if (closeBtn) closeBtn.click();
                return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
            }
            // Generic fallback (Option C): any snackbar/toast mentioning "error"
            const generic = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
            if (generic && generic.offsetParent !== null) {
                const gText = (generic.innerText || '').toLowerCase();
                if (gText.includes('error') || gText.includes('processing')) {
                    return 'NAUKRI_RATE_LIMITED: Generic error detected (' + gText + ')';
                }
            }
            return null;
        }
        """
        for _ in range(max(1, attempts)):
            try:
                found = await self._page.evaluate(check_js)
                if found:
                    return found
            except Exception as e:
                print(f"   ⚠️ snackbar poll evaluate failed: {e}")
                break
            await asyncio.sleep(interval)
        return ''

    def _parse_naukri_batch_size(self, result: str) -> int:
        """
        Parse the number of jobs selected in the last apply batch from a script
        result string. Handles formats like:
          - "NAUKRI_APPLY_CLICKED: 5 jobs selected"
          - "NAUKRI_APPLY_CLICKED: 1 jobs already selected"
          - "CHECKBOX_CLICKED: 5/5"
        Returns 0 if the count cannot be parsed.
        """
        if not isinstance(result, str):
            return 0
        import re
        # "NAUKRI_APPLY_CLICKED: 5 jobs selected" or "...already selected"
        m = re.search(r':\s*(\d+)\s+jobs?\s', result)
        if m:
            return int(m.group(1))
        # "CHECKBOX_CLICKED: 5/5"
        m = re.search(r':\s*(\d+)\s*/\s*\d+', result)
        if m:
            return int(m.group(1))
        return 0

    async def _handle_naukri_post_apply(self, chatbot_result) -> bool:
        """
        Decide what to do after a Naukri chatbot application attempt.

        Parses the cumulative applied count from the chatbot result string
        (format: 'CHATBOT_COMPLETE: <newTotal>/5' or 'CHATBOT_NO_PROGRESS:
        <prevTotal>/5'). If the 5-job target has been reached, marks the task
        complete and returns False (caller should break). Otherwise updates
        applications_submitted, navigates back to the recommended jobs page so
        the next iteration can select the remaining jobs from the next
        section/tab, and returns True (caller should continue).

        CLOSE-ENOUGH RULE: If the last batch selected >= TARGET_JOBS (5) jobs
        but one failed (e.g., 4/5 applied), the task is marked complete. There
        is no point in applying to extra jobs just to hit exactly 5 — one
        failure in a full batch is acceptable.

        NO-PROGRESS GUARD: If the result is CHATBOT_NO_PROGRESS (no "X out of Y"
        text found on the page) OR the parsed new_total did not advance beyond
        the previously recorded applications_submitted, a no-progress counter is
        incremented. After self._naukri_no_progress_max consecutive no-progress
        rounds, the task is marked complete to break the infinite
        "applied N/5, need more, navigate, repeat" loop. The counter is reset
        to 0 whenever real progress is made.

        Args:
            chatbot_result: Return value of _handle_chatbot_loop. Expected to
                be a string like 'CHATBOT_COMPLETE: 3/5' on success or
                'CHATBOT_NO_PROGRESS: 3/5' when the success text was not found.

        Returns:
            True if the main loop should continue (more jobs needed),
            False if the task is complete (target reached or unrecoverable).
        """
        TARGET_JOBS = 5

        is_no_progress_signal = (
            isinstance(chatbot_result, str)
            and 'CHATBOT_NO_PROGRESS' in chatbot_result
        )

        new_total = 0
        if isinstance(chatbot_result, str) and (
            'CHATBOT_COMPLETE' in chatbot_result or 'CHATBOT_NO_PROGRESS' in chatbot_result
        ):
            try:
                count_part = chatbot_result.split(':')[-1].strip()
                new_total = int(count_part.split('/')[0])
            except (ValueError, IndexError):
                print(f"   ⚠️ Could not parse count from '{chatbot_result}', assuming 1 applied")
                new_total = self.metrics.get('applications_submitted', 0) + 1
        else:
            new_total = self.metrics.get('applications_submitted', 0) + 1

        prev_total = self.metrics.get('applications_submitted', 0)
        made_progress = new_total > prev_total

        if new_total >= TARGET_JOBS:
            print(f"🎉 Naukri target reached ({new_total}/{TARGET_JOBS}). Task complete.")
            self.metrics['applications_submitted'] = new_total
            self._naukri_no_progress_count = 0
            self.state.task_complete = True
            return False

        # CLOSE-ENOUGH: Selected a full batch (>= TARGET_JOBS) but one job failed.
        # Accepting 4/5 is better than risk over-applying or getting stuck.
        if (
            self._naukri_last_batch_size >= TARGET_JOBS
            and new_total >= TARGET_JOBS - 1
            and new_total > 0
        ):
            print(
                f"✅ Naukri close-enough: selected {self._naukri_last_batch_size} jobs, "
                f"applied {new_total}/{TARGET_JOBS}. One job failed — accepting and moving on."
            )
            self.metrics['applications_submitted'] = new_total
            self._naukri_no_progress_count = 0
            self.state.task_complete = True
            return False

        if is_no_progress_signal or not made_progress:
            self._naukri_no_progress_count += 1
            print(
                f"   ⚠️ No progress on applications (stuck at {new_total}/{TARGET_JOBS}) "
                f"— no-progress {self._naukri_no_progress_count}/{self._naukri_no_progress_max}"
            )
            if self._naukri_no_progress_count >= self._naukri_no_progress_max:
                print(
                    f"🛑 Naukri stuck at {new_total}/{TARGET_JOBS} for "
                    f"{self._naukri_no_progress_max} rounds. Ending task to break infinite loop."
                )
                self.metrics['applications_submitted'] = new_total
                self._naukri_no_progress_count = 0
                self.state.task_complete = True
                return False
            # Still navigate back and try once more — the success text may surface
            # on the next page load. The counter will trip if it keeps failing.
            self.metrics['applications_submitted'] = new_total
            try:
                await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
                await asyncio.sleep(random.uniform(4, 6))
            except Exception as e:
                print(f"   ⚠️ Navigation to recommendedjobs failed: {e}")
            return True

        # Real progress was made — reset the no-progress counter.
        self._naukri_no_progress_count = 0
        self.metrics['applications_submitted'] = new_total

        remaining = TARGET_JOBS - new_total
        print(f"🔄 Applied to {new_total}/{TARGET_JOBS} jobs. Need {remaining} more — navigating to next section.")
        try:
            await self._page.goto('https://www.naukri.com/mnjuser/recommendedjobs', timeout=30000)
            await asyncio.sleep(random.uniform(4, 6))
        except Exception as e:
            print(f"   ⚠️ Navigation to recommendedjobs failed: {e}")
        return True

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
            
            # Python-side error snackbar check at start of each iteration
            if iteration < 3:
                snackbar_result = await self._poll_naukri_error_snackbar(attempts=1, interval=0.5)
                if 'NAUKRI_RATE_LIMITED' in snackbar_result:
                    print(f"   ⚠️ Error snackbar detected in chatbot loop iteration {iteration}")
                    return snackbar_result
            
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
                    // Normalize hyphens/dashes to spaces so "work-from-office" matches "work from office"
                    const qNormalized = qLower.replace(/[-–]/g, ' ');
                    let bestMatch = null;
                    let bestKeyLen = 0;
                    const detectedType = detectInputType(chatLayer);
                    
                    // PRE-CHECK: "How many years of exp/experience in X?" -> force experience pattern
                    // This prevents tech-specific patterns (microservices, cloud, etc.) from
                    // overriding when the question is clearly asking for numeric years.
                    const isYearsOfExpQuestion = /how many years|years of exp|years of experience|total years/.test(qLower);
                    if (isYearsOfExpQuestion) {{
                        // Find the experience pattern key explicitly
                        const expKeys = ['years of experience do you have', 'how many years of experience do you have',
                            'how many years of experience', 'years of experience', 'total years of exp',
                            'years of exp', 'years of work experience do you have', 'experience', 'exp', 'years'];
                        for (const ek of expKeys) {{
                            if (KNOWN_PATTERNS[ek] && qLower.includes(ek)) {{
                                return getAnswerForPattern(ek, detectedType, KNOWN_PATTERNS[ek]);
                            }}
                        }}
                    }}
                    
                    const sortedPatterns = Object.entries(KNOWN_PATTERNS).sort((a, b) => b[0].length - a[0].length);
                    
                    for (const [key, val] of sortedPatterns) {{
                        const keyLower = key.toLowerCase();
                        if (qLower === keyLower) {{
                            return getAnswerForPattern(key, detectedType, val);
                        }}
                        // Use normalized question so hyphenated text still matches space-separated patterns
                        if (qNormalized.includes(keyLower) && key.length > bestKeyLen) {{
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
                        // Normalize Yes/No from long answer - use word boundaries to avoid false matches like "Noida" containing "no"
                        const answerLower = defaultVal.toLowerCase();
                        if (/\\byes\\b/.test(answerLower) && !/\\bno\\b/.test(answerLower)) return 'Yes';
                        if (/\\bno\\b/.test(answerLower)) return 'No';
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

                    // LinkedIn: experience-category patterns must answer bare number ("4"), not "4 Years".
                    // Naukri text inputs now return "4 Years" from input_type_defaults.text; LinkedIn must
                    // strip the " Years" suffix for both the flat default and input_type_defaults.
                    Object.keys(KNOWN_PATTERNS_WITH_DEFAULTS).forEach(k => {{
                        const defaultObj = KNOWN_PATTERNS_WITH_DEFAULTS[k];
                        if (!defaultObj || defaultObj.category !== 'experience') return;
                        const flatVal = KNOWN_PATTERNS[k];
                        if (typeof flatVal === 'string' && /\d+\s*Years?/i.test(flatVal)) {{
                            const m = flatVal.match(/(\d+(?:\.\d+)?)/);
                            KNOWN_PATTERNS[k] = m ? m[1] : flatVal;
                        }}
                        if (defaultObj.input_type_defaults) {{
                            Object.keys(defaultObj.input_type_defaults).forEach(t => {{
                                const tv = defaultObj.input_type_defaults[t];
                                if (typeof tv === 'string' && /\d+\s*Years?/i.test(tv)) {{
                                    const m = tv.match(/(\d+(?:\.\d+)?)/);
                                    defaultObj.input_type_defaults[t] = m ? m[1] : tv;
                                }}
                            }});
                        }}
                    }});
                }}
                const snackBody = document.querySelector(
                    '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                    + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                );
                if (snackBody && snackBody.offsetParent !== null) {{
                    const snackText = snackBody.innerText.toLowerCase();
                    if (snackText.includes('error') || snackText.includes('limit') || snackText.includes('reached') || snackText.includes('something went wrong') || snackText.includes('processing') || snackText.includes('some error')) {{
                        const closeBtn = document.querySelector('button.ss-close, .ss-close');
                        if (closeBtn) closeBtn.click();
                        return 'NAUKRI_RATE_LIMITED: Error popup detected at loop start';
                    }}
                }}
                // Generic fallback (Option C): any snackbar/toast/alert mentioning error/processing
                const genericSnackStart = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                if (genericSnackStart && genericSnackStart.offsetParent !== null) {{
                    const gText = (genericSnackStart.innerText || '').toLowerCase();
                    if (gText.includes('error') || gText.includes('processing') || gText.includes('some error')) {{
                        return 'NAUKRI_RATE_LIMITED: Generic error detected at loop start';
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
                    const errSnack = document.querySelector(
                        '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                        + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                    );
                    if (errSnack && errSnack.offsetParent !== null) {{
                        const errText = (errSnack.innerText || '').toLowerCase();
                        if (errText.includes('error') || errText.includes('processing') || errText.includes('some error')) {{
                            const closeBtn = document.querySelector('button.ss-close, .ss-close');
                            if (closeBtn) closeBtn.click();
                            return 'NAUKRI_RATE_LIMITED: Error snackbar on no chatLayer';
                        }}
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
                    answer = fuzzyMatch(qText, chatLayer) || 'Yes';
                    
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
                        qLower.startsWith('need to ') ||
                        qLower.startsWith('required to ') ||
                        qLower.startsWith('willing to ') ||
                        qLower.startsWith('open to ') ||
                        qLower.startsWith('comfortable ') ||
                        qLower.includes('willing') ||
                        qLower.includes('comfortable') ||
                        qLower.includes('localite') ||
                        qLower.includes('relocate') ||
                        qLower.includes('relocation') ||
                        qLower.includes('open to') ||
                        qLower.includes('freelancer') ||
                        qLower.includes('freelance') ||
                        qLower.includes('days in a week') ||
                        qLower.includes('days in week') ||
                        qLower.includes('work from office') ||
                        qLower.includes('work from home') ||
                        qLower.includes('wfh') ||
                        qLower.includes('wfo') ||
                        qLower.includes('hybrid') ||
                        qLower.includes('onsite') ||
                        qLower.includes('night shift') ||
                        qLower.includes('rotational shift') ||
                        qLower.includes('bond') ||
                        qLower.includes('contract') ||
                        qLower.includes('agreement')
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
                        // Use word-boundary regex to avoid false matches like "Noida" containing "no"
                        const hasYesOrNo = /\\byes\\b/.test(answerLowerYN) || /\\bno\\b/.test(answerLowerYN);
                        const knownExceptions = ['serving notice', 'male', 'female', 'single', 'married', 'sde-', 'software developer'];
                        const isException = knownExceptions.some(e => answerLowerYN.includes(e));
                        
                        if (!answer || answer === '1' || isNumericResult || (!hasYesOrNo && !isException)) {{
                            // Check negative indicators for No vs Yes
                            const negativeIndicators = ['sponsorship', 'visa', 'referral', 'referred',
                                'conflict of interest', 'relative', 'family member', 'criminal', 'felony',
                                'convict', 'disability', 'previously employed', 'ever been employed',
                                'currently employed', 'worked at', 'worked for', 'worked with', 'backlog', 'backlogs',
                                'military spouse'];
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
                // isShortQuestion: a stale fragment like "2" left over from a previous chatbot
                // session. This is NOT a completion signal on its own — it must fall through to
                // CHATBOT_WAITING so the Python loop can re-evaluate instead of false-completing.
                const isShortQuestion = qText && qText.trim().length > 0 && qText.trim().length <= 3;
                const hasRealQuestion = qText && qText.trim().length > 10 && qText.includes('?');
                
                if (!hasAnyInput && chatLayer && isVisible(chatLayer)) {{
                    // Check for error snackbar BEFORE declaring completion
                    const errSnack2 = document.querySelector(
                        '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                        + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                    );
                    if (errSnack2 && errSnack2.offsetParent !== null) {{
                        const errText2 = (errSnack2.innerText || '').toLowerCase();
                        if (errText2.includes('error') || errText2.includes('processing') || errText2.includes('some error')) {{
                            const closeBtn = document.querySelector('button.ss-close, .ss-close');
                            if (closeBtn) closeBtn.click();
                            return 'NAUKRI_RATE_LIMITED: Error snackbar on empty chatLayer';
                        }}
                    }}
                    // Check for success indicators first
                    const hasSuccessMsg = document.querySelector('.chatbot_SuccessMsg') !== null ||
                                         document.querySelector('[class*="success"]') !== null ||
                                         document.body.innerText.includes('Application submitted') ||
                                         document.body.innerText.includes('Successfully applied') ||
                                         document.body.innerText.includes('applied successfully');
                    
                    // Declare completion ONLY when there is a real success message OR the
                    // chatLayer is genuinely empty (no real question AND no short stale
                    // fragment). A short fragment like "2" with no success message is a
                    // stale state, not completion — fall through to CHATBOT_WAITING so the
                    // Python no-progress guard can break the loop.
                    if (hasSuccessMsg || (!hasRealQuestion && !isShortQuestion)) {{
                        console.log('Chatbot Debug - Completion detected: success message or empty chatLayer');
                        return 'CHATBOT_COMPLETE';
                    }}
                    console.log('Chatbot Debug - Stale short text with no inputs and no success message, waiting instead of completing');
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
                    // No Skip button found - fall through to normal input handling
                    // (contenteditable/text input) instead of returning unanswerable
                    // which causes an infinite loop
                    console.log('Chatbot Debug - No skip button found for tool question, falling through to input handler');
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
                        // Yes/No matching - use word boundaries to avoid false matches (e.g. "Noida" contains "no")
                        if ((answerLower === 'yes' || /\\byes\\b/.test(answerLower)) && btnText === 'yes') {{
                            btn.click();
                            clickedBtn = btn;
                            console.log('Chatbot Debug - Clicked Yes option');
                            break;
                        }}
                        if ((answerLower === 'no' || /\\bno\\b/.test(answerLower)) && btnText === 'no') {{
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
                                    return 'CHATBOT_DROPDOWN_SELECTED|' + JSON.stringify({{q: qText.substring(0,200), a: opt.text, t: 'select', s: opt.text}});
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
                                    return 'CHATBOT_SELECTED|' + JSON.stringify({{q: qText.substring(0,200), a: opt.text, t: 'select', s: opt.text}});
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
                                return 'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: selectOptions[1].text, t: 'select', s: selectOptions[1].text}});
                            }}
                            return 'CHATBOT_SELECTED_DEFAULT|' + JSON.stringify({{q: qText.substring(0,200), a: selectOptions[1].text, t: 'select', s: selectOptions[1].text}});
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
                    
                    // Collect all matching ranges to pick the best one (closest to lower bound)
                    const matchingRanges = [];
                    
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
                        
                        // Match Yes/Serving for positive answers - use word boundaries to avoid "Noida" matching "no"
                        if ((/\\byes\\b/.test(answerLower) || answerLower.includes('true')) && 
                            (labelLower.includes('yes') || labelLower.includes('serving'))) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked Yes radio:', label);
                            }}
                            break;
                        }}
                        // Match No for negative answers — guard: skip if label starts with "yes"
                        if ((/\\bno\\b/.test(answerLower) || answerLower.includes('false')) && 
                            (labelLower === 'no' || labelLower.startsWith('no') || /(\bno\b|^no\b|\bno$)/.test(labelLower)) &&
                            !labelLower.startsWith('yes')) {{
                            if (!radio.checked) {{
                                radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked No radio:', label);
                            }}
                            break;
                        }}
                        
                        // Match numeric answers to experience ranges
                        // Collect all matching ranges to pick the one where answer is closest to lower bound
                        if (answerNumeric !== null && !clickedRadio) {{
                            // Extract numbers from label (e.g., "3-5 years" -> [3, 5])
                            const labelNumbers = labelLower.match(/(\d+\.?\d*)/g);
                            if (labelNumbers) {{
                                const nums = labelNumbers.map(n => parseFloat(n));
                                // Check if answer falls within range
                                if (nums.length >= 2) {{
                                    if (answerNumeric >= nums[0] && answerNumeric <= nums[1]) {{
                                        // Store this match with distance from lower bound
                                        const distanceFromMin = Math.abs(answerNumeric - nums[0]);
                                        matchingRanges.push({{radio, label, distanceFromMin}});
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
                            if (!clickedRadio && labelLower.includes(String(answerNumeric))) {{
                                if (!radio.checked) {{
                                    radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked exact numeric match radio:', label);
                                }}
                                break;
                            }}
                        }}
                    }}
                    
                    // After processing all radios, if we have multiple range matches, pick the best one
                    if (!clickedRadio && matchingRanges.length > 0) {{
                        // Sort by distance from lower bound (ascending) - prefer ranges where answer is closer to min
                        matchingRanges.sort((a, b) => a.distanceFromMin - b.distanceFromMin);
                        const bestMatch = matchingRanges[0];
                        if (!bestMatch.radio.checked) {{
                            bestMatch.radio.click();
                            clickedRadio = true;
                            console.log('Chatbot Debug - Clicked best range radio:', bestMatch.label, '| distance from min:', bestMatch.distanceFromMin);
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
                    
                    // If no match found, use answer-aware fallback
                    if (!clickedRadio) {{
                        // Collect all radio labels for smart fallback
                        const allRadioInfo = Array.from(radios).filter(r => !r.checked).map(r => {{
                            const label = r.parentElement?.innerText || r.nextSibling?.textContent || '';
                            return {{ radio: r, label: label, labelLower: label.toLowerCase().trim() }};
                        }});
                        
                        // When answer is "No"/"False", look for No radio FIRST, then decline
                        if (/\\bno\\b/.test(answerLower) || answerLower.includes('false')) {{
                            // Priority 1: Find a radio whose label starts with "no" (most specific)
                            const noRadio = allRadioInfo.find(r => 
                                r.labelLower === 'no' || r.labelLower.startsWith('no,') || 
                                r.labelLower.startsWith('no ') || r.labelLower.startsWith('no.')
                            );
                            if (noRadio) {{
                                noRadio.radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked No radio (fallback):', noRadio.label);
                            }}
                            
                            // Priority 2: Labels with explicit decline keywords (not generic 'not to')
                            if (!clickedRadio) {{
                                const declineKeywords = ['decline', 'prefer not to', 'choose not to', 'none', 'n/a', 'not applicable', 'neither', "i don't"];
                                const declineRadio = allRadioInfo.find(r => 
                                    declineKeywords.some(kw => r.labelLower.includes(kw))
                                );
                                if (declineRadio) {{
                                    declineRadio.radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked decline radio:', declineRadio.label);
                                }}
                            }}
                            
                            // Priority 3: Pick last non-Yes radio (safest negative in most UIs)
                            if (!clickedRadio) {{
                                const nonYesRadios = allRadioInfo.filter(r => 
                                    !r.labelLower.startsWith('yes') && !r.labelLower.startsWith('i am') &&
                                    !r.labelLower.startsWith('i have') && !r.labelLower.startsWith('i do')
                                );
                                if (nonYesRadios.length > 0) {{
                                    const target = nonYesRadios[nonYesRadios.length - 1];
                                    target.radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked last non-Yes radio for No answer:', target.label);
                                }}
                            }}
                        }}
                        
                        // When answer is "Yes", look for Yes radio or positive phrasing
                        if (!clickedRadio && /\\byes\\b/.test(answerLower)) {{
                            // Priority 1: Find a radio whose label starts with "yes" or contains "yes"
                            const yesRadio = allRadioInfo.find(r => 
                                r.labelLower.startsWith('yes') || r.labelLower.includes('yes')
                            );
                            if (yesRadio) {{
                                yesRadio.radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked Yes radio (fallback):', yesRadio.label);
                            }}
                            
                            // Priority 2: Find positive phrasing — "I have", "I am", "I do" (but NOT "I don't" or "I am not")
                            if (!clickedRadio) {{
                                const positiveRadio = allRadioInfo.find(r => {{
                                    const ll = r.labelLower;
                                    return ((ll.startsWith('i have') && !ll.includes('not')) ||
                                            (ll.startsWith('i am') && !ll.includes('not')) ||
                                            (ll.startsWith('i do') && !ll.includes("n't") && !ll.includes(' not')));
                                }});
                                if (positiveRadio) {{
                                    positiveRadio.radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked positive radio for Yes answer:', positiveRadio.label);
                                }}
                            }}
                            
                            // Priority 3: Avoid negative radios, pick first non-negative
                            if (!clickedRadio) {{
                                const nonNegativeRadios = allRadioInfo.filter(r => 
                                    !r.labelLower.startsWith('no') && !r.labelLower.startsWith('never') &&
                                    !r.labelLower.startsWith('i am not') && !r.labelLower.startsWith("i don't") &&
                                    !r.labelLower.includes('decline') && !r.labelLower.includes('choose not to')
                                );
                                if (nonNegativeRadios.length > 0) {{
                                    nonNegativeRadios[0].radio.click();
                                    clickedRadio = true;
                                    console.log('Chatbot Debug - Clicked first non-negative radio for Yes answer:', nonNegativeRadios[0].label);
                                }}
                            }}
                        }}
                        
                        // Generic fallback: click first non-"No experience" radio
                        if (!clickedRadio) {{
                            for (const info of allRadioInfo) {{
                                if (info.labelLower.includes('no experience') || info.labelLower.includes('0 years')) {{
                                    console.log('Chatbot Debug - Skipping "No experience" option');
                                    continue;
                                }}
                                info.radio.click();
                                clickedRadio = true;
                                console.log('Chatbot Debug - Clicked default radio:', info.label);
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
                            const _chkRadio = chatLayer ? chatLayer.querySelector('input[type="radio"]:checked') : null;
                            const _radLabel = _chkRadio ? (_chkRadio.parentElement?.innerText || _chkRadio.nextSibling?.textContent || _chkRadio.value || '').trim() : '';
                            return 'CHATBOT_RADIO_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: _radLabel || answer, t: 'radio', s: _radLabel || answer}});
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
                                const _chkRadio2 = chatLayer ? chatLayer.querySelector('input[type="radio"]:checked') : null;
                                const _radLabel2 = _chkRadio2 ? (_chkRadio2.parentElement?.innerText || _chkRadio2.nextSibling?.textContent || _chkRadio2.value || '').trim() : '';
                                return 'CHATBOT_RADIO_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: _radLabel2 || answer, t: 'radio', s: _radLabel2 || answer}});
                            }}
                        }}
                        
                        const _chkRadio3 = chatLayer ? chatLayer.querySelector('input[type="radio"]:checked') : null;
                        const _radLabel3 = _chkRadio3 ? (_chkRadio3.parentElement?.innerText || _chkRadio3.nextSibling?.textContent || _chkRadio3.value || '').trim() : '';
                        return 'CHATBOT_RADIO_CLICKED|' + JSON.stringify({{q: qText.substring(0,200), a: _radLabel3 || answer, t: 'radio', s: _radLabel3 || answer}});
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
                    if (!clickedCheckbox && (/\\byes\\b/.test(answerLower) || answerLower.includes('true'))) {{
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
                            const _chkCbs = chatLayer ? Array.from(chatLayer.querySelectorAll('input[type="checkbox"]:checked')) : [];
                            const _cbLabels = _chkCbs.map(function(cb) {{ return (cb.parentElement?.innerText || cb.nextSibling?.textContent || cb.name || '').trim(); }}).filter(Boolean);
                            return 'CHATBOT_CHECKBOX_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: _cbLabels.join('; ') || 'Yes', t: 'checkbox', s: _cbLabels.join('; ') || 'Yes'}});
                        }}
                        
                        const _chkCbs2 = chatLayer ? Array.from(chatLayer.querySelectorAll('input[type="checkbox"]:checked')) : [];
                        const _cbLabels2 = _chkCbs2.map(function(cb) {{ return (cb.parentElement?.innerText || cb.nextSibling?.textContent || cb.name || '').trim(); }}).filter(Boolean);
                        return 'CHATBOT_CHECKBOX_CLICKED|' + JSON.stringify({{q: qText.substring(0,200), a: _cbLabels2.join('; ') || 'Yes', t: 'checkbox', s: _cbLabels2.join('; ') || 'Yes'}});
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
                        const _dateVal = dd + '/' + mm + '/' + yyyy;
                        return 'CHATBOT_ANSWERED_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: _dateVal, t: 'date', s: _dateVal}});
                    }}
                    const _dateVal2 = dd + '/' + mm + '/' + yyyy;
                    return 'CHATBOT_DATE_FILLED|' + JSON.stringify({{q: qText.substring(0,200), a: _dateVal2, t: 'date', s: _dateVal2}});
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
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: answer || '', t: 'text', s: answer || ''}});
                    }}
                    return 'CHATBOT_ANSWERED|' + JSON.stringify({{q: qText.substring(0,200), a: answer || '', t: 'text', s: answer || ''}});
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
                        
                        return 'CHATBOT_ANSWERED_AND_SAVE|' + JSON.stringify({{q: qText.substring(0,200), a: answer || '', t: 'text', s: answer || ''}});
                    }}
                    return 'CHATBOT_ANSWERED|' + JSON.stringify({{q: qText.substring(0,200), a: answer || '', t: 'text', s: answer || ''}});
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
            
            # Extract question text from result for tracking and log Q&A to CSV
            current_question = None
            qa_data = None
            
            # New JSON format: "ACTION|{q:..., a:..., t:..., s:...}"
            if '|' in result and not result.startswith('NAUKRI_RATE_LIMITED'):
                try:
                    _, json_str = result.split('|', 1)
                    qa_data = json.loads(json_str)
                    current_question = qa_data.get('q', '')
                except Exception:
                    qa_data = None
            
            # Fallback: old text format (backward compat)
            if qa_data is None:
                colon_formats = [
                    'CHATBOT_ANSWERED_AND_SAVE:', 'CHATBOT_ANSWERED:',
                    'CHATBOT_SUBMISSION_ERROR:', 'CHATBOT_DROPDOWN_SELECTED:',
                    'CHATBOT_DROPDOWN_DEFAULT_AND_SAVE:', 'CHATBOT_SAVE_DISABLED:',
                    'CHATBOT_RADIO_AND_SAVE:', 'CHATBOT_RADIO_CLICKED:',
                    'CHATBOT_CHECKBOX_AND_SAVE:', 'CHATBOT_CHECKBOX_CLICKED:',
                ]
                for prefix in colon_formats:
                    fmt = prefix + ' '
                    if fmt in result:
                        current_question = result.split(fmt)[1] if fmt in result else None
                        break
            
            # NEW: Log Q&A to CSV if we got structured data
            if qa_data and qa_data.get('q') and qa_data.get('a'):
                self._log_qa_result(
                    question=qa_data['q'],
                    answer=qa_data['a'],
                    input_type=qa_data.get('t', '') or '',
                    selected_option=qa_data.get('s', '') or qa_data['a'],
                    confidence="pattern_match",
                    status="submitted",
                    url=self._page.url if self._page else "",
                    platform="naukri",
                )
                self.metrics['questions_answered'] += 1
            
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
                return await self._resolve_naukri_completion()
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
                # Chatbot modal closed — give page time to show success text
                if iteration > 3:
                    await asyncio.sleep(random.uniform(2, 3))
                    return await self._resolve_naukri_completion()
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
                    return await self._resolve_naukri_completion()
                continue
        
        print("⚠️ Chatbot loop exhausted")
        # If we answered at least one question before exhausting, consider it a success
        if last_action_was_answer:
            print("   📜 Chatbot likely completed - answered questions before exhausting")
            return await self._resolve_naukri_completion()
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
            
            # Step 2.5: Clean up stale componentkey elements to prevent false modal detection
            try:
                await self._page.evaluate("""() => {
                    const el = document.querySelector('[componentkey]');
                    if (el && !el.querySelector('svg[role="progressbar"]')) {
                        el.removeAttribute('componentkey');
                    }
                }""")
            except Exception:
                pass  # Non-critical cleanup
            
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
                    // Smart salary handling: check for monthly, LPA, expected keywords
                    const salaryKeys = [
                        'salary range', 'current salary range', 'expected salary range',
                        'annual salary', 'ctc range', 'current ctc', 'expected ctc',
                        'expected annual ctc in inr', 'expected annual ctc', 'expected ctc in inr', 'expected ctc inr',
                        'current salary', 'expected salary', 'current annual salary',
                        'what is your current annual salary', 'what is your current annual salary?',
                        'expected annual salary', 'what is your expected annual salary', 'what is your expected annual salary?',
                        'what is your current salary?', 'what is your expected salary?',
                        'what is your current ctc', 'what is your current ctc?',
                        'gross salary', 'gross current salary', 'gross expected salary', 'salary expectations',
                        'monthly salary', 'current monthly salary', 'expected monthly salary',
                        'per month salary', 'current ctc in lpa', 'expected ctc in lpa',
                        'desired compensation', 'desired salary'
                    ];
                    salaryKeys.forEach(k => {
                        if (KNOWN_PATTERNS[k]) {
                            const kLower = k.toLowerCase();
                            // Monthly salary questions
                            if (kLower.includes('monthly') || kLower.includes('per month')) {
                                KNOWN_PATTERNS[k] = kLower.includes('expected') ? '250000' : '191667';
                            }
                            // LPA/Lakh questions
                            else if (kLower.includes('lpa') || kLower.includes('lakh') || kLower.includes('lac')) {
                                KNOWN_PATTERNS[k] = (kLower.includes('expected') || kLower.includes('desired')) ? '30' : '23';
                            }
                            // Expected/desired salary (annual INR)
                            else if (kLower.includes('expected') || kLower.includes('ectc') || kLower.includes('desired')) {
                                KNOWN_PATTERNS[k] = '3000000';
                            }
                            // Current salary (annual INR)
                            else {
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

                    // LinkedIn: experience-category patterns must answer bare number ("4"), not "4 Years".
                    // Naukri text inputs now return "4 Years" from input_type_defaults.text; LinkedIn must
                    // strip the " Years" suffix for both the flat default and input_type_defaults.
                    Object.keys(KNOWN_PATTERNS_WITH_DEFAULTS).forEach(k => {
                        const defaultObj = KNOWN_PATTERNS_WITH_DEFAULTS[k];
                        if (!defaultObj || defaultObj.category !== 'experience') return;
                        const flatVal = KNOWN_PATTERNS[k];
                        if (typeof flatVal === 'string' && /\d+\s*Years?/i.test(flatVal)) {
                            const m = flatVal.match(/(\d+(?:\.\d+)?)/);
                            KNOWN_PATTERNS[k] = m ? m[1] : flatVal;
                        }
                        if (defaultObj.input_type_defaults) {
                            Object.keys(defaultObj.input_type_defaults).forEach(t => {
                                const tv = defaultObj.input_type_defaults[t];
                                if (typeof tv === 'string' && /\d+\s*Years?/i.test(tv)) {
                                    const m = tv.match(/(\d+(?:\.\d+)?)/);
                                    defaultObj.input_type_defaults[t] = m ? m[1] : tv;
                                }
                            });
                        }
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
                        // Naukri text inputs expect "4 Years"; LinkedIn numeric-only expects "4".
                        const isLinkedInHost = window.location.hostname.includes('linkedin');
                        const yearsDefault = isLinkedInHost ? '4' : '4 Years';
                        
                        if (isYearsQ) {
                            bestMatch = yearsDefault;
                        } else if (isNoticeQ) {
                            bestMatch = '15'; // Default notice period
                        } else if (isSalaryQ) {
                            // Smart salary handling: check for monthly, LPA, expected keywords
                            if (/monthly|per month/.test(qLower)) {
                                bestMatch = /expected|desired/.test(qLower) ? '250000' : '191667';
                            } else if (/lpa|lakh|lac/.test(qLower)) {
                                bestMatch = /expected|desired/.test(qLower) ? '30' : '23';
                            } else if (/expected|ectc|desired/.test(qLower)) {
                                bestMatch = '3000000';
                            } else {
                                bestMatch = '2300000';
                            }
                        } else if (isExpQ) {
                            bestMatch = yearsDefault;
                        }
                    }
                    
                    // --- PASS 6: Platform-specific overrides (post-match disambiguation) ---
                    if (bestMatch) {
                        const isSalaryQ = /salary|ctc|pay|compensation|package|remuneration/.test(qLower);
                        const isExpQ = /experience|years|\byear\b|months|exp\.?\b/.test(qLower) && !isSalaryQ;
                        const isNoticeQ = /notice\s*period|serving\s*notice|lwd/.test(qLower);
                        const isLinkedInHost6 = window.location.hostname.includes('linkedin');
                        
                        if (isSalaryQ) {
                            // Smart salary handling: check for monthly, LPA, expected keywords
                            if (/monthly|per month/.test(qLower)) {
                                bestMatch = /expected|desired/.test(qLower) ? '250000' : '191667';
                            } else if (/lpa|lakh|lac/.test(qLower)) {
                                bestMatch = /expected|desired/.test(qLower) ? '30' : '23';
                            } else if (/expected|ectc|desired/.test(qLower)) {
                                bestMatch = '3000000';
                            } else {
                                bestMatch = '2300000';
                            }
                        } else if (isExpQ && !/\d/.test(bestMatch)) {
                            if (/how many|years|months|\bexp\b/i.test(qLower)) {
                                // LinkedIn numeric-only fields get bare "4"; Naukri gets "4 Years".
                                bestMatch = isLinkedInHost6 ? '4' : '4 Years';
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
                    const answerInt = Math.floor(answerNum);                    const MIN_MATCH_SCORE = 10; // Don't select if no meaningful match found
                    let bestOpt = null;
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
                        // Also handles Indian number formats like "2,00,000 to 5,00,000 INR"
                        // Prefer ranges where answer is closer to the lower bound (e.g., 4 prefers "4-6" over "3-4")
                        else if (answerNum > 0) {
                            // Strip commas from option text to handle Indian/intl number formats
                            const textNoCommas = text.replace(/,/g, '');
                            const rangeMatch = textNoCommas.match(/(\d+(?:\.\d+)?)\s*(?:[-–]|\bto\b)\s*(\d+(?:\.\d+)?)/);
                            if (rangeMatch) {
                                const min = parseFloat(rangeMatch[1]);
                                const max = parseFloat(rangeMatch[2]);
                                if (answerNum >= min && answerNum <= max) {
                                    const rangeSize = max - min;
                                    const offsetFromMin = Math.abs(answerNum - min);
                                    // Higher score when closer to min (lower bound)
                                    score = Math.max(0, 85 - (offsetFromMin / Math.max(rangeSize, 1) * 30));
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
                    // Minimum score gate: don't select if no meaningful match found
                    // Score 0 means no pattern matched at all — selecting would be random garbage
                    if (bestScore < MIN_MATCH_SCORE) {
                        console.log('findBestMatch: score too low (' + bestScore + '), skipping selection');
                        return null;
                    }
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
                            
                            // Year-based range matching - prefer ranges where value is closer to lower bound
                            if (score === 0) {
                                const rangeMatch = lowerLabel.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
                                if (rangeMatch) {
                                    const min = parseFloat(rangeMatch[1]);
                                    const max = parseFloat(rangeMatch[2]);
                                    if (answerNum >= min && answerNum <= max) {
                                        const rangeSize = max - min;
                                        // Prefer ranges where answer is closer to the lower bound (min)
                                        // This ensures 4 prefers "4-6" over "3-4"
                                        const offsetFromMin = Math.abs(answerNum - min);
                                        const offsetFromCenter = Math.abs(answerNum - (min + max) / 2);
                                        // Higher score when closer to min, full score at min
                                        score = Math.max(0, 85 - (offsetFromMin / Math.max(rangeSize, 1) * 30));
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

                // Helper: Detect if a Yes/No question should default to "No"
                // Catches company employment history, compliance, and conflict-of-interest patterns
                const shouldDefaultToNo = (text) => {
                    if (!text) return false;
                    const t = text.replace(/[*?]/g, '').trim().toLowerCase();
                    const negativePatterns = [
                        'worked with', 'worked for', 'worked at',
                        'employed by', 'employed at', 'employed with',
                        'previously employed', 'ever been employed', 'currently employed',
                        'conflict of interest', 'close relative', 'family member',
                        'relative working', 'referred', 'referral',
                        'criminal', 'felony', 'convict',
                        'worked with nielsen', 'worked with navan', 'worked with visa',
                        'worked with reed', 'worked with mastercard'
                    ];
                    return negativePatterns.some(p => t.includes(p));
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
                        
                        // Helper: Read the visible value of a field from multiple sources.
                        // LinkedIn Easy Apply uses React-controlled / composite inputs where the
                        // visible text is NOT always reflected in element.value. We probe several
                        // sources in priority order and return the first non-empty trimmed string.
                        const readFieldValue = (element) => {
                            if (!element) return '';

                            // 1. Primary: the native .value property
                            const directVal = element.value;
                            if (typeof directVal === 'string' && directVal.trim().length > 0) {
                                return directVal.trim();
                            }

                            // 2. aria-valuenow (used by composite / custom widgets)
                            const ariaValNow = element.getAttribute && element.getAttribute('aria-valuenow');
                            if (ariaValNow && ariaValNow.trim().length > 0) return ariaValNow.trim();

                            // 3. data-value attribute (some LinkedIn composite inputs expose this)
                            const dataVal = element.getAttribute && element.getAttribute('data-value');
                            if (dataVal && dataVal.trim().length > 0) return dataVal.trim();

                            // 4. Walk up to the form-element wrapper and look for a visible
                            //    preview / display-value element. LinkedIn renders the chosen
                            //    value as a sibling span inside .fb-dash-form-element.
                            const wrapper = element.closest && element.closest(
                                '.fb-dash-form-element, .jobs-easy-apply-form-section__question, [class*="form-element"]'
                            );
                            if (wrapper) {
                                const previewSelectors = [
                                    '.fb-dash-form-element__preview-value',
                                    '[data-test*="displayValue"]',
                                    '[data-test*="DisplayValue"]',
                                    'span.fb-dash-form-element__value',
                                    '.fb-dash-form-element__text',
                                    '[class*="preview-value"]',
                                    '[class*="display-value"]'
                                ];
                                for (const sel of previewSelectors) {
                                    const preview = wrapper.querySelector(sel);
                                    if (preview) {
                                        const txt = (preview.innerText || preview.textContent || '').trim();
                                        if (txt.length > 0) return txt;
                                    }
                                }
                            }

                            return '';
                        };

                        // Helper: Check if a field is already filled
                        const isFieldPreFilled = (element) => {
                            if (!element) return false;
                            if (element.disabled) return true;
                            // For checkboxes/radios, readOnly is not an applicable check for filled state

                            const tagName = element.tagName.toLowerCase();

                            if (tagName === 'input' || tagName === 'textarea') {
                                // if it's radio or checkbox, it's prefilled if checked
                                if (element.type === 'radio' || element.type === 'checkbox') return element.checked;
                                // Use multi-source reader so React-controlled / composite inputs
                                // whose visible text is not in .value are still detected as filled.
                                return readFieldValue(element).length > 0;
                            }

                            if (tagName === 'select') {
                                // LinkedIn uses "Select an option" as placeholder.
                                const value = element.value ? element.value.trim() : "";
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
                            // DATE PICKER HANDLING: LinkedIn date pickers use data-testid="date-picker-input"
                            // These are React-controlled text inputs that accept a typed mm/dd/yyyy value.
                            // NOTE: This IIFE is synchronous (Playwright evaluate runs it in one microtask —
                            // see _handle_scripted_fallback docstring), so calendar-popup clicking is NOT
                            // viable here: React renders the popup on the NEXT microtask, after this
                            // function has already returned. So type the date string directly via the
                            // React-aware native value setter — the same approach proven for every other
                            // LinkedIn text field. Calendar-clicking "open then retry" caused an infinite
                            // loop (same result 5x -> "Stuck in loop" abort). Fixes the Step-6 loop bug.
                            if (input.getAttribute('data-testid') === 'date-picker-input' && isVisible(input)) {
                                console.log('DATE PICKER detected, filling via direct text input...');
                                
                                // Detect this field's label so we can pick the right date value.
                                // Reuses the same heuristics as the main label detector below, kept
                                // local so the date-picker branch stays self-contained.
                                let dpLabel = '';
                                {
                                    const fbParent = input.closest('.fb-dash-form-element');
                                    if (fbParent) {
                                        const lbl = fbParent.querySelector('label');
                                        if (lbl) dpLabel = (lbl.innerText || lbl.textContent || '').trim();
                                    }
                                    if (!dpLabel && input.id) {
                                        const lbl = queryDeep('label[for="' + input.id + '"]', modal);
                                        if (lbl) dpLabel = (lbl.innerText || lbl.textContent || '').trim();
                                    }
                                    if (!dpLabel) dpLabel = (input.getAttribute('aria-label') || '').trim();
                                    if (!dpLabel) {
                                        const lb = input.getAttribute('aria-labelledby');
                                        if (lb) { const el = document.getElementById(lb); if (el) dpLabel = (el.innerText || el.textContent || '').trim(); }
                                    }
                                    if (!dpLabel) {
                                        let p = input.parentElement;
                                        for (let k = 0; k < 5 && p && p !== modal; k++) {
                                            const lbl = p.querySelector('label');
                                            if (lbl && (lbl.innerText || '').trim().length > 2) { dpLabel = lbl.innerText.trim(); break; }
                                            p = p.parentElement;
                                        }
                                    }
                                    if (!dpLabel) dpLabel = (input.getAttribute('placeholder') || '').trim();
                                }
                                const dpLabelLower = dpLabel.toLowerCase().replace(/\*+$/g, '').trim();
                                const isDob = dpLabelLower.includes('date of birth') || dpLabelLower.includes('dob') || dpLabelLower.includes('birth date');
                                console.log('DATE PICKER label:', dpLabel, '| isDob:', isDob);
                                
                                // LinkedIn date-picker-input displays MM/DD/YYYY (the wrong value
                                // 07/25/2026 seen in the field was today+15 in MM/DD/YYYY, proving
                                // the field order). DOB is 17 Dec 2000 -> MM/DD/YYYY = 12/17/2000
                                // (per config/qa_patterns.json personal_dob default 17/12/2000 DD/MM).
                                // Any other date picker is treated as earliest-start / availability
                                // -> today + 15 days (notice period) in MM/DD/YYYY.
                                let dateStr, dpQuestion;
                                if (isDob) {
                                    dateStr = '12/17/2000';
                                    dpQuestion = 'Date of Birth';
                                } else {
                                    const today = new Date();
                                    const targetDate = new Date(today.getTime() + 15 * 24 * 60 * 60 * 1000);
                                    const targetMonth = targetDate.getMonth() + 1; // 1-indexed for display
                                    const targetDay = targetDate.getDate();
                                    const targetYear = targetDate.getFullYear();
                                    dateStr = String(targetMonth).padStart(2, '0') + '/' +
                                              String(targetDay).padStart(2, '0') + '/' +
                                              String(targetYear);
                                    dpQuestion = 'Earliest start date';
                                }
                                console.log('Target date:', dateStr);
                                
                                // Type the date directly via the React-aware native value setter
                                // (fillReactInput, defined above in this IIFE). Uses
                                // Object.getOwnPropertyDescriptor + input/change/blur so React state
                                // updates. Calendar-popup clicking is impossible here because this
                                // IIFE is synchronous (React renders the popup on the next microtask,
                                // after this function returns) — that caused the infinite loop bug.
                                const filled = fillReactInput(input, dateStr);
                                if (filled) {
                                    formResults.push({ question: dpQuestion, answer: dateStr, inputType: 'date' });
                                    console.log('DATE PICKER: filled with', dateStr);
                                } else {
                                    console.log('DATE PICKER: direct fill did not change value:', dateStr);
                                }
                                continue; // Skip normal text fill for date pickers
                            }
                            
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
                            let hasError = !!(inputParent && inputParent.querySelector('.artdeco-inline-feedback--error, .fb-dash-form-element__error-field'));
                            if (!hasError && inputParent) {
                                // Check for helper-text/error paragraphs
                                const helperPs = inputParent.querySelectorAll('[data-testid*="helper-text"] p, [data-testid*="error"] p, [class*="error"] p, [class*="feedback"] p');
                                for (const hp of helperPs) {
                                    const t = (hp.innerText || '').toLowerCase();
                                    if ((t.includes('invalid') || t.includes('required') || t.includes('enter a valid') || t.includes('please enter')) && hp.offsetParent !== null) {
                                        hasError = true;
                                        break;
                                    }
                                }
                            }
                            // Also check aria-invalid and red border indicators on input itself
                            if (!hasError && (input.getAttribute('aria-invalid') === 'true' || input.getAttribute('aria-describedby')?.includes('error'))) {
                                hasError = true;
                            }
                            // Check for any visible red text sibling near the input
                            if (!hasError && inputParent) {
                                const allSpans = inputParent.querySelectorAll('span, div, p');
                                for (const sp of allSpans) {
                                    const t = (sp.innerText || '').trim().toLowerCase();
                                    if (t === 'this field is required' || t === 'required' || t === 'please enter a valid answer') {
                                        if (sp.offsetParent !== null) {
                                            hasError = true;
                                            break;
                                        }
                                    }
                                }
                            }
                            if (isFieldPreFilled(input) && !hasError) {
                                // Capture pre-filled value before skipping
                                const pfLabel = labelText || input.placeholder || '(prefilled field)';
                                const pfVal = readFieldValue(input);
                                if (pfLabel && pfVal) {
                                    formResults.push({ question: pfLabel, answer: pfVal, inputType: input.tagName === 'TEXTAREA' ? 'textarea' : 'text', prefilled: true });
                                    console.log('Pre-filled field captured:', pfLabel, '=', pfVal);
                                }
                                continue;
                            }
                            
                            // If field is pre-filled but HAS a validation error, re-trigger
                            // the existing value to force React to recognize it
                            if (isFieldPreFilled(input) && hasError) {
                                const existingValue = readFieldValue(input);
                                console.log('Re-triggering pre-filled field with error:', labelText, '=', existingValue);
                                fillReactInput(input, existingValue);
                                // Also try focus+blur to clear validation
                                input.focus();
                                input.dispatchEvent(new Event('focus', { bubbles: true }));
                                input.dispatchEvent(new Event('blur', { bubbles: true }));
                                formResults.push({ question: labelText || '(re-triggered)', answer: existingValue, inputType: 'text', retriggered: true });
                                continue;
                            }
                            
                            // NOTE: The previous "clear invalid field before refilling" block ran
                            // here unconditionally on hasError, BEFORE an answer was resolved. If no
                            // answer resolved, the field was wiped to '' and left empty — causing
                            // "this field is required" on submit. The clear now happens ONLY inside
                            // the `if (answer)` block below, so a field is never emptied unless we
                            // have a concrete value to refill it with.
                            
                            // Check if input expects numeric values only
                            const isNumericInput = input.type === 'number' || 
                                                  input.getAttribute('inputmode') === 'numeric' ||
                                                  input.getAttribute('pattern')?.includes('\\d') ||
                                                  input.className?.toLowerCase().includes('number') ||
                                                  input.className?.toLowerCase().includes('decimal') ||
                                                  (labelText && /how many|total years|relevant experience|experience with|decimal number|numeric|experience you are having|years of experience|experience in years|enter a decimal/i.test(labelText));
                            
                            // Try to get answer from fuzzyMatch first
                            let answer = labelText ? fuzzyMatch(labelText) : null;

                            // GUARD: LinkedIn/Microsoft last-employment-date field must stay blank.
                            // We never worked there, so any fuzzyMatch answer ('No', 'Yes', etc.)
                            // would cause a date validation error and block the form.
                            if (answer && lowerLabel.includes('last date of employment')) {
                                console.log('LEAVE BLANK: last-employment-date field — discarding answer:', answer);
                                answer = null;
                            }
                            // Also skip any text input whose placeholder signals a date format
                            if (answer && (input.placeholder || '').toUpperCase().includes('MM/DD/YYYY')) {
                                console.log('LEAVE BLANK: MM/DD/YYYY date field — discarding answer:', answer);
                                answer = null;
                            }

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
                                    answer = 'Bangalore';
                                    console.log('Fallback: Filling location/city field');
                                } else if (combinedText.includes('street') || combinedText.includes('address line')) {
                                    answer = 'Koramangala';
                                    console.log('Fallback: Filling street address');
                                } else if (combinedText.includes('zip') || combinedText.includes('postal') || combinedText.includes('pincode') || combinedText.includes('pin code')) {
                                    answer = '560034';
                                    console.log('Fallback: Filling zip/postal code');
                                } else if (combinedText.match(/\bcity\b/) || combinedText.includes('town')) {
                                    answer = 'Bangalore';
                                    console.log('Fallback: Filling city');
                                } else if (combinedText.includes('state') || combinedText.includes('province')) {
                                    answer = 'Karnataka';
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
                                
                                // "How many X" fallback: always fill with a number for any unmatched "how many" question
                                if (!answer && /how many/i.test(combinedText)) {
                                    answer = '3';
                                    console.log('Fallback: Filling how-many question with numeric default 3');
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
                                
                                // Only clear the field now that we have a concrete answer to
                                // refill with. Previously the clear ran unconditionally on
                                // hasError before the answer was known, which could leave a
                                // field empty (and trigger "this field is required").
                                if (hasError) {
                                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                    if (nativeSetter) nativeSetter.call(input, '');
                                    else input.value = '';
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                    console.log('Cleared invalid field before refill:', labelText);
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
                            if (!isVisible(select)) continue;
                            
                            // Capture pre-filled selects before label detection
                            if (isFieldPreFilled(select)) {
                                let pfLabel = select.getAttribute('aria-label') || '';
                                if (!pfLabel && select.id) {
                                    const lbl = queryDeep(`label[for="${select.id}"]`, modal);
                                    if (lbl) pfLabel = lbl.innerText || lbl.textContent || '';
                                }
                                if (!pfLabel) {
                                    const fbParent = select.closest('.fb-dash-form-element');
                                    if (fbParent) {
                                        const lbl = fbParent.querySelector('label');
                                        if (lbl) pfLabel = lbl.innerText || lbl.textContent || '';
                                    }
                                }
                                const pfOpt = select.options[select.selectedIndex];
                                if (pfOpt && pfLabel) {
                                    formResults.push({ question: pfLabel, answer: pfOpt.text, inputType: 'select', prefilled: true });
                                    console.log('Pre-filled select captured:', pfLabel, '=', pfOpt.text);
                                }
                                continue;
                            }
                            
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
                            
                            // ===== CITIZENSHIP STATUS HANDLING =====
                            // Options: "Citizen (India)", "Non Citizen (India)" — must select directly
                            const isCitizenshipSelect = lowerLabel.includes('citizenship');
                            if (isCitizenshipSelect) {
                                const citizenOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                // Select "Citizen (India)" or "Citizen" — NOT "Non Citizen"
                                let citizenMatch = citizenOptions.find(o => {
                                    const t = o.text.toLowerCase().trim();
                                    return (t.includes('citizen') && !t.includes('non') && !t.includes('select'));
                                });
                                if (citizenMatch) {
                                    console.log('Citizenship match: Selecting', citizenMatch.text, 'for', labelText.substring(0, 80));
                                    select.value = citizenMatch.value;
                                    if (select.value !== citizenMatch.value) select.selectedIndex = citizenMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: citizenMatch.text, inputType: 'select-citizenship' });
                                }
                                continue;
                            }
                            
                            // ===== SELF-IDENTIFICATION HANDLING (gender, orientation, birth sex) =====
                            // These questions use non-standard option text ("Man" vs "Male", etc.)
                            // and must NOT fall through to generic findBestMatch which fails on them.
                            // Also catches diversity/equal-opportunity monitoring selects that don't
                            // explicitly mention "gender" in their label (e.g. "All applicants are invited...")
                            const isSelfIdQuestion = lowerLabel.includes('gender') || 
                                                    lowerLabel.includes('sexual orientation') ||
                                                    lowerLabel.includes('sex registered at birth') ||
                                                    lowerLabel.includes('identify with') ||
                                                    lowerLabel.includes('disability') ||
                                                    (lowerLabel.includes('equal opportunit') && lowerLabel.includes('statistical'));
                            
                            if (isSelfIdQuestion) {
                                const selfIdOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let selfIdOpt = null;
                                
                                if ((lowerLabel.includes('gender') || lowerLabel.includes('identify with') || (lowerLabel.includes('equal opportunit') && lowerLabel.includes('statistical'))) && 
                                    !lowerLabel.includes('sex registered') && !lowerLabel.includes('same as') &&
                                    !lowerLabel.includes('sexual orientation') && !lowerLabel.includes('disability')) {
                                    // Gender question — look for Man/Male
                                    selfIdOpt = selfIdOptions.find(o => {
                                        const t = o.text.toLowerCase().trim();
                                        return t === 'man' || t === 'male' || t.startsWith('man ');
                                    });
                                    // Fallback: Prefer not to say
                                    if (!selfIdOpt) {
                                        selfIdOpt = selfIdOptions.find(o => {
                                            const t = o.text.toLowerCase();
                                            return t.includes('prefer not') || t.includes('decline') || t.includes('rather not');
                                        });
                                    }
                                } else if (lowerLabel.includes('sex registered at birth') || lowerLabel.includes('same as your sex') || lowerLabel.includes('same as')) {
                                    // Gender same as birth — answer Yes
                                    selfIdOpt = selfIdOptions.find(o => o.text.toLowerCase().trim() === 'yes');
                                } else if (lowerLabel.includes('sexual orientation')) {
                                    // Sexual orientation — Heterosexual or Straight
                                    selfIdOpt = selfIdOptions.find(o => {
                                        const t = o.text.toLowerCase().trim();
                                        return t.includes('heterosexual') || t.includes('straight');
                                    });
                                    // Fallback: Decline to self-identify
                                    if (!selfIdOpt) {
                                        selfIdOpt = selfIdOptions.find(o => {
                                            const t = o.text.toLowerCase();
                                            return t.includes('prefer not') || t.includes('decline') || t.includes('rather not');
                                        });
                                    }
                                } else if (lowerLabel.includes('disability')) {
                                    // Disability question — No or Prefer not to say
                                    selfIdOpt = selfIdOptions.find(o => {
                                        const t = o.text.toLowerCase().trim();
                                        return t === 'no' || t.includes('do not') || t.includes('prefer not') || t.includes('decline');
                                    });
                                }
                                
                                if (selfIdOpt) {
                                    console.log('Self-ID match: Selecting', selfIdOpt.text, 'for:', labelText.substring(0, 80));
                                    select.value = selfIdOpt.value;
                                    if (select.value !== selfIdOpt.value) select.selectedIndex = selfIdOpt.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: selfIdOpt.text, inputType: 'select-self-id' });
                                } else {
                                    console.log('Self-ID: No match found for:', labelText.substring(0, 80), '— skipping (optional)');
                                }
                                continue;
                            }
                            
                            // ===== NOTICE SERVING QUESTION =====
                            // "Are you currently serving your notice?" is Yes/No, not numeric
                            const isNoticeServingQ = lowerLabel.includes('currently serving') && lowerLabel.includes('notice');
                            if (isNoticeServingQ) {
                                const noticeOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                const yesOpt = noticeOptions.find(o => o.text.toLowerCase().trim() === 'yes');
                                if (yesOpt) {
                                    console.log('Notice serving: Selecting Yes');
                                    select.value = yesOpt.value;
                                    if (select.value !== yesOpt.value) select.selectedIndex = yesOpt.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: 'Yes', inputType: 'select-notice' });
                                }
                                continue;
                            }
                            
                            // ===== EMPLOYER PARTNER QUESTION =====
                            const isEmployerPartnerQ = lowerLabel.includes('employer') && lowerLabel.includes('partner');
                            if (isEmployerPartnerQ) {
                                const partnerOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                const noOpt = partnerOptions.find(o => o.text.toLowerCase().trim() === 'no');
                                if (noOpt) {
                                    console.log('Employer partner: Selecting No');
                                    select.value = noOpt.value;
                                    if (select.value !== noOpt.value) select.selectedIndex = noOpt.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: 'No', inputType: 'select-partner' });
                                }
                                continue;
                            }
                            
                            // ===== NOTICE PERIOD SELECT HANDLER =====
                            // "What will be your notice period?" - options like "Serving Notice Period", "30 Days", etc.
                            // When "15 days" isn't an option, select "Serving Notice Period" as fallback
                            const isNoticePeriodSelect = lowerLabel.includes('notice') && (lowerLabel.includes('period') || lowerLabel.includes('day') || lowerLabel.includes('join'));
                            if (isNoticePeriodSelect) {
                                const npOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let npMatch = null;
                                
                                // Priority 1: Exact "15 days" match
                                npMatch = npOptions.find(o => o.text.toLowerCase().includes('15 day') || o.text.toLowerCase() === '15');
                                
                                // Priority 2: "Serving Notice Period" or "Serving Notice"
                                if (!npMatch) {
                                    npMatch = npOptions.find(o => o.text.toLowerCase().includes('serving notice'));
                                }
                                
                                // Priority 3: "0-15 days" or similar short notice range
                                if (!npMatch) {
                                    npMatch = npOptions.find(o => o.text.toLowerCase().includes('0-15') || o.text.toLowerCase().includes('0 - 15'));
                                }
                                
                                // Priority 4: "Immediate Joiner" / "Immediate"
                                if (!npMatch) {
                                    npMatch = npOptions.find(o => o.text.toLowerCase().includes('immediate'));
                                }
                                
                                // Priority 5: Shortest numeric days option (e.g., "30 Days" over "60 Days")
                                if (!npMatch) {
                                    let shortestDays = Infinity;
                                    for (const opt of npOptions) {
                                        const daysMatch = opt.text.match(/(\d+)\s*day/i);
                                        if (daysMatch) {
                                            const days = parseInt(daysMatch[1]);
                                            if (days < shortestDays) {
                                                shortestDays = days;
                                                npMatch = opt;
                                            }
                                        }
                                    }
                                }
                                
                                if (npMatch) {
                                    console.log('Notice Period Select: Selecting', npMatch.text, 'for', labelText);
                                    select.value = npMatch.value;
                                    if (select.value !== npMatch.value) select.selectedIndex = npMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: npMatch.text, inputType: 'select-notice-period' });
                                    continue;
                                }
                            }
                            
                            // ===== CTC/SALARY SELECT HANDLER =====
                            // Handles LinkedIn dropdowns with INR range options like "20,00,000 to 25,00,000 INR"
                            // The generic findBestMatch fails on these because answer is in raw INR (2300000)
                            // but options use Indian number format with commas
                            const isCTCQuestion = lowerLabel.includes('ctc') || 
                                                  lowerLabel.includes('salary') || 
                                                  (lowerLabel.includes('annual') && lowerLabel.includes('inr')) ||
                                                  (lowerLabel.includes('current') && lowerLabel.includes('inr')) ||
                                                  (lowerLabel.includes('expected') && lowerLabel.includes('inr'));
                            
                            if (isCTCQuestion) {
                                const ctcOptions = Array.from(select.options).map(o => ({ 
                                    text: o.text, 
                                    value: o.value, 
                                    index: o.index 
                                }));
                                
                                // Get the answer - fuzzyMatch returns INR value like "2300000"
                                let ctcAnswer = labelText ? fuzzyMatch(labelText) : null;
                                
                                // Fallback: detect expected vs current based on label
                                if (!ctcAnswer) {
                                    if (lowerLabel.includes('expected') || lowerLabel.includes('ectc')) {
                                        ctcAnswer = '3000000';
                                    } else {
                                        ctcAnswer = '2300000';
                                    }
                                    console.log('CTC Select: Using fallback answer', ctcAnswer, 'for', labelText.substring(0, 80));
                                }
                                
                                // Extract numeric INR value from answer
                                const ctcNumMatch = String(ctcAnswer).match(/(\d+(?:\.\d+)?)/);
                                const ctcValue = ctcNumMatch ? parseFloat(ctcNumMatch[1]) : 0;
                                
                                if (ctcValue > 0) {
                                    let bestCTCOpt = null;
                                    let closestCTCOpt = null;
                                    let minDistance = Infinity;
                                    
                                    for (const opt of ctcOptions) {
                                        const optText = (opt.text || '').toLowerCase().trim();
                                        if (!optText || optText.includes('select')) continue;
                                        
                                        // Robust range extraction: strip ALL non-digit chars except spaces, hyphens, "to"
                                        // Handle formats: "20,00,000 to 25,00,000 INR", "2000000-2500000", etc.
                                        const cleaned = optText.replace(/,/g, '').replace(/inr?/g, '').trim();
                                        
                                        // Try multiple regex patterns for range matching
                                        let rangeMatch = cleaned.match(/(\d+(?:\.\d+)?)\s*(?:[-\u2013\u2014]|\bto\b)\s*(\d+(?:\.\d+)?)/);
                                        
                                        // Fallback: any two numbers separated by space(s)
                                        if (!rangeMatch) {
                                            const numbers = cleaned.match(/(\d+(?:\.\d+)?)/g);
                                            if (numbers && numbers.length >= 2) {
                                                rangeMatch = [null, numbers[0], numbers[numbers.length - 1]];
                                            }
                                        }
                                        
                                        if (rangeMatch) {
                                            const minVal = parseFloat(rangeMatch[1]);
                                            const maxVal = parseFloat(rangeMatch[2]);
                                            
                                            // Check if exact match (value falls in range)
                                            if (ctcValue >= minVal && ctcValue <= maxVal) {
                                                bestCTCOpt = opt;
                                                console.log('CTC Select: Exact range match -', opt.text, 'contains', ctcValue);
                                                break; // Found exact match, stop searching
                                            }
                                            
                                            // Track closest range (for fallback)
                                            const distance = Math.min(
                                                Math.abs(ctcValue - minVal), 
                                                Math.abs(ctcValue - maxVal)
                                            );
                                            if (distance < minDistance) {
                                                minDistance = distance;
                                                closestCTCOpt = opt;
                                            }
                                        }
                                    }
                                    
                                    // Use exact match if found, otherwise closest range
                                    const selectedOpt = bestCTCOpt || closestCTCOpt;
                                    
                                    if (selectedOpt) {
                                        console.log('CTC Select: Selecting', selectedOpt.text, 'for', labelText.substring(0, 80), '(answer:', ctcValue + ')');
                                        select.value = selectedOpt.value;
                                        if (select.value !== selectedOpt.value) select.selectedIndex = selectedOpt.index;
                                        select.dispatchEvent(new Event('input', { bubbles: true }));
                                        select.dispatchEvent(new Event('change', { bubbles: true }));
                                        select.dispatchEvent(new Event('blur', { bubbles: true }));
                                        formResults.push({ question: labelText, answer: selectedOpt.text, inputType: 'select-ctc' });
                                        continue;
                                    } else {
                                        console.log('CTC Select: No matching range found for', ctcValue, '- falling through to generic handler');
                                    }
                                }
                            }
                            
                            // ===== LOCATION SELECT HANDLER =====
                            // Handles "Current Location?", "Preferred Location?", "City" dropdowns where
                            // the user's answer (e.g. "Noida") may not be among the listed options.
                            // Strategy: try exact/fuzzy match first (incl. each comma-separated preferred
                            // city); if nothing matches, select the FIRST real option so the required
                            // field is never left empty (which would stall the form on validation).
                            // Excludes street/address/zip/postal which are handled as text inputs.
                            const isLocationSelect = (lowerLabel.includes('location') ||
                                                      lowerLabel.includes('city') ||
                                                      lowerLabel.includes('based in') ||
                                                      lowerLabel.includes('where are you') ||
                                                      lowerLabel.includes('where do you')) &&
                                                     !lowerLabel.includes('street') &&
                                                     !lowerLabel.includes('address') &&
                                                     !lowerLabel.includes('zip') &&
                                                     !lowerLabel.includes('postal') &&
                                                     !lowerLabel.includes('pin code') &&
                                                     !lowerLabel.includes('pincode');
                            
                            if (isLocationSelect) {
                                const locOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let locAnswer = labelText ? fuzzyMatch(labelText) : null;
                                if (!locAnswer) locAnswer = 'Bangalore';
                                
                                // PRIORITY 1: Try Bangalore first (user's primary location)
                                let locMatch = findBestMatch('Bangalore', locOptions);
                                if (locMatch) {
                                    console.log('Location Select: matched Bangalore (primary preference)');
                                }
                                
                                // PRIORITY 2: Try the pattern-matched answer
                                if (!locMatch) {
                                    locMatch = findBestMatch(locAnswer, locOptions);
                                }
                                
                                // If answer is comma-separated (e.g. preferred locations), try each part
                                if (!locMatch && locAnswer.includes(',')) {
                                    const parts = locAnswer.split(',').map(s => s.trim()).filter(s => s.length > 1);
                                    for (const part of parts) {
                                        locMatch = findBestMatch(part, locOptions);
                                        if (locMatch) {
                                            console.log('Location Select: matched comma part:', part);
                                            break;
                                        }
                                    }
                                }
                                
                                // FALLBACK: select the first real (non-placeholder) option so the
                                // required dropdown is never left empty. Mirrors the "learn about"
                                // placeholder-skip logic above.
                                if (!locMatch) {
                                    locMatch = locOptions.find(o => {
                                        const t = (o.text || '').toLowerCase().trim();
                                        return t.length > 0 &&
                                               !t.includes('select') &&
                                               !t.includes('choose') &&
                                               !t.includes('please') &&
                                               !t.includes('an option') &&
                                               !t.includes('skip');
                                    });
                                    console.log('Location Select: no match for', locAnswer, '- defaulting to first option:', locMatch?.text);
                                }
                                
                                if (locMatch) {
                                    console.log('Location Select: Selecting', locMatch.text, 'for', labelText);
                                    select.value = locMatch.value;
                                    if (select.value !== locMatch.value) select.selectedIndex = locMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: locMatch.text, inputType: 'select-location' });
                                    continue;
                                }
                            }
                            
                            // ===== NATIONALITY SELECT HANDLER =====
                            // Handles "Nationality" dropdowns where options are country names ("India")
                            // but our default answer is "Indian" (demonym). Substring matching would
                            // incorrectly pick "British Indian Ocean Territory". Use exact matching instead.
                            const isNationalitySelect = lowerLabel.includes('nationality') && !lowerLabel.includes('citizenship');
                            if (isNationalitySelect) {
                                const natOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let natMatch = null;
                                
                                // Priority 1: Exact "India" or "Indian" (case-insensitive)
                                natMatch = natOptions.find(o => {
                                    const t = o.text.toLowerCase().trim();
                                    return t === 'india' || t === 'indian';
                                });
                                
                                // Priority 2: Starts with "India" but NOT "Indian Ocean" or "British Indian"
                                if (!natMatch) {
                                    natMatch = natOptions.find(o => {
                                        const t = o.text.toLowerCase().trim();
                                        return t.startsWith('india') && !t.includes('ocean') && !t.includes('british');
                                    });
                                }
                                
                                // Priority 3: Contains "India" as a standalone word
                                if (!natMatch) {
                                    natMatch = natOptions.find(o => {
                                        const t = o.text.toLowerCase().trim();
                                        return /\bindia\b/.test(t) && !t.includes('british') && !t.includes('ocean');
                                    });
                                }
                                
                                if (natMatch) {
                                    console.log('Nationality match: Selecting', natMatch.text, 'for', labelText.substring(0, 80));
                                    select.value = natMatch.value;
                                    if (select.value !== natMatch.value) select.selectedIndex = natMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: natMatch.text, inputType: 'select-nationality' });
                                }
                                continue;
                            }
                            
                            // ===== JOB TITLE / SENIORITY LEVEL HANDLER =====
                            // Handles "Current Job Title", "Designation", "Seniority Level" dropdowns
                            // where options are level names (Fresher, Junior, Mid-Level, Senior, Lead)
                            // and the user's actual title ("SDE-2") won't match any option.
                            const isJobLevelSelect = lowerLabel.includes('job title') || lowerLabel.includes('designation') || 
                                                     lowerLabel.includes('seniority') || lowerLabel.includes('job level') ||
                                                     lowerLabel.includes('career level') || lowerLabel.includes('experience level');
                            if (isJobLevelSelect) {
                                const jlOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let jlMatch = null;
                                
                                // With 4 years experience, select Mid-Level > Senior > Experienced > Associate
                                jlMatch = jlOptions.find(o => /\bmid[\s-]?level\b/i.test(o.text));
                                if (!jlMatch) jlMatch = jlOptions.find(o => /\bsenior\b/i.test(o.text) && !/\bsuper\b|\bstaff\b|\bprincipal\b/i.test(o.text));
                                if (!jlMatch) jlMatch = jlOptions.find(o => /\bexperienced\b/i.test(o.text));
                                if (!jlMatch) jlMatch = jlOptions.find(o => /\bassociate\b/i.test(o.text));
                                if (!jlMatch) jlMatch = jlOptions.find(o => /\bprofessional\b/i.test(o.text));
                                
                                // Fallback: first non-placeholder option
                                if (!jlMatch) {
                                    jlMatch = jlOptions.find(o => {
                                        const t = (o.text || '').toLowerCase().trim();
                                        return t.length > 0 && !t.includes('select') && !t.includes('choose') && !t.includes('please') && !t.includes('fresher');
                                    });
                                }
                                
                                if (jlMatch) {
                                    console.log('Job Level match: Selecting', jlMatch.text, 'for', labelText.substring(0, 80));
                                    select.value = jlMatch.value;
                                    if (select.value !== jlMatch.value) select.selectedIndex = jlMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: jlMatch.text, inputType: 'select-job-level' });
                                }
                                continue;
                            }
                            
                            // ===== WORKPLACE TYPE / WORK MODE HANDLER =====
                            // Handles "Preferred Workplace Type", "Work Mode" dropdowns where
                            // options are like Onsite, Remote, Hybrid, Any. fuzzyMatch often returns
                            // an unrelated answer (e.g. "Serving Notice Period") due to keyword overlap.
                            const isWorkplaceType = lowerLabel.includes('workplace') || lowerLabel.includes('work mode') || 
                                                    lowerLabel.includes('work type') || lowerLabel.includes('working model') ||
                                                    lowerLabel.includes('work preference') || lowerLabel.includes('mode of work');
                            if (isWorkplaceType) {
                                const wpOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                let wpMatch = null;
                                
                                // Preference order: Hybrid > Any > Flexible > Remote > Onsite
                                wpMatch = wpOptions.find(o => /\bhybrid\b/i.test(o.text));
                                if (!wpMatch) wpMatch = wpOptions.find(o => /\bany\b/i.test(o.text));
                                if (!wpMatch) wpMatch = wpOptions.find(o => /\bflexible\b/i.test(o.text));
                                if (!wpMatch) wpMatch = wpOptions.find(o => /\bremote\b/i.test(o.text));
                                if (!wpMatch) wpMatch = wpOptions.find(o => /\bonsite\b|\bon[\s-]?site\b/i.test(o.text));
                                
                                // Fallback: first non-placeholder option
                                if (!wpMatch) {
                                    wpMatch = wpOptions.find(o => {
                                        const t = (o.text || '').toLowerCase().trim();
                                        return t.length > 0 && !t.includes('select') && !t.includes('choose') && !t.includes('please');
                                    });
                                }
                                
                                if (wpMatch) {
                                    console.log('Workplace Type match: Selecting', wpMatch.text, 'for', labelText.substring(0, 80));
                                    select.value = wpMatch.value;
                                    if (select.value !== wpMatch.value) select.selectedIndex = wpMatch.index;
                                    select.dispatchEvent(new Event('input', { bubbles: true }));
                                    select.dispatchEvent(new Event('change', { bubbles: true }));
                                    select.dispatchEvent(new Event('blur', { bubbles: true }));
                                    formResults.push({ question: labelText, answer: wpMatch.text, inputType: 'select-workplace' });
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
                                
                                // EDUCATION LEVEL MATCHING — bypass generic findBestMatch which
                                // fails on free-text education descriptions (e.g. "B.Tech in Computer
                                // Science Engineering"). User has B.Tech = Bachelor's Degree.
                                if (lowerLabel.includes('education') || lowerLabel.includes('highest level') || lowerLabel.includes('qualification') || lowerLabel.includes('degree')) {
                                    const eduOptions = Array.from(select.options).map(o => ({ text: o.text, value: o.value, index: o.index }));
                                    let eduMatch = eduOptions.find(o =>
                                        o.text.toLowerCase().includes('bachelor') &&
                                        !o.text.toLowerCase().includes('master')
                                    );
                                    if (!eduMatch) {
                                        eduMatch = eduOptions.find(o => {
                                            const t = o.text.toLowerCase().trim();
                                            return t.includes('b.tech') ||
                                                t.includes('undergraduate') ||
                                                t.includes('college degree') ||
                                                t.includes("bachelor's") ||
                                                t === 'ug' ||
                                                t.startsWith('ug ') ||
                                                t.includes('ug/');
                                        });
                                    }
                                    if (eduMatch) {
                                        select.value = eduMatch.value;
                                        if (select.value !== eduMatch.value) select.selectedIndex = eduMatch.index;
                                        select.dispatchEvent(new Event('input', { bubbles: true }));
                                        select.dispatchEvent(new Event('change', { bubbles: true }));
                                        select.dispatchEvent(new Event('blur', { bubbles: true }));
                                        console.log('Education match: Selected', eduMatch.text, 'for', labelText);
                                        formResults.push({ question: labelText, answer: eduMatch.text, inputType: 'select-education' });
                                        continue;
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
                                            const defaultNo = shouldDefaultToNo(legend);
                                            const targetValue = defaultNo ? 'no' : 'yes';
                                            const targetRadio = radios.find(r => {
                                                const val = (r.value || '').toLowerCase();
                                                const labelText = getInputLabelText(r);
                                                return val === targetValue || labelText === targetValue || labelText.includes(targetValue);
                                            });
                                            if (targetRadio) {
                                                console.log(`Defaulting to ${defaultNo ? 'No' : 'Yes'} for Yes/No question:`, legend.substring(0, 50));
                                                clickInput(targetRadio);
                                                formResults.push({ question: legend.substring(0, 100), answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                                        const defaultNo = shouldDefaultToNo(legend);
                                        const targetValue = defaultNo ? 'no' : 'yes';
                                        const targetRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === targetValue || labelText === targetValue || labelText.includes(targetValue);
                                        });
                                        if (targetRadio) {
                                            console.log(`Defaulting Yes/No question to ${defaultNo ? 'No' : 'Yes'} in fieldset:`, legend.substring(0, 50));
                                            clickInput(targetRadio);
                                            formResults.push({ question: legend.substring(0, 100), answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                                            const defaultNo = shouldDefaultToNo(questionText);
                                            const targetValue = defaultNo ? 'no' : 'yes';
                                            const targetRadio = customRadios.find(r => {
                                                const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                                return t === targetValue || t.includes(targetValue);
                                            });
                                            if (targetRadio) {
                                                console.log(`Defaulting custom radio to ${defaultNo ? 'No' : 'Yes'}:`, questionText.substring(0, 50));
                                                clickCustomRadio(targetRadio);
                                                formResults.push({ question: questionText.substring(0, 100), answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                                        const defaultNo = shouldDefaultToNo(questionText);
                                        const targetValue = defaultNo ? 'no' : 'yes';
                                        const targetRadio = customRadios.find(r => {
                                            const t = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
                                            return t === targetValue || t.includes(targetValue);
                                        });
                                        if (targetRadio) {
                                            console.log(`Defaulting custom Yes/No to ${defaultNo ? 'No' : 'Yes'}:`, questionText.substring(0, 50));
                                            clickCustomRadio(targetRadio);
                                            formResults.push({ question: questionText.substring(0, 100) || 'Yes/No question', answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                                            const defaultNo = shouldDefaultToNo(questionText);
                                            const targetValue = defaultNo ? 'no' : 'yes';
                                            const targetRadio = radios.find(r => {
                                                const val = (r.value || '').toLowerCase();
                                                const labelText = getInputLabelText(r);
                                                return val === targetValue || labelText === targetValue || labelText.includes(targetValue);
                                            });
                                            if (targetRadio) {
                                                console.log(`Defaulting to ${defaultNo ? 'No' : 'Yes'} for Yes/No question:`, questionText.substring(0, 50));
                                                clickInput(targetRadio);
                                                formResults.push({ question: questionText.substring(0, 100), answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                                        const defaultNo = shouldDefaultToNo(questionText);
                                        const targetValue = defaultNo ? 'no' : 'yes';
                                        const targetRadio = radios.find(r => {
                                            const val = (r.value || '').toLowerCase();
                                            const labelText = getInputLabelText(r);
                                            return val === targetValue || labelText === targetValue || labelText.includes(targetValue);
                                        });
                                        if (targetRadio) {
                                            console.log(`Defaulting Yes/No question to ${defaultNo ? 'No' : 'Yes'}:`, questionText.substring(0, 50) || 'Unknown question');
                                            clickInput(targetRadio);
                                            formResults.push({ question: questionText.substring(0, 100) || 'Yes/No question', answer: defaultNo ? 'No' : 'Yes', inputType: 'radio' });
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
                            // EXTENDED: LinkedIn places question text OUTSIDE the fieldset as a preceding sibling.
                            // Walk up to 3 ancestor levels looking at previous siblings.
                            let ancestor = fieldset;
                            for (let lvl = 0; lvl < 3; lvl++) {
                                let sib = ancestor.previousElementSibling;
                                while (sib) {
                                    const t = (sib.innerText || '').trim();
                                    if (t.length > 10 && t.length < 400 &&
                                        !sib.querySelector('input[type="checkbox"], input[type="radio"]') &&
                                        !t.toLowerCase().includes('this field is required')) {
                                        console.log('getGroupQuestionText: found label in prev-sibling (lvl', lvl, '):', t.substring(0, 80));
                                        return t.replace(/\*$/, '').replace(/\* This field is required/gi, '').trim();
                                    }
                                    sib = sib.previousElementSibling;
                                }
                                if (!ancestor.parentElement) break;
                                ancestor = ancestor.parentElement;
                            }
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
                                // Fallback: span sibling (used by LinkedIn nationality checkboxes)
                                const spanSibling = parent.querySelector('span');
                                if (spanSibling && spanSibling.innerText.trim()) return spanSibling.innerText.trim();
                                // Fallback: direct text content of parent (excluding checkbox input)
                                const parentText = Array.from(parent.childNodes)
                                    .filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'INPUT'))
                                    .map(n => n.textContent.trim())
                                    .filter(t => t.length > 0)
                                    .join(' ').trim();
                                if (parentText) return parentText;
                            }
                            // Fallback: grandparent traversal for deeply nested checkboxes
                            const grandparent = cb.parentElement?.parentElement;
                            if (grandparent) {
                                const gpLabel = grandparent.querySelector('label, span');
                                if (gpLabel && gpLabel.innerText.trim()) return gpLabel.innerText.trim();
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

                            // ===== NATIONALITY CHECKBOX DETECTION =====
                            // LinkedIn Avaloq-style: 187 checkboxes with country demonyms (Afghan, Albanian, ...Indian...)
                            const isNationalityGroup = groupQuestion.toLowerCase().includes('nationality') ||
                                                     groupQuestion.toLowerCase().includes('nationalities') ||
                                                     groupQuestion.toLowerCase().includes('citizenship');
                            
                            if (isNationalityGroup) {
                                console.log('Nationality checkbox group detected, looking for Indian...');
                                const groupCbs = fieldset.querySelectorAll('input[type="checkbox"]');
                                let found = false;
                                for (const cb of groupCbs) {
                                    handledCheckboxes.add(cb);
                                    if (found || !isVisible(cb) || cb.checked) continue;
                                    const optLabel = getOptionLabel(cb);
                                    if (optLabel.toLowerCase() === 'indian') {
                                        console.log('Nationality: Selecting Indian checkbox');
                                        clickInput(cb);
                                        formResults.push({ question: groupQuestion || 'Nationality', answer: 'Indian', inputType: 'checkbox-nationality' });
                                        found = true;
                                    }
                                }
                                if (!found) console.log('Nationality: Could not find Indian option');
                                continue;
                            }

                            // ===== FALLBACK: If group has 50+ checkboxes with no question, check if they look like nationalities =====
                            const groupCbsAll = fieldset.querySelectorAll('input[type="checkbox"]');
                            if (!groupQuestion && groupCbsAll.length > 50) {
                                // Sample a few labels to detect nationality pattern
                                const sampleLabels = [];
                                const sampleCbs = Array.from(groupCbsAll).slice(0, 10);
                                for (const cb of sampleCbs) {
                                    const lbl = getOptionLabel(cb);
                                    if (lbl) sampleLabels.push(lbl.toLowerCase());
                                }
                                const nationalityHints = ['afghan', 'albanian', 'american', 'australian', 'indian', 'british', 'chinese'];
                                const looksLikeNationality = sampleLabels.filter(l => nationalityHints.some(h => l.includes(h))).length >= 2;
                                
                                if (looksLikeNationality) {
                                    console.log('Detected unlabeled nationality checkbox group (heuristic), looking for Indian...');
                                    let found = false;
                                    for (const cb of groupCbsAll) {
                                        handledCheckboxes.add(cb);
                                        if (found || !isVisible(cb) || cb.checked) continue;
                                        const optLabel = getOptionLabel(cb);
                                        if (optLabel.toLowerCase() === 'indian') {
                                            console.log('Nationality (heuristic): Selecting Indian checkbox');
                                            clickInput(cb);
                                            formResults.push({ question: 'Nationality (detected)', answer: 'Indian', inputType: 'checkbox-nationality' });
                                            found = true;
                                        }
                                    }
                                    if (!found) console.log('Nationality (heuristic): Could not find Indian option');
                                    continue;
                                }
                            }

                            const groupAnswer = groupQuestion ? fuzzyMatch(groupQuestion) : null;
                            console.log('Checkbox group answer:', groupAnswer);

                            const groupCbs = fieldset.querySelectorAll('input[type="checkbox"]');
                            let groupAllLabelsEmpty = true; // track if all option labels are undetectable
                            for (const cb of groupCbs) {
                                handledCheckboxes.add(cb);
                                if (!isVisible(cb) || cb.checked) continue;

                                const optLabel = getOptionLabel(cb);
                                console.log('Checkbox option label:', optLabel || '(none)');
                                if (optLabel) groupAllLabelsEmpty = false;

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

                            // ===== NOT-APPLICABLE FALLBACK =====
                            // If all option labels were undetectable (LinkedIn obfuscated DOM for
                            // affiliation/employment-type fieldsets) AND no answer was resolved,
                            // click the FIRST checkbox. On LinkedIn these fieldsets always list
                            // "Not Applicable" first, so this safely unblocks the form.
                            if (groupAllLabelsEmpty && !groupAnswer) {
                                const firstUnchecked = Array.from(groupCbs).find(cb => isVisible(cb) && !cb.checked);
                                if (firstUnchecked) {
                                    console.log('NOT-APPLICABLE FALLBACK: all labels empty + no answer → clicking first checkbox for group:', groupQuestion.substring(0, 60) || '(unknown)');
                                    clickInput(firstUnchecked);
                                    formResults.push({ question: groupQuestion || 'Affiliation/EmploymentType', answer: 'Not Applicable (auto)', inputType: 'checkbox' });
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
                            
                            // Method 7: If label is short/generic (e.g. "Yes"), scan nearest ancestor
                            // containers for GDPR/consent text. Handles SmartBear-style checkboxes where
                            // the checkbox is labeled simply "Yes" but the consent question is a paragraph
                            // above it. Without this, the bot logs "Skipping checkbox" and gets stuck.
                            if (!labelText || /^(yes|no|agree|ok|accept|confirm|check)$/i.test(labelText.trim())) {
                                const ancestors = [
                                    checkbox.closest('.jobs-easy-apply-form-section__question'),
                                    checkbox.closest('.fb-dash-form-element'),
                                    checkbox.closest('[data-test-form-element]'),
                                    checkbox.closest('fieldset'),
                                    checkbox.closest('li'),
                                    checkbox.parentElement ? checkbox.parentElement.parentElement : null,
                                    (checkbox.parentElement && checkbox.parentElement.parentElement)
                                        ? checkbox.parentElement.parentElement.parentElement : null,
                                ].filter(Boolean);
                                for (const container of ancestors) {
                                    const containerText = container.innerText || '';
                                    const ctLower = containerText.toLowerCase();
                                    if (ctLower.includes('consent') || ctLower.includes('privacy') ||
                                        ctLower.includes('collect') || ctLower.includes('store and process') ||
                                        ctLower.includes('1825 days') || ctLower.includes('730 days') ||
                                        ctLower.includes('365 days') || ctLower.includes('days thereafter') ||
                                        ctLower.includes('for employment') || ctLower.includes('acknowledge') ||
                                        ctLower.includes('processing of my') || ctLower.includes('personal data')) {
                                        const overrideText = containerText.substring(0, 500);
                                        console.log('Method 7: Generic label "' + labelText.trim() + '" — using surrounding consent context: ' + overrideText.substring(0, 80));
                                        labelText = overrideText;
                                        break;
                                    }
                                }
                            }
                            
                            console.log('Checkbox label text found:', labelText.substring(0, 100));
                            const lowerLabel = labelText.toLowerCase();
                            
                            // Check if this is a privacy/consent/acknowledge/confirm checkbox
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
                                                     lowerLabel.includes('confirmed') ||
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
                            
                            const hasEmptyInput = requiredInputs.some(i => isVisible(i) && !readFieldValue(i));
                            
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
                        
                        // Scroll modal content to bottom so lazy-rendered buttons are in DOM.
                        // Prefer .artdeco-modal__content (the actual scrollable container) over
                        // the FORM element, which may not have overflow scrolling.
                        const scrollableContent = modal.querySelector('.artdeco-modal__content, [class*="modal__content"], [class*="body"], [class*="content"], div[style*="overflow"]') ||
                                                  (modal.matches && modal.matches('.artdeco-modal__content, .artdeco-modal') ? modal : null) ||
                                                  modal.querySelector('form') || modal;
                        if (scrollableContent && scrollableContent.scrollHeight > scrollableContent.clientHeight) {
                            scrollableContent.scrollTop = scrollableContent.scrollHeight;
                            console.log('Scrolled modal content to bottom to reveal lazy buttons');
                        }
                        
                        // Find action buttons (Review, Next, Submit)
                        // NOTE: 'review your application' (not just 'review') to avoid
                        // matching "Review job post" on the safety reminder modal.
                        console.log('Searching for primary action button...');
                        const modalFooter = queryDeep('footer', modal);
                        const primaryBtn = queryDeep('button[aria-label*="Review your application"]', modal) ||
                                         queryDeep('button[aria-label*="Continue to next step"]', modal) ||
                                         queryDeep('button[aria-label*="next step"]', modal) ||
                                         queryDeep('button[aria-label*="Submit application"]', modal) ||
                                         queryDeep('button[data-easy-apply-next-button]', modal) ||
                                         queryDeep('button[data-live-test-easy-apply-next-button]', modal) ||
                                         queryDeep('button[data-live-test-easy-apply-review-button]', modal) ||
                                         queryDeep('.jobs-apply-button--primary', modal) ||
                                         findByText('button', 'submit application', false, modal) ||
                                         findByText('button', 'review your application', false, modal) ||
                                         (modalFooter ? findByText('button', 'review', false, modalFooter) : null) ||
                                         findByText('button', 'next', false, modal);

                        if (primaryBtn) {
                            // Only click if form is valid
                            if (checkForErrors()) {
                                // Check if the ONLY issue is visible errors (stale React validation)
                                // When all fields are filled but LinkedIn shows "This field is required",
                                // force-click Next to let LinkedIn's submission re-validate
                                const allInputsFilled = !queryAllDeep('input[type="text"], input[type="number"], input:not([type]), textarea', modal)
                                    .some(inp => isVisible(inp) && !readFieldValue(inp) && !inp.disabled);
                                const allSelectsFilled = !queryAllDeep('select', modal)
                                    .some(sel => isVisible(sel) && (!sel.value || sel.options[sel.selectedIndex]?.text.toLowerCase().includes('select')));
                                
                                if (allInputsFilled && allSelectsFilled) {
                                    console.log('All fields filled but visible errors remain — force-clicking Next to re-trigger validation');
                                    // Don't return FORM_STUCK, fall through to click the button
                                } else {
                                    console.log('Form has errors or missing required fields. Waiting for resolution...');
                                    return 'LINKEDIN_FORM_STUCK: Validation errors or required fields missing';
                                }
                            }
                            
                            // Scroll the button into view before clicking (handles tall forms
                            // where the footer/Next button is scrolled out of view)
                            try {
                                primaryBtn.scrollIntoView({block: 'center', behavior: 'instant'});
                                console.log('Scrolled primary button into view');
                            } catch (e) {
                                console.log('scrollIntoView failed (non-critical):', e.message);
                            }
                            
                            console.log('Clicking modal primary button:', primaryBtn.innerText || primaryBtn.getAttribute('aria-label'));
                            primaryBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                            primaryBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                            primaryBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                            primaryBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                            primaryBtn.click();
                            const btnText = (primaryBtn.innerText || primaryBtn.textContent || '').toLowerCase();
                            const btnAria = (primaryBtn.getAttribute('aria-label') || '').toLowerCase();
                            const isSubmit = btnText.includes('submit') || btnAria.includes('submit');
                            const actionResult = isSubmit ? 'LINKEDIN_SUBMITTED' : 'LINKEDIN_FORM_STEP_CONTINUED';
                            return actionResult + (formResults.length > 0 ? '|' + JSON.stringify(formResults) : '');
                        }

                        // Conservative global fallback: search entire page ONLY for modal-specific
                        // button phrasings. Never match generic 'next' globally — that matches the
                        // job search results pagination button and dismisses the modal.
                        console.log('No button found in modal, trying conservative global fallback (no generic next)...');
                        const globalPrimaryBtn = queryDeep('button[aria-label*="Review your application"]') ||
                                                 queryDeep('button[aria-label*="Submit application"]') ||
                                                 queryDeep('button[data-live-test-easy-apply-review-button]') ||
                                                 findByText('button', 'submit application') ||
                                                 findByText('button', 'review your application') ||
                                                 findByText('button', 'review');
                        if (globalPrimaryBtn && isVisible(globalPrimaryBtn)) {
                            if (checkForErrors()) {
                                // Same force-proceed logic as primary button
                                const allInputsFilled2 = !queryAllDeep('input[type="text"], input[type="number"], input:not([type]), textarea', modal)
                                    .some(inp => isVisible(inp) && !readFieldValue(inp) && !inp.disabled);
                                const allSelectsFilled2 = !queryAllDeep('select', modal)
                                    .some(sel => isVisible(sel) && (!sel.value || sel.options[sel.selectedIndex]?.text.toLowerCase().includes('select')));
                                if (!(allInputsFilled2 && allSelectsFilled2)) {
                                    console.log('Form has errors. Waiting...');
                                    return 'LINKEDIN_FORM_STUCK: Validation errors';
                                }
                                console.log('All fields filled but visible errors remain (global fallback) — force-clicking');
                            }
                            try {
                                globalPrimaryBtn.scrollIntoView({block: 'center', behavior: 'instant'});
                            } catch (e) {}
                            console.log('Found button via global fallback:', globalPrimaryBtn.innerText || globalPrimaryBtn.getAttribute('aria-label'));
                            globalPrimaryBtn.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                            globalPrimaryBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                            globalPrimaryBtn.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                            globalPrimaryBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                            globalPrimaryBtn.click();
                            const btnText = (globalPrimaryBtn.innerText || '').toLowerCase();
                            const btnAria = (globalPrimaryBtn.getAttribute('aria-label') || '').toLowerCase();
                            const isSubmit = btnText.includes('submit') || btnAria.includes('submit');
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
                        // GUARD: Require Easy Apply-specific indicators to prevent false positives
                        // from job details panel or other page elements with [componentkey]
                        const compKeyEl = document.querySelector('[componentkey]');
                        if (compKeyEl && isVisible(compKeyEl) && compKeyEl.querySelector('input, select, textarea') &&
                            (compKeyEl.querySelector('svg[role="progressbar"]') ||
                             compKeyEl.querySelector('button[aria-label*="Submit"], button[aria-label*="next step"], button[aria-label*="Review"]') ||
                             /apply|application|resume|contact info/i.test((compKeyEl.innerText || '').substring(0, 500)))) {
                            console.log('Modal detected via componentkey+inputs heuristic');
                            return true;
                        }
                        return false;
                    };

// Helper: Get the modal element for form handling
                    const findEasyApplyModalEl = () => {
                        // Strategy 1: Walk up from progress bar if found (Guaranteed correct modal container)
                        // Prefer .artdeco-modal__content / .artdeco-modal / [role="dialog"] over FORM,
                        // because the content container is the actual scrollable element and contains
                        // the footer buttons (Next/Review/Submit). Returning FORM breaks scrolling.
                        const pb = document.querySelector('svg[role="progressbar"][aria-valuenow]');
                        if (pb) {
                            let el = pb.parentElement;
                            let formFallback = null;
                            while (el && el !== document.body) {
                                const cls = typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '');
                                const lowerCls = cls.toLowerCase();
                                const isBlacklisted = lowerCls.includes('dropdown-to-modal') || 
                                                      lowerCls.includes('msg-overlay') || 
                                                      lowerCls.includes('msg-convo') || 
                                                      lowerCls.includes('messaging') ||
                                                      lowerCls.includes('filter__dropdown');
                                                  
                                if (!isBlacklisted) {
                                    // Priority 1: modal content container (scrollable, contains footer buttons)
                                    if (el.matches && (el.matches('.artdeco-modal__content') || lowerCls.includes('modal__content'))) {
                                        return el;
                                    }
                                    // Priority 2: outer modal/dialog container
                                    if (el.matches && (el.matches('.artdeco-modal') || el.matches('[role="dialog"]') || el.classList.contains('jobs-easy-apply-modal'))) {
                                        return el;
                                    }
                                    // Priority 3 (fallback): FORM or componentkey — remember but keep walking
                                    if (!formFallback && (el.tagName === 'FORM' || el.hasAttribute('componentkey'))) {
                                        formFallback = el;
                                    }
                                }
                                el = el.parentElement;
                            }
                            // Return FORM fallback only if no modal container was found walking up
                            if (formFallback) return formFallback;
                        }

                        // Strategy 2: Check standard modal container selectors next
                        // Skip messaging overlays and background filter dropdowns
                        const selectors = [
                            '.artdeco-modal__content',
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
                            if (text.includes('success') || dialog.querySelector('[data-test-icon="signal-success"]') || /application\s+\w+\s+(sent|submitted)/i.test(text)) {
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

                    // Persistent skip-list across invocations (survives between evaluate calls)
                    if (!window.__skippedJobIds) window.__skippedJobIds = new Set();

                    // No modal open - handle job selection and clicking Easy Apply
                    console.log('No modal detected. Checking for Easy Apply button...');
                    const easyApplyBtn = findEasyApplyButton();
                    if (easyApplyBtn) {
                        console.log('Easy Apply button found, clicking...');
                        easyApplyBtn.click();
                        return 'LINKEDIN_EASY_APPLY_CLICKED';
                    }

                    // ── NO EASY APPLY BUTTON FOUND ──
                    // If a job is currently selected/active but has no Easy Apply button
                    // (e.g. "No longer accepting applications"), mark it as skipped so we
                    // don't keep re-selecting it in an infinite loop.
                    {
                        // Detect active job ID from URL parameter OR from active card in DOM
                        const urlParams = new URLSearchParams(window.location.search);
                        let currentJobId = urlParams.get('currentJobId');
                        
                        // Fallback: extract job ID from the active card in the sidebar
                        if (!currentJobId) {
                            const activeCard = document.querySelector('.jobs-search-results-list__list-item--active [data-job-id]') ||
                                              document.querySelector('[aria-current="true"] [data-job-id]') ||
                                              document.querySelector('.job-card-list__list-item--active [data-job-id]') ||
                                              document.querySelector('.active [data-job-id]') ||
                                              document.querySelector('[data-occludable-job-id].jobs-search-results-list__list-item--active');
                            if (activeCard) {
                                currentJobId = activeCard.getAttribute('data-job-id') || 
                                              activeCard.getAttribute('data-occludable-job-id');
                            }
                        }
                        
                        // NOT_ELIGIBLE_FOR_CHARGING in URL = LinkedIn internally marks the job as closed/ineligible
                        const isNotEligible = window.location.href.includes('NOT_ELIGIBLE_FOR_CHARGING') ||
                                              window.location.href.includes('eBP=NOT_ELIGIBLE') ||
                                              window.location.search.includes('eBP=NOT');
                        if (isNotEligible && currentJobId && !window.__skippedJobIds.has(currentJobId)) {
                            console.log('Job ' + currentJobId + ' is NOT_ELIGIBLE_FOR_CHARGING (URL signal). Marking as skipped.');
                            window.__skippedJobIds.add(currentJobId);
                            return 'LINKEDIN_JOB_SKIPPED: No Easy Apply — job closed (URL signal)';
                        }
                        
                        if (currentJobId && !window.__skippedJobIds.has(currentJobId)) {
                            // Check for signs this job cannot be applied to
                            const detailPane = document.querySelector('.job-view-layout, .jobs-unified-top-card, .jobs-details, .scaffold-layout__detail');
                            const detailText = detailPane ? (detailPane.innerText || '').toLowerCase() : document.body.innerText.toLowerCase();
                            const noApplySignals = [
                                'no longer accepting',
                                'application closed',
                                'applications closed',
                                'no longer available',
                                'this job is no longer',
                                'expired',
                                'position has been filled',
                                'no longer accepting applications'
                            ];
                            const hasNoApplySignal = noApplySignals.some(sig => detailText.includes(sig));
                            // Also skip if we simply can't find an Easy Apply button after selecting this job
                            if (hasNoApplySignal || !findEasyApplyButton()) {
                                console.log('Job ' + currentJobId + ' has no Easy Apply button (closed/expired). Marking as skipped.');
                                window.__skippedJobIds.add(currentJobId);
                                return 'LINKEDIN_JOB_SKIPPED: No Easy Apply — ' + (hasNoApplySignal ? 'job closed' : 'button not found');
                            }
                        }
                        
                        // Fallback: even without a job ID, detect closed jobs by URL or detail pane
                        if (!currentJobId) {
                            const detailPane = document.querySelector('.job-view-layout, .jobs-unified-top-card, .jobs-details, .scaffold-layout__detail');
                            const detailText = detailPane ? (detailPane.innerText || '').toLowerCase() : '';
                            const isClosed = isNotEligible || 
                                            detailText.includes('no longer accepting') ||
                                            detailText.includes('no longer available') ||
                                            detailText.includes('application closed');
                            if (isClosed && !findEasyApplyButton()) {
                                console.log('Job with no ID appears closed (URL/detail signal). Skipping...');
                                // Track by title to avoid re-selecting
                                const titleEl = document.querySelector('.job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1');
                                const title = titleEl ? titleEl.innerText.trim().substring(0, 80) : '';
                                if (title) {
                                    if (!window.__skippedJobTitles) window.__skippedJobTitles = new Set();
                                    window.__skippedJobTitles.add(title);
                                    console.log('Added to skipped titles:', title);
                                }
                                return 'LINKEDIN_JOB_SKIPPED: No Easy Apply — closed job (no ID)';
                            }
                        }
                        
                        // Even without a job ID, if we still can't find Easy Apply, return skip
                        if (!currentJobId && !findEasyApplyButton()) {
                            console.log('No Easy Apply button and could not identify job ID. Skipping...');
                            return 'LINKEDIN_JOB_SKIPPED: No Easy Apply — unknown job';
                        }
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
                    // 5. Must not be in the skipped jobs set
                    const candidates = jobCards.filter(card => {
                        const text = card.innerText.toLowerCase();
                        // Active class may be on card itself OR on a parent <li> element
                        // LinkedIn puts --active on the <li> wrapper, not on .job-card-container
                        const isActive = card.classList.contains('jobs-search-results-list__list-item--active') ||
                                        card.classList.contains('job-card-list__list-item--active') ||
                                        card.closest('.jobs-search-results-list__list-item--active') !== null ||
                                        card.closest('.job-card-list__list-item--active') !== null ||
                                        card.closest('[aria-current="true"]') !== null ||
                                        card.getAttribute('aria-current') === 'true' ||
                                        card.classList.contains('active') ||
                                        card.closest('.active') !== null;
                        
                        if (isActive) return false;
                        if (!isVisible(card)) return false;
                        
                        // Check if this job's ID is in the skip list
                        const cardJobId = card.getAttribute('data-job-id') ||
                                         card.querySelector('[data-job-id]')?.getAttribute('data-job-id') ||
                                         card.getAttribute('data-occludable-job-id') ||
                                         card.querySelector('[data-occludable-job-id]')?.getAttribute('data-occludable-job-id');
                        if (cardJobId && window.__skippedJobIds && window.__skippedJobIds.has(cardJobId)) {
                            console.log('Skipping previously-skipped job ID:', cardJobId);
                            return false;
                        }
                        
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

                    // Filter out jobs whose title was skipped by the title-based skip list
                    const titleFilteredCandidates = candidates.filter(card => {
                        if (!window.__skippedJobTitles || window.__skippedJobTitles.size === 0) return true;
                        const cardTitle = card.innerText.split('\\n')[0].trim().substring(0, 80);
                        return !window.__skippedJobTitles.has(cardTitle);
                    });

                    if (titleFilteredCandidates.length > 0) {
                        const nextJob = titleFilteredCandidates[0];
                        const nextJobTitle = nextJob.innerText.split('\\n')[0].trim();
                        
                        // Detect infinite loop: if we already clicked this exact job title last time,
                        // it means clicking it did not advance state. Skip it.
                        if (window.__lastClickedJobTitle === nextJobTitle) {
                            window.__lastClickedJobSameCount = (window.__lastClickedJobSameCount || 0) + 1;
                            console.log('Same job selected again (' + window.__lastClickedJobSameCount + 'x): ' + nextJobTitle);
                            if (window.__lastClickedJobSameCount >= 2) {
                                console.log('Infinite loop detected on: ' + nextJobTitle + ' — adding to skip list');
                                if (!window.__skippedJobTitles) window.__skippedJobTitles = new Set();
                                window.__skippedJobTitles.add(nextJobTitle);
                                window.__lastClickedJobTitle = null;
                                window.__lastClickedJobSameCount = 0;
                                // Scroll sidebar to reveal next jobs
                                if (sidebar) sidebar.scrollBy(0, 400);
                                return 'LINKEDIN_SCROLLED: Skipping stuck job — ' + nextJobTitle;
                            }
                        } else {
                            window.__lastClickedJobSameCount = 0;
                        }
                        window.__lastClickedJobTitle = nextJobTitle;
                        
                        console.log('Clicking next job:', nextJobTitle);
                        nextJob.click();
                        nextJob.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        return 'LINKEDIN_JOB_SELECTED';
                    } else if (candidates.length > 0) {
                        // All candidates were filtered by title skip list — scroll to load more
                        console.log('All visible candidates are in skip list, scrolling sidebar...');
                        if (sidebar) sidebar.scrollBy(0, 400);
                        return 'LINKEDIN_SCROLLED: All candidates skipped';
                    }

                    // No eligible jobs found — check if we should paginate or scroll
                    const isAtBottom = (sidebar.scrollTop + sidebar.clientHeight) >= (sidebar.scrollHeight - 50);
                    
                    if (!isAtBottom) {
                        // Still have room to scroll in sidebar
                        console.log('No eligible jobs visible in sidebar, scrolling sidebar...');
                        sidebar.scrollBy(0, 800);
                        return 'LINKEDIN_SCROLLED: No jobs found';
                    }
                    
                    // At bottom of sidebar — try to click next page pagination button
                    console.log('Sidebar fully scrolled. Looking for next page pagination button...');
                    
                    // Strategy 1: data-testid based (most reliable)
                    const nextBtnByTestId = document.querySelector('button[data-testid="pagination-controls-next-button-visible"]');
                    if (nextBtnByTestId) {
                        console.log('Found Next button via data-testid, clicking...');
                        nextBtnByTestId.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        nextBtnByTestId.click();
                        return 'LINKEDIN_SCROLLED: No jobs found — NEXT_PAGE_CLICKED';
                    }
                    
                    // Strategy 2: Find current page and click next page number
                    const currentPageBtn = document.querySelector('button[aria-current="true"][aria-label^="Page"]');
                    if (currentPageBtn) {
                        const label = currentPageBtn.getAttribute('aria-label');
                        const match = label && label.match(/Page (\d+)/);
                        if (match) {
                            const nextPageNum = parseInt(match[1]) + 1;
                            const nextPageBtn = document.querySelector('button[aria-label="Page ' + nextPageNum + '"]');
                            if (nextPageBtn) {
                                console.log('Found Page ' + nextPageNum + ' button, clicking...');
                                nextPageBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                nextPageBtn.click();
                                return 'LINKEDIN_SCROLLED: No jobs found — NEXT_PAGE_CLICKED';
                            }
                        }
                    }
                    
                    // Strategy 3: Find any pagination "Next" button with chevron
                    const allBtns = Array.from(document.querySelectorAll('button'));
                    const nextChevronBtn = allBtns.find(btn => {
                        const hasNext = (btn.innerText || '').toLowerCase().includes('next');
                        const hasChevron = btn.querySelector('svg[id*="chevron-right"]');
                        const isVisible = btn.offsetParent !== null && !btn.disabled;
                        return hasNext && hasChevron && isVisible;
                    });
                    if (nextChevronBtn) {
                        console.log('Found Next button via chevron match, clicking...');
                        nextChevronBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        nextChevronBtn.click();
                        return 'LINKEDIN_SCROLLED: No jobs found — NEXT_PAGE_CLICKED';
                    }
                    
                    // No pagination found — might be last page
                    console.log('No pagination button found — possibly last page. Scrolling sidebar as fallback...');
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
                    // Hybrid selector: real DOM is div.ss-snackbar.ss-snackbar-error.ss-snackbar-active
                    // (no -body suffix). Keep legacy + attribute fallbacks.
                    const snackbarBody = document.querySelector(
                        '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                        + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                    );
                    if (snackbarBody) {
                        const snackText = snackbarBody.innerText.toLowerCase();
                        if (snackText.includes('error processing') || snackText.includes('some error')
                            || snackText.includes('error') || snackText.includes('processing')
                            || snackText.includes('limit') || snackText.includes('reached')
                            || snackText.includes('something went wrong')) {
                            const closeBtn = document.querySelector('button.ss-close, .ss-close');
                            if (closeBtn) closeBtn.click();
                            return 'NAUKRI_RATE_LIMITED: Error popup detected during fallback start';
                        }
                    }
                    // Generic fallback (Option C)
                    const genericSnackFallback = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                    if (genericSnackFallback && genericSnackFallback.offsetParent !== null) {
                        const gText = (genericSnackFallback.innerText || '').toLowerCase();
                        if (gText.includes('error') || gText.includes('processing') || gText.includes('some error')) {
                            return 'NAUKRI_RATE_LIMITED: Generic error detected during fallback start';
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
                                sessionStorage.removeItem('naukri_tab_idx');
                                sessionStorage.removeItem('naukri_cycled_once');
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
                        
                        // Only select from a section when it has at least TARGET_JOBS (5) jobs.
                        // If fewer, move to the next section. After cycling all tabs once
                        // with no section reaching 5, fall back to applying to whatever is
                        // available (best-available) rather than applying to nothing.
                        const cycledOnce = sessionStorage.getItem('naukri_cycled_once') === '1';
                        
                        if (uncheckedBoxes.length < TARGET_JOBS && !cycledOnce) {
                            // Section has fewer than 5 jobs — navigate to next tab
                            // Tab cycle: Applies -> Preferences -> You might like -> Profile -> Top Candidate
                            const tabOrder = ['apply', 'preference', 'similar_jobs', 'profile', 'top_candidate'];
                            
                            // Use sessionStorage tracker to follow the fixed cycle order
                            let nextIdx = parseInt(sessionStorage.getItem('naukri_tab_idx') || '-1');
                            nextIdx = (nextIdx + 1) % tabOrder.length;
                            sessionStorage.setItem('naukri_tab_idx', nextIdx);
                            
                            // If we've cycled all the way back to index 0, we've checked all
                            // tabs once. Set the cycled-once flag so the next <5 section falls
                            // through to best-available instead of navigating forever.
                            if (nextIdx === 0) {
                                sessionStorage.setItem('naukri_cycled_once', '1');
                            }
                            
                            const nextTabId = tabOrder[nextIdx];
                            console.log('NAUKRI DEBUG: Cycle step', nextIdx, '- navigating to:', nextTabId, '(section had', uncheckedBoxes.length, 'jobs <', TARGET_JOBS + ')');
                            
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
                                return 'NAUKRI_NAVIGATING_TO_TAB (' + uncheckedBoxes.length + ' jobs < ' + TARGET_JOBS + '): ' + nextTabId;
                            } else {
                                console.log('NAUKRI DEBUG: Could not find tab element for:', nextTabId);
                                return 'NAUKRI_NO_JOBS_LEFT: All tabs exhausted';
                            }
                        }
                        
                        // Apply to jobs in this section. We only reach here when:
                        // - uncheckedBoxes.length >= TARGET_JOBS (normal: 5+ jobs), OR
                        // - cycledOnce is true (best-available: apply to whatever is here)
                        // The remaining counter caps selection at what we still need.
                        
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
                                // Hybrid selector: real DOM is div.ss-snackbar.ss-snackbar-error.ss-snackbar-active
                                const snackBody = document.querySelector(
                                    '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                                    + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                                );
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong') || text.includes('processing') || text.includes('some error')) {
                                        const closeBtn = document.querySelector('button.ss-close, .ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                                if (genericSnack && genericSnack.offsetParent !== null
                                    && (genericSnack.innerText.toLowerCase().includes('error')
                                        || genericSnack.innerText.toLowerCase().includes('processing'))) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + clickedCount + ' jobs selected';
                        }
                        
                        // Check if there are already some checked.
                        // Only submit already-checked jobs when there are at least TARGET_JOBS,
                        // OR when in best-available mode (cycledOnce) — submit whatever is checked.
                        const alreadyChecked = document.querySelectorAll('i.naukicon-ot-Checked, .tuple-check-box i.checked, input[type="checkbox"]:checked').length;
                        if (alreadyChecked >= TARGET_JOBS || (cycledOnce && alreadyChecked > 0)) {
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
                                // Hybrid selector: real DOM is div.ss-snackbar.ss-snackbar-error.ss-snackbar-active
                                const snackBody = document.querySelector(
                                    '.ss-snackbar-error, .ss-snackbar.ss-snackbar-active, .ss-snackbar-body, '
                                    + '[class*="ss-snackbar"][class*="error"], div.ss-snackbar[role="alert"]'
                                );
                                if (snackBody && snackBody.offsetParent !== null) {
                                    const text = snackBody.innerText.toLowerCase();
                                    if (text.includes('error') || text.includes('limit') || text.includes('reached') || text.includes('something went wrong') || text.includes('processing') || text.includes('some error')) {
                                        const closeBtn = document.querySelector('button.ss-close, .ss-close');
                                        if (closeBtn) closeBtn.click();
                                        return 'NAUKRI_RATE_LIMITED: Error snackbar detected (' + text + ')';
                                    }
                                }
                                // Generic fallback
                                const genericSnack = document.querySelector('[class*="snackbar"], [class*="toast"], [role="alert"]');
                                if (genericSnack && genericSnack.offsetParent !== null
                                    && (genericSnack.innerText.toLowerCase().includes('error')
                                        || genericSnack.innerText.toLowerCase().includes('processing'))) {
                                    return 'NAUKRI_RATE_LIMITED: Generic error detected';
                                }
                            }
                            
                            return 'NAUKRI_APPLY_CLICKED: ' + alreadyChecked + ' jobs already selected';
                        }
                        
                        // No selectable jobs in current section - navigate to next tab in order
                        // Tab cycle: Applies -> Preferences -> You might like -> Profile -> Top Candidate
                        const tabOrder = ['apply', 'preference', 'similar_jobs', 'profile', 'top_candidate'];
                        
                        // Use sessionStorage tracker to follow the fixed cycle order
                        let nextIdx = parseInt(sessionStorage.getItem('naukri_tab_idx') || '-1');
                        nextIdx = (nextIdx + 1) % tabOrder.length;
                        sessionStorage.setItem('naukri_tab_idx', nextIdx);
                        
                        // If we've cycled all the way back to index 0:
                        // - In best-available mode (cycledOnce), this is true exhaustion.
                        // - Otherwise, set the flag and keep navigating.
                        if (nextIdx === 0) {
                            if (cycledOnce) {
                                return 'NAUKRI_NO_CHECKBOX_IN_SECTION: All tabs exhausted';
                            }
                            sessionStorage.setItem('naukri_cycled_once', '1');
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
                                sessionStorage.setItem('instahyre_results_clicked', Date.now().toString());
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
                    
                    // Grace period: if we recently clicked "Show Results", wait for jobs to load
                    // before declaring no more jobs (prevents race condition with slow rendering)
                    const resultsClickedAt = sessionStorage.getItem('instahyre_results_clicked');
                    const inResultsGracePeriod = resultsClickedAt && (Date.now() - parseInt(resultsClickedAt) < 15000);
                    
                    if (!inResultsGracePeriod && noJobsIndicators.some(Boolean)) {
                        sessionStorage.removeItem('instahyre_results_clicked');
                        return 'INSTAHYRE_NO_MORE_JOBS';
                    }
                    if (inResultsGracePeriod && noJobsIndicators.some(Boolean)) {
                        return 'INSTAHYRE_WAITING_FOR_RESULTS';
                    }
                    
                    // D2. Check if results page has zero actual job cards (not generic .card elements)
                    const jobCards = document.querySelectorAll('.job-card, [class*="opportunity-card"], [class*="job-listing"], .opportunity-card');
                    const viewBtnsExist = document.querySelectorAll('button#interested-btn, button.button-interested').length > 0;
                    if (jobCards.length === 0 && !viewBtnsExist) {
                        if (inResultsGracePeriod) {
                            return 'INSTAHYRE_WAITING_FOR_RESULTS';
                        }
                        // On the results page but no job cards at all — no jobs match
                        sessionStorage.removeItem('instahyre_results_clicked');
                        return 'INSTAHYRE_NO_MORE_JOBS';
                    }
                    // Results loaded successfully — clear the grace period timestamp
                    if (jobCards.length > 0 || viewBtnsExist) {
                        sessionStorage.removeItem('instahyre_results_clicked');
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


