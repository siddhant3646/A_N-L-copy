"""
Patterns module - Q&A pattern loading, matching, and learning.

This module provides functionality to:
1. Load Q&A patterns from JSON files
2. Match them against user questions using fuzzy string matching
3. Resolve answers based on input type and available options
4. Learn new patterns from successful answers

Example:
    from src.patterns import PatternLoader, PatternMatcher, InputAwareResolver
    
    # Load patterns
    loader = PatternLoader()
    patterns = loader.load()
    
    # Create matcher
    matcher = PatternMatcher(patterns)
    
    # Match a question
    answer, confidence = matcher.fuzzy_match("What is your current salary?")
    print(f"Answer: {answer} (confidence: {confidence:.2f})")
    
    # Resolve answer for dropdown
    resolver = InputAwareResolver()
    result = resolver.resolve("4 Years", InputType.SELECT, options)
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

from .input_aware_resolver import (
    InputType,
    InputAwareResolver,
    Option,
    MatchResult,
    NumericRangeMatcher,
    OptionExtractor,
)

from .pattern_learner import (
    PatternLearner,
    PatternExpander,
    OptionMappingLearner,
)

from src.sentinel.semantic_matcher import (
    SemanticQuestionMatcher,
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

    # Input Aware Resolver
    'InputType',
    'InputAwareResolver',
    'Option',
    'MatchResult',
    'NumericRangeMatcher',
    'OptionExtractor',

    # Pattern Learner
    'PatternLearner',
    'PatternExpander',
    'OptionMappingLearner',

    # Semantic Matcher
    'SemanticQuestionMatcher',
]
