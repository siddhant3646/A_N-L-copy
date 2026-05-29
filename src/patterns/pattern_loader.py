"""
Pattern Loader Module - Load and validate Q&A patterns from JSON files.

This module provides functionality to load, validate, and manage Q&A patterns
from JSON configuration files. It ensures patterns are properly structured
and provides utilities for accessing them.
"""

import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path


class PatternLoadError(Exception):
    """Exception raised when pattern loading fails."""
    pass


class PatternValidationError(Exception):
    """Exception raised when pattern validation fails."""
    pass


def load_patterns(json_path: str) -> Dict[str, Any]:
    """
    Load Q&A patterns from a JSON file.
    
    Args:
        json_path: Path to the JSON file containing patterns
        
    Returns:
        Dictionary containing the loaded patterns
        
    Raises:
        PatternLoadError: If the file doesn't exist or JSON is invalid
    """
    if not os.path.exists(json_path):
        raise PatternLoadError(f"Pattern file not found: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise PatternLoadError(f"Invalid JSON in pattern file: {e}")
    except Exception as e:
        raise PatternLoadError(f"Error reading pattern file: {e}")
    
    return data


def validate_patterns(patterns: Dict[str, Any]) -> List[str]:
    """
    Validate that patterns are correctly structured.
    
    Args:
        patterns: Dictionary containing patterns to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check for required top-level keys
    if 'patterns' not in patterns:
        errors.append("Missing required key: 'patterns'")
        return errors
    
    if not isinstance(patterns['patterns'], dict):
        errors.append("'patterns' must be a dictionary")
        return errors
    
    # Validate each pattern
    for pattern_id, pattern_data in patterns['patterns'].items():
        if not isinstance(pattern_data, dict):
            errors.append(f"Pattern '{pattern_id}' must be a dictionary")
            continue
        
        # Check required fields
        if 'patterns' not in pattern_data:
            errors.append(f"Pattern '{pattern_id}' missing 'patterns' field")
        elif not isinstance(pattern_data['patterns'], list):
            errors.append(f"Pattern '{pattern_id}' 'patterns' must be a list")
        
        if 'category' not in pattern_data:
            errors.append(f"Pattern '{pattern_id}' missing 'category' field")
        
        if 'default' not in pattern_data:
            errors.append(f"Pattern '{pattern_id}' missing 'default' field")
    
    return errors


def get_pattern(patterns: Dict[str, Any], pattern_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific pattern by ID.
    
    Args:
        patterns: Dictionary containing all patterns
        pattern_id: ID of the pattern to retrieve
        
    Returns:
        Pattern dictionary or None if not found
    """
    if 'patterns' not in patterns:
        return None
    
    return patterns['patterns'].get(pattern_id)


def get_patterns_by_category(patterns: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
    """
    Get all patterns belonging to a specific category.
    
    Args:
        patterns: Dictionary containing all patterns
        category: Category to filter by
        
    Returns:
        List of pattern dictionaries
    """
    if 'patterns' not in patterns:
        return []
    
    return [
        pattern_data 
        for pattern_data in patterns['patterns'].values()
        if pattern_data.get('category') == category
    ]


def get_all_pattern_strings(patterns: Dict[str, Any]) -> List[str]:
    """
    Get a flat list of all pattern strings.
    
    Args:
        patterns: Dictionary containing all patterns
        
    Returns:
        List of all pattern strings
    """
    if 'patterns' not in patterns:
        return []
    
    all_patterns = []
    for pattern_data in patterns['patterns'].values():
        if 'patterns' in pattern_data and isinstance(pattern_data['patterns'], list):
            all_patterns.extend(pattern_data['patterns'])
    
    return all_patterns


def get_pattern_answer(patterns: Dict[str, Any], pattern_id: str) -> Optional[str]:
    """
    Get the default answer for a pattern.
    
    Args:
        patterns: Dictionary containing all patterns
        pattern_id: ID of the pattern
        
    Returns:
        Default answer string or None
    """
    pattern = get_pattern(patterns, pattern_id)
    if pattern:
        return pattern.get('default')
    return None


def get_pattern_numeric_answer(patterns: Dict[str, Any], pattern_id: str) -> Optional[str]:
    """
    Get the numeric default answer for a pattern.
    
    Args:
        patterns: Dictionary containing all patterns
        pattern_id: ID of the pattern
        
    Returns:
        Numeric default answer string or None
    """
    pattern = get_pattern(patterns, pattern_id)
    if pattern:
        return pattern.get('numeric_default') or pattern.get('default')
    return None


def get_pattern_answer_for_input_type(
    patterns: Dict[str, Any],
    pattern_id: str,
    input_type: str
) -> Optional[str]:
    """
    Get the default answer for a pattern based on input type.
    
    This function returns input-type-specific answers when available,
    falling back to the default answer if no specific mapping exists.
    
    Args:
        patterns: Dictionary containing all patterns
        pattern_id: ID of the pattern
        input_type: Type of input (text, radio, checkbox, select, number, etc.)
        
    Returns:
        Answer string appropriate for the input type, or None if pattern not found
        
    Example:
        >>> get_pattern_answer_for_input_type(patterns, 'notice_period', 'radio')
        'Yes'
        >>> get_pattern_answer_for_input_type(patterns, 'notice_period', 'text')
        'Serving Notice Period'
    """
    pattern = get_pattern(patterns, pattern_id)
    if not pattern:
        return None
    
    # Normalize input type
    input_type = input_type.lower().strip()
    
    # Check for input_type_defaults
    input_type_defaults = pattern.get('input_type_defaults', {})
    if input_type_defaults and input_type in input_type_defaults:
        return input_type_defaults[input_type]
    
    # Fallback to numeric_default for number inputs
    if input_type == 'number':
        return pattern.get('numeric_default') or pattern.get('default')
    
    # Fallback to default
    return pattern.get('default')


class PatternLoader:
    """
    High-level pattern loader with caching support.
    
    This class provides a convenient interface for loading and accessing
    patterns with optional caching.
    """
    
    def __init__(self, json_path: Optional[str] = None):
        """
        Initialize the pattern loader.
        
        Args:
            json_path: Path to the patterns JSON file. If None, uses default.
        """
        if json_path is None:
            # Default path relative to this file
            base_dir = Path(__file__).parent.parent.parent
            json_path = base_dir / "config" / "qa_patterns.json"
        
        self.json_path = str(json_path)
        self._patterns: Optional[Dict[str, Any]] = None
        self._validation_errors: List[str] = []
    
    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load patterns from file.
        
        Args:
            force_reload: If True, reload even if already loaded
            
        Returns:
            Dictionary containing patterns
            
        Raises:
            PatternLoadError: If loading fails
            PatternValidationError: If validation fails
        """
        if self._patterns is not None and not force_reload:
            return self._patterns
        
        self._patterns = load_patterns(self.json_path)
        self._validation_errors = validate_patterns(self._patterns)
        
        if self._validation_errors:
            error_msg = "; ".join(self._validation_errors)
            raise PatternValidationError(f"Pattern validation failed: {error_msg}")
        
        return self._patterns
    
    def get_pattern(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific pattern by ID."""
        if self._patterns is None:
            self.load()
        return get_pattern(self._patterns, pattern_id)
    
    def get_patterns_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all patterns in a category."""
        if self._patterns is None:
            self.load()
        return get_patterns_by_category(self._patterns, category)
    
    def get_answer(self, pattern_id: str) -> Optional[str]:
        """Get the default answer for a pattern."""
        if self._patterns is None:
            self.load()
        return get_pattern_answer(self._patterns, pattern_id)
    
    def get_answer_for_input_type(self, pattern_id: str, input_type: str) -> Optional[str]:
        """
        Get the answer for a pattern based on input type.
        
        Args:
            pattern_id: ID of the pattern
            input_type: Type of input (text, radio, checkbox, select, number, etc.)
            
        Returns:
            Answer string appropriate for the input type
        """
        if self._patterns is None:
            self.load()
        return get_pattern_answer_for_input_type(self._patterns, pattern_id, input_type)
    
    def get_all_pattern_strings(self) -> List[str]:
        """Get all pattern strings."""
        if self._patterns is None:
            self.load()
        return get_all_pattern_strings(self._patterns)
    
    @property
    def is_loaded(self) -> bool:
        """Check if patterns have been loaded."""
        return self._patterns is not None
    
    @property
    def validation_errors(self) -> List[str]:
        """Get validation errors from last load."""
        return self._validation_errors.copy()


# Convenience function for one-off loads
def get_loader(json_path: Optional[str] = None) -> PatternLoader:
    """
    Get a PatternLoader instance.
    
    Args:
        json_path: Optional path to patterns file
        
    Returns:
        PatternLoader instance
    """
    return PatternLoader(json_path)
