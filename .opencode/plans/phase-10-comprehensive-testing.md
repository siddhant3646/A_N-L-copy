# Phase 10: Comprehensive Unit Testing

## Objective
Add comprehensive unit tests with heavy mocking for all new modules.

## Current State
- Existing tests: 50 lines in `tests/test_qa_updates.py`
- Test coverage: Minimal

## Testing Strategy

### 10.1 Test Fixtures
**File**: `tests/conftest.py`

**Fixtures**:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_page():
    """Create a mocked Playwright page"""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    page.click = AsyncMock()
    page.goto = AsyncMock()
    page.url = "https://example.com"
    page.content = AsyncMock(return_value="<html></html>")
    return page

@pytest.fixture
def mock_browser():
    """Create a mocked Browser instance"""
    browser = MagicMock()
    browser.get_current_page = AsyncMock()
    browser.start = AsyncMock()
    browser.stop = AsyncMock()
    return browser

@pytest.fixture
def mock_platform_handlers():
    """Create mocked platform handlers"""
    return {
        "linkedin": AsyncMock(),
        "naukri": AsyncMock(),
        "instahyre": AsyncMock()
    }

@pytest.fixture
def sample_patterns():
    """Sample Q&A patterns for testing"""
    return {
        "salary": {
            "patterns": ["current salary", "what is your ctc"],
            "category": "salary",
            "default": "13.5 LPA"
        },
        "experience": {
            "patterns": ["years of experience", "total experience"],
            "category": "experience",
            "default": "4"
        }
    }
```

### 10.2 Test Coverage Goals

| Module | Target Coverage | Test File |
|--------|----------------|-----------|
| Pattern Loader | 95% | test_pattern_loader.py |
| Pattern Matcher | 95% | test_pattern_matcher.py |
| Browser Actions | 90% | test_browser_actions.py |
| Human Simulation | 90% | test_human_simulation.py |
| Platform Handlers | 85% | test_*_handler.py |
| Agent State | 95% | test_state.py |
| Rate Limiter | 95% | test_rate_limiter.py |
| Agent Executor | 80% | test_executor.py |
| Profile Manager | 95% | test_profile_manager.py |
| JS Loader | 90% | test_js_loader.py |

### 10.3 Key Test Scenarios

**Pattern Matching**:
- Exact matches
- Fuzzy matches
- No matches
- Multi-word queries
- Special characters

**Browser Actions**:
- Successful clicks
- Retry on failure
- Timeout handling
- Element not found
- JavaScript errors

**Platform Handlers**:
- Login detection
- Rate limit detection
- Form filling success
- Form filling failure
- Task completion

**Agent State**:
- State initialization
- Step incrementing
- Result tracking
- Loop detection
- State reset

**Rate Limiter**:
- Setting rate limits
- Checking rate limits
- Expiration handling
- Multiple platforms

### 10.4 Test Configuration
**File**: `pytest.ini`
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --cov=src
    --cov-report=term-missing
    --cov-report=html
markers =
    unit: Unit tests (fast, no external deps)
    integration: Integration tests
    slow: Tests that take >5 seconds
```

## Test Files to Create
- [ ] Update: `tests/conftest.py` (comprehensive fixtures)
- [ ] Create: `tests/unit/patterns/test_pattern_loader.py` (10+ tests)
- [ ] Create: `tests/unit/patterns/test_pattern_matcher.py` (15+ tests)
- [ ] Create: `tests/unit/browser/test_interactions.py` (20+ tests)
- [ ] Create: `tests/unit/browser/test_human_simulation.py` (10+ tests)
- [ ] Create: `tests/unit/browser/test_browser_actions.py` (25+ tests)
- [ ] Create: `tests/unit/platforms/test_interface.py` (8+ tests)
- [ ] Create: `tests/unit/platforms/test_linkedin_handler.py` (15+ tests)
- [ ] Create: `tests/unit/platforms/test_naukri_handler.py` (15+ tests)
- [ ] Create: `tests/unit/platforms/test_instahyre_handler.py` (10+ tests)
- [ ] Create: `tests/unit/question/test_classifier.py` (20+ tests)
- [ ] Create: `tests/unit/question/test_fingerprint.py` (15+ tests)
- [ ] Create: `tests/unit/question/test_matching.py` (20+ tests)
- [ ] Create: `tests/unit/logging/test_logging.py` (12+ tests)
- [ ] Create: `tests/unit/agent/test_state.py` (15+ tests)
- [ ] Create: `tests/unit/agent/test_rate_limiter.py` (12+ tests)
- [ ] Create: `tests/unit/agent/test_executor.py` (15+ tests)
- [ ] Create: `tests/unit/core/test_profile_manager.py` (10+ tests)
- [ ] Create: `tests/unit/sentinel/test_js_loader.py` (8+ tests)
- [ ] Create: `tests/integration/test_platform_integration.py` (5+ tests)

## Success Criteria
- [ ] >200 total test cases
- [ ] >85% overall code coverage
- [ ] All tests pass
- [ ] Tests run in <60 seconds
- [ ] No external dependencies in unit tests (all mocked)

## Estimated Time
20-30 hours (can be done in parallel with other phases)

## Dependencies
- All previous phases

## Risk Mitigation
- Write tests as modules are created (don't wait until end)
- Use TDD approach when possible
- Keep tests focused and isolated
- Use fixtures to avoid duplication
- Run tests frequently during development
