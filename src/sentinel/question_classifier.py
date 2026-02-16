"""
Question Classifier Module - Smart categorization and platform-specific answer generation.

This module provides:
1. Question categorization using keyword and regex patterns
2. Platform-specific defaults (Naukri vs LinkedIn experience values)
3. Smart fallback answers for unknown questions
4. Input type detection (text, radio, checkbox, select)
"""

import re
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class QuestionCategory(Enum):
    """Categories of job application questions."""
    SALARY = "salary"
    EXPERIENCE = "experience"
    NOTICE_PERIOD = "notice_period"
    LOCATION = "location"
    SKILLS = "skills"
    YES_NO = "yes_no"
    PERSONAL_INFO = "personal_info"
    EDUCATION = "education"
    AVAILABILITY = "availability"
    PREFERENCE = "preference"
    UNKNOWN = "unknown"


class InputType(Enum):
    """Types of form inputs."""
    TEXT = "text"
    NUMBER = "number"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    SELECT = "select"
    TEXTAREA = "textarea"
    DATE = "date"
    EMAIL = "email"
    TEL = "tel"


@dataclass
class PlatformConfig:
    """Platform-specific configuration."""
    name: str
    experience_years: str
    experience_months: str
    numeric_only_experience: bool


# Platform-specific defaults
PLATFORM_CONFIGS = {
    "naukri": PlatformConfig(
        name="naukri",
        experience_years="3.8 Years",
        experience_months="46",
        numeric_only_experience=False
    ),
    "linkedin": PlatformConfig(
        name="linkedin",
        experience_years="4",
        experience_months="46",
        numeric_only_experience=True
    ),
    "instahyre": PlatformConfig(
        name="instahyre",
        experience_years="3.8 Years",
        experience_months="46",
        numeric_only_experience=False
    ),
    "default": PlatformConfig(
        name="default",
        experience_years="3.8 Years",
        experience_months="46",
        numeric_only_experience=False
    )
}


