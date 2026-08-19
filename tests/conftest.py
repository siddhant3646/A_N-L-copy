"""
Pytest configuration and shared fixtures for Sentinel testing.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# =============================================================================
# Mock Browser Fixtures
# =============================================================================

@pytest.fixture
def mock_page():
    """Create a mocked Playwright page."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    page.click = AsyncMock()
    page.goto = AsyncMock()
    page.url = "https://example.com"
    page.content = AsyncMock(return_value="<html><body>Test</body></html>")
    page.title = AsyncMock(return_value="Test Page")
    page.screenshot = AsyncMock(return_value=b"screenshot_data")
    
    # Mouse actions
    page.mouse = AsyncMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    
    # Locator mock
    mock_locator = AsyncMock()
    mock_locator.click = AsyncMock()
    mock_locator.fill = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.is_enabled = AsyncMock(return_value=True)
    mock_locator.text_content = AsyncMock(return_value="Button Text")
    mock_locator.get_attribute = AsyncMock(return_value="attr_value")
    mock_locator.count = AsyncMock(return_value=1)
    
    page.locator = MagicMock(return_value=mock_locator)
    page.query_selector = AsyncMock(return_value=mock_locator)
    page.query_selector_all = AsyncMock(return_value=[mock_locator])
    
    return page


@pytest.fixture
def mock_context():
    """Create a mocked Playwright context."""
    context = AsyncMock()
    context.new_page = AsyncMock()
    context.pages = []
    context.close = AsyncMock()
    return context


@pytest.fixture
def mock_browser():
    """Create a mocked Browser instance."""
    browser = MagicMock()
    browser.get_current_page = AsyncMock()
    browser.start = AsyncMock()
    browser.stop = AsyncMock()
    browser.new_page = AsyncMock()
    browser.context = None
    return browser


# =============================================================================
# Mock Platform Handlers
# =============================================================================

@pytest.fixture
def mock_platform_handlers():
    """Create mocked platform handlers for all platforms."""
    handlers = {
        "linkedin": AsyncMock(),
        "naukri": AsyncMock(),
        "instahyre": AsyncMock()
    }
    
    # Set up default return values
    for handler in handlers.values():
        handler.platform_name = "test_platform"
        handler.detect_login_required = AsyncMock(return_value=False)
        handler.detect_rate_limit = AsyncMock(return_value=False)
        handler.handle_task = AsyncMock(return_value="SUCCESS")
        handler.handle_form = AsyncMock(return_value="SUCCESS")
        handler.get_selectors = MagicMock(return_value={})
    
    return handlers


@pytest.fixture
def mock_linkedin_handler():
    """Create a mocked LinkedIn handler."""
    handler = AsyncMock()
    handler.platform_name = "linkedin"
    handler.detect_login_required = AsyncMock(return_value=False)
    handler.detect_rate_limit = AsyncMock(return_value=False)
    handler.handle_task = AsyncMock(return_value="SUCCESS")
    handler.handle_autopilot = AsyncMock(return_value="SUCCESS")
    handler.handle_form = AsyncMock(return_value="SUCCESS")
    handler.get_selectors = MagicMock(return_value={
        "easy_apply_button": ".jobs-apply-button",
        "job_card": ".job-card-container",
        "next_button": "button[aria-label='Continue']"
    })
    return handler


