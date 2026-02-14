# Phase 8: Refactor Agent Module

## Objective
Split agent.py into focused modules: state, executor, and rate_limiter.

## Current State
- agent.py: ~4950 lines
- Contains: state, execution logic, rate limiting, logging, metrics, browser actions

## Implementation Steps

### 8.1 Create Agent State Module
**File**: `src/agent/state.py`

**Content**:
```python
@dataclass
class AgentState:
    """Agent state management"""
    step_count: int = 0
    task_complete: bool = False
    errors: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_result: str = ""
    linkedin_applications: int = 0
    naukri_applications: int = 0
    same_result_count: int = 0
    steps_since_cleanup: int = 0
    logged_questions: Set[str] = field(default_factory=set)
    all_logged_questions: Set[str] = field(default_factory=set)
    
    def reset(self):
        """Reset state for new task"""
    
    def increment_step(self):
        """Increment step counter"""
    
    def track_result(self, result: str):
        """Track result for loop detection"""
```

### 8.2 Create Rate Limiter Module
**File**: `src/agent/rate_limiter.py`

**Content**:
```python
class RateLimiter:
    """Rate limiting for platforms"""
    
    def __init__(self):
        self.linkedin_rate_limit_until: Optional[datetime] = None
        self.naukri_rate_limit_until: Optional[datetime] = None
    
    def is_rate_limited(self, platform: str) -> bool
    
    def set_rate_limit(self, platform: str, duration_hours: float)
    
    def get_remaining_time(self, platform: str) -> Optional[timedelta]
    
    def clear_rate_limit(self, platform: str)
```

### 8.3 Create Agent Executor Module
**File**: `src/agent/executor.py`

**Content**:
```python
class AgentExecutor:
    """Main agent execution - orchestrates platform handlers"""
    
    def __init__(
        self,
        browser,
        platform_handlers: Dict[str, BasePlatformHandler],
        rate_limiter: RateLimiter,
        state: AgentState
    ):
        self.browser = browser
        self.platform_handlers = platform_handlers
        self.rate_limiter = rate_limiter
        self.state = state
    
    async def run(self, task_description: str) -> bool
        """Main execution loop"""
    
    async def _execute_task(self, task_context: dict) -> str
    
    async def _handle_result(self, result: str, platform: str) -> str
    
    def _get_platform_from_task(self, task: str) -> str
```

### 8.4 Refactor Original agent.py
**File**: `src/sentinel/agent.py`

**Content**: Reduce to ~500 lines
- Remove extracted methods
- Import from new modules
- Keep public API (`create_agent()`)
- Delegate to AgentExecutor

## Testing Strategy

### Unit Tests: `tests/unit/agent/test_state.py`
```python
class TestAgentState:
    def test_initial_state(self):
        state = AgentState()
        assert state.step_count == 0
        assert not state.task_complete
    
    def test_increment_step(self):
        state = AgentState()
        state.increment_step()
        assert state.step_count == 1
    
    def test_track_result_loop_detection(self):
        state = AgentState()
        state.track_result("continue")
        state.track_result("continue")
        state.track_result("continue")
        assert state.same_result_count == 3
```

### Unit Tests: `tests/unit/agent/test_rate_limiter.py`
```python
class TestRateLimiter:
    def test_not_rate_limited_initially(self):
        limiter = RateLimiter()
        assert not limiter.is_rate_limited("linkedin")
    
    def test_set_rate_limit(self):
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 24)
        assert limiter.is_rate_limited("linkedin")
    
    def test_rate_limit_expires(self):
        limiter = RateLimiter()
        limiter.set_rate_limit("linkedin", 0.001)  # 3.6 seconds
        time.sleep(0.01)
        assert not limiter.is_rate_limited("linkedin")
```

### Unit Tests: `tests/unit/agent/test_executor.py`
```python
@pytest.mark.asyncio
class TestAgentExecutor:
    async def test_executor_initialization(self):
        browser = AsyncMock()
        handlers = {"linkedin": AsyncMock()}
        limiter = RateLimiter()
        state = AgentState()
        
        executor = AgentExecutor(browser, handlers, limiter, state)
        assert executor.browser == browser
    
    async def test_run_task_success(self):
        browser = AsyncMock()
        handler = AsyncMock()
        handler.handle_task = AsyncMock(return_value=RESULT_SUCCESS)
        handlers = {"linkedin": handler}
        limiter = RateLimiter()
        state = AgentState()
        
        executor = AgentExecutor(browser, handlers, limiter, state)
        result = await executor.run("LinkedIn Application")
        
        assert result is True
```

## Files to Create/Modify
- [ ] Create: `src/agent/__init__.py`
- [ ] Create: `src/agent/state.py`
- [ ] Create: `src/agent/rate_limiter.py`
- [ ] Create: `src/agent/executor.py`
- [ ] Create: `tests/unit/agent/test_state.py`
- [ ] Create: `tests/unit/agent/test_rate_limiter.py`
- [ ] Create: `tests/unit/agent/test_executor.py`
- [ ] Modify: `src/sentinel/agent.py` (reduce to ~500 lines)

## Success Criteria
- [ ] Agent split into focused modules
- [ ] All tests pass
- [ ] agent.py reduced to <600 lines
- [ ] No breaking changes to public API
- [ ] State, rate limiting, execution cleanly separated

## Estimated Time
16-20 hours

## Dependencies
- Phase 0 (Testing Infrastructure)
- Phase 1 (Patterns)
- Phase 2 (Constants)
- Phase 3 (Browser Actions)
- Phase 4 (Platform Abstraction)
- Phase 5 (Platform Handlers)
- Phase 6 (JavaScript Extraction)

## Risk Mitigation
- Keep agent.py API unchanged during refactoring
- Use dependency injection for testability
- Ensure state is properly managed across modules
- Test orchestration logic thoroughly
