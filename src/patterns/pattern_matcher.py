"""
Pattern Matcher Module - Fuzzy matching for question-answer patterns.

This module provides fuzzy string matching capabilities to match user questions
against known patterns and return appropriate answers with confidence scores.
"""

from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple, Optional
import re

from .pattern_loader import PatternLoader, get_pattern_answer


class PatternMatcher:
    """
    Matcher for finding the best matching pattern for a given question.
    
    Uses fuzzy string matching combined with keyword priority matching
    to find the best answer for a question.
    """
    
    DEFAULT_THRESHOLD = 0.65
    
    def __init__(self, patterns: Dict[str, Any], threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize the pattern matcher.
        
        Args:
            patterns: Dictionary containing patterns (as loaded by PatternLoader)
            threshold: Minimum similarity score to consider a match (0.0-1.0)
        """
        self.patterns = patterns
        self.threshold = threshold
        self._pattern_cache: Dict[str, List[str]] = {}
        self._build_cache()
    
    def _build_cache(self):
        """Build internal cache of all pattern strings."""
        if 'patterns' not in self.patterns:
            return
        
        for pattern_id, pattern_data in self.patterns['patterns'].items():
            if 'patterns' in pattern_data and isinstance(pattern_data['patterns'], list):
                self._pattern_cache[pattern_id] = pattern_data['patterns']
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for better matching.
        
        Args:
            text: Input text
            
        Returns:
            Normalized text
        """
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Remove all punctuation
        text = re.sub(r'[^\w\s]', '', text)
        
        return text
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using SequenceMatcher.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _keyword_priority_match(self, question: str) -> Tuple[Optional[str], float]:
        """
        Check for keyword-based priority matches.
        
        This helps prevent CTC questions matching experience patterns, etc.
        
        Args:
            question: The question to match
            
        Returns:
            Tuple of (answer, confidence) or (None, 0.0)
        """
        question_lower = question.lower()
        
        # Define keyword categories with their associated patterns
        keyword_categories = {
            'salary': {
                'keywords': ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc'],
                'patterns': ['current_salary', 'expected_salary']
            },
            'experience': {
                'keywords': ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp'],
                'patterns': ['experience', 'experience_months']
            },
            'notice_period': {
                'keywords': ['notice', 'serving', 'join', 'availability'],
                'patterns': ['notice_period']
            },
            'location': {
                'keywords': ['location', 'city', 'relocate', 'preferred location', 'based in'],
                'patterns': ['location_current', 'location_preferred']
            }
        }
        
        # Check which category has the most keyword matches
        best_category = None
        best_score = 0
        
        for category, data in keyword_categories.items():
            score = sum(1 for kw in data['keywords'] if kw in question_lower)
            if score > best_score:
                best_score = score
                best_category = category
        
        # If we found a strong category match, return the best matching pattern from that category
        if best_category and best_score > 0:
            category_data = keyword_categories[best_category]
            best_match = None
            best_match_score = 0.0
            
            for pattern_id in category_data['patterns']:
                pattern = self.patterns['patterns'].get(pattern_id)
                if not pattern:
                    continue
                
                # Check all pattern strings for this pattern
                for pattern_str in pattern.get('patterns', []):
                    similarity = self._calculate_similarity(
                        self._normalize_text(question),
                        self._normalize_text(pattern_str)
                    )
                    if similarity > best_match_score:
                        best_match_score = similarity
                        best_match = pattern
            
            if best_match and best_match_score >= self.threshold:
                return best_match.get('default'), best_match_score
        
        return None, 0.0
    
    def fuzzy_match(self, question: str) -> Tuple[Optional[str], float]:
        """
        Find the best matching answer for a question using fuzzy matching.
        
        Args:
            question: The question to match
            
        Returns:
            Tuple of (answer, confidence_score)
            If no match found, returns (None, 0.0)
        """
        if not question:
            return None, 0.0
        
        normalized_question = self._normalize_text(question)
        
        # First try keyword priority matching
        answer, confidence = self._keyword_priority_match(question)
        if answer:
            return answer, confidence
        
        # Fall back to general fuzzy matching
        best_match = None
        best_score = 0.0
        
        for pattern_id, pattern_strings in self._pattern_cache.items():
            for pattern_str in pattern_strings:
                normalized_pattern = self._normalize_text(pattern_str)
                
                # Calculate similarity
                similarity = self._calculate_similarity(
                    normalized_question,
                    normalized_pattern
                )
                
                # Also check for substring match (bonus)
                if normalized_pattern in normalized_question or normalized_question in normalized_pattern:
                    similarity = max(similarity, 0.85)
                
                if similarity > best_score and similarity >= self.threshold:
                    best_score = similarity
                    pattern = self.patterns['patterns'].get(pattern_id)
                    if pattern:
                        best_match = pattern.get('default')
        
        return best_match, best_score
    
    def match_with_details(self, question: str) -> Dict[str, Any]:
        """
        Match a question and return detailed results.
        
        Args:
            question: The question to match
            
        Returns:
            Dictionary containing:
                - question: Original question
                - answer: Matched answer (or None)
                - confidence: Confidence score
                - matched: Whether a match was found
        """
        answer, confidence = self.fuzzy_match(question)
        
        return {
            'question': question,
            'answer': answer,
            'confidence': confidence,
            'matched': answer is not None
        }
    
    def get_all_matches(self, question: str, min_confidence: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Get all matching patterns above a confidence threshold.
        
        Args:
            question: The question to match
            min_confidence: Minimum confidence to include (default 0.5)
            
        Returns:
            List of tuples (pattern_id, answer, confidence)
        """
        matches = []
        normalized_question = self._normalize_text(question)
        
        for pattern_id, pattern_strings in self._pattern_cache.items():
            pattern = self.patterns['patterns'].get(pattern_id)
            if not pattern:
                continue
            
            best_similarity = 0.0
            for pattern_str in pattern_strings:
                normalized_pattern = self._normalize_text(pattern_str)
                similarity = self._calculate_similarity(
                    normalized_question,
                    normalized_pattern
                )
                best_similarity = max(best_similarity, similarity)
            
            if best_similarity >= min_confidence:
                matches.append((
                    pattern_id,
                    pattern.get('default'),
                    best_similarity
                ))
        
        # Sort by confidence (highest first)
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches
    
    def update_patterns(self, patterns: Dict[str, Any]):
        """
        Update the patterns and rebuild the cache.
        
        Args:
            patterns: New patterns dictionary
        """
        self.patterns = patterns
        self._pattern_cache.clear()
        self._build_cache()


def create_matcher(json_path: Optional[str] = None, threshold: float = PatternMatcher.DEFAULT_THRESHOLD) -> PatternMatcher:
    """
    Convenience function to create a PatternMatcher from a JSON file.
    
    Args:
        json_path: Path to patterns JSON file (None for default)
        threshold: Matching threshold
        
    Returns:
        PatternMatcher instance
    """
    loader = PatternLoader(json_path)
    patterns = loader.load()
    return PatternMatcher(patterns, threshold)
