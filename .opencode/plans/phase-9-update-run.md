# Phase 9: Update run.py Integration

## Objective
Update main entry point to use new modular structure with all extracted components.

## Current State
- run.py contains Browser class and main() function
- Calls agent.run() directly
- Manages tasks list and cycle loop

## Implementation Steps

### 9.1 Update Imports
**File**: `src/sentinel/run.py`

**New Imports**:
```python
from src.sentinel.profile_manager import ProfileManager
from src.sentinel.metrics import MetricsTracker
from src.platforms import get_platform_handler
from src.agent.executor import AgentExecutor
from src.agent.rate_limiter import RateLimiter
from src.agent.state import AgentState
```

### 9.2 Update Browser Integration
**File**: `src/sentinel/run.py`

**Changes**:
```python
async def main():
    print(f"🛡️  SENTINEL REBORN - Infinite Loop Mode")
    
    tasks = [...]  # Keep existing task definitions
    
    cycle_count = 0
    rate_limiter = RateLimiter()
    
    while True:
        cycle_count += 1
        
        # FRESH PROFILE at cycle start
        ProfileManager.ensure_fresh()
        
        browser = Browser(
            executable_path=CHROME_EXECUTABLE_PATH,
            user_data_dir=ProfileManager.PROFILE_DIR
        )
        
        try:
            await browser.start()
            
            # Create platform handlers
            platform_handlers = {
                "linkedin": get_platform_handler("linkedin", browser),
                "naukri": get_platform_handler("naukri", browser),
                "instahyre": get_platform_handler("instahyre", browser)
            }
            
            for task_name, start_url, prompt in tasks:
                # Check rate limits
                platform = get_platform_from_task(task_name)
                if rate_limiter.is_rate_limited(platform):
                    print(f"⏳ {platform} rate limited, skipping...")
                    continue
                
                # Create executor for this task
                state = AgentState()
                executor = AgentExecutor(
                    browser=browser,
                    platform_handlers=platform_handlers,
                    rate_limiter=rate_limiter,
                    state=state
                )
                
                # Run task
                success = await executor.run(prompt)
                
                # Update rate limits if needed
                if state.rate_limited:
                    rate_limiter.set_rate_limit(platform, 24)
        
        except Exception as e:
            print(f"❌ Cycle {cycle_count} error: {e}")
        
        finally:
            await browser.stop()
            # CLEANUP PROFILE at cycle end
            ProfileManager.cleanup()
            
            # Intersession delay
            await intersession_delay()
```

### 9.3 Add Helper Functions
**File**: `src/sentinel/run.py`

**Add**:
```python
def get_platform_from_task(task_name: str) -> str:
    """Extract platform from task name"""
    task_lower = task_name.lower()
    if "linkedin" in task_lower:
        return "linkedin"
    elif "naukri" in task_lower:
        return "naukri"
    elif "instahyre" in task_lower:
        return "instahyre"
    return "default"

async def intersession_delay():
    """Handle intersession delay"""
    # Implementation from current run.py
```

## Testing Strategy

### Integration Tests: `tests/integration/test_platform_integration.py`
```python
@pytest.mark.asyncio
async def test_full_task_cycle():
    """Test complete task execution cycle"""
    # Mock all external dependencies
    browser = AsyncMock()
    handler = AsyncMock()
    handler.handle_task = AsyncMock(return_value=RESULT_SUCCESS)
    
    limiter = RateLimiter()
    state = AgentState()
    
    executor = AgentExecutor(browser, {"linkedin": handler}, limiter, state)
    
    result = await executor.run("LinkedIn Application")
    assert result is True
    assert handler.handle_task.called
```

## Files to Modify
- [ ] Modify: `src/sentinel/run.py` (full integration)

## Success Criteria
- [ ] run.py uses new modular structure
- [ ] ProfileManager integrated
- [ ] All components work together
- [ ] Integration tests pass
- [ ] No regression in functionality

## Estimated Time
6-8 hours

## Dependencies
- All previous phases

## Risk Mitigation
- Test integration step by step
- Verify each component is properly initialized
- Use extensive logging during transition
- Keep fallback to old structure during testing