# Category detection patterns
CATEGORY_PATTERNS = {
    QuestionCategory.SALARY: {
        "keywords": [
            "ctc", "salary", "compensation", "package", "lpa", "pay",
            "income", "remuneration", "stipend", "wage", "cctc", "ectc"
        ],
        "regex_patterns": [
            r"current\s+ctc",
            r"expected\s+salary",
            r"compensation\s+expect",
            r"ctc\s+in\s+lakhs",
            r"salary\s+expectation",
            r"pay\s+range",
            r"what\s+is\s+your\s+ctc",
            r"mention\s+your\s+ctc"
        ],
        "input_type_hints": ["number", "text"],
        "requires_numeric": True
    },
    QuestionCategory.EXPERIENCE: {
        "keywords": [
            "experience", "years", "exp", "tenure", "worked", "yrs",
            "work\s+experience", "professional\s+experience", "total\s+exp",
            "how\s+long", "duration", "period"
        ],
        "regex_patterns": [
            r"\d+\+?\s*years?\s*of\s*experience",
            r"total\s*exp",
            r"overall\s*experience",
            r"years?\s*of\s*work",
            r"experience\s*in\s*years",
            r"how\s+many\s+years",
            r"work\s+experience"
        ],
        "input_type_hints": ["number", "text"],
        "requires_numeric": True
    },
    QuestionCategory.NOTICE_PERIOD: {
        "keywords": [
            "notice", "serving", "lwd", "last working", "join",
            "joining", "available", "availability", "np", "notice period"
        ],
        "regex_patterns": [
            r"notice\s*period",
            r"last\s*working\s*day",
            r"lwd",
            r"serving\s*notice",
            r"when\s*can\s*you\s*join",
            r"joining\s*date",
            r"availability"
        ],
        "input_type_hints": ["number", "text", "radio", "select"],
        "requires_numeric": False
    },
    QuestionCategory.LOCATION: {
        "keywords": [
            "location", "city", "relocate", "based", "stay", "place",
            "where", "address", "reside", "live", "currently\s*in",
            "currently located", "where are you"
        ],
        "regex_patterns": [
            r"current\s*location",
            r"where\s*are\s*you\s*based",
            r"based\s*in",
            r"located\s*in",
            r"preferred\s*location",
            r"willing\s*to\s*relocate",
            r"current\s*city"
        ],
        "input_type_hints": ["text", "select"],
        "requires_numeric": False
    },
    QuestionCategory.SKILLS: {
        "keywords": [
            "skills", "proficiency", "expertise", "knowledge", "tech\s*stack",
            "technologies", "tools", "programming", "languages", "frameworks",
            "libraries", "competencies", "technologies"
        ],
        "regex_patterns": [
            r"tech\s*stack",
            r"programming\s*languages",
            r"skills\s*do\s*you",
            r"proficiency\s*in",
            r"expertise\s*in",
            r"rate\s*yourself",
            r"rate\s*your\s*proficiency",
            r"how\s*good\s*are\s*you"
        ],
        "input_type_hints": ["text", "select", "radio"],
        "requires_numeric": False
    },
    QuestionCategory.YES_NO: {
        "keywords": [
            "willing", "comfortable", "available", "ready", "interested",
            "agree", "accept", "confirm", "authorized", "eligible",
            "open\\s*to", "fine\\s*with", "okay\\s*with", "do you have", 
            "have all", "educational and professional", "lawfully authorized",
            "consent", "collect", "process", "data", "1825 days"
        ],
        "regex_patterns": [
            r"willing\s*to\s*relocate",
            r"available\s*for",
            r"comfortable\s*with",
            r"ready\s*to",
            r"interested\s*in",
            r"do\s*you\s*have",
            r"have\s*you\s*ever",
            r"are\s*you",
            r"have\s*your\s*all\s*educational",
            r"educational\s*and\s*professional"
        ],
        "input_type_hints": ["radio", "checkbox", "select"],
        "requires_numeric": False
    },
    QuestionCategory.PERSONAL_INFO: {
        "keywords": [
            "phone", "mobile", "email", "dob", "date\s*of\s*birth",
            "pan", "aadhar", "name", "gender", "marital", "nationality"
        ],
        "regex_patterns": [
            r"phone\s*number",
            r"mobile\s*number",
            r"email\s*address",
            r"date\s*of\s*birth",
            r"pan\s*card",
            r"aadhar",
            r"full\s*name",
            r"first\s*name",
            r"last\s*name"
        ],
        "input_type_hints": ["text", "tel", "email", "date"],
        "requires_numeric": False,
        "requires_exact_match": True
    },
    QuestionCategory.EDUCATION: {
        "keywords": [
            "education", "degree", "university", "college", "graduation",
            "cgpa", "percentage", "marks", "qualification", "academic"
        ],
        "regex_patterns": [
            r"highest\s*education",
            r"educational\s*qualification",
            r"graduation\s*year",
            r"cgpa",
            r"percentage",
            r"university",
            r"college\s*name"
        ],
        "input_type_hints": ["text", "select", "number"],
        "requires_numeric": False
    },
    QuestionCategory.AVAILABILITY: {
        "keywords": [
            "interview", "assessment", "schedule", "time", "slot",
            "date", "when", "available\s*on"
        ],
        "regex_patterns": [
            r"available\s*for\s*interview",
            r"interview\s*slot",
            r"assessment\s*date",
            r"when\s*can\s*we",
            r"preferred\s*time",
            r"time\s*slot"
        ],
        "input_type_hints": ["text", "select", "radio"],
        "requires_numeric": False
    },
    QuestionCategory.PREFERENCE: {
        "keywords": [
            "prefer", "choice", "option", "select", "which",
            "role", "position", "domain", "department"
        ],
        "regex_patterns": [
            r"preferred\s*position",
            r"which\s*role",
            r"frontend\s*or\s*backend",
            r"preferred\s*domain"
        ],
        "input_type_hints": ["select", "radio"],
        "requires_numeric": False
    }
}


