# Phase 0: Testing Infrastructure Setup

## Objective
Establish the testing framework and directory structure before beginning modularization.

## Tasks

### 0.1 Create Test Directory Structure
```bash
mkdir -p tests/unit/{patterns,browser,platforms,question,logging,agent,core}
mkdir -p tests/integration
mkdir -p tests/e2e
```

### 0.2 Install Dependencies
Add to `requirements-dev.txt`:
```
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-mock>=3.10.0
pytest-cov>=4.0.0
```

### 0.3 Create pytest.ini

### 0.4 Create conftest.py with Shared Fixtures

### 0.5 Create Initial Test Files

## Key Fixtures Needed

1. **Mock Browser Objects**
   - `mock_page`: AsyncMock Playwright page
   - `mock_context`: AsyncMock browser context
   - `mock_browser`: AsyncMock browser instance

2. **Mock Platform Handlers**
   - `mock_linkedin_handler`
   - `mock_naukri_handler`
   - `mock_instahyre_handler`

3. **Test Data**
   - `sample_questions`: List of question-answer pairs
   - `sample_patterns`: Q&A patterns for testing
   - `mock_agent_state`: Pre-configured agent state

## Success Criteria
- [ ] All test directories created
- [ ] pytest configuration working
- [ ] Fixtures can be imported in all test files
- [ ] Can run `pytest --collect-only` without errors

## Estimated Time
1-2 hours
