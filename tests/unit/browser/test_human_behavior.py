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
    resync_input_state,
    resync_all_inputs,
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


@pytest.mark.asyncio
class TestResyncInputState:
    """Test resync_input_state function."""

    async def test_resync_success_with_value(self, mock_page):
        """Test successful resync when field has a value."""
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value="4")
        mock_element.click = AsyncMock()
        mock_element.press = AsyncMock()
        mock_element.type = AsyncMock()

        result = await resync_input_state(mock_page, mock_element)

        assert result is True
        mock_element.click.assert_called_once()
        mock_element.press.assert_any_call('End')
        mock_element.press.assert_any_call('Backspace')
        mock_element.press.assert_any_call('Tab')
        mock_element.type.assert_called()

    async def test_resync_success_empty_value_types_space(self, mock_page):
        """Test resync when field is empty (types space then deletes)."""
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value="")
        mock_element.click = AsyncMock()
        mock_element.press = AsyncMock()
        mock_element.type = AsyncMock()

        result = await resync_input_state(mock_page, mock_element)

        assert result is True
        mock_element.type.assert_any_call(' ', delay=mock_element.type.call_args.kwargs['delay'] if mock_element.type.call_args.kwargs else mock_element.type.call_args.args[1] if len(mock_element.type.call_args.args) > 1 else None)
        mock_element.press.assert_any_call('Backspace')

    async def test_resync_returns_false_on_exception(self, mock_page):
        """Test resync returns False when element.click raises."""
        mock_element = AsyncMock()
        mock_element.click = AsyncMock(side_effect=Exception("Click failed"))

        result = await resync_input_state(mock_page, mock_element)

        assert result is False

    async def test_resync_blur_with_tab(self, mock_page):
        """Test that blur is triggered via Tab key by default."""
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value="hello")
        mock_element.click = AsyncMock()
        mock_element.press = AsyncMock()
        mock_element.type = AsyncMock()

        await resync_input_state(mock_page, mock_element, blur_with_tab=True)

        mock_element.press.assert_any_call('Tab')

    async def test_resync_blur_without_tab(self, mock_page):
        """Test that blur falls back to mouse click when blur_with_tab=False."""
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value="hello")
        mock_element.click = AsyncMock()
        mock_element.press = AsyncMock()
        mock_element.type = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"w": 800, "h": 600})
        mock_page.mouse.click = AsyncMock()

        await resync_input_state(mock_page, mock_element, blur_with_tab=False)

        mock_page.mouse.click.assert_called_once()
        mock_element.press.assert_not_awaited  # Tab not pressed


@pytest.mark.asyncio
class TestResyncAllInputs:
    """Test resync_all_inputs function."""

    async def test_resync_all_inputs_no_invalid_fields(self, mock_page):
        """Test resync_all_inputs when no aria-invalid fields exist."""
        mock_page.query_selector_all = AsyncMock(return_value=[])

        count = await resync_all_inputs(mock_page)

        assert count == 0

    async def test_resync_all_inputs_resyncs_visible_fields(self, mock_page):
        """Test resync_all_inputs resyncs visible invalid fields."""
        mock_handle1 = AsyncMock()
        mock_handle1.evaluate = AsyncMock(side_effect=["4", True])
        mock_handle1.click = AsyncMock()
        mock_handle1.press = AsyncMock()
        mock_handle1.type = AsyncMock()

        mock_handle2 = AsyncMock()
        mock_handle2.evaluate = AsyncMock(side_effect=["", False])  # Not visible

        mock_page.query_selector_all = AsyncMock(return_value=[mock_handle1, mock_handle2])

        with patch('src.sentinel.human_behavior.resync_input_state', new_callable=AsyncMock) as mock_resync:
            mock_resync.return_value = True
            count = await resync_all_inputs(mock_page)

        assert count == 1
        mock_resync.assert_called_once()

    async def test_resync_all_inputs_handles_enumeration_error(self, mock_page):
        """Test resync_all_inputs returns 0 when query_selector_all fails."""
        mock_page.query_selector_all = AsyncMock(side_effect=Exception("Query failed"))

        count = await resync_all_inputs(mock_page)

        assert count == 0
