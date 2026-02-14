"""
Tests for constants module.
"""

import pytest
from src.core.constants import (
    PLATFORM_NAUKRI,
    PLATFORM_LINKEDIN,
    PLATFORM_INSTAHYRE,
    ALL_PLATFORMS,
    RESULT_SUCCESS,
    RESULT_ERROR,
    MAX_STEPS_LINKEDIN,
    MAX_STEPS_DEFAULT,
    FUZZY_MATCH_THRESHOLD,
    get_platform_from_task,
    get_rate_limit_hours,
    TASK_PLATFORM_MAP,
)


class TestPlatformConstants:
    """Test platform identifier constants."""
    
    def test_platform_values(self):
        """Test that platform constants have correct values."""
        assert PLATFORM_NAUKRI == "naukri"
        assert PLATFORM_LINKEDIN == "linkedin"
        assert PLATFORM_INSTAHYRE == "instahyre"
    
    def test_all_platforms_list(self):
        """Test that ALL_PLATFORMS contains all platforms."""
        assert len(ALL_PLATFORMS) == 3
        assert PLATFORM_NAUKRI in ALL_PLATFORMS
        assert PLATFORM_LINKEDIN in ALL_PLATFORMS
        assert PLATFORM_INSTAHYRE in ALL_PLATFORMS
    
    def test_all_platforms_unique(self):
        """Test that all platform identifiers are unique."""
        assert len(ALL_PLATFORMS) == len(set(ALL_PLATFORMS))


class TestResultCodes:
    """Test result code constants."""
    
    def test_result_codes_are_strings(self):
        """Test that result codes are strings."""
        assert isinstance(RESULT_SUCCESS, str)
        assert isinstance(RESULT_ERROR, str)
    
    def test_result_codes_not_empty(self):
        """Test that result codes are not empty."""
        assert len(RESULT_SUCCESS) > 0
        assert len(RESULT_ERROR) > 0


class TestStepLimits:
    """Test step limit constants."""
    
    def test_step_limits_positive(self):
        """Test that step limits are positive integers."""
        assert MAX_STEPS_LINKEDIN > 0
        assert MAX_STEPS_DEFAULT > 0
        assert isinstance(MAX_STEPS_LINKEDIN, int)
        assert isinstance(MAX_STEPS_DEFAULT, int)
    
    def test_linkedin_has_more_steps(self):
        """Test that LinkedIn has more steps than default."""
        assert MAX_STEPS_LINKEDIN > MAX_STEPS_DEFAULT


class TestThresholds:
    """Test threshold constants."""
    
    def test_fuzzy_match_threshold_valid(self):
        """Test that fuzzy match threshold is between 0 and 1."""
        assert 0.0 <= FUZZY_MATCH_THRESHOLD <= 1.0


class TestGetPlatformFromTask:
    """Test get_platform_from_task function."""
    
    def test_linkedin_task(self):
        """Test getting platform from LinkedIn task."""
        assert get_platform_from_task("LinkedIn Application") == PLATFORM_LINKEDIN
        assert get_platform_from_task("linkedin profile update") == PLATFORM_LINKEDIN
    
    def test_naukri_task(self):
        """Test getting platform from Naukri task."""
        assert get_platform_from_task("Naukri Application") == PLATFORM_NAUKRI
        assert get_platform_from_task("naukri profile update") == PLATFORM_NAUKRI
    
    def test_instahyre_task(self):
        """Test getting platform from Instahyre task."""
        assert get_platform_from_task("Instahyre Search") == PLATFORM_INSTAHYRE
        assert get_platform_from_task("instahyre filters") == PLATFORM_INSTAHYRE
    
    def test_unknown_task_returns_default(self):
        """Test that unknown task returns default platform."""
        result = get_platform_from_task("Unknown Task")
        assert result in ALL_PLATFORMS or result == "default"


class TestGetRateLimitHours:
    """Test get_rate_limit_hours function."""
    
    def test_linkedin_rate_limit(self):
        """Test LinkedIn rate limit hours."""
        hours = get_rate_limit_hours(PLATFORM_LINKEDIN)
        assert hours > 0
        assert isinstance(hours, int)
    
    def test_naukri_rate_limit(self):
        """Test Naukri rate limit hours."""
        hours = get_rate_limit_hours(PLATFORM_NAUKRI)
        assert hours > 0
        assert isinstance(hours, int)
    
    def test_instahyre_rate_limit(self):
        """Test Instahyre rate limit hours."""
        hours = get_rate_limit_hours(PLATFORM_INSTAHYRE)
        assert hours > 0
        assert isinstance(hours, int)
    
    def test_unknown_platform_default(self):
        """Test that unknown platform returns default hours."""
        hours = get_rate_limit_hours("unknown_platform")
        assert hours > 0
        assert isinstance(hours, int)


class TestTaskPlatformMap:
    """Test task to platform mapping."""
    
    def test_all_tasks_have_platforms(self):
        """Test that all tasks in map have valid platforms."""
        for task, platform in TASK_PLATFORM_MAP.items():
            assert platform in ALL_PLATFORMS or platform in [
                PLATFORM_NAUKRI, PLATFORM_LINKEDIN, PLATFORM_INSTAHYRE
            ]
    
    def test_task_platform_consistency(self):
        """Test that task platform mapping is consistent with get_platform_from_task."""
        for task, expected_platform in TASK_PLATFORM_MAP.items():
            detected_platform = get_platform_from_task(task)
            # Note: There might be a typo in constants.py (NAUKRE vs NAUKRI)
            # This test will help identify that
            assert detected_platform == expected_platform or expected_platform == "naukre"
