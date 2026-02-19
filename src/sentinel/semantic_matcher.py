"""
Semantic Question Matcher - Intent-based question understanding.

Matches questions based on semantic intent rather than exact text,
enabling cross-question learning and better pattern matching.
"""

from typing import Dict, List, Optional, Tuple, Set
from difflib import SequenceMatcher


class SemanticQuestionMatcher:
    """
    Matches questions based on semantic intent.
    """
    
    # Question intent categories with common variations
    INTENTS = {
        'experience_duration': {
            'keywords': [
                'years of experience', 'total experience', 'overall experience',
                'how many years', 'experience in years', 'yr of exp', 'exp in years',
                'how long have you worked', 'worked for', 'experience level',
                'total exp', 'overall exp', 'work experience', 'professional experience'
            ],
            'answer': '3.8 Years',
            'category': 'experience'
        },
        'salary_current': {
            'keywords': [
                'current salary', 'current ctc', 'present compensation', 'present salary',
                'what is your salary', 'earning currently', 'current pay',
                'compensation currently', 'salary now', 'current package',
                'how much do you earn', 'what do you make', 'current remuneration'
            ],
            'answer': '13.5 LPA',
            'category': 'salary'
        },
        'salary_expected': {
            'keywords': [
                'expected salary', 'expected ctc', 'salary expectation',
                'looking for', 'desired compensation', 'expected pay',
                'salary expected', 'compensation expected', 'expected package',
                'how much do you want', 'salary you want', 'expecting salary'
            ],
            'answer': '20 LPA',
            'category': 'salary'
        },
        'notice_period': {
            'keywords': [
                'notice period', 'when can you join', 'availability',
                'how soon can you', 'serving notice', 'notice period days',
                'joining time', 'can join in', 'last working day', 'lwd',
                'when are you available', 'serving notice period', 'np'
            ],
            'answer': 'Serving Notice Period',
            'category': 'notice'
        },
        'work_mode': {
            'keywords': [
                'work mode', 'remote/hybrid/onsite', 'work from',
                'preferred working style', 'location preference', 'work arrangement',
                'remote work', 'work location', 'preferred mode', 'working mode',
                'office or remote', 'hybrid work', 'wfh or office'
            ],
            'answer': 'Hybrid',
            'category': 'work_mode'
        },
        'education': {
            'keywords': [
                'education', 'degree', 'qualification', 'highest degree',
                'academic qualification', 'educational background', 'qualifications',
                'what degree', 'highest education', 'academic degree'
            ],
            'answer': "Bachelor's",
            'category': 'education'
        },
        'skills_primary': {
            'keywords': [
                'primary skills', 'key skills', 'main skills', 'core skills',
                'primary technology', 'tech stack', 'technologies',
                'programming languages', 'what skills', 'tech you know'
            ],
            'answer': 'Python, JavaScript, React, Node.js',
            'category': 'skills'
        },
        'location_current': {
            'keywords': [
                'current location', 'where are you based', 'located in',
                'city you are in', 'current city', 'present location',
                'where do you stay', 'based out of', 'currently in'
            ],
            'answer': 'Noida',
            'category': 'location'
        },
        'location_preferred': {
            'keywords': [
                'preferred location', 'where do you want', 'relocate to',
                'willing to move', 'preferred city', 'location preference',
                'where would you like', 'preferred place', 'desired location'
            ],
            'answer': 'Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune',
            'category': 'location'
        },
        'company_current': {
            'keywords': [
                'current company', 'present employer', 'working at',
                'current employer', 'company you work for', 'where do you work',
                'current organization', 'who do you work for', 'employer name'
            ],
            'answer': 'Fiserv',
            'category': 'company'
        },
        'position_current': {
            'keywords': [
                'current role', 'current position', 'current designation',
                'job title', 'what is your role', 'what do you do',
                'current job', 'your position', 'what role', 'designation'
            ],
            'answer': 'SDE-2 Full Stack Developer',
            'category': 'position'
        },
    }
    
    # Equivalent questions that should share answers
    EQUIVALENT_QUESTIONS = {
        'experience': [
            'years of experience', 'total experience', 'overall experience',
            'how many years have you worked', 'experience in years',
            'years of professional experience', 'total exp', 'overall exp',
            'work experience', 'professional experience', 'industry experience',
            'years you have worked', 'how long have you been working'
        ],
        'current_salary': [
            'current salary', 'current ctc', 'present salary',
            'what is your current salary', 'current compensation',
            'how much do you earn now', 'current package', 'present ctc'
        ],
        'expected_salary': [
            'expected salary', 'expected ctc', 'salary expectation',
            'how much are you looking for', 'expected package',
            'desired salary', 'salary you want', 'expected compensation'
        ],
        'notice': [
            'notice period', 'when can you join', 'availability',
            'how soon can you join', 'serving notice period',
            'notice period in days', 'when are you available', 'joining time'
        ],
        'work_mode': [
            'work mode', 'remote or office', 'preferred working style',
            'work from home or office', 'work arrangement', 'work location preference'
        ],
        'location_current': [
            'current location', 'where are you based', 'where do you stay',
            'current city', 'where are you located', 'present location'
        ],
        'skills': [
            'primary skills', 'key skills', 'core skills', 'tech stack',
            'technologies you know', 'programming skills', 'technical skills'
        ]
    }
    
    def classify_intent(self, question: str) -> Tuple[Optional[str], float]:
        """
        Classify a question into an intent category.
        
        Returns:
            Tuple of (intent_name, confidence)
        """
        if not question:
            return None, 0.0
        
        question_lower = question.lower()
        best_intent = None
        best_score = 0.0
        
        for intent, data in self.INTENTS.items():
            max_keyword_score = 0.0
            
            for keyword in data['keywords']:
                if keyword in question_lower:
                    # Calculate match strength based on keyword length ratio
                    score = len(keyword) / len(question_lower)
                    score = min(0.95, 0.7 + score * 0.25)
                    max_keyword_score = max(max_keyword_score, score)
                else:
                    # Check fuzzy match
                    similarity = SequenceMatcher(None, question_lower, keyword).ratio()
                    if similarity > 0.8:
                        max_keyword_score = max(max_keyword_score, similarity * 0.9)
            
            if max_keyword_score > best_score:
                best_score = max_keyword_score
                best_intent = intent
        
        return best_intent, best_score
    
    def get_answer_for_intent(self, intent: str) -> Optional[str]:
        """Get canonical answer for an intent."""
        if intent in self.INTENTS:
            return self.INTENTS[intent]['answer']
        return None
    
    def get_category_for_intent(self, intent: str) -> Optional[str]:
        """Get category for an intent."""
        if intent in self.INTENTS:
            return self.INTENTS[intent]['category']
        return None
    
    def find_equivalence_class(self, question: str) -> Optional[str]:
        """
        Find which equivalence class a question belongs to.
        
        Returns:
            Equivalence class name or None
        """
        question_lower = question.lower()
        
        for eq_class, patterns in self.EQUIVALENT_QUESTIONS.items():
            for pattern in patterns:
                if pattern in question_lower:
                    return eq_class
                # Fuzzy match
                if SequenceMatcher(None, question_lower, pattern).ratio() > 0.85:
                    return eq_class
        
        return None
    
    def get_equivalent_questions(self, question: str) -> List[str]:
        """
        Get all questions equivalent to the given question.
        
        Returns:
            List of equivalent question patterns
        """
        eq_class = self.find_equivalence_class(question)
        if eq_class:
            return self.EQUIVALENT_QUESTIONS.get(eq_class, [])
        return []
    
    def are_semantically_equivalent(self, q1: str, q2: str, threshold: float = 0.8) -> bool:
        """
        Check if two questions are semantically equivalent.
        
        Args:
            q1: First question
            q2: Second question
            threshold: Minimum similarity threshold
            
        Returns:
            True if questions are equivalent
        """
        # Check if same equivalence class
        eq1 = self.find_equivalence_class(q1)
        eq2 = self.find_equivalence_class(q2)
        
        if eq1 and eq2 and eq1 == eq2:
            return True
        
        # Check intent classification
        intent1, conf1 = self.classify_intent(q1)
        intent2, conf2 = self.classify_intent(q2)
        
        if intent1 and intent2 and intent1 == intent2:
            return True
        
        # Check text similarity
        similarity = SequenceMatcher(None, q1.lower(), q2.lower()).ratio()
        return similarity >= threshold
    
    def extract_entities(self, question: str) -> Dict[str, str]:
        """
        Extract entities from a question.
        
        Returns:
            Dictionary of entity types and values
        """
        entities = {}
        question_lower = question.lower()
        
        # Extract technology mentions
        technologies = [
            'python', 'javascript', 'react', 'angular', 'vue', 'node', 'nodejs',
            'java', 'c++', 'c#', '.net', 'django', 'flask', 'spring',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes'
        ]
        
        found_techs = [tech for tech in technologies if tech in question_lower]
        if found_techs:
            entities['technologies'] = found_techs
        
        # Extract numeric ranges
        import re
        ranges = re.findall(r'(\d+)\s*[-–to]+\s*(\d+)', question_lower)
        if ranges:
            entities['range'] = ranges[0]
        
        # Extract single numbers
        numbers = re.findall(r'\d+\.?\d*', question_lower)
        if numbers:
            entities['numbers'] = numbers
        
        return entities
    
    def get_all_keywords_for_intent(self, intent: str) -> List[str]:
        """Get all keywords for an intent."""
        if intent in self.INTENTS:
            return self.INTENTS[intent]['keywords']
        return []
    
    def add_custom_intent(
        self,
        intent_name: str,
        keywords: List[str],
        answer: str,
        category: str
    ):
        """Add a custom intent."""
        self.INTENTS[intent_name] = {
            'keywords': keywords,
            'answer': answer,
            'category': category
        }
    
    def add_equivalent_questions(self, eq_class: str, questions: List[str]):
        """Add equivalent question patterns."""
        if eq_class in self.EQUIVALENT_QUESTIONS:
            self.EQUIVALENT_QUESTIONS[eq_class].extend(questions)
            # Remove duplicates
            self.EQUIVALENT_QUESTIONS[eq_class] = list(set(
                self.EQUIVALENT_QUESTIONS[eq_class]
            ))
        else:
            self.EQUIVALENT_QUESTIONS[eq_class] = questions
