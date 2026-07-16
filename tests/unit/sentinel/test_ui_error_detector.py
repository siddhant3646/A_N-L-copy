from unittest.mock import AsyncMock, MagicMock
import pytest
from src.sentinel.ui_error_detector import (
    UIErrorDetector, UIError, UIErrorRecovery, ErrorType, Platform
)


class TestErrorTypeEnum:
    def test_has_expected_members(self):
        assert ErrorType.VALIDATION_ERROR.value == "validation_error"
        assert ErrorType.RATE_LIMIT.value == "rate_limit"
        assert ErrorType.SESSION_EXPIRED.value == "session_expired"
        assert ErrorType.GENERIC_ERROR.value == "generic_error"

    def test_has_state_desync_member(self):
        assert ErrorType.STATE_DESYNC.value == "state_desync"


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

    def test_state_desync_error(self):
        err = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Please enter a valid number",
            field_label="Years of experience",
            field_value="4",
            available_options=[],
            suggestions=[],
        )
        assert err.error_type == ErrorType.STATE_DESYNC
        assert err.field_value == "4"


class TestUIErrorDetectorInit:
    def test_init_with_page(self):
        mock_page = AsyncMock()
        detector = UIErrorDetector(page=mock_page)
        assert detector is not None
        assert detector.page == mock_page


class TestAriaInvalidDetection:
    """Tests for Method A: aria-invalid detection."""

    @pytest.mark.asyncio
    async def test_detect_aria_invalid_with_value_classifies_state_desync(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                'message': 'Invalid input',
                'field_label': 'Years of experience',
                'field_value': '4',
                'available_options': []
            }
        ])
        detector = UIErrorDetector(page=mock_page)

        errors = await detector._detect_aria_invalid_errors(Platform.LINKEDIN)

        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.STATE_DESYNC
        assert errors[0].field_value == '4'
        assert errors[0].platform == Platform.LINKEDIN

    @pytest.mark.asyncio
    async def test_detect_aria_invalid_empty_value_not_state_desync(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                'message': 'This field is required',
                'field_label': 'Name',
                'field_value': '',
                'available_options': []
            }
        ])
        detector = UIErrorDetector(page=mock_page)

        errors = await detector._detect_aria_invalid_errors(Platform.LINKEDIN)

        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.REQUIRED_FIELD_EMPTY

    @pytest.mark.asyncio
    async def test_detect_aria_invalid_handles_evaluation_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        detector = UIErrorDetector(page=mock_page)

        errors = await detector._detect_aria_invalid_errors(Platform.LINKEDIN)

        assert errors == []


class TestComputedColorDetection:
    """Tests for Method D: computed color detection."""

    @pytest.mark.asyncio
    async def test_detect_error_color_with_value_classifies_state_desync(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {
                'message': 'Please enter a valid number',
                'field_label': 'Experience',
                'field_value': '7',
                'available_options': []
            }
        ])
        detector = UIErrorDetector(page=mock_page)

        errors = await detector._detect_error_color_elements(Platform.LINKEDIN)

        assert len(errors) == 1
        assert errors[0].error_type == ErrorType.STATE_DESYNC
        assert errors[0].field_value == '7'

    @pytest.mark.asyncio
    async def test_detect_error_color_handles_evaluation_error(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        detector = UIErrorDetector(page=mock_page)

        errors = await detector._detect_error_color_elements(Platform.LINKEDIN)

        assert errors == []


class TestDedupeErrors:
    """Tests for error deduplication."""

    def test_dedupe_removes_duplicates(self):
        err1 = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Invalid input",
            field_label="Experience",
            field_value="4",
            available_options=[],
            suggestions=[]
        )
        err2 = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Invalid input",
            field_label="Experience",
            field_value="4",
            available_options=[],
            suggestions=[]
        )
        detector = UIErrorDetector(page=AsyncMock())

        result = detector._dedupe_errors([err1, err2])

        assert len(result) == 1

    def test_dedupe_keeps_distinct_errors(self):
        err1 = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Invalid input",
            field_label="Experience",
            field_value="4",
            available_options=[],
            suggestions=[]
        )
        err2 = UIError(
            error_type=ErrorType.REQUIRED_FIELD_EMPTY,
            platform=Platform.LINKEDIN,
            message="This field is required",
            field_label="Name",
            field_value=None,
            available_options=[],
            suggestions=[]
        )
        detector = UIErrorDetector(page=AsyncMock())

        result = detector._dedupe_errors([err1, err2])

        assert len(result) == 2


class TestStateDesyncRecovery:
    """Tests for STATE_DESYNC recovery branch."""

    @pytest.mark.asyncio
    async def test_state_desync_recovery_calls_resync(self, monkeypatch):
        mock_page = AsyncMock()
        mock_page.url = "https://linkedin.com"
        mock_page.query_selector = AsyncMock(return_value=AsyncMock())

        resync_called = []

        async def fake_resync(page, element, blur_with_tab=True):
            resync_called.append(True)
            return True

        monkeypatch.setattr(
            "src.sentinel.human_behavior.resync_input_state", fake_resync
        )

        detector = UIErrorDetector(page=mock_page)
        recovery = UIErrorRecovery(
            detector=detector,
            self_healing_matcher=MagicMock(),
            input_resolver=MagicMock()
        )

        error = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Invalid input",
            field_label="Experience",
            field_value="4",
            available_options=[],
            suggestions=[]
        )

        success, answer, strategy = await recovery.attempt_recovery(
            error, "4", "Experience"
        )

        assert success is True
        assert answer == "4"
        assert strategy == "state_resync"
        assert len(resync_called) == 1

    @pytest.mark.asyncio
    async def test_state_desync_recovery_fails_when_no_element(self, monkeypatch):
        mock_page = AsyncMock()
        mock_page.url = "https://linkedin.com"
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.evaluate_handle = AsyncMock(return_value=None)

        async def fake_resync(page, element, blur_with_tab=True):
            return True

        monkeypatch.setattr(
            "src.sentinel.human_behavior.resync_input_state", fake_resync
        )

        detector = UIErrorDetector(page=mock_page)
        recovery = UIErrorRecovery(
            detector=detector,
            self_healing_matcher=MagicMock(),
            input_resolver=MagicMock()
        )

        error = UIError(
            error_type=ErrorType.STATE_DESYNC,
            platform=Platform.LINKEDIN,
            message="Invalid input",
            field_label="Experience",
            field_value="4",
            available_options=[],
            suggestions=[]
        )

        success, answer, strategy = await recovery.attempt_recovery(
            error, "4", "Experience"
        )

        assert success is False
        assert strategy == "state_resync_failed"
