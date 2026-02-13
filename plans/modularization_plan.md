# Sentinel Codebase Modularization Plan

## Executive Summary

The current codebase is a job application automation system that applies to jobs on Naukri, LinkedIn, and Instahyre. The main issue is that [`agent.py`](src/sentinel/agent.py) is a monolithic file with ~4863 lines containing multiple responsibilities. This plan proposes splitting the codebase into focused, single-responsibility modules.

---

## Current Architecture Analysis

### File Structure
```
src/
├── core/
│   └── config.py              # Browser configuration (6 lines)
├── sentinel/
│   ├── agent.py               # MAIN FILE - 4863 lines (TOO LARGE)
│   ├── question_classifier.py # Question categorization (625 lines)
│   ├── question_fingerprint.py# Question normalization (616 lines)
│   ├── schemas.py             # Data classes (28 lines)
│   ├── prompts.py             # Task prompts (309 lines)
│   └── run.py                 # Main runner (371 lines)
config/
└── qa_patterns.json           # QA patterns config (382 lines)
```

### Problems with Current Structure

1. **Monolithic Agent File**: [`agent.py`](src/sentinel/agent.py:516) contains:
   - 500+ lines of QA patterns dictionary
   - Browser interaction methods
   - Platform-specific logic for Naukri, LinkedIn, Instahyre
   - Form handling JavaScript
   - Human simulation behaviors
   - Error handling and logging
   - Rate limiting logic

2. **Duplicated QA Patterns**: Patterns exist in both [`agent.py`](src/sentinel/agent.py:25) and [`config/qa_patterns.json`](config/qa_patterns.json:21)

3. **Mixed Concerns**: Platform-specific logic is interleaved with generic methods

4. **Embedded JavaScript**: Large JavaScript strings embedded in Python make code hard to maintain

---

## Proposed Modular Architecture

### New Directory Structure

```
src/
├── core/
│   ├── __init__.py
│   ├── config.py              # Browser + app configuration
│   └── constants.py           # Global constants
│
├── patterns/
│   ├── __init__.py
│   ├── qa_patterns.py         # QA pattern definitions
│   ├── pattern_loader.py      # Load patterns from JSON
│   └── pattern_matcher.py     # Fuzzy matching logic
│
├── browser/
│   ├── __init__.py
│   ├── browser.py             # Browser class (from run.py)
│   ├── interactions.py        # Click, scroll, type helpers
│   ├── human_simulation.py    # Human-like behaviors
│   └── page_health.py         # Page health checks
│
├── platforms/
│   ├── __init__.py
│   ├── base.py                # Base platform handler
│   ├── naukri/
│   │   ├── __init__.py
│   │   ├── handler.py         # Naukri-specific logic
│   │   ├── selectors.py       # DOM selectors
│   │   └── form_handler.py    # Form filling JS
│   ├── linkedin/
│   │   ├── __init__.py
│   │   ├── handler.py         # LinkedIn-specific logic
│   │   ├── selectors.py       # DOM selectors
│   │   └── form_handler.py    # Form filling JS
│   └── instahyre/
│       ├── __init__.py
│       ├── handler.py         # Instahyre-specific logic
│       ├── selectors.py       # DOM selectors
│       └── form_handler.py    # Form filling JS
│
├── question/
│   ├── __init__.py
│   ├── classifier.py          # Question classification
│   ├── fingerprint.py         # Question fingerprinting
│   └── answer_generator.py    # Generate answers
│
├── logging/
│   ├── __init__.py
│   ├── question_logger.py     # Question logging
│   ├── metrics.py             # Metrics tracking
│   └── error_handler.py       # Error handling + screenshots
│
├── agent/
│   ├── __init__.py
│   ├── state.py               # Agent state management
│   ├── executor.py            # Main execution loop
│   └── rate_limiter.py        # Rate limiting logic
│
└── sentinel/
    ├── __init__.py
    ├── prompts.py             # Task prompts
    ├── schemas.py             # Data classes
    └── run.py                 # Entry point
```

---

## Module Breakdown

### 1. Core Module

