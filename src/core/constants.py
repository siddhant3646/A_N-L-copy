"""
Constants module - Global constants and configuration values.

This module contains all magic strings, platform identifiers, result codes,
and configuration constants used throughout the application.
"""

from pathlib import Path
import os

# =============================================================================
# Platform Identifiers
# =============================================================================

PLATFORM_NAUKRI = "naukri"
PLATFORM_LINKEDIN = "linkedin"
PLATFORM_INSTAHYRE = "instahyre"
PLATFORM_DEFAULT = "default"

ALL_PLATFORMS = [PLATFORM_NAUKRI, PLATFORM_LINKEDIN, PLATFORM_INSTAHYRE]

# =============================================================================
# Result Codes
# =============================================================================

RESULT_TASK_COMPLETE = "TASK_COMPLETE"
RESULT_SUCCESS = "SUCCESS"
RESULT_RATE_LIMITED = "RATE_LIMITED"
RESULT_LOGIN_REQUIRED = "LOGIN_REQUIRED"
RESULT_ERROR = "ERROR"
RESULT_CONTINUE = "CONTINUE"
RESULT_DONE = "DONE"
RESULT_STOP = "STOP"

# =============================================================================
# Step Limits
# =============================================================================

MAX_STEPS_LINKEDIN = 120
MAX_STEPS_DEFAULT = 50
MEMORY_CLEANUP_INTERVAL = 50

# =============================================================================
# Matching Thresholds
# =============================================================================

FUZZY_MATCH_THRESHOLD = 0.6
MIN_CONFIDENCE_SCORE = 0.7

# =============================================================================
# Rate Limiting
# =============================================================================

LINKEDIN_RATE_LIMIT_HOURS = 24
NAUKRI_RATE_LIMIT_HOURS = 12
INSTAHYRE_RATE_LIMIT_HOURS = 6

# =============================================================================
# File Paths
# =============================================================================

# Default directories
SCREENSHOT_DIR = os.path.expanduser("~/Desktop/sentinel_errors")
LOG_DIR = os.path.expanduser("~/Desktop/sentinel_errors")

# Log files
UNKNOWN_QUESTIONS_LOG = os.path.join(LOG_DIR, "unknown_questions.log")
ALL_QUESTIONS_LOG = os.path.join(LOG_DIR, "all_questions.log")
METRICS_LOG = os.path.join(LOG_DIR, "metrics.jsonl")

# Pattern file
PATTERNS_FILE = Path(__file__).parent.parent.parent / "config" / "qa_patterns.json"

# =============================================================================
# Browser Settings
# =============================================================================

# Chrome arguments
CHROME_ARGS = [
    '--no-sandbox',
    '--disable-blink-features=AutomationControlled',
    '--start-maximized',
    '--disable-session-crashed-bubble',
    '--no-restore-session-state',
    '--ignore-certificate-errors',
    '--ignore-ssl-errors'
]

# Default timeouts
DEFAULT_TIMEOUT = 5000
CLICK_TIMEOUT = 3000
PAGE_LOAD_TIMEOUT = 10000

# =============================================================================
# Human Simulation Settings
# =============================================================================

# Mouse movement
MOUSE_MOVE_MIN = 200
MOUSE_MOVE_MAX = 800
MOUSE_STEP_MIN = 5
MOUSE_STEP_MAX = 15

# Scrolling
SCROLL_AMOUNT_MIN = 300
SCROLL_AMOUNT_MAX = 800
SCROLL_DELAY_MIN = 100
SCROLL_DELAY_MAX = 300

# Delays
MIN_ACTION_DELAY = 1.0
MAX_ACTION_DELAY = 3.0
MIN_TYPING_DELAY = 0.05
MAX_TYPING_DELAY = 0.15

# =============================================================================
# Application State
# =============================================================================

# Agent states
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_ERROR = "error"
STATE_COMPLETED = "completed"

