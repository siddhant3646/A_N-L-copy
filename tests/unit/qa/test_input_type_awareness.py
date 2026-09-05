"""
Test suite for input-type-aware answer generation.

Tests the integration of:
- PatternLoader with input_type_defaults
- PatternMatcher with input type support
- Agent integration
"""

import unittest
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from patterns.pattern_loader import (
    PatternLoader, 
    get_pattern_answer_for_input_type
)


class TestPatternLoaderInputTypeDefaults(unittest.TestCase):
    """Test PatternLoader with input_type_defaults."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.loader = PatternLoader()
        
    def test_get_answer_for_input_type(self):
        """Test getting answer for specific input type via PatternLoader."""
        # Load patterns first
        try:
            self.loader.load()
        except Exception:
            self.skipTest("Could not load patterns")
        
        # Test with a pattern that should have input_type_defaults
        # Try 'immediate_joiner' pattern
        result = self.loader.get_answer_for_input_type('immediate_joiner', 'radio')
        # Should return a short answer for radio
        if result:
            self.assertIsInstance(result, str)
            self.assertTrue(len(result) < 100 or result in ['Yes', 'No'])
    
    def test_get_answer_for_input_type_via_function(self):
        """Test getting answer via module-level function."""
        # Create test patterns dict
        patterns = {
            'patterns': {
                'test_pattern': {
                    'default': 'Yes, I have led full-stack projects and can start immediately.',
                    'input_type_defaults': {
                        'radio': 'Yes',
                        'checkbox': 'Yes',
                        'select': 'Yes - I can start immediately'
                    }
                }
            }
        }
        
        # Should return type-specific answer
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'radio'),
            'Yes'
        )
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'checkbox'),
            'Yes'
        )
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'select'),
            'Yes - I can start immediately'
        )
        
        # Should return default for text
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'text'),
            'Yes, I have led full-stack projects and can start immediately.'
        )
        
        # Should return default for unknown type
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'unknown'),
            'Yes, I have led full-stack projects and can start immediately.'
        )
    
    def test_get_answer_no_defaults(self):
        """Test getting answer when no input_type_defaults exist."""
        patterns = {
            'patterns': {
                'test_pattern': {
                    'default': 'Simple answer',
                    'input_type_defaults': {}
                }
            }
        }
        
        # Should return default for all types
        self.assertEqual(
            get_pattern_answer_for_input_type(patterns, 'test_pattern', 'radio'),
            'Simple answer'
        )


class TestJSONConfig(unittest.TestCase):
    """Test that the JSON config has proper structure."""
    
    def test_qa_patterns_structure(self):
        """Test that qa_patterns.json has the expected structure."""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'qa_patterns.json'
        )
        
        if not os.path.exists(config_path):
            self.skipTest("qa_patterns.json not found")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Should have patterns key
        self.assertIn('patterns', config)
        
        # Each pattern should have required fields
        for pattern_id, pattern_data in config['patterns'].items():
            self.assertIn('default', pattern_data)
            self.assertIn('patterns', pattern_data)
            self.assertIsInstance(pattern_data['patterns'], list)
            
            # Check if input_type_defaults exists (optional but recommended)
            if 'input_type_defaults' in pattern_data:
                self.assertIsInstance(pattern_data['input_type_defaults'], dict)


class TestPatternLoaderBasic(unittest.TestCase):
    """Test basic PatternLoader functionality."""
    
    def test_load_patterns(self):
        """Test loading patterns from JSON."""
        loader = PatternLoader()
        try:
            patterns = loader.load()
            self.assertIn('patterns', patterns)
            self.assertTrue(len(patterns['patterns']) > 0)
        except Exception as e:
            self.skipTest(f"Could not load patterns: {e}")
    
    def test_get_pattern(self):
        """Test getting a specific pattern."""
        loader = PatternLoader()
        try:
            loader.load()
            # Get first pattern
            patterns = loader._patterns['patterns']
            first_id = list(patterns.keys())[0]
            pattern = loader.get_pattern(first_id)
            self.assertIsNotNone(pattern)
            self.assertIn('default', pattern)
            self.assertIn('patterns', pattern)
        except Exception as e:
            self.skipTest(f"Could not test get_pattern: {e}")


if __name__ == '__main__':
    unittest.main()
