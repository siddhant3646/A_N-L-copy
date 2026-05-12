"""
Question Fingerprint Module - Normalizes questions for better matching.

This module provides:
1. Question fingerprinting - Normalize similar questions to same fingerprint
2. Success rate tracking - Track which patterns work/fail
3. Validation rules - Ensure answers match expected formats
"""

import re
import hashlib
import json
import os
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
from dataclasses import dataclass, asdict


# Common words to remove during normalization
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here',
    'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more',
    'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or',
    'because', 'until', 'while', 'what', 'which', 'who', 'whom', 'this',
    'that', 'these', 'those', 'am', 'it', 'its', 'your', 'yours', 'we',
    'our', 'ours', 'they', 'them', 'their', 'theirs', 'my', 'mine', 'me',
    'you', 'he', 'him', 'his', 'she', 'her', 'hers', 'please', 'enter',
    'mention', 'provide', 'share', 'tell', 'us', 'give', 'select', 'choose',
    'pick', 'indicate', 'specify', 'state', 'write', 'type', 'put', 'add'
}

# Synonym mappings for question normalization
SYNONYM_MAP = {
    # Experience
    'exp': 'experience',
    'exp.': 'experience',
    'ex': 'experience',
    'yr': 'year',
    'yrs': 'years',
    'yoe': 'years of experience',
    'tenure': 'experience',
    'worked': 'experience',
    'working': 'experience',
    'career': 'experience',
    'background': 'experience',
    
    # Salary
    'ctc': 'salary',
    'pay': 'salary',
    'compensation': 'salary',
    'package': 'salary',
    'remuneration': 'salary',
    'income': 'salary',
    'stipend': 'salary',
    'wage': 'salary',
    'cctc': 'current salary',
    'ectc': 'expected salary',
    'lpa': 'lakhs per annum',
    
    # Location
    'loc': 'location',
    'city': 'location',
    'place': 'location',
    'based': 'location',
    'reside': 'location',
    'live': 'location',
    'stay': 'location',
    'hometown': 'location',
    'native': 'location',
    'relocate': 'relocation',
    'moving': 'relocation',
    'shift': 'relocation',
    
    # Skills
    'skill': 'skills',
    'tech': 'technology',
    'stack': 'technology',
    'techstack': 'technology',
    'proficiency': 'skill level',
    'expertise': 'skill level',
    'competency': 'skill level',
    'competencies': 'skills',
    'knowledge': 'skills',
    'know': 'skills',
    'technologies': 'skills',
    'tools': 'skills',
    
    # Notice Period
    'np': 'notice period',
    'notice': 'notice period',
    'lwd': 'last working day',
    'joining': 'join date',
    'available': 'availability',
    'serve': 'notice period',
    'serving': 'notice period',
    
    # Contact
    'phone': 'mobile',
    'cell': 'mobile',
    'contact': 'mobile',
    'tel': 'mobile',
    'telephone': 'mobile',
    'mail': 'email',
    'id': 'email',
    
    # Company
    'employer': 'company',
    'org': 'company',
    'organization': 'company',
    'firm': 'company',
    'current': 'present company',
    'previous': 'past company',
    'last': 'past company',
    
    # Education
    'edu': 'education',
    'qualification': 'education',
    'qualifications': 'education',
    'degree': 'education',
    'grad': 'graduation',
    'college': 'university',
    'school': 'university',
    'institute': 'university',
    'cgpa': 'gpa',
    'percentage': 'marks',
    'percent': 'marks',
    
    # Interview
    'interview': 'interview availability',
    'assessment': 'test availability',
    'test': 'test availability',
    'slot': 'time slot',
    'timing': 'time slot',
    
    # Yes/No
    'willing': 'agree',
    'comfortable': 'agree',
    'ready': 'agree',
    'interested': 'agree',
    'ok': 'agree',
    'okay': 'agree',
    'fine': 'agree',
    'accept': 'agree',
    'authorize': 'agree',
    'permit': 'agree',
    'allow': 'agree',
    'eligible': 'qualify',
    
    # ========== PHASE 3: EXTENDED SYNONYMS FOR ROBUSTNESS ==========
    
    # Joining/Availability - Extended
    'join': 'join date',
    'start': 'join date',
    'begin': 'join date',
    'commence': 'join date',
    'available': 'availability',
    'availability': 'join date',
    'earliest': 'join date',
    'soon': 'join date',
    'immediate': 'immediate joining',
    'asap': 'immediate joining',
    'urgent': 'immediate joining',
    'relieving': 'last working day',
    'relieve': 'last working day',
    
    # Salary Components - Extended
    'monthly': 'per month',
    'annual': 'per year',
    'yearly': 'per year',
    'gross': 'total before deductions',
    'net': 'take home',
    'takehome': 'take home',
    'inhand': 'take home',
    'fixed': 'fixed component',
    'variable': 'variable component',
    'bonus': 'variable component',
    'esop': 'stock options',
    'equity': 'stock options',
    'stocks': 'stock options',
    'shares': 'stock options',
    'benefits': 'perks',
    'perks': 'benefits',
    'allowance': 'benefits',
    'drawn': 'current salary',
    'drawing': 'current salary',
    
    # Experience Types - Extended
    'relevant': 'related',
    'total': 'overall',
    'overall': 'total',
    'professional': 'work',
    'industry': 'sector',
    'corporate': 'work',
    'it': 'information technology',
    'hands': 'hands on',
    'handson': 'practical',
    'practical': 'hands on',
    'exposure': 'familiarity',
    'familiar': 'familiarity',
    'competent': 'competency',
    'expert': 'expertise',
    'span': 'duration',
    'history': 'background',
    'domain': 'field',
    'sector': 'industry',
    
    # Address/Location Types - Extended
    'current': 'present',
    'present': 'current',
    'permanent': 'home',
    'home': 'permanent',
    'residential': 'home',
    'residence': 'home',
    'native': 'hometown',
    'hometown': 'native',
    'onsite': 'on site',
    'offshore': 'off shore',
    'client': 'client location',
    'travel': 'willing to travel',
    'travelling': 'willing to travel',
    'commute': 'willing to travel',
    
    # Education - Extended
    'academic': 'education',
    'studied': 'education',
    'institution': 'university',
    'completion': 'graduation',
    'complete': 'graduation',
    'graduated': 'graduation',
    'postgrad': 'post graduation',
    'pg': 'post graduation',
    'masters': 'post graduation',
    'bachelors': 'undergraduate',
    'undergrad': 'undergraduate',
    'certified': 'certification',
    'certificate': 'certification',
    'trained': 'training',
    
    # Skills - Extended
    'primary': 'main',
    'secondary': 'additional',
    'core': 'main',
    'key': 'main',
    'area': 'field',
    'specialized': 'specialization',
    'framework': 'technology',
    'library': 'technology',
    'database': 'db',
    'storage': 'db',
    'methodology': 'method',
    'agile': 'methodology',
    'scrum': 'methodology',
    'version': 'version control',
    'review': 'code review',
    
    # Proficiency/Rating - Extended
    'rate': 'rating',
    'rating': 'proficiency',
    'self': 'self assessment',
    'level': 'proficiency level',
    'mastery': 'expertise',
    'comfort': 'comfort level',
    'scale': 'rating scale',
    
    # Personal Info - Extended
    'fullname': 'full name',
    'firstname': 'first name',
    'lastname': 'last name',
    'middlename': 'middle name',
    'emergency': 'emergency contact',
    'alternate': 'alternative',
    'alternative': 'alternate',
    'nationality': 'citizenship',
    'citizen': 'citizenship',
    'country': 'nationality',
    'visa': 'work permit',
    'permit': 'work permit',
    'marital': 'marriage status',
    'language': 'languages',
    'speak': 'languages',
    
    # Company - Extended
    'work': 'employer',
    'works': 'employer',
    'working': 'employer',
    'report': 'reporting',
    'reports': 'reporting',
    'reporting': 'manager',
    'hr': 'human resources',
    'supervisor': 'manager',
    'dept': 'department',
    'division': 'department',
    'unit': 'department',
    'vertical': 'department',
    
    # Interview - Extended
    'free': 'available',
    'convenient': 'suitable',
    'suitable': 'preferred',
    'book': 'schedule',
    'fix': 'schedule',
    'appointment': 'schedule',
    'mode': 'format',
    'format': 'mode',
    'round': 'stage',
    'stage': 'round',
    'panel': 'group',
    'group': 'panel',
    'assignment': 'task',
    'task': 'assignment',
    
    # Job Change - Extended
    'leaving': 'reason for change',
    'change': 'job change',
    'switching': 'job change',
    'motivation': 'reason',
    'goal': 'objective',
    'aspiration': 'career goal',
    'objective': 'career goal',
    'plan': 'career plan',
    
    # Referral - Extended
    'hear': 'source',
    'heard': 'source',
    'learn': 'source',
    'learned': 'source',
    'find': 'source',
    'found': 'source',
    'refer': 'referral',
    'reference': 'referral',
    'recommend': 'referral',
    'recommended': 'referral',
    'suggest': 'referral',
    'suggested': 'referral',
    'portal': 'job portal',
    'consultant': 'recruiter',
    'agency': 'recruiter',
    'vendor': 'recruiter',
    
    # Diversity - Extended
    'accommodation': 'special needs',
    'needs': 'special needs',
    'gender': 'sex',
    'sex': 'gender',
    'identity': 'self identify',
    'ethnic': 'ethnicity',
    'race': 'ethnicity',
    'minority': 'protected class',
    'military': 'armed forces',
    'service': 'military service',
    'reserve': 'military',
    'guard': 'military',
    
    # Contract - Extended
    'duration': 'period',
    'length': 'period',
    'engagement': 'contract',
    'assignment': 'project',
    'timeframe': 'time frame',
    'ctype': 'contract type',
    'employment': 'job type',
    'fulltime': 'full time',
    'parttime': 'part time',
    'freelance': 'independent',
    'consulting': 'consultant',
    'temporary': 'temp',
    'temp': 'temporary',
    'permanent': 'permanent role',
    'direct': 'direct hire',
    'payroll': 'payroll type',
    
    # Availability - Extended
    'flexible': 'flexibility',
    'flexibility': 'flexible',
    'weekdays': 'working days',
    'weekends': 'weekend availability',
    'calendar': 'schedule',
    'earliest': 'earliest date',
    'immediately': 'immediate joining',
    
    # Negotiation
    'negotiate': 'negotiable',
    'negotiable': 'open to discussion',
    'discussion': 'negotiable',
    'expectation': 'expected',
    'expectations': 'expected',
    'range': 'salary range',
    'flexible': 'negotiable',
    
    # Miscellaneous
    'relocate': 'relocation',
    'relocation': 'willing to relocate',
    'travel': 'willing to travel',
    'ready': 'prepared',
    'comfortable': 'okay',
    'fine': 'okay',
    'accept': 'agree',
    'willingness': 'willing',
}


