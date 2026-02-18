"""
Pattern Learner - Automatic pattern expansion and learning.

This module provides:
1. Automatic generation of new patterns from successful answers
2. Option mapping learning
3. Pattern confidence management
4. Integration with existing pattern systems
"""

import re
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from difflib import SequenceMatcher


class PatternExpander:
    """Expands patterns with common variations."""
    
    PREFIXES = [
        'please enter', 'please select', 'please provide', 'please specify',
        'what is', 'what are', 'how many', 'how much', 'do you have',
        'are you', 'have you', 'can you', 'will you', 'would you',
        'enter', 'select', 'choose', 'specify', 'provide', 'mention'
    ]
    
    SUFFIXES = [
        '?', '.', ':', ' in years', ' in months', ' in days',
        ' in lakhs', ' in lpa', ' in inr', ' (in years)', ' (in lpa)'
    ]
    
    @classmethod
    def normalize_question(cls, question: str) -> str:
        if not question:
            return ""
        text = question.lower().strip()
        
        for prefix in cls.PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        for suffix in cls.SUFFIXES:
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
        
        text = re.sub(r'[^\w\s]', ' ', text)
        text = ' '.join(text.split())
        
        return text
    
    @classmethod
    def generate_variations(cls, question: str) -> List[str]:
        if not question:
            return []
        variations = [question.lower().strip()]
        
        for prefix in cls.PREFIXES:
            if question.lower().startswith(prefix):
                variations.append(question[len(prefix):].strip())
        
        normalized = cls.normalize_question(question)
        for prefix in ['what is your', 'enter your', 'please enter']:
            variations.append(f"{prefix} {normalized}")
        
        abbreviations = {
            'experience': 'exp',
            'years': 'yrs',
            'salary': 'ctc',
            'current ctc': 'cctc',
            'expected ctc': 'ectc',
            'notice period': 'np'
        }
        
        for full, abbr in abbreviations.items():
            if full in normalized:
                variations.append(normalized.replace(full, abbr))
        
        return list(set(variations))


class PatternLearner:
    """
    Main class for learning and managing patterns.
    """
    
    def __init__(self):
        self.pattern_cache: Dict[str, Set[str]] = {}
        self.answer_index: Dict[str, List[str]] = {}
        self.option_learning_enabled = True
    
    def learn_from_success(
        self,
        question: str,
        answer: str,
        selected_option: str = None,
        confidence: float = 0.8
    ) -> Optional[str]:
        if not question or not answer:
            return None
        
        variations = PatternExpander.generate_variations(question)
        
        fingerprint = self._create_fingerprint(question)
        
        if fingerprint not in self.pattern_cache:
            self.pattern_cache[fingerprint] = set()
        
        for var in variations:
            self.pattern_cache[fingerprint].add(var.lower())
        
        if answer not in self.answer_index:
            self.answer_index[answer] = []
        
        for var in variations:
            if var.lower() not in self.answer_index[answer]:
                self.answer_index[answer].append(var.lower())
        
        pattern_id = f"learned_{fingerprint[:8]}"
        
        return pattern_id
    
    def find_answer(self, question: str, threshold: float = 0.7) -> Optional[Tuple[str, float]]:
        if not question:
            return None
        question_lower = question.lower().strip()
        
        for answer, patterns in self.answer_index.items():
            if question_lower in patterns:
                return (answer, 0.95)
            
            for pattern in patterns:
                similarity = SequenceMatcher(None, question_lower, pattern).ratio()
                if similarity >= threshold:
                    return (answer, similarity * 0.9)
        
        return None
    
    def get_similar_patterns(self, question: str, limit: int = 5) -> List[Tuple[str, str, float]]:
        if not question:
            return []
        results = []
        question_lower = question.lower()
        
        for answer, patterns in self.answer_index.items():
            for pattern in patterns:
                similarity = SequenceMatcher(None, question_lower, pattern).ratio()
                if similarity >= 0.5:
                    results.append((pattern, answer, similarity))
        
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:limit]
    
    def _create_fingerprint(self, question: str) -> str:
        normalized = PatternExpander.normalize_question(question)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def export_patterns(self) -> Dict:
        return {
            'pattern_cache': {k: list(v) for k, v in self.pattern_cache.items()},
            'answer_index': self.answer_index,
            'exported_at': datetime.now().isoformat()
        }
    
    def import_patterns(self, data: Dict):
        if 'pattern_cache' in data:
            for fp, patterns in data['pattern_cache'].items():
                if fp not in self.pattern_cache:
                    self.pattern_cache[fp] = set()
                self.pattern_cache[fp].update(patterns)
        
        if 'answer_index' in data:
            for answer, patterns in data['answer_index'].items():
                if answer not in self.answer_index:
                    self.answer_index[answer] = []
                for p in patterns:
                    if p not in self.answer_index[answer]:
                        self.answer_index[answer].append(p)


class OptionMappingLearner:
    """Learns mappings between answers and dropdown options."""
    
    def __init__(self):
        self.mappings: Dict[str, Dict[str, List[str]]] = {}
    
    def learn_mapping(
        self,
        question_pattern: str,
        option_value: str,
        option_label: str,
        provided_answer: str
    ):
        key = self._normalize_pattern(question_pattern)
        
        if key not in self.mappings:
            self.mappings[key] = {}
        
        if option_value not in self.mappings[key]:
            self.mappings[key][option_value] = []
        
        answers_to_add = [
            provided_answer,
            option_label,
            option_value,
            provided_answer.lower(),
            option_label.lower()
        ]
        
        for answer in answers_to_add:
            if answer and answer not in self.mappings[key][option_value]:
                self.mappings[key][option_value].append(answer)
    
    def find_option_for_answer(
        self,
        question_pattern: str,
        answer: str,
        available_options: Dict[str, str]
    ) -> Optional[Tuple[str, float]]:
        key = self._normalize_pattern(question_pattern)
        
        if key not in self.mappings:
            return None
        
        answer_lower = answer.lower()
        
        for option_value, possible_answers in self.mappings[key].items():
            if option_value in available_options:
                for possible in possible_answers:
                    if answer_lower == possible.lower():
                        return (option_value, 1.0)
                    if answer_lower in possible.lower() or possible.lower() in answer_lower:
                        return (option_value, 0.85)
        
        return None
    
    def _normalize_pattern(self, pattern: str) -> str:
        return re.sub(r'[^\w\s]', '', pattern.lower())[:50]
    
    def export_mappings(self) -> Dict:
        return {
            'mappings': self.mappings,
            'exported_at': datetime.now().isoformat()
        }
    
    def import_mappings(self, data: Dict):
        if 'mappings' in data:
            self.mappings.update(data['mappings'])