#### [`config.py`](src/core/config.py) - Enhanced Configuration
```python
# Configuration management
CHROME_USER_DATA = os.getenv("CHROME_USER_DATA", "...")
CHROME_EXECUTABLE_PATH = os.getenv("CHROME_EXECUTABLE_PATH", "...")

# App settings
SCREENSHOT_DIR = os.path.expanduser("~/Desktop/sentinel_errors")
LOG_DIR = os.path.expanduser("~/Desktop/sentinel_errors")
MAX_STEPS_LINKEDIN = 120
MAX_STEPS_DEFAULT = 50
MEMORY_CLEANUP_INTERVAL = 50
```

#### [`constants.py`](src/core/constants.py) - Global Constants
```python
# Platform identifiers
PLATFORM_NAUKRI = "naukri"
PLATFORM_LINKEDIN = "linkedin"
PLATFORM_INSTAHYRE = "instahyre"

# Result codes
RESULT_TASK_COMPLETE = "TASK_COMPLETE"
RESULT_SUCCESS = "SUCCESS"
RESULT_RATE_LIMITED = "RATE_LIMITED"
# ... etc
```

---

### 2. Patterns Module

#### [`qa_patterns.py`](src/patterns/qa_patterns.py) - Pattern Definitions
```python
# Extract from agent.py lines 25-511
QA_PATTERNS = {
    'years of experience': '3.8 Years',
    'current salary': '13.5 LPA',
    # ... all patterns
}

FUZZY_MATCH_THRESHOLD = 0.6
```

#### [`pattern_matcher.py`](src/patterns/pattern_matcher.py) - Matching Logic
```python
class PatternMatcher:
    def __init__(self, patterns: dict):
        self.patterns = patterns
    
    def fuzzy_match(self, question: str) -> Tuple[Optional[str], float]:
        """Extract from agent.py lines 586-894"""
        pass
    
    def keyword_match(self, question: str) -> Tuple[Optional[str], float]:
        """Keyword-based priority matching"""
        pass
```

---

### 3. Browser Module

#### [`browser.py`](src/browser/browser.py) - Browser Management
```python
# Extract Browser class from run.py lines 8-175
class Browser:
    async def start(self): ...
    async def get_current_page(self): ...
    async def stop(self): ...
```

#### [`interactions.py`](src/browser/interactions.py) - Interaction Helpers
```python
# Extract from agent.py lines 1298-1543
async def robust_click(locator, description: str, timeout: int, retries: int) -> bool: ...
async def robust_js_click(page, selector: str, description: str) -> bool: ...
async def robust_radio_click(page, value_or_text: str, fallback_index: int) -> bool: ...
async def robust_checkbox_click(page, value_or_text: str, select_all: bool) -> bool: ...
async def robust_button_click(page, text_patterns: list, fallback_selector: str) -> bool: ...
async def scroll_element_into_view(page, selector_or_locator, block: str) -> bool: ...
```

#### [`human_simulation.py`](src/browser/human_simulation.py) - Human-like Behaviors
```python
# Extract from agent.py lines 1190-1293
async def human_mouse_move(page, target_x: int, target_y: int): ...
async def human_scroll(page, direction: str, amount: int): ...
async def human_click(page, locator): ...
```

#### [`page_health.py`](src/browser/page_health.py) - Page Health Checks
```python
# Extract from agent.py lines 1079-1118
async def check_page_health(page) -> bool: ...
async def maybe_cleanup_memory(page, steps_since_cleanup: int) -> int: ...
```

---

### 4. Platforms Module

#### [`base.py`](src/platforms/base.py) - Base Platform Handler
```python
from abc import ABC, abstractmethod

class BasePlatformHandler(ABC):
    """Base class for platform-specific logic."""
    
    @property
    @abstractmethod
    def platform_name(self) -> str: ...
    
    @abstractmethod
    async def detect_login_required(self, page) -> bool: ...
    
    @abstractmethod
    async def handle_form(self, page, question_data: dict) -> str: ...
    
    @abstractmethod
    def get_selectors(self) -> dict: ...
```

#### [`naukri/handler.py`](src/platforms/naukri/handler.py) - Naukri Logic
```python
class NaukriHandler(BasePlatformHandler):
    platform_name = "naukri"
    
    async def detect_login_required(self, page) -> bool:
        """Extract from agent.py lines 1148-1163"""
        pass
    
    async def handle_form(self, page, question_data: dict) -> str:
        """Naukri-specific form handling"""
        pass
```