@pytest.fixture
def mock_naukri_handler():
    """Create a mocked Naukri handler."""
    handler = AsyncMock()
    handler.platform_name = "naukri"
    handler.detect_login_required = AsyncMock(return_value=False)
    handler.detect_rate_limit = AsyncMock(return_value=False)
    handler.handle_task = AsyncMock(return_value="SUCCESS")
    handler.handle_profile_update = AsyncMock(return_value="SUCCESS")
    handler.handle_employment_update = AsyncMock(return_value="SUCCESS")
    handler.handle_apply = AsyncMock(return_value="SUCCESS")
    handler.get_selectors = MagicMock(return_value={
        "job_checkbox": ".saveJobContainer",
        "apply_button": ".multi-apply-button",
        "chatbot_drawer": "#chatbot_DrawerContentWrapper"
    })
    return handler


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_qa_patterns():
    """Sample Q&A patterns for testing."""
    return {
        "salary": {
            "patterns": ["current salary", "what is your ctc", "current ctc"],
            "category": "salary",
            "default": "13.5 LPA",
            "numeric_default": "13.5"
        },
        "experience": {
            "patterns": ["years of experience", "total experience", "work experience"],
            "category": "experience",
            "default": "4.2",
            "numeric_default": "4.2"
        },
        "notice_period": {
            "patterns": ["notice period", "serving notice", "np"],
            "category": "notice_period",
            "default": "Serving Notice Period",
            "numeric_default": "30"
        },
        "last_working_date": {
            "patterns": ["last working date", "what is your lwd", "lwd date"],
            "category": "notice_period",
            "default": "__DYNAMIC_LWD__",
            "input_type_defaults": {
                "text": "__DYNAMIC_LWD__",
                "date": "__DYNAMIC_LWD__"
            },
            "priority": 13
        },
        "location": {
            "patterns": ["current location", "current city", "where are you located"],
            "category": "location",
            "default": "Bangalore"
        }
    }


@pytest.fixture
def sample_questions():
    """Sample questions for testing pattern matching."""
    return [
        ("What is your current salary?", "13.5 LPA", "salary"),
        ("How many years of experience do you have?", "4.2", "experience"),
        ("What is your notice period?", "Serving Notice Period", "notice_period"),
        ("Where are you currently located?", "Bangalore", "location"),
        ("Current CTC in LPA?", "13.5", "salary"),
        ("Total years of experience", "4.2", "experience"),
    ]


@pytest.fixture
def sample_agent_state():
    """Sample agent state for testing."""
    return {
        "step_count": 0,
        "task_complete": False,
        "errors": [],
        "last_action": None,
        "last_result": "",
        "linkedin_applications": 0,
        "naukri_applications": 0,
        "same_result_count": 0,
        "steps_since_cleanup": 0,
        "logged_questions": set(),
        "all_logged_questions": set()
    }


# =============================================================================
# File System Fixtures
# =============================================================================

@pytest.fixture
def temp_directory():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_profile_dir():
    """Create a temporary profile directory for testing."""
    temp_dir = tempfile.mkdtemp()
    profile_dir = os.path.join(temp_dir, "p")
    os.makedirs(profile_dir, exist_ok=True)
    yield profile_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_qa_patterns_file(temp_directory):
    """Create a temporary QA patterns JSON file."""
    patterns = {
        "version": "1.0",
        "patterns": {
            "test_pattern": {
                "patterns": ["test question"],
                "category": "test",
                "default": "test answer"
            }
        }
    }
    
    file_path = os.path.join(temp_directory, "test_patterns.json")
    with open(file_path, "w") as f:
        json.dump(patterns, f, indent=2)
    
    return file_path


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """Mock configuration values."""
    return {
        "CHROME_USER_DATA": "/tmp/chrome_profile",
        "CHROME_EXECUTABLE_PATH": "/usr/bin/chrome",
        "SCREENSHOT_DIR": "/tmp/screenshots",
        "LOG_DIR": "/tmp/logs",
        "MAX_STEPS_LINKEDIN": 120,
        "MAX_STEPS_DEFAULT": 50
    }


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("CHROME_USER_DATA", "/tmp/test_chrome_profile")
    monkeypatch.setenv("CHROME_EXECUTABLE_PATH", "/usr/bin/test_chrome")


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def mock_datetime():
    """Mock datetime for rate limiting tests."""
    with patch("datetime.datetime") as mock_dt:
        yield mock_dt


@pytest.fixture
def mock_sleep():
    """Mock asyncio.sleep for faster tests."""
    with patch("asyncio.sleep") as mock:
        yield mock


# =============================================================================
# Test Categories
# =============================================================================

def pytest_collection_modifyitems(config, items):
    """Add markers to tests based on their location."""
    for item in items:
        # Mark tests in tests/unit as unit tests
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Mark tests in tests/integration as integration tests
        elif "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        # Mark tests in tests/e2e as e2e tests
        elif "tests/e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