# Task types
TASK_LINKEDIN_APPLICATION = "LinkedIn Application"
TASK_NAUKRI_APPLICATION = "Naukri Application"
TASK_INSTAHYRE_SEARCH = "Instahyre Search"
TASK_NAUKRI_PROFILE_UPDATE = "Naukri Profile Update"
TASK_NAUKRI_EMPLOYMENT_UPDATE = "Naukri Employment Update"
TASK_NAUKRI_EARLY_ACCESS = "Naukri Early Access"

# Task to platform mapping
TASK_PLATFORM_MAP = {
    TASK_LINKEDIN_APPLICATION: PLATFORM_LINKEDIN,
    TASK_NAUKRI_APPLICATION: PLATFORM_NAUKRI,
    TASK_INSTAHYRE_SEARCH: PLATFORM_INSTAHYRE,
    TASK_NAUKRI_PROFILE_UPDATE: PLATFORM_NAUKRI,
    TASK_NAUKRI_EMPLOYMENT_UPDATE: PLATFORM_NAUKRI,
    TASK_NAUKRI_EARLY_ACCESS: PLATFORM_NAUKRI,
}

# =============================================================================
# Selectors (to be moved to platform-specific files in Phase 5)
# =============================================================================

# These are placeholders - actual selectors will be in platform handler files
LINKEDIN_SELECTORS = {
    "easy_apply_button": ".jobs-apply-button",
    "job_card": ".job-card-container",
    "next_button": "button[aria-label='Continue']",
    "submit_button": "button[aria-label='Submit application']",
    "modal_close": "button[aria-label='Dismiss']"
}

NAUKRI_SELECTORS = {
    "job_checkbox": ".saveJobContainer",
    "apply_button": ".multi-apply-button",
    "chatbot_drawer": "#chatbot_DrawerContentWrapper",
    "profile_edit": ".edit-profile",
    "save_button": ".save-button"
}

INSTAHYRE_SELECTORS = {
    "filter_panel": ".filter-panel",
    "show_results": ".show-results-button",
    "view_button": ".view-button",
    "apply_button": ".apply-button"
}

# =============================================================================
# Error Messages
# =============================================================================

ERROR_MESSAGES = {
    "login_required": "Login required for {platform}",
    "rate_limited": "Rate limited on {platform}. Try again after {hours} hours.",
    "page_not_found": "Page not found or not loaded",
    "element_not_found": "Element not found: {selector}",
    "timeout": "Operation timed out after {seconds} seconds",
    "unknown_error": "Unknown error occurred: {error}"
}

# =============================================================================
# Success Messages
# =============================================================================

SUCCESS_MESSAGES = {
    "application_submitted": "Application submitted successfully",
    "profile_updated": "Profile updated successfully",
    "task_completed": "Task completed: {task}",
    "form_filled": "Form filled successfully"
}

# =============================================================================
# Helper Functions
# =============================================================================

def get_platform_from_task(task_name: str) -> str:
    """
    Get platform identifier from task name.
    
    Args:
        task_name: Name of the task
        
    Returns:
        Platform identifier string
    """
    task_lower = task_name.lower()
    
    if PLATFORM_LINKEDIN in task_lower:
        return PLATFORM_LINKEDIN
    elif PLATFORM_NAUKRI in task_lower:
        return PLATFORM_NAUKRI
    elif PLATFORM_INSTAHYRE in task_lower:
        return PLATFORM_INSTAHYRE
    
    return PLATFORM_DEFAULT


def is_rate_limited(platform: str) -> bool:
    """
    Check if a platform is currently rate limited.
    
    Args:
        platform: Platform identifier
        
    Returns:
        True if rate limited
    """
    # This is a placeholder - actual implementation will check timestamps
    return False


def get_rate_limit_hours(platform: str) -> int:
    """
    Get rate limit duration for a platform.
    
    Args:
        platform: Platform identifier
        
    Returns:
        Hours to wait before retry
    """
    limits = {
        PLATFORM_LINKEDIN: LINKEDIN_RATE_LIMIT_HOURS,
        PLATFORM_NAUKRI: NAUKRI_RATE_LIMIT_HOURS,
        PLATFORM_INSTAHYRE: INSTAHYRE_RATE_LIMIT_HOURS
    }
    
    return limits.get(platform, 12)