# Default answers by category
CATEGORY_DEFAULTS = {
    QuestionCategory.SALARY: {
        "current": "13.5 LPA",
        "expected": "20 LPA",
        "numeric": "20"  # For fields requiring just numbers
    },
    QuestionCategory.EXPERIENCE: {
        "years": "3.8 Years",  # Will be overridden by platform config
        "months": "46",
        "numeric": "4"  # Will be overridden by platform config
    },
    QuestionCategory.NOTICE_PERIOD: {
        "period": "30 days",
        "days": "30",
        "serving": "Yes",
        "lwd": None  # Calculated dynamically
    },
    QuestionCategory.LOCATION: {
        "current": "Noida",
        "preferred": "Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune",
        "relocate": "Yes"
    },
    QuestionCategory.SKILLS: {
        "tech_stack": "Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes, PostgreSQL, MongoDB, Kafka, Redis",
        "languages": "Java, Python, JavaScript",
        "proficiency": "8",
        "dsa": "8"
    },
    QuestionCategory.YES_NO: "Yes",
    QuestionCategory.PERSONAL_INFO: {
        "phone": "7905828880",
        "email": "siddhant3646@gmail.com",
        "dob": "17/12/2000",
        "pan": "MTKPS1941P",
        "name": "Siddhant Singh"
    },
    QuestionCategory.EDUCATION: {
        "degree": "B.Tech Computer Science",
        "university": "VIT Bhopal University",
        "year": "2022",
        "cgpa": "8.5"
    },
    QuestionCategory.AVAILABILITY: {
        "interview": "Yes, available for interview",
        "assessment": "Any weekday works - flexible",
        "time": "Flexible with timing"
    },
    QuestionCategory.PREFERENCE: {
        "role": "Backend",
        "domain": "Backend Development",
        "work_mode": "Hybrid"
    }
}


