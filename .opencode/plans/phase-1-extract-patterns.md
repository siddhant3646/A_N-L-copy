# Phase 1: Extract Patterns Module

## Objective
Move QA patterns from agent.py to JSON-only storage and create pattern loading/matching logic.

## Current State
- Patterns defined in `agent.py` lines 25-511 (KNOWN_QA_PATTERNS dict)
- Duplicate patterns in `config/qa_patterns.json`
- Pattern matching logic in `_fuzzy_match_question()` lines 586-894

## Implementation Steps

### 1.1 Consolidate Patterns to JSON
**File**: `config/qa_patterns.json` (exists, needs updates)

**Actions**:
- Merge patterns from agent.py KNOWN_QA_PATTERNS into JSON
- Ensure all patterns have required fields:
  - `patterns`: List of question variations
  - `category`: Question category
  - `default`: Default answer
  - `numeric_default`: Optional numeric version

### 1.2 Create Pattern Loader
**File**: `src/patterns/pattern_loader.py`

**Functions**:
```python
load_patterns(json_path: str) -> Dict[str, Any]
get_pattern(pattern_id: str) -> Optional[Dict]
get_patterns_by_category(category: str) -> List[Dict]
validate_patterns(patterns: Dict) -> List[str]  # Returns validation errors
```

### 1.3 Create Pattern Matcher
**File**: `src/patterns/pattern_matcher.py`

**Class**: `PatternMatcher`

**Methods**:
```python
__init__(patterns: Dict[str, Any])
fuzzy_match(question: str) -> Tuple[Optional[str], float]
keyword_match(question: str) -> Tuple[Optional[str], float]
get_confidence_score(question: str, pattern_id: str) -> float
```

### 1.4 Remove Duplicates
- Delete KNOWN_QA_PATTERNS from agent.py
- Import patterns from JSON in agent.py

## Testing Strategy

### Unit Tests: `tests/unit/patterns/test_pattern_loader.py`
```python
def test_load_valid_patterns():
    """Test loading valid JSON patterns"""
    patterns = load_patterns("config/qa_patterns.json")
    assert patterns is not None
    assert "version" in patterns
    assert "patterns" in patterns

def test_load_invalid_json():
    """Test handling of invalid JSON"""
    with pytest.raises(json.JSONDecodeError):
        load_patterns("invalid.json")

def test_get_pattern_by_id():
    """Test retrieving specific pattern"""
    patterns = load_patterns("config/qa_patterns.json")
    pattern = get_pattern(patterns, "current_salary")
    assert pattern is not None
    assert pattern["default"] == "13.5 LPA"
```

### Unit Tests: `tests/unit/patterns/test_pattern_matcher.py`
```python
class TestPatternMatcher:
    def setup_method(self):
        self.patterns = {
            "salary": {"patterns": ["current salary"], "default": "13.5 LPA"},
            "experience": {"patterns": ["years of experience"], "default": "4"}
        }
        self.matcher = PatternMatcher(self.patterns)
    
    def test_exact_match(self):
        answer, confidence = self.matcher.fuzzy_match("current salary")
        assert answer == "13.5 LPA"
        assert confidence == 1.0
    
    def test_fuzzy_match_similar(self):
        answer, confidence = self.matcher.fuzzy_match("what is your current salary")
        assert answer == "13.5 LPA"
        assert confidence > 0.8
    
    def test_no_match(self):
        answer, confidence = self.matcher.fuzzy_match("random question")
        assert answer is None
        assert confidence == 0.0
```

## Files to Create/Modify
- [ ] Update: `config/qa_patterns.json` (merge patterns)
- [ ] Create: `src/patterns/__init__.py`
- [ ] Create: `src/patterns/pattern_loader.py`
- [ ] Create: `src/patterns/pattern_matcher.py`
- [ ] Create: `tests/unit/patterns/test_pattern_loader.py`
- [ ] Create: `tests/unit/patterns/test_pattern_matcher.py`
- [ ] Modify: `src/sentinel/agent.py` (remove KNOWN_QA_PATTERNS, use loader)

## Success Criteria
- [ ] All patterns consolidated in JSON
- [ ] Pattern loader working correctly
- [ ] Pattern matcher achieves >95% accuracy on test questions
- [ ] All tests pass
- [ ] agent.py lines reduced by ~500 lines

## Estimated Time
4-6 hours

## Dependencies
- Phase 0 (Testing Infrastructure)

## Risk Mitigation
- Keep backup of original agent.py
- Run existing tests after each change
- Validate pattern matching on sample questions before/after
