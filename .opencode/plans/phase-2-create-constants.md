# Phase 2: Create Constants Module

## Objective
Extract magic strings and constants into a centralized constants module.

## Current State
- Magic strings scattered throughout agent.py and run.py
- Platform identifiers hardcoded
- Result codes defined inline
- Thresholds and limits defined as class attributes

## Implementation Steps

### 2.1 Create Constants Module
**File**: `src/core/constants.py`

**Content**:
```python
# Platform Identifiers
PLATFORM_NAUKRI = "naukri"
PLATFORM_LINKEDIN = "linkedin"
PLATFORM_INSTAHYRE = "instahyre"
PLATFORM_DEFAULT = "default"
ALL_PLATFORMS = [PLATFORM_NAUKRI, PLATFORM_LINKEDIN, PLATFORM_INSTAHYRE]

# Result Codes
RESULT_TASK_COMPLETE = "TASK_COMPLETE"
RESULT_SUCCESS = "SUCCESS"
RESULT_RATE_LIMITED = "RATE_LIMITED"
RESULT_LOGIN_REQUIRED = "LOGIN_REQUIRED"
RESULT_ERROR = "ERROR"
RESULT_CONTINUE = "CONTINUE"

# Step Limits
MAX_STEPS_LINKEDIN = 120
MAX_STEPS_DEFAULT = 50
MEMORY_CLEANUP_INTERVAL = 50

# Matching Thresholds
FUZZY_MATCH_THRESHOLD = 0.6
MIN_CONFIDENCE_SCORE = 0.7

# Rate Limiting
LINKEDIN_RATE_LIMIT_HOURS = 24
NAUKRI_RATE_LIMIT_HOURS = 12

# File Paths
SCREENSHOT_DIR = "~/Desktop/sentinel_errors"
UNKNOWN_QUESTIONS_LOG = "~/Desktop/sentinel_errors/unknown_questions.log"
ALL_QUESTIONS_LOG = "~/Desktop/sentinel_errors/all_questions.log"
METRICS_LOG = "~/Desktop/sentinel_errors/metrics.jsonl"

# Selectors (will move to platform-specific files in Phase 5)
# For now, keep as placeholders
```

### 2.2 Update Existing Files
Replace magic strings with constants in:
- `src/sentinel/agent.py`
- `src/sentinel/run.py`
- `src/sentinel/question_classifier.py`

## Testing Strategy

### Unit Tests: `tests/unit/core/test_constants.py`
```python
def test_platform_identifiers():
    """Test platform constants are correct"""
    assert PLATFORM_NAUKRI == "naukri"
    assert PLATFORM_LINKEDIN == "linkedin"
    assert PLATFORM_INSTAHYRE == "instahyre"

def test_result_codes_unique():
    """Test all result codes are unique"""
    codes = [RESULT_TASK_COMPLETE, RESULT_SUCCESS, RESULT_RATE_LIMITED, 
             RESULT_LOGIN_REQUIRED, RESULT_ERROR, RESULT_CONTINUE]
    assert len(codes) == len(set(codes))

def test_step_limits_positive():
    """Test step limits are positive integers"""
    assert MAX_STEPS_LINKEDIN > 0
    assert MAX_STEPS_DEFAULT > 0
    assert isinstance(MAX_STEPS_LINKEDIN, int)
```

## Files to Create/Modify
- [ ] Create: `src/core/constants.py`
- [ ] Modify: `src/sentinel/agent.py` (use constants)
- [ ] Modify: `src/sentinel/run.py` (use constants)
- [ ] Create: `tests/unit/core/test_constants.py`

## Success Criteria
- [ ] No magic strings remain in agent.py (except platform-specific selectors)
- [ ] All tests pass
- [ ] Constants module is imported correctly

## Estimated Time
2-3 hours

## Dependencies
- None (can be done in parallel with Phase 1)

## Risk Mitigation
- Use IDE find-and-replace to catch all instances
- Review changes carefully to avoid typos
- Run tests after each file modification
