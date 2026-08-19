"""
Tests for pattern_loader module.
"""

import json
import os
import pytest
from src.patterns.pattern_loader import (
    PatternLoader,
    load_patterns,
    validate_patterns,
    get_pattern,
    get_patterns_by_category,
    get_pattern_answer,
    get_all_pattern_strings,
    PatternLoadError,
    PatternValidationError,
)


class TestLoadPatterns:
    """Tests for load_patterns function."""
    
    def test_load_valid_json_file(self, temp_qa_patterns_file):
        """Test loading a valid JSON pattern file."""
        patterns = load_patterns(temp_qa_patterns_file)
        
        assert patterns is not None
        assert 'version' in patterns
        assert 'patterns' in patterns
    
    def test_load_nonexistent_file(self):
        """Test that loading a nonexistent file raises PatternLoadError."""
        with pytest.raises(PatternLoadError) as exc_info:
            load_patterns("/nonexistent/path/patterns.json")
        
        assert "not found" in str(exc_info.value).lower()
    
    def test_load_invalid_json(self, temp_directory):
        """Test that loading invalid JSON raises PatternLoadError."""
        invalid_file = os.path.join(temp_directory, "invalid.json")
        with open(invalid_file, "w") as f:
            f.write("{invalid json content}")
        
        with pytest.raises(PatternLoadError) as exc_info:
            load_patterns(invalid_file)
        
        assert "invalid json" in str(exc_info.value).lower()


class TestValidatePatterns:
    """Tests for validate_patterns function."""
    
    def test_valid_patterns(self, sample_qa_patterns):
        """Test validation of valid patterns."""
        patterns = {
            "version": "1.0",
            "patterns": sample_qa_patterns
        }
        
        errors = validate_patterns(patterns)
        assert len(errors) == 0
    
    def test_missing_patterns_key(self):
        """Test validation fails without 'patterns' key."""
        patterns = {"version": "1.0"}
        
        errors = validate_patterns(patterns)
        assert len(errors) == 1
        assert "missing required key" in errors[0].lower()
    
    def test_patterns_not_dict(self):
        """Test validation fails when patterns is not a dict."""
        patterns = {"patterns": []}
        
        errors = validate_patterns(patterns)
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0].lower()
    
    def test_pattern_missing_fields(self):
        """Test validation catches missing fields in patterns."""
        patterns = {
            "patterns": {
                "incomplete": {
                    "patterns": ["test"]
                    # Missing 'category' and 'default'
                }
            }
        }
        
        errors = validate_patterns(patterns)
        assert len(errors) >= 2
        assert any("missing" in e.lower() and "category" in e.lower() for e in errors)
        assert any("missing" in e.lower() and "default" in e.lower() for e in errors)
    
    def test_pattern_patterns_not_list(self):
        """Test validation catches when patterns field is not a list."""
        patterns = {
            "patterns": {
                "bad": {
                    "patterns": "not a list",
                    "category": "test",
                    "default": "answer"
                }
            }
        }
        
        errors = validate_patterns(patterns)
        assert any("must be a list" in e.lower() for e in errors)


class TestGetPattern:
    """Tests for get_pattern function."""
    
    def test_get_existing_pattern(self, sample_qa_patterns):
        """Test getting an existing pattern."""
        patterns = {"patterns": sample_qa_patterns}
        
        pattern = get_pattern(patterns, "salary")
        assert pattern is not None
        assert pattern["default"] == "13.5 LPA"
    
    def test_get_nonexistent_pattern(self, sample_qa_patterns):
        """Test getting a nonexistent pattern returns None."""
        patterns = {"patterns": sample_qa_patterns}
        
        pattern = get_pattern(patterns, "nonexistent")
        assert pattern is None
    
    def test_get_pattern_no_patterns_key(self):
        """Test getting pattern when no patterns key exists."""
        pattern = get_pattern({}, "salary")
        assert pattern is None


class TestGetPatternsByCategory:
    """Tests for get_patterns_by_category function."""
    
    def test_get_by_existing_category(self, sample_qa_patterns):
        """Test getting patterns by existing category."""
        patterns = {"patterns": sample_qa_patterns}
        
        salary_patterns = get_patterns_by_category(patterns, "salary")
        assert len(salary_patterns) == 1
        assert salary_patterns[0]["default"] == "13.5 LPA"
    
    def test_get_by_nonexistent_category(self, sample_qa_patterns):
        """Test getting patterns by nonexistent category returns empty list."""
        patterns = {"patterns": sample_qa_patterns}
        
        result = get_patterns_by_category(patterns, "nonexistent")
        assert result == []
    
    def test_get_by_category_no_patterns_key(self):
        """Test getting by category when no patterns key exists."""
        result = get_patterns_by_category({}, "salary")
        assert result == []


