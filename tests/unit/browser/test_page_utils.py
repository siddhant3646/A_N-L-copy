"""
Tests for Page Utils module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.sentinel.page_utils import (
    check_page_health,
    maybe_cleanup_memory,
    wait_for_page_stable,
    get_page_metrics,
    clear_browser_data,
)


@pytest.mark.asyncio
class TestCheckPageHealth:
    """Test check_page_health function."""
    
    async def test_healthy_page(self, mock_page):
        """Test healthy page returns True."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        
        result = await check_page_health(mock_page)
        
        assert result is True
    
    async def test_interactive_page(self, mock_page):
        """Test interactive page returns True."""
        mock_page.evaluate = AsyncMock(return_value="interactive")
        
        result = await check_page_health(mock_page)
        
        assert result is True
    
    async def test_loading_page(self, mock_page):
        """Test loading page returns False."""
        mock_page.evaluate = AsyncMock(return_value="loading")
        
        result = await check_page_health(mock_page)
        
        assert result is False
    
    async def test_none_page(self):
        """Test None page returns False."""
        result = await check_page_health(None)
        
        assert result is False
    
    async def test_exception_page(self, mock_page):
        """Test page that throws exception returns False."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Page crashed"))
        
        result = await check_page_health(mock_page)
        
        assert result is False


@pytest.mark.asyncio
class TestMaybeCleanupMemory:
    """Test maybe_cleanup_memory function."""
    
    async def test_no_cleanup_needed(self, mock_page):
        """Test cleanup not performed before interval."""
        result = await maybe_cleanup_memory(mock_page, steps_since_cleanup=10, interval=50)
        
        assert result == 11  # Incremented
        mock_page.evaluate.assert_not_called()
    
    async def test_cleanup_performed(self, mock_page):
        """Test cleanup performed at interval."""
        mock_page.evaluate = AsyncMock(return_value=None)
        
        result = await maybe_cleanup_memory(mock_page, steps_since_cleanup=50, interval=50)
        
        assert result == 0  # Reset
        assert mock_page.evaluate.call_count >= 2  # gc + console.clear
    
    async def test_cleanup_exception(self, mock_page):
        """Test cleanup handles exceptions gracefully."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Cleanup failed"))
        
        result = await maybe_cleanup_memory(mock_page, steps_since_cleanup=50, interval=50)
        
        # Should return original value on error
        assert result == 50


@pytest.mark.asyncio
class TestWaitForPageStable:
    """Test wait_for_page_stable function."""
    
    async def test_page_becomes_stable(self, mock_page):
        """Test successful wait for stability."""
        mock_page.wait_for_load_state = AsyncMock(return_value=None)
        
        result = await wait_for_page_stable(mock_page)
        
        assert result is True
        mock_page.wait_for_load_state.assert_called_once()
    
    async def test_page_timeout(self, mock_page):
        """Test timeout waiting for stability."""
        mock_page.wait_for_load_state = AsyncMock(side_effect=Exception("Timeout"))
        
        result = await wait_for_page_stable(mock_page, timeout_ms=1000)
        
        assert result is False


@pytest.mark.asyncio
class TestGetPageMetrics:
    """Test get_page_metrics function."""
    
    async def test_get_metrics_success(self, mock_page):
        """Test successful metrics retrieval."""
        mock_metrics = {
            "loadTime": 1000,
            "domContentLoaded": 500,
            "memory": {
                "usedJSHeapSize": 1000000,
                "totalJSHeapSize": 2000000
            }
        }
        mock_page.evaluate = AsyncMock(return_value=mock_metrics)
        
        result = await get_page_metrics(mock_page)
        
        assert result["loadTime"] == 1000
        assert result["domContentLoaded"] == 500
        assert "memory" in result
    
    async def test_get_metrics_failure(self, mock_page):
        """Test metrics retrieval failure."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Metrics error"))
        
        result = await get_page_metrics(mock_page)
        
        assert result == {}


@pytest.mark.asyncio
class TestClearBrowserData:
    """Test clear_browser_data function."""
    
    async def test_clear_success(self, mock_page):
        """Test successful clearing of browser data."""
        mock_page.context.clear_cookies = AsyncMock(return_value=None)
        mock_page.evaluate = AsyncMock(return_value=None)
        
        result = await clear_browser_data(mock_page)
        
        assert result is True
        mock_page.context.clear_cookies.assert_called_once()
        assert mock_page.evaluate.call_count >= 2  # localStorage + sessionStorage
    
    async def test_clear_failure(self, mock_page):
        """Test clearing failure."""
        mock_page.context.clear_cookies = AsyncMock(side_effect=Exception("Clear failed"))
        
        result = await clear_browser_data(mock_page)
        
        assert result is False
