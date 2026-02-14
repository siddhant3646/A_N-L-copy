# Phase 3: Extract Browser Module

## Objective
Extract browser interaction methods into separate modules for better testability and maintainability.

## Current State
**Location**: `src/sentinel/agent.py` lines 1079-1595

**Methods to Extract**:
- `_check_page_health()` (Lines 1079-1098) - Page health checks
- `_maybe_cleanup_memory()` (Lines 1100-1118) - Memory management
- `_human_mouse_move()` (Lines 1190-1223) - Human-like mouse movement
- `_human_scroll()` (Lines 1225-1269) - Human-like scrolling
- `_human_click()` (Lines 1271-1292) - Human-like clicking
- `_robust_click()` (Lines 1298-1349) - Robust element clicking
- `_robust_js_click()` (Lines 1351-1383) - JavaScript-based clicking
- `_robust_click_by_text()` (Lines 1385-1409) - Text-based clicking
- `_robust_radio_click()` (Lines 1411-1452) - Radio button clicking
- `_robust_checkbox_click()` (Lines 1454-1494) - Checkbox clicking
- `_robust_button_click()` (Lines 1496-1525) - Button clicking
- `_scroll_element_into_view()` (Lines 1527-1542) - Element scrolling
- `_dismiss_browser_dialogs()` (Lines 1545-1593) - Dialog dismissal

## Implementation Steps

### 3.1 Create Page Utilities Module
**File**: `src/sentinel/page_utils.py`

**Functions**:
```python
async def check_page_health(page) -> bool
async def maybe_cleanup_memory(page, steps_since_cleanup: int) -> int
```

### 3.2 Create Human Behavior Module
**File**: `src/sentinel/human_behavior.py`

**Functions**:
```python
async def human_mouse_move(page, target_x: int, target_y: int)
async def human_scroll(page, direction: str, amount: int)
async def human_click(page, locator)
```

### 3.3 Create Browser Actions Module
**File**: `src/sentinel/browser_actions.py`

**Functions**:
```python
async def robust_click(locator, description: str, timeout: int, retries: int) -> bool
async def robust_js_click(page, selector: str, description: str) -> bool
async def robust_click_by_text(page, text: str, tag: str, exact: bool) -> bool
async def robust_radio_click(page, value_or_text: str, fallback_index: int) -> bool
async def robust_checkbox_click(page, value_or_text: str, select_all: bool) -> bool
async def robust_button_click(page, text_patterns: list, fallback_selector: str) -> bool
async def scroll_element_into_view(page, selector_or_locator, block: str) -> bool
async def dismiss_browser_dialogs(page) -> bool
```

### 3.4 Extract JavaScript for Dialog Dismissal
**File**: `src/sentinel/js/dialog_dismiss.js`

**Content**: Extract JS from lines 1548-1585

## Testing Strategy

### Unit Tests: `tests/unit/browser/test_human_simulation.py`
```python
@pytest.mark.asyncio
async def test_human_mouse_move_success(mock_page):
    mock_page.evaluate = AsyncMock(return_value={"x": 100, "y": 200})
    await human_mouse_move(mock_page, 100, 200)
    assert mock_page.evaluate.called

@pytest.mark.asyncio
async def test_human_scroll_down(mock_page):
    mock_page.evaluate = AsyncMock()
    await human_scroll(mock_page, "down", 500)
    assert mock_page.evaluate.called

@pytest.mark.asyncio
async def test_human_click_success(mock_page):
    mock_locator = AsyncMock()
    await human_click(mock_page, mock_locator)
    assert mock_locator.click.called
```

### Unit Tests: `tests/unit/browser/test_browser_actions.py`
```python
@pytest.mark.asyncio
async def test_robust_click_success(mock_page):
    mock_locator = AsyncMock()
    mock_locator.click = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=True)
    
    result = await robust_click(mock_locator, "test button", 5000, 3)
    assert result is True

@pytest.mark.asyncio
async def test_robust_click_retry_on_failure(mock_page):
    mock_locator = AsyncMock()
    mock_locator.click = AsyncMock(side_effect=[Exception("Timeout"), None])
    mock_locator.is_visible = AsyncMock(return_value=True)
    
    result = await robust_click(mock_locator, "test button", 5000, 2)
    assert result is True
    assert mock_locator.click.call_count == 2

@pytest.mark.asyncio
async def test_robust_radio_click_by_value(mock_page):
    mock_page.evaluate = AsyncMock(return_value=True)
    result = await robust_radio_click(mock_page, "Yes", None)
    assert result is True
```

## Files to Create/Modify
- [ ] Create: `src/sentinel/page_utils.py`
- [ ] Create: `src/sentinel/human_behavior.py`
- [ ] Create: `src/sentinel/browser_actions.py`
- [ ] Create: `src/sentinel/js/dialog_dismiss.js`
- [ ] Create: `tests/unit/browser/test_human_simulation.py`
- [ ] Create: `tests/unit/browser/test_browser_actions.py`
- [ ] Modify: `src/sentinel/agent.py` (remove extracted methods, import from new modules)

## Success Criteria
- [ ] All browser methods extracted to separate modules
- [ ] All tests pass with heavy mocking
- [ ] No regression in browser functionality
- [ ] agent.py reduced by ~600 lines

## Estimated Time
8-12 hours

## Dependencies
- Phase 0 (Testing Infrastructure)
- Phase 2 (Constants - for timeout values)

## Risk Mitigation
- Keep original methods as wrappers during transition
- Test each extracted method individually before removing from agent.py
- Use integration tests to verify browser interactions still work
