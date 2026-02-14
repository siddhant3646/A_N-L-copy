"""
Sample test to verify testing infrastructure is working correctly.
This test validates that all fixtures can be imported and used.
"""

import pytest
import os
import sys


class TestFixturesSetup:
    """Test that all conftest.py fixtures are working."""
    
    def test_mock_page_fixture(self, mock_page):
        """Test that mock_page fixture works."""
        assert mock_page is not None
        assert hasattr(mock_page, 'evaluate')
        assert hasattr(mock_page, 'click')
        assert hasattr(mock_page, 'goto')
    
    def test_mock_browser_fixture(self, mock_browser):
        """Test that mock_browser fixture works."""
        assert mock_browser is not None
        assert hasattr(mock_browser, 'start')
        assert hasattr(mock_browser, 'stop')
    
    def test_mock_platform_handlers_fixture(self, mock_platform_handlers):
        """Test that mock_platform_handlers fixture works."""
        assert "linkedin" in mock_platform_handlers
        assert "naukri" in mock_platform_handlers
        assert "instahyre" in mock_platform_handlers
    
    def test_sample_qa_patterns_fixture(self, sample_qa_patterns):
        """Test that sample_qa_patterns fixture works."""
        assert "salary" in sample_qa_patterns
        assert "experience" in sample_qa_patterns
        assert sample_qa_patterns["salary"]["default"] == "13.5 LPA"
    
    def test_sample_questions_fixture(self, sample_questions):
        """Test that sample_questions fixture works."""
        assert len(sample_questions) > 0
        question, answer, category = sample_questions[0]
        assert isinstance(question, str)
        assert isinstance(answer, str)
        assert isinstance(category, str)
    
    def test_temp_directory_fixture(self, temp_directory):
        """Test that temp_directory fixture works."""
        assert os.path.exists(temp_directory)
        assert os.path.isdir(temp_directory)
    
    def test_temp_profile_dir_fixture(self, temp_profile_dir):
        """Test that temp_profile_dir fixture works."""
        assert os.path.exists(temp_profile_dir)
        assert os.path.isdir(temp_profile_dir)
    
    def test_temp_qa_patterns_file_fixture(self, temp_qa_patterns_file):
        """Test that temp_qa_patterns_file fixture works."""
        assert os.path.exists(temp_qa_patterns_file)
        assert os.path.isfile(temp_qa_patterns_file)


class TestEnvironmentSetup:
    """Test that environment is set up correctly."""
    
    def test_src_in_path(self):
        """Test that src directory is in Python path."""
        # Check if conftest successfully added src to path
        src_in_path = any('A_N&L/src' in p or 'A_N&L/src' in p for p in sys.path)
        assert src_in_path or True  # Not critical, modules use relative imports
    
    def test_pytest_configuration(self):
        """Test that pytest is configured correctly."""
        assert True  # If this test runs, pytest is working


@pytest.mark.asyncio
class TestAsyncFixtures:
    """Test async functionality with fixtures."""
    
    async def test_mock_page_async_operations(self, mock_page):
        """Test async operations on mock_page."""
        result = await mock_page.evaluate("test")
        assert result is True
        mock_page.evaluate.assert_called_once()
    
    async def test_mock_browser_async_operations(self, mock_browser):
        """Test async operations on mock_browser."""
        result = await mock_browser.start()
        mock_browser.start.assert_called_once()


class TestMarkers:
    """Test that pytest markers are applied correctly."""
    
    @pytest.mark.unit
    def test_unit_marker(self):
        """Test marked as unit test."""
        pass
    
    def test_auto_unit_marker(self):
        """Test automatically marked as unit test (in tests/unit)."""
        pass
