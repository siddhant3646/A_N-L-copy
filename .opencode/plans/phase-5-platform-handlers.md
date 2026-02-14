# Phase 5: Implement Platform Handlers

## Objective
Extract platform-specific logic from agent.py into dedicated handler classes.

## Implementation Steps

### 5.1 LinkedIn Handler
**File**: `src/platforms/linkedin/handler.py`

**Methods to Extract from agent.py**:
- LinkedIn autopilot logic (Lines 1837-2052)
- Rate limit detection (Lines 1885-1890)
- Modal handling (Lines 1859-1878, 1915-1933, 1987-2006)

**Class Structure**:
```python
class LinkedInHandler(BasePlatformHandler):
    platform_name = PLATFORM_LINKEDIN
    
    async def detect_login_required(self, page) -> bool
    async def detect_rate_limit(self, page) -> bool
    async def handle_task(self, page, task_context: dict) -> str
    async def handle_autopilot(self, page) -> str
    async def handle_modal(self, page) -> str
    async def handle_form(self, page, form_data: dict) -> str
    def get_selectors(self) -> dict
```

**JavaScript Files**:
- `src/sentinel/js/linkedin/form_fill.js`
- `src/sentinel/js/linkedin/job_navigation.js`
- `src/sentinel/js/linkedin/modal_close.js`
- `src/sentinel/js/linkedin/rate_limit.js`

### 5.2 Naukri Handler
**File**: `src/platforms/naukri/handler.py`

**Methods to Extract from agent.py**:
- Profile update (Lines 2062-2186)
- Employment LWD update (Lines 2192-2384)
- Early Access (Lines 2391-2441)
- Apply/Chatbot (Lines 2460-2630)

**Additional File**: `src/platforms/naukri/chatbot_handler.py`

**Class Structure**:
```python
class NaukriHandler(BasePlatformHandler):
    platform_name = PLATFORM_NAUKRI
    
    async def detect_login_required(self, page) -> bool
    async def detect_rate_limit(self, page) -> bool
    async def handle_task(self, page, task_context: dict) -> str
    async def handle_profile_update(self, page) -> str
    async def handle_employment_update(self, page) -> str
    async def handle_early_access(self, page) -> str
    async def handle_apply(self, page) -> str
    def get_selectors(self) -> dict
```

**JavaScript Files**:
- `src/sentinel/js/naukri/chatbot.js` (Lines 2758-3033)
- `src/sentinel/js/naukri/form_submit.js`
- `src/sentinel/js/naukri/profile_edit.js`

### 5.3 Instahyre Handler
**File**: `src/platforms/instahyre/handler.py`

**Methods to Extract from agent.py**:
- Filter panel handling (Lines 2687-2733)

**Class Structure**:
```python
class InstahyreHandler(BasePlatformHandler):
    platform_name = PLATFORM_INSTAHYRE
    
    async def detect_login_required(self, page) -> bool
    async def detect_rate_limit(self, page) -> bool
    async def handle_task(self, page, task_context: dict) -> str
    async def handle_filters(self, page) -> str
    def get_selectors(self) -> dict
```

**JavaScript Files**:
- `src/sentinel/js/instahyre/filter_panel.js`

## Testing Strategy

### Unit Tests: `tests/unit/platforms/test_linkedin_handler.py`
```python
@pytest.mark.asyncio
class TestLinkedInHandler:
    async def test_detect_login_required_true(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        
        handler = LinkedInHandler(mock_browser)
        result = await handler.detect_login_required(mock_page)
        assert result is True
    
    async def test_detect_rate_limit(self):
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="You've reached the limit")
        
        handler = LinkedInHandler(mock_browser)
        result = await handler.detect_rate_limit(mock_page)
        assert result is True
    
    async def test_handle_autopilot_success(self):
        mock_page = AsyncMock()
        # Mock successful form submission
        mock_page.evaluate = AsyncMock(return_value={"success": True})
        
        handler = LinkedInHandler(mock_browser)
        result = await handler.handle_autopilot(mock_page)
        assert result == RESULT_SUCCESS
```

### Unit Tests: `tests/unit/platforms/test_naukri_handler.py`
```python
@pytest.mark.asyncio
class TestNaukriHandler:
    async def test_handle_profile_update(self):
        mock_page = AsyncMock()
        handler = NaukriHandler(mock_browser)
        
        result = await handler.handle_profile_update(mock_page)
        assert result in [RESULT_SUCCESS, RESULT_CONTINUE]
    
    async def test_handle_chatbot(self):
        mock_page = AsyncMock()
        handler = NaukriHandler(mock_browser)
        
        result = await handler.handle_apply(mock_page)
        assert result in [RESULT_SUCCESS, RESULT_CONTINUE, RESULT_ERROR]
```

## Files to Create/Modify
- [ ] Create: `src/platforms/linkedin/handler.py`
- [ ] Create: `src/platforms/linkedin/autopilot.py` (optional)
- [ ] Create: `src/platforms/naukri/handler.py`
- [ ] Create: `src/platforms/naukri/chatbot_handler.py`
- [ ] Create: `src/platforms/instahyre/handler.py`
- [ ] Create: LinkedIn JS files (4 files)
- [ ] Create: Naukri JS files (3 files)
- [ ] Create: Instahyre JS files (1 file)
- [ ] Create: Platform handler tests
- [ ] Modify: `src/sentinel/agent.py` (remove platform logic, use handlers)

## Success Criteria
- [ ] All three platform handlers implemented
- [ ] Each handler implements BasePlatformHandler interface
- [ ] All JavaScript extracted to .js files
- [ ] All platform handler tests pass
- [ ] agent.py reduced by ~1500 lines
- [ ] No regression in platform functionality

## Estimated Time
20-30 hours (largest phase)

## Dependencies
- Phase 0 (Testing Infrastructure)
- Phase 2 (Constants)
- Phase 3 (Browser Actions - handlers use these)
- Phase 4 (Base Platform Interface)

## Risk Mitigation
- Implement one platform at a time
- Test each platform thoroughly before moving to next
- Keep original agent.py logic as fallback during development
- Create integration tests for each platform
