# Phase 4: Create Platform Abstraction Layer

## Objective
Create an abstract base class for platform handlers to enable clean separation of platform-specific logic.

## Current State
Platform logic is scattered throughout agent.py:
- LinkedIn: Lines 1837-2052 (autopilot)
- Naukri: Lines 2057-2630 (profile, employment, apply, chatbot)
- Instahyre: Lines 2687-2733 (filters, apply)

## Implementation Steps

### 4.1 Create Base Platform Class
**File**: `src/platforms/base_platform.py`

**Class**: `BasePlatformHandler`

**Abstract Methods**:
```python
@property
@abstractmethod
def platform_name(self) -> str:
    """Return platform identifier"""

@abstractmethod
async def detect_login_required(self, page) -> bool:
    """Detect if login is required"""

@abstractmethod
async def handle_task(self, page, task_context: dict) -> str:
    """Handle platform-specific task"""

@abstractmethod
async def detect_rate_limit(self, page) -> bool:
    """Detect if rate limited"""

@abstractmethod
async def handle_form(self, page, form_data: dict) -> str:
    """Handle form filling"""

@abstractmethod
def get_selectors(self) -> dict:
    """Return platform-specific DOM selectors"""
```

### 4.2 Define Platform Handler Interface
**File**: `src/platforms/__init__.py`

**Content**:
```python
from .base_platform import BasePlatformHandler
from .linkedin.handler import LinkedInHandler
from .naukri.handler import NaukriHandler
from .instahyre.handler import InstahyreHandler

__all__ = [
    "BasePlatformHandler",
    "LinkedInHandler", 
    "NaukriHandler",
    "InstahyreHandler"
]

# Factory function
def get_platform_handler(platform: str, browser) -> BasePlatformHandler:
    """Get appropriate platform handler"""
    handlers = {
        PLATFORM_LINKEDIN: LinkedInHandler,
        PLATFORM_NAUKRI: NaukriHandler,
        PLATFORM_INSTAHYRE: InstahyreHandler
    }
    handler_class = handlers.get(platform)
    if not handler_class:
        raise ValueError(f"Unknown platform: {platform}")
    return handler_class(browser)
```

## Testing Strategy

### Unit Tests: `tests/unit/platforms/test_interface.py`
```python
class TestBasePlatformInterface:
    def test_base_class_is_abstract(self):
        """Test that BasePlatformHandler cannot be instantiated"""
        with pytest.raises(TypeError):
            BasePlatformHandler()
    
    def test_linkedin_handler_implements_interface(self):
        """Test LinkedInHandler implements all abstract methods"""
        handler = LinkedInHandler(mock_browser)
        assert isinstance(handler, BasePlatformHandler)
        assert handler.platform_name == PLATFORM_LINKEDIN
    
    def test_naukri_handler_implements_interface(self):
        """Test NaukriHandler implements all abstract methods"""
        handler = NaukriHandler(mock_browser)
        assert isinstance(handler, BasePlatformHandler)
        assert handler.platform_name == PLATFORM_NAUKRI
    
    def test_factory_returns_correct_handler(self):
        """Test factory function returns correct handler type"""
        linkedin_handler = get_platform_handler("linkedin", mock_browser)
        assert isinstance(linkedin_handler, LinkedInHandler)
        
        naukri_handler = get_platform_handler("naukri", mock_browser)
        assert isinstance(naukri_handler, NaukriHandler)
    
    def test_factory_raises_on_unknown_platform(self):
        """Test factory raises error for unknown platform"""
        with pytest.raises(ValueError):
            get_platform_handler("unknown", mock_browser)
```

## Files to Create
- [ ] Create: `src/platforms/__init__.py`
- [ ] Create: `src/platforms/base_platform.py`
- [ ] Create: `src/platforms/linkedin/__init__.py`
- [ ] Create: `src/platforms/naukri/__init__.py`
- [ ] Create: `src/platforms/instahyre/__init__.py`
- [ ] Create: `tests/unit/platforms/test_interface.py`

## Success Criteria
- [ ] BasePlatformHandler abstract class created
- [ ] Factory function working
- [ ] All tests pass
- [ ] Clear interface for platform handlers defined

## Estimated Time
4-6 hours

## Dependencies
- Phase 0 (Testing Infrastructure)
- Phase 2 (Constants - for platform identifiers)

## Risk Mitigation
- Define interface carefully to accommodate all platform needs
- Review interface with all three platforms in mind
- Keep interface simple and focused
