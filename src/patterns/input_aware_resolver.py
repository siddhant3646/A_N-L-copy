"""
Input-Aware Answer Resolver - Matches answers to available options.

This module provides intelligent answer resolution that considers:
1. Input type (text, select, radio, checkbox)
2. Available options for select/radio/checkbox elements
3. Numeric range matching for experience/salary dropdowns
4. Fuzzy matching of answer text to option labels
"""

from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import re


class InputType(Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"
    DATE = "date"
    EMAIL = "email"
    TEL = "tel"


@dataclass
class Option:
    value: str
    label: str
    index: int = 0
    is_selected: bool = False


@dataclass
class MatchResult:
    matched_option: Optional[Option]
    confidence: float
    match_type: str
    original_answer: str
    alternatives: List[Tuple['Option', float]] = None
    
    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []


class NumericRangeMatcher:
    """Matches numeric values to range options like '3-5 years'."""
    
    RANGE_PATTERNS = [
        (r'(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)', 'range'),
        (r'(\d+(?:\.\d+)?)\s*\+', 'min'),
        (r'(?:less than|under|below)\s*(\d+(?:\.\d+)?)', 'max'),
        (r'(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)', 'min'),
    ]
    
    @classmethod
    def extract_range(cls, option_text: str) -> Optional[Tuple[float, float, str]]:
        if not option_text:
            return None
        text = option_text.lower().strip()
        
        for pattern, range_type in cls.RANGE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if range_type == 'range':
                    return (float(match.group(1)), float(match.group(2)), 'range')
                elif range_type == 'min':
                    return (float(match.group(1)), float('inf'), 'min')
                elif range_type == 'max':
                    return (0, float(match.group(1)), 'max')
        
        return None
    
    @classmethod
    def value_in_range(cls, value: float, range_info: Tuple[float, float, str]) -> bool:
        if range_info is None:
            return False
        min_val, max_val, _ = range_info
        return min_val <= value <= max_val


class OptionExtractor:
    """Extracts options from form elements."""
    
    @staticmethod
    def extract_select_options(element_html: str) -> List[Option]:
        options = []
        pattern = r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>([^<]*)</option>'
        for i, match in enumerate(re.finditer(pattern, element_html, re.IGNORECASE)):
            value = match.group(1).strip()
            label = match.group(2).strip()
            if value and label and value.lower() not in ['', 'select', 'choose', '-']:
                options.append(Option(value=value, label=label, index=i))
        return options
    
    @staticmethod
    def extract_radio_options(elements_html: List[str]) -> List[Option]:
        options = []
        for i, html in enumerate(elements_html):
            value_match = re.search(r'value=["\']([^"\']*)["\']', html, re.IGNORECASE)
            label_match = re.search(r'<label[^>]*>([^<]*)</label>', html, re.IGNORECASE)
            
            value = value_match.group(1).strip() if value_match else ""
            label = label_match.group(1).strip() if label_match else value
            
            if label:
                options.append(Option(value=value, label=label, index=i))
        return options


class InputAwareResolver:
    """
    Main resolver that matches answers to available options.
    """
    
    OPTION_SYNONYMS = {
        'yes': ['yes', 'yeah', 'yep', 'y', 'true', '1', 'agree', 'accept', 'ok', 'okay'],
        'no': ['no', 'nope', 'n', 'false', '0', 'decline', 'reject', 'not'],
        
        'fresher': ['0', 'fresher', 'fresh graduate', 'no experience', 'entry level'],
        'junior': ['1', '1-2', 'junior', 'entry'],
        'mid': ['2', '2-3', '3', '3-4', 'mid', 'intermediate'],
        'senior': ['4', '4-5', '5', '5+', 'senior', 'lead'],
        
        'immediate': ['0', 'immediate', 'now', 'immediately'],
        'short': ['15', '15 days', '2 weeks', 'short notice'],
        'standard': ['30', '30 days', '1 month', 'one month', 'standard'],
        'long': ['60', '60 days', '2 months', '90', '90 days', '3 months'],
        
        'remote': ['remote', 'work from home', 'wfh', 'virtual'],
        'hybrid': ['hybrid', 'flexible', 'mixed'],
        'onsite': ['onsite', 'work from office', 'wfo', 'in-office'],
        
        "bachelor's": ["bachelor's", 'bachelors', 'b.tech', 'b.e', 'undergraduate'],
        "master's": ["master's", 'masters', 'm.tech', 'm.e', 'postgraduate'],
        'phd': ['phd', 'doctorate', 'doctoral'],
        
        'beginner': ['beginner', 'novice', 'entry', 'low', '1', '2', '3',
                     '1 out of 10', '2 out of 10', '3 out of 10',
                     '1/10', '2/10', '3/10'],
        'intermediate': ['intermediate', 'mid', 'medium', 'average', '4', '5', '6',
                         '4 out of 10', '5 out of 10', '6 out of 10',
                         '4/10', '5/10', '6/10'],
        'advanced': ['advanced', 'expert', 'senior', 'high', '7', '8', '9', '10',
                     '7 out of 10', '8 out of 10', '9 out of 10', '10 out of 10',
                     '7/10', '8/10', '9/10', '10/10'],
    }
    
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.range_matcher = NumericRangeMatcher()
    
    def resolve(
        self,
        answer: str,
        input_type: InputType,
        options: List[Option] = None,
        question: str = ""
    ) -> MatchResult:
        if input_type in [InputType.TEXT, InputType.TEXTAREA, InputType.EMAIL, InputType.TEL]:
            return MatchResult(
                matched_option=Option(value=answer, label=answer),
                confidence=1.0,
                match_type='text',
                original_answer=answer
            )
        
        if input_type == InputType.NUMBER:
            numeric_answer = self._extract_number(answer)
            return MatchResult(
                matched_option=Option(value=numeric_answer, label=numeric_answer),
                confidence=0.95,
                match_type='numeric',
                original_answer=answer
            )
        
        if options is None or len(options) == 0:
            return MatchResult(
                matched_option=Option(value=answer, label=answer),
                confidence=0.5,
                match_type='fallback',
                original_answer=answer
            )
        
        return self._match_to_options(answer, options, question)
    
    def _match_to_options(
        self,
        answer: str,
        options: List[Option],
        question: str = ""
    ) -> MatchResult:
        answer_lower = answer.lower().strip()
        
        for opt in options:
            if opt.value.lower() == answer_lower or opt.label.lower() == answer_lower:
                return MatchResult(
                    matched_option=opt,
                    confidence=1.0,
                    match_type='exact',
                    original_answer=answer
                )
        
        answer_num = self._extract_number(answer)
        if answer_num:
            for opt in options:
                range_info = self.range_matcher.extract_range(opt.label)
                if range_info and self.range_matcher.value_in_range(float(answer_num), range_info):
                    return MatchResult(
                        matched_option=opt,
                        confidence=0.95,
                        match_type='numeric_range',
                        original_answer=answer
                    )
        
        for opt in options:
            if self._is_synonym_match(answer_lower, opt.label.lower()):
                return MatchResult(
                    matched_option=opt,
                    confidence=0.9,
                    match_type='synonym',
                    original_answer=answer
                )
        
        best_match = None
        best_score = 0.0
        all_scores = []
        
        for opt in options:
            value_sim = self._similarity(answer_lower, opt.value.lower())
            label_sim = self._similarity(answer_lower, opt.label.lower())
            score = max(value_sim, label_sim)
            
            all_scores.append((opt, score))
            
            if score > best_score:
                best_score = score
                best_match = opt
        
        if best_match and best_score >= self.threshold:
            return MatchResult(
                matched_option=best_match,
                confidence=best_score,
                match_type='fuzzy',
                original_answer=answer,
                alternatives=[(o, s) for o, s in all_scores if o != best_match and s >= 0.5]
            )
        
        return MatchResult(
            matched_option=None,
            confidence=best_score,
            match_type='none',
            original_answer=answer,
            alternatives=sorted(all_scores, key=lambda x: x[1], reverse=True)[:3]
        )
    
    def _extract_number(self, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r'(\d+\.?\d*)', text.replace(',', ''))
        return match.group(1) if match else None
    
    def _is_synonym_match(self, answer: str, option: str) -> bool:
        for canonical, synonyms in self.OPTION_SYNONYMS.items():
            answer_in_group = any(s in answer for s in synonyms)
            option_in_group = any(s in option for s in synonyms)
            if answer_in_group and option_in_group:
                return True
        return False
    
    def _similarity(self, s1: str, s2: str) -> float:
        return SequenceMatcher(None, s1, s2).ratio()
    
    def get_best_option_for_value(
        self,
        value: float,
        options: List[Option],
        value_type: str = "years"
    ) -> Optional[Option]:
        for opt in options:
            range_info = self.range_matcher.extract_range(opt.label)
            if range_info:
                min_val, max_val, _ = range_info
                if max_val == float('inf'):
                    if value >= min_val:
                        return opt
                elif min_val <= value <= max_val:
                    return opt
        return None
