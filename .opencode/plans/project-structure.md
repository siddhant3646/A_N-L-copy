# Job Application Automation System - Implementation Plan

## Project Structure After Refactoring

```
src/
├── core/
│   ├── __init__.py
│   ├── config.py                 # Browser + app configuration
│   └── constants.py              # Global constants, platform identifiers
├── sentinel/
│   ├── __init__.py
│   ├── agent.py                  # Main agent (~500 lines after refactor)
│   ├── prompts.py                # Task prompts
│   ├── schemas.py                # Data classes
│   ├── question_classifier.py    # Question categorization
│   ├── question_fingerprint.py   # Question normalization
│   ├── question_matching.py      # NEW: Fuzzy matching logic
│   ├── browser_actions.py        # NEW: Robust click helpers
│   ├── human_behavior.py         # NEW: Mouse/scroll simulation
│   ├── logging_utils.py          # NEW: Question & metrics logging
│   ├── metrics.py                # NEW: Metrics tracking
│   ├── page_utils.py             # NEW: Page health, cleanup
│   ├── profile_manager.py        # NEW: Profile cleanup logic
│   ├── js_loader.py              # NEW: JavaScript file loader
│   ├── run.py                    # Entry point with Browser class
│   └── js/                       # NEW: JavaScript files
│       ├── utils.js              # Shared JS utilities
│       ├── dialog_dismiss.js
│       ├── login_detection.js
│       ├── memory_cleanup.js
│       ├── linkedin/
│       │   ├── form_fill.js
│       │   ├── job_navigation.js
│       │   ├── modal_close.js
│       │   └── rate_limit.js
│       ├── naukri/
│       │   ├── chatbot.js
│       │   ├── form_submit.js
│       │   └── profile_edit.js
│       └── instahyre/
│           └── filter_panel.js
└── platforms/                    # NEW: Platform handlers
    ├── __init__.py
    ├── base_platform.py          # Abstract base class
    ├── linkedin/
    │   ├── __init__.py
    │   ├── handler.py            # LinkedIn platform logic
    │   └── autopilot.py          # LinkedIn autopilot mode
    ├── naukri/
    │   ├── __init__.py
    │   ├── handler.py            # Naukri platform logic
    │   └── chatbot_handler.py    # Naukri chatbot wrapper
    └── instahyre/
        ├── __init__.py
        └── handler.py            # Instahyre platform logic

tests/
├── __init__.py
├── conftest.py                   # Shared fixtures and config
├── unit/                         # Unit tests (fast, isolated)
│   ├── patterns/
│   │   ├── test_qa_patterns.py
│   │   └── test_pattern_matcher.py
│   ├── browser/
│   │   ├── test_interactions.py
│   │   ├── test_human_simulation.py
│   │   └── test_browser_actions.py
│   ├── platforms/
│   │   ├── test_interface.py
│   │   ├── test_linkedin_handler.py
│   │   ├── test_naukri_handler.py
│   │   └── test_instahyre_handler.py
│   ├── question/
│   │   ├── test_classifier.py
│   │   ├── test_fingerprint.py
│   │   └── test_matching.py
│   ├── logging/
│   │   └── test_logging.py
│   ├── agent/
│   │   ├── test_state.py
│   │   ├── test_executor.py
│   │   └── test_rate_limiter.py
│   └── core/
│       └── test_profile_manager.py
├── integration/
│   └── test_platform_integration.py
└── e2e/
    └── test_real_browser.py
```

## Migration Approach

**Incremental (Option B)**: Module-by-module extraction while maintaining backward compatibility

## Key Principles

1. **Single Source of Truth**: Patterns stored only in `config/qa_patterns.json`
2. **Dynamic JS Loading**: JavaScript extracted to `.js` files, loaded dynamically
3. **Platform Abstraction**: Clean separation between platform-specific logic
4. **Comprehensive Testing**: Heavy mocking for fast, reliable tests
5. **Profile Cleanup**: Automatic cleanup after every cycle

## Module Size Targets

| Module | Target Lines | Current Location |
|--------|--------------|------------------|
| agent.py | ~500 | 4950 lines |
| browser_actions.py | ~250 | Lines 1294-1595 |
| human_behavior.py | ~100 | Lines 1190-1293 |
| logging_utils.py | ~150 | Lines 896-1025 |
| question_matching.py | ~300 | Lines 586-894 |
| profile_manager.py | ~50 | New |
| Platform handlers | ~400-600 each | Lines 1837-2733 |

## Success Criteria

- All existing tests pass
- New unit tests achieve >80% code coverage
- No breaking changes to public APIs
- agent.py reduced to <600 lines
- JavaScript extracted to 15+ separate .js files
- Profile cleanup works reliably after every cycle
