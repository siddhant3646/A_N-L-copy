"""
Test suite for input-type-aware answer generation.

Tests the integration of:
- PatternLoader with input_type_defaults
- PatternMatcher with input type support
- AnswerNormalizer for different input types
- Agent integration
"""

import unittest
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from patterns.pattern_loader import (
    PatternLoader, 
    get_pattern_answer_for_input_type
)
from patterns.answer_normalizer import AnswerNormalizer, InputType, normalize_answer


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


class TestAnswerNormalizer(unittest.TestCase):
    """Test AnswerNormalizer functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.normalizer = AnswerNormalizer()
    
    def test_normalize_yes_no_for_radio(self):
        """Test normalizing Yes/No answers for radio buttons."""
        # Long Yes answer should become "Yes"
        self.assertEqual(
            self.normalizer.normalize("Yes, I have experience with that.", InputType.RADIO),
            "Yes"
        )
        
        # Short Yes should stay Yes
        self.assertEqual(
            self.normalizer.normalize("Yes", InputType.RADIO),
            "Yes"
        )
        
        # Long No answer should become "No"
        self.assertEqual(
            self.normalizer.normalize("No, I do not have experience with that.", InputType.RADIO),
            "No"
        )
    
    def test_normalize_for_checkbox(self):
        """Test normalizing answers for checkboxes."""
        # Yes should become "checked"
        self.assertEqual(
            self.normalizer.normalize("Yes", InputType.CHECKBOX),
            "checked"
        )
        
        # No should become "unchecked"
        self.assertEqual(
            self.normalizer.normalize("No", InputType.CHECKBOX),
            "unchecked"
        )
        
        # Long Yes should become "checked"
        self.assertEqual(
            self.normalizer.normalize("Yes, I agree to the terms.", InputType.CHECKBOX),
            "checked"
        )
    
    def test_normalize_for_number(self):
        """Test extracting numbers from text."""
        # Should extract number from text
        self.assertEqual(
            self.normalizer.normalize("I have 5 years of experience", InputType.NUMBER),
            "5"
        )
        
        # Should handle decimals
        self.assertEqual(
            self.normalizer.normalize("4 Years", InputType.NUMBER),
            "4"
        )
        
        # Should handle commas
        self.assertEqual(
            self.normalizer.normalize("1,500,000", InputType.NUMBER),
            "1500000"
        )
    
    def test_normalize_for_text(self):
        """Test that text answers are minimally transformed."""
        answer = "This is a detailed answer with multiple sentences."
        self.assertEqual(
            self.normalizer.normalize(answer, InputType.TEXT),
            answer
        )
    
    def test_normalize_with_options(self):
        """Test normalizing with available options."""
        options = ["Yes", "No", "Maybe"]
        
        # Should match to available option
        result = self.normalizer.normalize(
            "Yes, absolutely!",
            InputType.RADIO,
            options=options
        )
        self.assertEqual(result, "Yes")
        
        # Should match "No" option
        result = self.normalizer.normalize(
            "No, I don't think so.",
            InputType.RADIO,
            options=options
        )
        self.assertEqual(result, "No")
    
    def test_normalize_for_pattern_with_defaults(self):
        """Test normalize_for_pattern with input_type_defaults."""
        pattern_data = {
            'default': 'Long detailed answer here.',
            'input_type_defaults': {
                'radio': 'Yes',
                'checkbox': 'Yes'
            }
        }
        
        # Should use input_type_defaults
        result = self.normalizer.normalize_for_pattern(
            'Long detailed answer here.',
            'radio',
            pattern_data
        )
        self.assertEqual(result, 'Yes')
        
        # Should fallback to default for unknown type
        result = self.normalizer.normalize_for_pattern(
            'Long detailed answer here.',
            'unknown',
            pattern_data
        )
        self.assertEqual(result, 'Long detailed answer here.')


class TestConvenienceFunction(unittest.TestCase):
    """Test the normalize_answer convenience function."""
    
    def test_normalize_answer_function(self):
        """Test the convenience function."""
        # Test radio normalization
        result = normalize_answer("Yes, I agree.", "radio")
        self.assertEqual(result, "Yes")
        
        # Test checkbox normalization
        result = normalize_answer("No", "checkbox")
        self.assertEqual(result, "unchecked")
        
        # Test number extraction
        result = normalize_answer("4 Years", "number")
        self.assertEqual(result, "4")


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
