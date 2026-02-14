# Phase 6: Extract JavaScript Files

## Objective
Extract all JavaScript code blocks from agent.py into separate .js files for better maintainability.

## Current State
**Total JavaScript**: ~3000+ lines embedded in Python strings

**JavaScript Blocks to Extract**:

### Login Detection
- Lines 1129-1138: LinkedIn login detection
- Lines 1149-1156: Naukri login detection  
- Lines 1167-1175: Instahyre login detection

### Page Utilities
- Lines 1108-1114: Memory cleanup (gc)

### Dialog Handling
- Lines 1548-1585: Dialog dismissal

### Platform-Specific JavaScript
- **LinkedIn**: Lines 3304-3785 (481 lines)
  - Easy Apply button finding
  - Form field handling
  - Shadow DOM helpers
  - Modal detection
  - Job navigation
- **Naukri**: Lines 3786-4503 (717 lines)
  - Feedback modal dismissal
  - Chatbot handling
  - Job checkbox selection
  - Tab navigation
- **Instahyre**: Lines 4505-4932 (427 lines)
  - Filter panel
  - Selectize dropdowns
  - View/Apply buttons

## Implementation Steps

### 6.1 Create JavaScript Loader
**File**: `src/sentinel/js_loader.py`

**Functions**:
```python
def load_js(filename: str) -> str
    """Load JavaScript from file"""

def load_js_with_vars(filename: str, variables: dict) -> str
    """Load JS and replace template variables"""
```

### 6.2 Create Shared Utilities JS
**File**: `src/sentinel/js/utils.js`

**Content**: Shadow DOM query helpers, common utilities

### 6.3 Extract Login Detection JS
**File**: `src/sentinel/js/login_detection.js`

**Content**: Combined login detection for all platforms

### 6.4 Extract LinkedIn JavaScript
Files:
- `src/sentinel/js/linkedin/job_navigation.js`
- `src/sentinel/js/linkedin/form_fill.js`
- `src/sentinel/js/linkedin/modal_close.js`
- `src/sentinel/js/linkedin/rate_limit.js`

### 6.5 Extract Naukri JavaScript
Files:
- `src/sentinel/js/naukri/chatbot.js`
- `src/sentinel/js/naukri/form_submit.js`
- `src/sentinel/js/naukri/profile_edit.js`
- `src/sentinel/js/naukri/checkbox_select.js`
- `src/sentinel/js/naukri/tab_navigation.js`

### 6.6 Extract Instahyre JavaScript
Files:
- `src/sentinel/js/instahyre/filter_panel.js`
- `src/sentinel/js/instahyre/selectize_helpers.js`
- `src/sentinel/js/instahyre/view_apply.js`

## Testing Strategy

### Unit Tests: `tests/unit/sentinel/test_js_loader.py`
```python
def test_load_js_file_exists():
    """Test loading existing JS file"""
    js_content = load_js("utils.js")
    assert js_content is not None
    assert "function" in js_content

def test_load_js_file_not_found():
    """Test handling of missing JS file"""
    with pytest.raises(FileNotFoundError):
        load_js("nonexistent.js")

def test_load_js_with_variables():
    """Test loading JS with variable substitution"""
    js_content = load_js_with_vars("template.js", {"timeout": 5000})
    assert "5000" in js_content
```

## Files to Create
- [ ] Create: `src/sentinel/js_loader.py`
- [ ] Create: `src/sentinel/js/utils.js`
- [ ] Create: `src/sentinel/js/login_detection.js`
- [ ] Create: `src/sentinel/js/dialog_dismiss.js`
- [ ] Create: `src/sentinel/js/memory_cleanup.js`
- [ ] Create: `src/sentinel/js/linkedin/*.js` (4 files)
- [ ] Create: `src/sentinel/js/naukri/*.js` (5 files)
- [ ] Create: `src/sentinel/js/instahyre/*.js` (3 files)
- [ ] Create: `tests/unit/sentinel/test_js_loader.py`

## Success Criteria
- [ ] All JavaScript extracted to .js files
- [ ] JS loader working correctly
- [ ] No inline JavaScript strings remaining in agent.py
- [ ] All tests pass
- [ ] agent.py reduced by ~3000 lines

## Estimated Time
12-16 hours

## Dependencies
- Phase 5 (Platform Handlers - JS is used by handlers)

## Risk Mitigation
- Extract JS block by block to avoid missing code
- Test each JS file works before moving to next
- Keep backups of original agent.py
- Validate JS syntax after extraction
