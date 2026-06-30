"""
Tests for Human Behavior module.
"""

import pytest
from unittest.mock import AsyncMock, patch
from src.sentinel.human_behavior import (
    human_mouse_move,
    human_scroll,
    human_click,
    human_type,
    random_delay,
    human_hover,
)


@pytest.mark.asyncio
class TestHumanMouseMove:
    """Test human_mouse_move function."""
    
    async def test_mouse_move_success(self, mock_page):
        """Test successful mouse movement."""
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_page.mouse.move = AsyncMock()
        
        result = await human_mouse_move(mock_page, 100, 200)
        
        assert result is True
        assert mock_page.mouse.move.call_count > 0
    
    async def test_mouse_move_with_duration(self, mock_page):
        """Test mouse movement with custom duration."""
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_page.mouse.move = AsyncMock()
        
        result = await human_mouse_move(mock_page, 100, 200, duration=0.5)
        
        assert result is True
    
    async def test_mouse_move_failure(self, mock_page):
        """Test mouse movement failure."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Mouse error"))
        
        result = await human_mouse_move(mock_page, 100, 200)
        
        assert result is False


@pytest.mark.asyncio
class TestHumanScroll:
    """Test human_scroll function."""
    
    async def test_scroll_down(self, mock_page):
        """Test scrolling down."""
        mock_page.evaluate = AsyncMock()
        
        result = await human_scroll(mock_page, "down", 500)
        
        assert result is True
        mock_page.evaluate.assert_called()
    
    async def test_scroll_up(self, mock_page):
        """Test scrolling up."""
        mock_page.evaluate = AsyncMock()
        
        result = await human_scroll(mock_page, "up", 300)
        
        assert result is True
    
    async def test_scroll_not_smooth(self, mock_page):
        """Test non-smooth scrolling."""
        mock_page.evaluate = AsyncMock()
        
        result = await human_scroll(mock_page, "down", 500, smooth=False)
        
        assert result is True
        mock_page.evaluate.assert_called_once()
    
    async def test_scroll_failure(self, mock_page):
        """Test scroll failure."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Scroll error"))
        
        result = await human_scroll(mock_page, "down", 500)
        
        assert result is False


@pytest.mark.asyncio
class TestHumanClick:
    """Test human_click function."""
    
    async def test_click_by_selector(self, mock_page):
        """Test clicking by selector."""
        mock_element = AsyncMock()
        mock_element.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 50, "height": 30
        })
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.mouse.move = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        
        result = await human_click(mock_page, selector="#button")
        
        assert result is True
    
    async def test_click_by_coordinates(self, mock_page):
        """Test clicking by coordinates."""
        mock_page.mouse.move = AsyncMock()
        mock_page.mouse.click = AsyncMock()
        
        result = await human_click(mock_page, x=100, y=200)
        
        assert result is True
    
    async def test_click_element_not_found(self, mock_page):
        """Test click when element not found."""
        mock_page.query_selector = AsyncMock(return_value=None)
        
        result = await human_click(mock_page, selector="#missing")
        
        assert result is False
    
    async def test_click_double_click(self, mock_page):
        """Test double click."""
        mock_page.mouse.move = AsyncMock()
        mock_page.mouse.dblclick = AsyncMock()
        
        result = await human_click(mock_page, x=100, y=200, double_click=True)
        
        assert result is True
        mock_page.mouse.dblclick.assert_called_once()
    
    async def test_click_no_position(self, mock_page):
        """Test click without position."""
        result = await human_click(mock_page)
        
        assert result is False


@pytest.mark.asyncio
class TestHumanType:
    """Test human_type function."""
    
    async def test_type_success(self, mock_page):
        """Test successful typing."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()
        mock_element.type = AsyncMock()
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        
        result = await human_type(mock_page, "#input", "hello")
        
        assert result is True
        mock_element.type.assert_called()
    
    async def test_type_without_clear(self, mock_page):
        """Test typing without clearing first."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.type = AsyncMock()
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        
        result = await human_type(mock_page, "#input", "hello", clear_first=False)
        
        assert result is True
        mock_element.fill.assert_not_called()
    
    async def test_type_element_not_found(self, mock_page):
        """Test typing when element not found."""
        mock_page.query_selector = AsyncMock(return_value=None)
        
        result = await human_type(mock_page, "#missing", "hello")
        
        assert result is False
    
    async def test_type_with_typos(self, mock_page):
        """Test typing with simulated typos."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()
        mock_element.fill = AsyncMock()
        mock_element.type = AsyncMock()
        mock_element.press = AsyncMock()
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        
        # With high typo chance, should make some typos
        with patch('random.random', return_value=0.01):  # Always trigger typo
            result = await human_type(mock_page, "#input", "hi", typo_chance=0.5)
        
        assert result is True


@pytest.mark.asyncio
class TestRandomDelay:
    """Test random_delay function."""
    
    async def test_random_delay(self):
        """Test random delay waits appropriate time."""
        import time
        
        start = time.time()
        await random_delay(0.1, 0.1)  # Fixed 0.1 second
        elapsed = time.time() - start
        
        assert elapsed >= 0.1
    
    async def test_random_delay_range(self):
        """Test random delay respects range."""
        import time
        
        start = time.time()
        await random_delay(0.05, 0.1)
        elapsed = time.time() - start
        
        assert 0.05 <= elapsed <= 0.15  # Allow some tolerance


@pytest.mark.asyncio
class TestHumanHover:
    """Test human_hover function."""
    
    async def test_hover_success(self, mock_page):
        """Test successful hover."""
        mock_element = AsyncMock()
        mock_element.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 50, "height": 30
        })
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.mouse.move = AsyncMock()
        
        result = await human_hover(mock_page, "#element")
        
        assert result is True
    
    async def test_hover_with_duration(self, mock_page):
        """Test hover with custom duration."""
        mock_element = AsyncMock()
        mock_element.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 50, "height": 30
        })
        
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.mouse.move = AsyncMock()
        
        result = await human_hover(mock_page, "#element", duration=0.1)
        
        assert result is True
    
    async def test_hover_element_not_found(self, mock_page):
        """Test hover when element not found."""
        mock_page.query_selector = AsyncMock(return_value=None)
        
        result = await human_hover(mock_page, "#missing")
        
        assert result is False
