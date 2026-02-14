"""
Patterns module - Q&A pattern loading and matching.

This module provides functionality to load Q&A patterns from JSON files
and match them against user questions using fuzzy string matching.

Example:
    from src.patterns import PatternLoader, PatternMatcher
    
    # Load patterns
    loader = PatternLoader()
    patterns = loader.load()
    
    # Create matcher
    matcher = PatternMatcher(patterns)
    
    # Match a question
    answer, confidence = matcher.fuzzy_match("What is your current salary?")
    print(f"Answer: {answer} (confidence: {confidence:.2f})")
"""

from .pattern_loader import (
    PatternLoader,
    load_patterns,
    validate_patterns,
    get_pattern,
    get_patterns_by_category,
    get_pattern_answer,
    PatternLoadError,
    PatternValidationError,
)

from .pattern_matcher import (
    PatternMatcher,
    create_matcher,
)

__all__ = [
    # Pattern Loader
    'PatternLoader',
    'load_patterns',
    'validate_patterns',
    'get_pattern',
    'get_patterns_by_category',
    'get_pattern_answer',
    'PatternLoadError',
    'PatternValidationError',
    
    # Pattern Matcher
    'PatternMatcher',
    'create_matcher',
]