class TestGetPatternAnswer:
    """Tests for get_pattern_answer function."""
    
    def test_get_existing_answer(self, sample_qa_patterns):
        """Test getting answer for existing pattern."""
        patterns = {"patterns": sample_qa_patterns}
        
        answer = get_pattern_answer(patterns, "experience")
        assert answer == "4.2"
    
    def test_get_nonexistent_answer(self, sample_qa_patterns):
        """Test getting answer for nonexistent pattern returns None."""
        patterns = {"patterns": sample_qa_patterns}
        
        answer = get_pattern_answer(patterns, "nonexistent")
        assert answer is None


class TestGetAllPatternStrings:
    """Tests for get_all_pattern_strings function."""
    
    def test_get_all_strings(self, sample_qa_patterns):
        """Test getting all pattern strings."""
        patterns = {"patterns": sample_qa_patterns}
        
        strings = get_all_pattern_strings(patterns)
        
        assert len(strings) > 0
        assert "current salary" in strings
        assert "years of experience" in strings
    
    def test_get_all_strings_no_patterns(self):
        """Test getting strings when no patterns exist."""
        strings = get_all_pattern_strings({})
        assert strings == []


class TestPatternLoader:
    """Tests for PatternLoader class."""
    
    def test_init_with_default_path(self):
        """Test initialization with default path."""
        loader = PatternLoader()
        assert loader.json_path is not None
        assert not loader.is_loaded
    
    def test_init_with_custom_path(self, temp_qa_patterns_file):
        """Test initialization with custom path."""
        loader = PatternLoader(temp_qa_patterns_file)
        assert loader.json_path == temp_qa_patterns_file
    
    def test_load_valid_patterns(self, temp_qa_patterns_file):
        """Test loading valid patterns."""
        loader = PatternLoader(temp_qa_patterns_file)
        patterns = loader.load()
        
        assert patterns is not None
        assert loader.is_loaded
    
    def test_load_caches_result(self, temp_qa_patterns_file):
        """Test that load caches the result."""
        loader = PatternLoader(temp_qa_patterns_file)
        
        patterns1 = loader.load()
        patterns2 = loader.load()
        
        assert patterns1 is patterns2  # Same object (cached)
    
    def test_force_reload(self, temp_qa_patterns_file):
        """Test force reload option."""
        loader = PatternLoader(temp_qa_patterns_file)
        
        patterns1 = loader.load()
        patterns2 = loader.load(force_reload=True)
        
        assert patterns1 is not patterns2  # Different objects
    
    def test_load_invalid_patterns_raises(self, temp_directory):
        """Test that loading invalid patterns raises validation error."""
        invalid_patterns = {
            "patterns": {
                "incomplete": {
                    "patterns": ["test"]
                    # Missing required fields
                }
            }
        }
        
        invalid_file = os.path.join(temp_directory, "invalid.json")
        with open(invalid_file, "w") as f:
            json.dump(invalid_patterns, f)
        
        loader = PatternLoader(invalid_file)
        
        with pytest.raises(PatternValidationError) as exc_info:
            loader.load()
        
        assert "validation failed" in str(exc_info.value).lower()
    
    def test_get_pattern_after_load(self, temp_qa_patterns_file):
        """Test getting pattern after loading."""
        loader = PatternLoader(temp_qa_patterns_file)
        
        pattern = loader.get_pattern("test_pattern")
        assert pattern is not None
        assert pattern["default"] == "test answer"
    
    def test_get_answer(self, temp_qa_patterns_file):
        """Test getting answer through loader."""
        loader = PatternLoader(temp_qa_patterns_file)
        
        answer = loader.get_answer("test_pattern")
        assert answer == "test answer"
    
    def test_validation_errors_property(self, temp_qa_patterns_file):
        """Test validation_errors property."""
        loader = PatternLoader(temp_qa_patterns_file)
        loader.load()
        
        errors = loader.validation_errors
        assert isinstance(errors, list)