#### [`naukri/selectors.py`](src/platforms/naukri/selectors.py) - Naukri DOM Selectors
```python
NAUKRI_SELECTORS = {
    'job_checkbox': '.dspIB.saveJobContainer tuple-check-box i',
    'apply_button': '.multi-apply-button.typ-16Bold',
    'chatbot_drawer': '#chatbot_DrawerContentWrapper',
    # ... all Naukri selectors
}
```

#### [`linkedin/handler.py`](src/platforms/linkedin/handler.py) - LinkedIn Logic
```python
class LinkedInHandler(BasePlatformHandler):
    platform_name = "linkedin"
    
    async def handle_autopilot(self, page, agent_state: dict) -> str:
        """Extract from agent.py lines 1837-2100+"""
        pass
    
    async def handle_success_modal(self, page) -> str:
        """Handle LinkedIn success modal"""
        pass
```

---

### 5. Question Module

#### [`classifier.py`](src/question/classifier.py) - Question Classification
```python
# Already exists in question_classifier.py - keep as is
# Just move to question/ directory
```

#### [`fingerprint.py`](src/question/fingerprint.py) - Question Fingerprinting
```python
# Already exists in question_fingerprint.py - keep as is
# Just move to question/ directory
```

#### [`answer_generator.py`](src/question/answer_generator.py) - Answer Generation
```python
class AnswerGenerator:
    def __init__(self, pattern_matcher, classifier, platform: str):
        self.pattern_matcher = pattern_matcher
        self.classifier = classifier
        self.platform = platform
    
    def get_answer(self, question: str, context: dict) -> Tuple[str, float]:
        """Generate answer using pattern matching + classification fallback"""
        pass
```

---

### 6. Logging Module

#### [`question_logger.py`](src/logging/question_logger.py) - Question Logging
```python
# Extract from agent.py lines 896-1025
class QuestionLogger:
    def log_unknown_question(self, question: str, context: str, ...): ...
    def log_all_questions(self, question: str, answer: str, ...): ...
    def log_question_detailed(self, question_data: dict): ...
```

#### [`metrics.py`](src/logging/metrics.py) - Metrics Tracking
```python
# Extract from agent.py lines 1054-1065
class MetricsTracker:
    def __init__(self):
        self.metrics = {
            'task_name': '',
            'start_time': None,
            'applications_submitted': 0,
            'questions_answered': 0,
            # ...
        }
    
    def save(self): ...
    def increment(self, key: str): ...
```

#### [`error_handler.py`](src/logging/error_handler.py) - Error Handling
```python
# Extract from agent.py lines 1067-1077
class ErrorHandler:
    async def screenshot_on_error(self, page, error_context: str) -> str: ...
    def log_error(self, error: Exception, context: str): ...
```

---

### 7. Agent Module

#### [`state.py`](src/agent/state.py) - Agent State
```python
@dataclass
class AgentState:
    step_count: int = 0
    task_complete: bool = False
    errors: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_result: str = ""
    linkedin_applications: int = 0
    naukri_applications: int = 0
```

#### [`executor.py`](src/agent/executor.py) - Main Execution Loop
```python
class AgentExecutor:
    """Main agent execution - simplified from agent.py"""
    
    def __init__(self, browser, platform_handlers: dict):
        self.browser = browser
        self.platform_handlers = platform_handlers
        self.state = AgentState()
        self.answer_generator = AnswerGenerator(...)
        self.logger = QuestionLogger(...)
    
    async def run(self, task_description: str) -> bool:
        """Main execution loop - extract from agent.py lines 1609-2100+"""
        pass
    
    async def handle_scripted_fallback(self) -> str:
        """The main JavaScript execution - extract from agent.py"""
        pass
```

#### [`rate_limiter.py`](src/agent/rate_limiter.py) - Rate Limiting
```python
class RateLimiter:
    def __init__(self):
        self.linkedin_rate_limit_until = None
        self.naukri_rate_limit_until = None
    
    def is_rate_limited(self, platform: str) -> bool: ...
    def set_rate_limit(self, platform: str, duration_hours: float): ...
```

---

## Migration Strategy