class QuestionClassifier:
    """Classifies questions and provides smart default answers."""
    
    def __init__(self, platform: str = "default"):
        """
        Initialize classifier with platform-specific settings.
        
        Args:
            platform: One of 'naukri', 'linkedin', 'instahyre', or 'default'
        """
        self.platform = platform.lower()
        self.config = PLATFORM_CONFIGS.get(self.platform, PLATFORM_CONFIGS["default"])
    
    def classify(self, question: str) -> Tuple[QuestionCategory, float]:
        """
        Classify a question into a category.
        
        Args:
            question: The question text to classify
            
        Returns:
            Tuple of (category, confidence_score)
        """
        if not question:
            return QuestionCategory.UNKNOWN, 0.0
            
        question_lower = question.lower().strip()
        scores = {}
        
        for category, patterns in CATEGORY_PATTERNS.items():
            score = 0.0
            
            # Check keywords
            keywords = patterns.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in question_lower:
                    score += 0.3  # Keyword match weight
            
            # Check regex patterns
            regex_patterns = patterns.get("regex_patterns", [])
            for pattern in regex_patterns:
                if re.search(pattern, question_lower, re.IGNORECASE):
                    score += 0.5  # Regex match weight
            
            # Bonus for exact phrase matches
            for keyword in keywords:
                if keyword.lower() == question_lower:
                    score += 0.2
            
            scores[category] = min(score, 1.0)  # Cap at 1.0
        
        # Get best matching category
        if scores:
            best_category = max(scores, key=scores.get)
            best_score = scores[best_category]
            
            if best_score >= 0.3:  # Minimum threshold
                return best_category, best_score
        
        return QuestionCategory.UNKNOWN, 0.0
    
    def get_answer(
        self, 
        question: str, 
        category: Optional[QuestionCategory] = None,
        input_type: Optional[InputType] = None
    ) -> Tuple[str, float]:
        """
        Get a smart default answer for a question.
        
        Args:
            question: The question text
            category: Optional pre-determined category
            input_type: Type of input field (affects answer format)
            
        Returns:
            Tuple of (answer, confidence)
        """
        if category is None:
            category, cat_confidence = self.classify(question)
        else:
            cat_confidence = 0.9
        
        if category == QuestionCategory.UNKNOWN:
            return "", 0.0
        
        question_lower = question.lower()
        defaults = CATEGORY_DEFAULTS.get(category, "")
        
        # Handle EXPERIENCE with platform-specific values
        if category == QuestionCategory.EXPERIENCE:
            return self._get_experience_answer(question_lower, input_type), cat_confidence
        
        # Handle SALARY
        if category == QuestionCategory.SALARY:
            return self._get_salary_answer(question_lower, input_type), cat_confidence
        
        # Handle NOTICE PERIOD
        if category == QuestionCategory.NOTICE_PERIOD:
            return self._get_notice_answer(question_lower, input_type), cat_confidence
        
        # Handle LOCATION
        if category == QuestionCategory.LOCATION:
            return self._get_location_answer(question_lower), cat_confidence
        
        # Handle SKILLS
        if category == QuestionCategory.SKILLS:
            return self._get_skills_answer(question_lower), cat_confidence
        
        # Handle YES_NO
        if category == QuestionCategory.YES_NO:
            return self._get_yes_no_answer(question_lower), cat_confidence
        
        # Handle PERSONAL_INFO
        if category == QuestionCategory.PERSONAL_INFO:
            return self._get_personal_info_answer(question_lower), cat_confidence
        
        # Handle PREFERENCE
        if category == QuestionCategory.PREFERENCE:
            return self._get_preference_answer(question_lower), cat_confidence
        
        # Default for other categories
        if isinstance(defaults, dict):
            return list(defaults.values())[0], cat_confidence
        return defaults, cat_confidence
    
    def _get_experience_answer(self, question: str, input_type: Optional[InputType]) -> str:
        """Get platform-appropriate experience answer."""
        is_numeric_field = (
            input_type == InputType.NUMBER or
            "number" in question or
            "whole number" in question or
            "enter a number" in question or
            "how many" in question or
            self.config.numeric_only_experience
        )
        
        if "month" in question:
            return self.config.experience_months
        elif is_numeric_field or "years" not in question:
            return self.config.experience_years.split()[0] if " " in self.config.experience_years else self.config.experience_years
        else:
            return self.config.experience_years
    
    def _get_salary_answer(self, question: str, input_type: Optional[InputType]) -> str:
        """Get appropriate salary answer."""
        is_numeric = (
            input_type == InputType.NUMBER or
            "in lakhs" in question or
            "lpa" in question or
            "number" in question
        )
        
        # For LinkedIn, we need to return full numeric value (1350000 or 2000000) instead of lakhs
        if self.platform == "linkedin":
            if "current" in question or "cctc" in question:
                return "1350000"  # 13.5 LPA as numeric
            elif "expected" in question or "ectc" in question:
                return "2000000"  # 20 LPA as numeric
            else:
                return "2000000"
        else:
            if "current" in question or "cctc" in question:
                return "13.5" if is_numeric else "13.5 LPA"
            elif "expected" in question or "ectc" in question:
                return "20" if is_numeric else "20 LPA"
            else:
                return "20" if is_numeric else "20 LPA"
    
    def _get_notice_answer(self, question: str, input_type: Optional[InputType]) -> str:
        """Get notice period answer."""
        if "lwd" in question or "last working" in question:
            from datetime import datetime, timedelta
            lwd = datetime.now() + timedelta(days=30)
            return lwd.strftime('%d %B %Y')
        elif "serving" in question:
            return "Yes"
        elif "days" in question or input_type == InputType.NUMBER:
            return "30"
        else:
            return "30 days"
    
    def _get_location_answer(self, question: str) -> str:
        """Get location answer."""
        if "preferred" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.LOCATION]["preferred"]
        elif "relocate" in question or "willing" in question:
            return "Yes"
        elif any(city in question for city in ["bangalore", "mumbai", "pune", "hyderabad", "chennai"]):
            return f"No, I am currently based in Noida. However, I am willing to relocate."
        else:
            return CATEGORY_DEFAULTS[QuestionCategory.LOCATION]["current"]
    
    def _get_skills_answer(self, question: str) -> str:
        """Get skills/proficiency answer."""
        if "proficiency" in question or "rate yourself" in question or "scale" in question:
            return "8"
        elif "tech stack" in question or "technologies" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.SKILLS]["tech_stack"]
        elif "language" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.SKILLS]["languages"]
        elif "dsa" in question or "data structure" in question or "algorithm" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.SKILLS]["dsa"]
        else:
            return CATEGORY_DEFAULTS[QuestionCategory.SKILLS]["tech_stack"]
    
    def _get_yes_no_answer(self, question: str) -> str:
        """Get yes/no answer with context awareness."""
        # Questions that should be "No"
        negative_indicators = [
            "sponsorship", "referral", "referred", "registered", 
            "medical condition", "disability", "criminal"
        ]
        
        for indicator in negative_indicators:
            if indicator in question:
                return "No"
        
        return "Yes"
    
    def _get_personal_info_answer(self, question: str) -> str:
        """Get personal information answer."""
        if "phone" in question or "mobile" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PERSONAL_INFO]["phone"]
        elif "email" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PERSONAL_INFO]["email"]
        elif "dob" in question or "date of birth" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PERSONAL_INFO]["dob"]
        elif "pan" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PERSONAL_INFO]["pan"]
        elif "name" in question and "pan" not in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PERSONAL_INFO]["name"]
        return ""
    
    def _get_preference_answer(self, question: str) -> str:
        """Get preference/role answer."""
        if "frontend" in question and "backend" in question:
            return "Backend"
        elif "role" in question or "position" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PREFERENCE]["role"]
        elif "domain" in question:
            return CATEGORY_DEFAULTS[QuestionCategory.PREFERENCE]["domain"]
        return ""
    
    def detect_input_type(self, element_info: Dict[str, Any]) -> InputType:
        """
        Detect input type from element attributes.
        
        Args:
            element_info: Dictionary with element attributes (type, tag, etc.)
            
        Returns:
            Detected InputType
        """
        input_type = element_info.get("type", "").lower()
        tag = element_info.get("tag", "").lower()
        
        type_mapping = {
            "text": InputType.TEXT,
            "number": InputType.NUMBER,
            "radio": InputType.RADIO,
            "checkbox": InputType.CHECKBOX,
            "email": InputType.EMAIL,
            "tel": InputType.TEL,
            "date": InputType.DATE,
            "textarea": InputType.TEXTAREA,
            "select": InputType.SELECT
        }
        
        return type_mapping.get(input_type, InputType.TEXT)
    
    def should_skip_question(self, question: str) -> bool:
        """
        Determine if a question should be skipped.
        
        Args:
            question: The question text
            
        Returns:
            True if question should be skipped
        """
        skip_patterns = [
            "skip this question",
            "try again",
            "restart conversation",
            "no worries",
            "change your input",
            "optional",
            "not required"
        ]
        
        question_lower = question.lower()
        return any(pattern in question_lower for pattern in skip_patterns)


# Convenience function for quick classification
def classify_question(question: str, platform: str = "default") -> Tuple[str, float]:
    """
    Quick function to classify a question and get an answer.
    
    Args:
        question: The question text
        platform: Platform name (naukri, linkedin, etc.)
        
    Returns:
        Tuple of (answer, confidence)
    """
    classifier = QuestionClassifier(platform)
    category, confidence = classifier.classify(question)
    
    if category == QuestionCategory.UNKNOWN:
        return "", 0.0
    
    answer, ans_confidence = classifier.get_answer(question, category)
    return answer, min(confidence, ans_confidence)
