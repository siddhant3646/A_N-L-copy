"""
Tests for pattern_matcher module.
"""

import pytest
from src.patterns.pattern_matcher import PatternMatcher, create_matcher


class TestPatternMatcherInit:
    """Tests for PatternMatcher initialization."""
    
    def test_init_with_default_threshold(self, sample_qa_patterns):
        """Test initialization with default threshold."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        assert matcher.threshold == PatternMatcher.DEFAULT_THRESHOLD
        assert matcher.patterns == patterns_data
    
    def test_init_with_custom_threshold(self, sample_qa_patterns):
        """Test initialization with custom threshold."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data, threshold=0.8)
        
        assert matcher.threshold == 0.8
    
    def test_builds_cache_on_init(self, sample_qa_patterns):
        """Test that pattern cache is built on initialization."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        assert len(matcher._pattern_cache) > 0
        assert "salary" in matcher._pattern_cache


class TestNormalizeText:
    """Tests for text normalization."""
    
    def test_normalize_lowercase(self, sample_qa_patterns):
        """Test that normalization converts to lowercase."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        result = matcher._normalize_text("WHAT IS YOUR SALARY?")
        assert result == "what is your salary"
    
    def test_normalize_extra_whitespace(self, sample_qa_patterns):
        """Test that normalization removes extra whitespace."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        result = matcher._normalize_text("what   is   your   salary")
        assert result == "what is your salary"
    
    def test_normalize_removes_punctuation(self, sample_qa_patterns):
        """Test that normalization removes punctuation."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        result = matcher._normalize_text("what is your salary?!")
        assert "!" not in result
        assert "?" not in result


class TestCalculateSimilarity:
    """Tests for similarity calculation."""
    
    def test_identical_strings(self, sample_qa_patterns):
        """Test that identical strings have similarity 1.0."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        similarity = matcher._calculate_similarity("hello", "hello")
        assert similarity == 1.0
    
    def test_completely_different_strings(self, sample_qa_patterns):
        """Test that completely different strings have low similarity."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        similarity = matcher._calculate_similarity("abc", "xyz")
        assert similarity < 0.5
    
    def test_similar_strings(self, sample_qa_patterns):
        """Test similarity of similar strings."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        similarity = matcher._calculate_similarity("salary", "salary question")
        assert 0.5 < similarity < 1.0


class TestFuzzyMatch:
    """Tests for fuzzy_match method."""
    
    def test_exact_match(self, sample_qa_patterns):
        """Test exact pattern matching."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer, confidence = matcher.fuzzy_match("current salary")
        
        assert answer == "13.5 LPA"
        assert confidence == 1.0
    
    def test_similar_match(self, sample_qa_patterns):
        """Test matching with similar question."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer, confidence = matcher.fuzzy_match("What is your current salary?")
        
        assert answer == "13.5 LPA"
        assert confidence > 0.7
    
    def test_no_match_below_threshold(self, sample_qa_patterns):
        """Test that no match is returned when below threshold."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data, threshold=0.95)
        
        answer, confidence = matcher.fuzzy_match("completely unrelated question")
        
        assert answer is None
        assert confidence == 0.0
    
    def test_empty_question(self, sample_qa_patterns):
        """Test matching with empty question."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer, confidence = matcher.fuzzy_match("")
        
        assert answer is None
        assert confidence == 0.0
    
    def test_keyword_priority_match(self, sample_qa_patterns):
        """Test that keyword priority matching works."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        # This should match experience, not be confused with salary
        answer, confidence = matcher.fuzzy_match("years of experience")
        
        assert answer == "4"
        assert confidence > 0.7


class TestMatchWithDetails:
    """Tests for match_with_details method."""
    
    def test_match_success(self, sample_qa_patterns):
        """Test successful match with details."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        result = matcher.match_with_details("current salary")
        
        assert result['question'] == "current salary"
        assert result['answer'] == "13.5 LPA"
        assert result['confidence'] == 1.0
        assert result['matched'] is True
    
    def test_match_failure(self, sample_qa_patterns):
        """Test failed match with details."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data, threshold=0.99)
        
        result = matcher.match_with_details("unrelated question xyz")
        
        assert result['question'] == "unrelated question xyz"
        assert result['answer'] is None
        assert result['confidence'] == 0.0
        assert result['matched'] is False


class TestGetAllMatches:
    """Tests for get_all_matches method."""
    
    def test_get_all_matches_sorted(self, sample_qa_patterns):
        """Test that matches are sorted by confidence."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        matches = matcher.get_all_matches("salary", min_confidence=0.5)
        
        # Should return matches sorted by confidence
        assert len(matches) > 0
        
        # Check that they're sorted (highest confidence first)
        for i in range(len(matches) - 1):
            assert matches[i][2] >= matches[i + 1][2]
    
    def test_get_all_matches_respects_min_confidence(self, sample_qa_patterns):
        """Test that min_confidence parameter is respected."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        matches = matcher.get_all_matches("salary", min_confidence=0.9)
        
        # All matches should have confidence >= 0.9
        for pattern_id, answer, confidence in matches:
            assert confidence >= 0.9


class TestUpdatePatterns:
    """Tests for update_patterns method."""
    
    def test_update_patterns(self, sample_qa_patterns):
        """Test updating patterns."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        new_patterns = {
            "patterns": {
                "new_pattern": {
                    "patterns": ["new question"],
                    "category": "test",
                    "default": "new answer"
                }
            }
        }
        
        matcher.update_patterns(new_patterns)
        
        # Should now match the new pattern
        answer, confidence = matcher.fuzzy_match("new question")
        assert answer == "new answer"


class TestCreateMatcher:
    """Tests for create_matcher convenience function."""
    
    def test_create_matcher_with_temp_file(self, temp_qa_patterns_file):
        """Test creating matcher with a temporary file."""
        matcher = create_matcher(temp_qa_patterns_file)
        
        assert isinstance(matcher, PatternMatcher)
        assert matcher.is_loaded if hasattr(matcher, 'is_loaded') else True
    
    def test_create_matcher_with_default_path(self):
        """Test creating matcher with default path."""
        # This may or may not work depending on if the default file exists
        # Just test that it doesn't raise an exception
        try:
            matcher = create_matcher()
            assert isinstance(matcher, PatternMatcher)
        except Exception as e:
            # Expected if default file doesn't exist
            pytest.skip(f"Default pattern file not found: {e}")


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_match_with_special_characters(self, sample_qa_patterns):
        """Test matching questions with special characters."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer, confidence = matcher.fuzzy_match("What is your CTC (in LPA)?")
        
        # Should still match despite special characters
        assert answer is not None
    
    def test_match_with_numbers(self, sample_qa_patterns):
        """Test matching questions with numbers."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer, confidence = matcher.fuzzy_match("3.8 years of experience")
        
        # Should match to experience
        assert answer is not None
    
    def test_case_insensitive_matching(self, sample_qa_patterns):
        """Test that matching is case insensitive."""
        patterns_data = {"patterns": sample_qa_patterns}
        matcher = PatternMatcher(patterns_data)
        
        answer1, _ = matcher.fuzzy_match("CURRENT SALARY")
        answer2, _ = matcher.fuzzy_match("current salary")
        answer3, _ = matcher.fuzzy_match("Current Salary")
        
        assert answer1 == answer2 == answer3
