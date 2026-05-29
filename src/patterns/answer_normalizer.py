"""
Answer Normalizer - Transform answers to fit input type constraints.

This module provides intelligent answer normalization to ensure answers
are appropriate for the target input type (radio, checkbox, select, text).
"""

import re
from typing import Optional, Dict, Any, List
from enum import Enum


class InputType(Enum):
    """Input types for answer normalization."""
    TEXT = "text"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    SELECT = "select"
    NUMBER = "number"
    TEXTAREA = "textarea"


class AnswerNormalizer:
    """
    Normalizes answers to fit input type constraints.
    
    This class transforms verbose text answers into appropriate formats
    for different input types (radio buttons need simple Yes/No,
    checkboxes need boolean values, etc.).
    """
    
    # Synonyms for Yes/No detection
    YES_SYNONYMS = [
        'yes', 'yeah', 'yep', 'y', 'true', '1', 'agree', 'accept', 'ok', 'okay',
        'sure', 'absolutely', 'definitely', 'certainly', 'indeed'
    ]
    
    NO_SYNONYMS = [
        'no', 'nope', 'n', 'false', '0', 'decline', 'reject', 'not',
        'never', 'nah', 'negative'
    ]
    
    def __init__(self):
        """Initialize the answer normalizer."""
        pass
    
    def normalize(
        self,
        answer: str,
        input_type: InputType,
        question: str = "",
        options: List[str] = None
    ) -> str:
        """
        Normalize an answer for the given input type.
        
        Args:
            answer: The original answer text
            input_type: Target input type
            question: Optional question text for context
            options: Optional available options for radio/select
            
        Returns:
            Normalized answer appropriate for the input type
        """
        if not answer:
            return answer
        
        if input_type == InputType.TEXT or input_type == InputType.TEXTAREA:
            return self._normalize_text(answer)
        
        elif input_type == InputType.NUMBER:
            return self._normalize_number(answer)
        
        elif input_type == InputType.RADIO:
            return self._normalize_radio(answer, options)
        
        elif input_type == InputType.CHECKBOX:
            return self._normalize_checkbox(answer)
        
        elif input_type == InputType.SELECT:
            return self._normalize_select(answer, options)
        
        return answer
    
    def _normalize_text(self, answer: str) -> str:
        """Normalize for text input - minimal transformation."""
        return answer.strip()
    
    def _normalize_number(self, answer: str) -> str:
        """Normalize for number input - extract numeric value."""
        # Extract first number from answer
        match = re.search(r'(\d+\.?\d*)', answer.replace(',', ''))
        if match:
            return match.group(1)
        return answer.strip()
    
    def _normalize_radio(self, answer: str, options: List[str] = None) -> str:
        """
        Normalize for radio button input.
        
        Radio buttons typically need simple Yes/No or short option values.
        """
        answer_lower = answer.lower().strip()
        
        # Check for Yes/No pattern
        if self._is_yes(answer_lower):
            # If options provided, find the Yes option
            if options:
                yes_option = self._find_matching_option(options, ['yes', 'true', 'agree', 'accept'])
                if yes_option:
                    return yes_option
            return "Yes"
        
        if self._is_no(answer_lower):
            # If options provided, find the No option
            if options:
                no_option = self._find_matching_option(options, ['no', 'false', 'decline', 'reject'])
                if no_option:
                    return no_option
            return "No"
        
        # For long answers, extract first sentence or key phrase
        if len(answer) > 50:
            # Try to extract key information
            simplified = self._extract_key_phrase(answer)
            
            # If options provided, try to match
            if options:
                best_match = self._find_best_match(simplified, options)
                if best_match:
                    return best_match
            
            return simplified
        
        # If options provided, try to match
        if options:
            best_match = self._find_best_match(answer, options)
            if best_match:
                return best_match
        
        return answer.strip()
    
    def _normalize_checkbox(self, answer: str) -> str:
        """
        Normalize for checkbox input.
        
        Checkboxes need boolean-like values or simple Yes/No.
        """
        answer_lower = answer.lower().strip()
        
        if self._is_yes(answer_lower):
            return "checked"
        
        if self._is_no(answer_lower):
            return "unchecked"
        
        # For long answers, assume Yes if it starts with positive affirmation
        if len(answer) > 50:
            if any(answer_lower.startswith(yes) for yes in self.YES_SYNONYMS):
                return "checked"
        
        return "checked"  # Default to checked for non-negative answers
    
    def _normalize_select(self, answer: str, options: List[str] = None) -> str:
        """Normalize for select dropdown input."""
        if options:
            best_match = self._find_best_match(answer, options)
            if best_match:
                return best_match
        
        return answer.strip()
    
    def _is_yes(self, answer_lower: str) -> bool:
        """Check if answer indicates Yes/True."""
        return any(yes in answer_lower for yes in self.YES_SYNONYMS)
    
    def _is_no(self, answer_lower: str) -> bool:
        """Check if answer indicates No/False."""
        return any(no in answer_lower for no in self.NO_SYNONYMS)
    
    def _extract_key_phrase(self, answer: str) -> str:
        """Extract key phrase from a long answer."""
        # Split by sentence
        sentences = answer.split('.')
        first_sentence = sentences[0].strip()
        
        # If first sentence is still too long, take first clause
        if len(first_sentence) > 50:
            clauses = first_sentence.split(',')
            return clauses[0].strip()
        
        return first_sentence
    
    def _find_matching_option(self, options: List[str], keywords: List[str]) -> Optional[str]:
        """Find an option that matches any of the keywords."""
        for option in options:
            option_lower = option.lower()
            for keyword in keywords:
                if keyword in option_lower:
                    return option
        return None
    
    def _find_best_match(self, answer: str, options: List[str]) -> Optional[str]:
        """Find the best matching option using fuzzy matching."""
        from difflib import SequenceMatcher
        
        answer_lower = answer.lower()
        best_match = None
        best_score = 0.0
        
        for option in options:
            option_lower = option.lower()
            
            # Exact match
            if answer_lower == option_lower:
                return option
            
            # Partial match
            if answer_lower in option_lower or option_lower in answer_lower:
                return option
            
            # Fuzzy match
            similarity = SequenceMatcher(None, answer_lower, option_lower).ratio()
            if similarity > best_score and similarity > 0.6:
                best_score = similarity
                best_match = option
        
        return best_match
    
    def normalize_for_pattern(
        self,
        answer: str,
        input_type: str,
        pattern_data: Dict[str, Any]
    ) -> str:
        """
        Normalize answer using pattern's input_type_defaults if available.
        
        Args:
            answer: The original answer
            input_type: Target input type
            pattern_data: Pattern data containing input_type_defaults
            
        Returns:
            Normalized answer
        """
        # Check if pattern has input_type_defaults
        input_type_defaults = pattern_data.get('input_type_defaults', {})
        
        if input_type_defaults and input_type in input_type_defaults:
            return input_type_defaults[input_type]
        
        # Fall back to general normalization
        try:
            input_type_enum = InputType(input_type.lower())
        except ValueError:
            input_type_enum = InputType.TEXT
        
        return self.normalize(answer, input_type_enum)


# Convenience function
def normalize_answer(
    answer: str,
    input_type: str,
    question: str = "",
    options: List[str] = None
) -> str:
    """
    Normalize an answer for the given input type.
    
    Args:
        answer: The original answer text
        input_type: Target input type (text, radio, checkbox, select, number)
        question: Optional question text for context
        options: Optional available options for radio/select
        
    Returns:
        Normalized answer appropriate for the input type
    """
    normalizer = AnswerNormalizer()
    
    try:
        input_type_enum = InputType(input_type.lower())
    except ValueError:
        input_type_enum = InputType.TEXT
    
    return normalizer.normalize(answer, input_type_enum, question, options)