def normalize_word(word: str) -> str:
    """Normalize a single word using synonym map."""
    word_lower = word.lower().strip()
    return SYNONYM_MAP.get(word_lower, word_lower)


def create_fingerprint(question: str) -> str:
    """
    Create a normalized fingerprint for a question.
    
    This allows similar questions to match:
    - "Years of experience" → "year experience"
    - "Total experience" → "total experience"  
    - "How many years have you worked" → "year work"
    
    Args:
        question: The question text
        
    Returns:
        Normalized fingerprint string
    """
    if not question:
        return ""
    
    # Convert to lowercase
    text = question.lower()
    
    # Remove punctuation except apostrophes (for contractions)
    text = re.sub(r"[^\w\s']", ' ', text)
    
    # Split into words
    words = text.split()
    
    # Normalize each word (synonym replacement)
    normalized_words = [normalize_word(word) for word in words]
    
    # Remove stop words
    filtered_words = [w for w in normalized_words if w not in STOP_WORDS and len(w) > 1]
    
    # Sort alphabetically for consistency
    filtered_words.sort()
    
    # Join to create fingerprint
    fingerprint = ' '.join(filtered_words)
    
    return fingerprint


def create_fingerprint_hash(question: str) -> str:
    """Create a hash of the fingerprint for fast lookup."""
    fingerprint = create_fingerprint(question)
    return hashlib.md5(fingerprint.encode()).hexdigest()[:16]


