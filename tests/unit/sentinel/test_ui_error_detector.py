import pytest
from unittest.mock import AsyncMock, MagicMock
from src.sentinel.ui_error_detector import (
    UIErrorDetector, UIError, ErrorType, Platform
)


class TestErrorTypeEnum:
    def test_has_expected_members(self):
        assert ErrorType.VALIDATION_ERROR.value == "validation_error"
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
        assert ErrorType.SESSION_EXPIRED.value == "session_expired"
        assert ErrorType.GENERIC_ERROR.value == "generic_error"


class TestPlatformEnum:
    def test_has_expected_members(self):
        assert Platform.LINKEDIN.value == "linkedin"
        assert Platform.NAUKRI.value == "naukri"
        assert Platform.INSTAHYRE.value == "instahyre"
        assert Platform.UNKNOWN.value == "unknown"


class TestUIErrorDataclass:
    def test_default_screenshot_path(self):
        err = UIError(
            error_type=ErrorType.VALIDATION_ERROR,
            platform=Platform.LINKEDIN,
            message="Error",
            field_label=None,
            field_value=None,
            available_options=[],
            suggestions=[],
        )
        assert err.screenshot_path is None

    def test_with_all_fields(self):
        err = UIError(
            error_type=ErrorType.RATE_LIMIT,
            platform=Platform.NAUKRI,
            message="Too many requests",
            field_label="submit",
            field_value="Yes",
            available_options=["Yes", "No"],
            suggestions=["Wait"],
            screenshot_path="/tmp/screen.png",
        )
        assert err.platform == Platform.NAUKRI
        assert err.screenshot_path == "/tmp/screen.png"


class TestUIErrorDetectorInit:
    def test_init_with_page(self):
        mock_page = AsyncMock()
        detector = UIErrorDetector(page=mock_page)
        assert detector is not None
        assert detector.page == mock_page