### Phase 1: Extract Independent Modules
1. Create [`src/patterns/`](src/patterns/) module - extract QA patterns
2. Create [`src/browser/`](src/browser/) module - extract Browser class and helpers
3. Create [`src/logging/`](src/logging/) module - extract logging utilities

### Phase 2: Extract Platform Logic
1. Create [`src/platforms/base.py`](src/platforms/base.py) with abstract base class
2. Create platform-specific handlers for Naukri, LinkedIn, Instahyre
3. Move platform-specific JavaScript to separate files

### Phase 3: Refactor Agent
1. Create [`src/agent/`](src/agent/) module
2. Split agent.py into state, executor, and rate_limiter
3. Inject dependencies (platform handlers, pattern matcher, logger)

### Phase 4: Integration
1. Update imports across all modules
2. Update [`run.py`](src/sentinel/run.py) to use new structure
3. Add comprehensive tests

---

## Benefits of Modularization

| Aspect | Before | After |
|--------|--------|-------|
| Main agent file | 4863 lines | ~500 lines |
| Module count | 6 files | 25+ focused files |
| Platform logic | Mixed in agent | Separate handlers |
| Testing | Difficult | Unit testable |
| Adding new platform | Modify agent.py | Add new handler |
| JavaScript maintenance | Embedded strings | Separate .js files |

---

## File Size Estimates After Refactoring

| Module | File | Estimated Lines |
|--------|------|-----------------|
| patterns | qa_patterns.py | ~300 |
| patterns | pattern_matcher.py | ~200 |
| browser | browser.py | ~150 |
| browser | interactions.py | ~250 |
| browser | human_simulation.py | ~100 |
| platforms | base.py | ~50 |
| platforms | naukri/handler.py | ~400 |
| platforms | linkedin/handler.py | ~600 |
| platforms | instahyre/handler.py | ~200 |
| agent | executor.py | ~500 |
| agent | state.py | ~50 |
| logging | question_logger.py | ~150 |
| logging | metrics.py | ~100 |

---

## Next Steps

1. **Review this plan** - Confirm the modular structure makes sense
2. **Prioritize modules** - Decide which to extract first
3. **Create implementation tickets** - Break down into actionable tasks
4. **Start with Phase 1** - Begin with independent modules

---

## Profile Folder Management

### Current Behavior
- Chrome profile is copied from source to local `p/` folder ([`run.py:47`](src/sentinel/run.py:47))
- Profile persists across cycles, accumulating cache and session data
- Can cause disk space issues and stale session problems

### Proposed Enhancement
Add automatic profile cleanup at the end of each cycle:

```python
# In browser.py or a new profile_manager.py
import shutil
import os

class ProfileManager:
    PROFILE_DIR = os.path.join(os.getcwd(), "p")
    
    @classmethod
    def cleanup(cls):
        """Delete profile folder after cycle completion."""
        if os.path.exists(cls.PROFILE_DIR):
            try:
                shutil.rmtree(cls.PROFILE_DIR, ignore_errors=True)
                print("🧹 Profile folder cleaned up")
            except Exception as e:
                print(f"⚠️ Profile cleanup failed: {e}")
    
    @classmethod
    def ensure_fresh(cls):
        """Ensure fresh profile folder at cycle start."""
        cls.cleanup()
        os.makedirs(cls.PROFILE_DIR, exist_ok=True)
```

### Integration Points
1. **Cycle Start**: Call `ProfileManager.ensure_fresh()` before browser launch
2. **Cycle End**: Call `ProfileManager.cleanup()` after all tasks complete
3. **Error Handling**: Ensure cleanup happens even if cycle fails

### Updated run.py Flow
```python
async def main():
    cycle_count = 0
    
    while True:
        cycle_count += 1
        
        # FRESH START: Clean profile at cycle start
        ProfileManager.ensure_fresh()
        
        try:
            for task in tasks:
                # ... run tasks
                pass
            
            # INTERSESSION
            # ... intersession logic
            
        finally:
            # CLEANUP: Delete profile at cycle end
            ProfileManager.cleanup()
```

---

## Questions for Discussion

1. Should JavaScript be extracted to separate `.js` files or kept as Python strings?
2. Do you want to maintain backward compatibility during migration?
3. Should we add type hints throughout?
4. Do you want unit tests for each module?
5. **Should profile cleanup be optional via config flag?**