@dataclass
class PatternStats:
    """Statistics for a question pattern."""
    pattern: str
    fingerprint: str
    answer: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    last_used: Optional[str] = None
    avg_confidence: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts
    
    def record_attempt(self, success: bool, confidence: float = 0.0):
        """Record an attempt."""
        self.attempts += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
        
        # Update average confidence
        self.avg_confidence = ((self.avg_confidence * (self.attempts - 1)) + confidence) / self.attempts
        self.last_used = datetime.now().isoformat()


class SuccessTracker:
    """Tracks success rates of question patterns."""
    
    def __init__(self, storage_path: str = None):
        """
        Initialize the tracker.
        
        Args:
            storage_path: Path to store stats JSON file
        """
        if storage_path is None:
            storage_path = os.path.expanduser("~/Desktop/sentinel_errors/pattern_stats.json")
        self.storage_path = storage_path
        self.stats: Dict[str, PatternStats] = {}
        self.fingerprint_index: Dict[str, List[str]] = {}  # fingerprint -> pattern keys
        self._load()
    
    def _load(self):
        """Load stats from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        self.stats[key] = PatternStats(**value)
                        # Build fingerprint index
                        fp = value.get('fingerprint', '')
                        if fp:
                            if fp not in self.fingerprint_index:
                                self.fingerprint_index[fp] = []
                            self.fingerprint_index[fp].append(key)
            except Exception as e:
                print(f"⚠️ Failed to load pattern stats: {e}")
    
    def _save(self):
        """Save stats to disk."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = {k: asdict(v) for k, v in self.stats.items()}
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save pattern stats: {e}")
    
    def record_attempt(self, question: str, answer: str, success: bool, confidence: float = 0.0):
        """
        Record a pattern usage attempt.
        
        Args:
            question: The question text
            answer: The answer provided
            success: Whether the answer was accepted
            confidence: Match confidence score
        """
        fingerprint = create_fingerprint(question)
        key = f"{fingerprint}:{answer}"
        
        if key not in self.stats:
            self.stats[key] = PatternStats(
                pattern=question,
                fingerprint=fingerprint,
                answer=answer
            )
            # Update fingerprint index
            if fingerprint not in self.fingerprint_index:
                self.fingerprint_index[fingerprint] = []
            self.fingerprint_index[fingerprint].append(key)
        
        self.stats[key].record_attempt(success, confidence)
        self._save()
    
    def get_stats(self, question: str, answer: str) -> Optional[PatternStats]:
        """Get stats for a specific question/answer pair."""
        fingerprint = create_fingerprint(question)
        key = f"{fingerprint}:{answer}"
        return self.stats.get(key)
    
    def get_success_rate(self, question: str, answer: str) -> float:
        """Get success rate for a question/answer pair."""
        stats = self.get_stats(question, answer)
        return stats.success_rate if stats else 0.0
    
    def get_low_success_patterns(self, threshold: float = 0.7) -> List[PatternStats]:
        """Get patterns with success rate below threshold."""
        return [s for s in self.stats.values() if s.success_rate < threshold and s.attempts >= 3]
    
    def find_similar_questions(self, question: str) -> List[Tuple[str, float]]:
        """
        Find questions with similar fingerprints.
        
        Returns:
            List of (question, success_rate) tuples
        """
        fingerprint = create_fingerprint(question)
        results = []
        
        # Check exact fingerprint matches
        if fingerprint in self.fingerprint_index:
            for key in self.fingerprint_index[fingerprint]:
                stats = self.stats[key]
                results.append((stats.pattern, stats.success_rate))
        
        # Check for partial matches (words in common)
        fp_words = set(fingerprint.split())
        for stats in self.stats.values():
            other_words = set(stats.fingerprint.split())
            common = fp_words & other_words
            if len(common) >= min(2, len(fp_words)):
                results.append((stats.pattern, stats.success_rate))
        
        # Sort by success rate
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:5]  # Top 5
    
    def get_stats_summary(self) -> Dict:
        """Get summary statistics."""
        if not self.stats:
            return {"total_patterns": 0}
        
        total_attempts = sum(s.attempts for s in self.stats.values())
        total_successes = sum(s.successes for s in self.stats.values())
        
        return {
            "total_patterns": len(self.stats),
            "total_attempts": total_attempts,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_attempts if total_attempts > 0 else 0,
            "low_success_patterns": len(self.get_low_success_patterns(0.7)),
            "top_patterns": sorted(
                [(s.pattern, s.success_rate, s.attempts) for s in self.stats.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


# Validation rules for different answer types
VALIDATION_RULES = {
    'phone': {
        'patterns': [
            r'^\d{10}$',  # 10 digits
            r'^\+\d{12}$',  # + country code
            r'^\d{3}-\d{3}-\d{4}$',  # US format
            r'^\(\d{3}\)\s?\d{3}-\d{4}$',  # (XXX) XXX-XXXX
        ],
        'message': 'Phone number should be 10 digits'
    },
    'email': {
        'patterns': [
            r'^[\w\.-]+@[\w\.-]+\.\w+$',
        ],
        'message': 'Invalid email format'
    },
    'numeric': {
        'patterns': [
            r'^\d+$',  # Integer
            r'^\d+\.\d+$',  # Decimal
        ],
        'message': 'Should be a number'
    },
    'year': {
        'patterns': [
            r'^19\d{2}$',  # 1900s
            r'^20\d{2}$',  # 2000s
        ],
        'message': 'Should be a valid year (1900-2099)'
    },
    'percentage': {
        'patterns': [
            r'^\d{1,2}$',  # 0-99
            r'^100$',  # 100
            r'^\d{1,2}\.\d+$',  # Decimal
        ],
        'message': 'Should be 0-100'
    },
    'cgpa': {
        'patterns': [
            r'^\d(\.\d+)?$',  # 0-9 with optional decimal
            r'^10(\.0)?$',  # 10
        ],
        'message': 'CGPA should be 0-10'
    },
    'salary_lpa': {
        'patterns': [
            r'^\d+(\.\d+)?$',  # Numeric
        ],
        'range': (0, 100),
        'message': 'Salary should be numeric (in LPA)'
    },
    'date': {
        'patterns': [
            r'^\d{2}/\d{2}/\d{4}$',  # DD/MM/YYYY or MM/DD/YYYY
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{1,2}\s+[A-Za-z]+\s+\d{4}$',  # 1 January 2024
        ],
        'message': 'Invalid date format'
    },
    'yes_no': {
        'valid_values': ['yes', 'no', 'true', 'false', 'agree', 'decline'],
        'message': 'Should be Yes or No'
    }
}


def detect_expected_format(question: str) -> Optional[str]:
    """
    Detect expected answer format from question.
    
    Args:
        question: The question text
        
    Returns:
        Format type key or None
    """
    q_lower = question.lower()
    
    # Phone/Mobile
    if any(x in q_lower for x in ['phone', 'mobile', 'contact number', 'cell']):
        return 'phone'
    
    # Email
    if any(x in q_lower for x in ['email', 'mail id', 'e-mail']):
        return 'email'
    
    # Year (graduation, etc.)
    if any(x in q_lower for x in ['graduation year', 'year of passing', 'passed out', 'batch']):
        return 'year'
    
    # Percentage/CGPA
    if any(x in q_lower for x in ['percentage', 'percent', '%']):
        return 'percentage'
    if any(x in q_lower for x in ['cgpa', 'gpa', 'grade']):
        return 'cgpa'
    
    # Salary
    if any(x in q_lower for x in ['ctc', 'salary']):
        if any(x in q_lower for x in ['lakhs', 'lpa', 'lakh']):
            return 'salary_lpa'
        return 'numeric'
    
    # Date
    if any(x in q_lower for x in ['date', 'when', 'dob', 'birth']):
        return 'date'
    
    # Experience (numeric)
    if any(x in q_lower for x in ['years', 'experience', 'how many']):
        if 'year' in q_lower or 'month' in q_lower:
            return 'numeric'
    
    # Yes/No
    if any(x in q_lower for x in ['willing', 'comfortable', 'agree', 'accept', 'serving']):
        return 'yes_no'
    
    # Default to text
    return None


def validate_answer(answer: str, format_type: str) -> Tuple[bool, str]:
    """
    Validate an answer against expected format.
    
    Args:
        answer: The answer to validate
        format_type: Format type from VALIDATION_RULES
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not answer or not format_type:
        return True, ""  # No validation possible
    
    rules = VALIDATION_RULES.get(format_type)
    if not rules:
        return True, ""  # Unknown format type
    
    answer_clean = answer.strip().lower()
    
    # Check valid_values list
    if 'valid_values' in rules:
        if answer_clean not in rules['valid_values']:
            return False, rules['message']
        return True, ""
    
    # Check regex patterns
    if 'patterns' in rules:
        for pattern in rules['patterns']:
            if re.match(pattern, answer.strip()):
                # Check range if specified
                if 'range' in rules:
                    try:
                        value = float(answer.strip())
                        min_val, max_val = rules['range']
                        if not (min_val <= value <= max_val):
                            return False, f"Value should be between {min_val} and {max_val}"
                    except ValueError:
                        return False, rules['message']
                return True, ""
        return False, rules['message']
    
    return True, ""


class FingerprintMatcher:
    """Matches questions using fingerprints."""
    
    def __init__(self):
        """Initialize with empty fingerprint cache."""
        self.fingerprint_cache: Dict[str, str] = {}  # fingerprint -> answer
        self.question_index: Dict[str, str] = {}  # question -> fingerprint
    
    def add_pattern(self, question: str, answer: str):
        """Add a question-answer pattern."""
        fingerprint = create_fingerprint(question)
        self.fingerprint_cache[fingerprint] = answer
        self.question_index[question.lower()] = fingerprint
    
    def match(self, question: str) -> Optional[Tuple[str, float]]:
        """
        Match a question to an answer.
        
        Returns:
            Tuple of (answer, confidence) or None
        """
        fingerprint = create_fingerprint(question)
        
        # Exact fingerprint match
        if fingerprint in self.fingerprint_cache:
            return (self.fingerprint_cache[fingerprint], 1.0)
        
        # Partial fingerprint match
        fp_words = set(fingerprint.split())
        best_match = None
        best_score = 0.0
        
        for cached_fp, answer in self.fingerprint_cache.items():
            cached_words = set(cached_fp.split())
            common_words = fp_words & cached_words
            
            if len(common_words) > 0:
                # Score based on word overlap
                score = len(common_words) / max(len(fp_words), len(cached_words))
                if score > best_score and score >= 0.5:  # At least 50% match
                    best_score = score
                    best_match = answer
        
        if best_match:
            return (best_match, best_score)
        
        return None
    
    def build_from_patterns(self, patterns: Dict):
        """
        Build fingerprint cache from existing patterns.
        
        Supports both formats:
        1. Flat dict: {question: answer}
        2. JSON structure: {pattern_id: {patterns: [], category: "", default: ""}}
        """
        # Check if this is the JSON structure with nested patterns
        if patterns and isinstance(next(iter(patterns.values())), dict):
            # JSON structure format
            for pattern_id, pattern_data in patterns.items():
                answer = pattern_data.get('default', '')
                for question in pattern_data.get('patterns', []):
                    self.add_pattern(question, answer)
        else:
            # Flat dict format {question: answer}
            for question, answer in patterns.items():
                self.add_pattern(question, answer)


# Convenience functions
def normalize_question(question: str) -> str:
    """Normalize a question for display/logging."""
    return create_fingerprint(question)


def are_questions_similar(q1: str, q2: str, threshold: float = 0.7) -> bool:
    """Check if two questions are similar."""
    fp1 = set(create_fingerprint(q1).split())
    fp2 = set(create_fingerprint(q2).split())
    
    if not fp1 or not fp2:
        return False
    
    common = fp1 & fp2
    similarity = len(common) / max(len(fp1), len(fp2))
    
    return similarity >= threshold
