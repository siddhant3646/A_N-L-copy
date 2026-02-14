"""
Tests for Browser Actions module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.sentinel.browser_actions import (
    robust_click,
    robust_js_click,
    robust_click_by_text,
    robust_radio_click,
    robust_checkbox_click,
    robust_button_click,
    scroll_element_into_view,
    dismiss_browser_dialogs,
)


@pytest.mark.asyncio
class TestRobustClick:
    """Test robust_click function."""
    
    async def test_click_success(self, mock_page):
        """Test successful click."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.click = AsyncMock()
        
        result = await robust_click(mock_locator, "test button", human_like=False)
        
        assert result is True
        mock_locator.click.assert_called_once()
    
    async def test_click_not_visible(self, mock_page):
        """Test click when element not visible."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=False)
        
        result = await robust_click(mock_locator, "test button", retries=1)
        
        assert result is False
    
    async def test_click_retry_success(self, mock_page):
        """Test click succeeds after retry."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(side_effect=[False, True])
        mock_locator.click = AsyncMock()
        
        result = await robust_click(mock_locator, "test button")
        
        assert result is True
    
    async def test_click_all_retries_fail(self, mock_page):
        """Test click fails after all retries."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=False)
        
        result = await robust_click(mock_locator, "test button", retries=2)
        
        assert result is False


@pytest.mark.asyncio
class TestRobustJSClick:
    """Test robust_js_click function."""
    
    async def test_js_click_success(self, mock_page):
        """Test successful JS click."""
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.evaluate = AsyncMock(return_value=True)
        
        result = await robust_js_click(mock_page, "#button", "test button")
        
        assert result is True
    
    async def test_js_click_element_not_found(self, mock_page):
        """Test JS click when element not found."""
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_page.evaluate = AsyncMock(return_value=False)
        
        result = await robust_js_click(mock_page, "#missing", "missing button")
        
        assert result is False
    
    async def test_js_click_exception(self, mock_page):
        """Test JS click with exception."""
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
        
        result = await robust_js_click(mock_page, "#button", "test button")
        
        assert result is False


@pytest.mark.asyncio
class TestRobustClickByText:
    """Test robust_click_by_text function."""
    
    async def test_click_by_text_success(self, mock_page):
        """Test click by text success."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.click = AsyncMock()
        
        mock_page.get_by_text = MagicMock(return_value=mock_locator)
        
        result = await robust_click_by_text(mock_page, "Submit")
        
        assert result is True
    
    async def test_click_by_text_not_found(self, mock_page):
        """Test click by text not found."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=False)
        
        mock_page.get_by_text = MagicMock(return_value=mock_locator)
        
        result = await robust_click_by_text(mock_page, "Nonexistent")
        
        assert result is False


@pytest.mark.asyncio
class TestRobustRadioClick:
    """Test robust_radio_click function."""
    
    async def test_radio_by_label(self, mock_page):
        """Test radio click by label text."""
        mock_label = AsyncMock()
        mock_radio = AsyncMock()
        mock_label.query_selector = AsyncMock(return_value=mock_radio)
        
        mock_page.query_selector_all = AsyncMock(return_value=[mock_label])
        
        result = await robust_radio_click(mock_page, "Yes")
        
        assert result is True
    
    async def test_radio_by_value(self, mock_page):
        """Test radio click by value."""
        mock_radio = AsyncMock()
        mock_page.query_selector_all = AsyncMock(side_effect=[
            [],  # No labels found
            [mock_radio]  # Radio by value found
        ])
        
        result = await robust_radio_click(mock_page, "option1")
        
        assert result is True
    
    async def test_radio_fallback_index(self, mock_page):
        """Test radio click with fallback index."""
        mock_radio = AsyncMock()
        mock_page.query_selector_all = AsyncMock(side_effect=[
            [],  # No labels
            [],  # No value match
            [mock_radio]  # All radios
        ])
        
        result = await robust_radio_click(mock_page, "missing", fallback_index=0)
        
        assert result is True
    
    async def test_radio_not_found(self, mock_page):
        """Test radio not found."""
        mock_page.query_selector_all = AsyncMock(return_value=[])
        
        result = await robust_radio_click(mock_page, "missing")
        
        assert result is False


@pytest.mark.asyncio
class TestRobustCheckboxClick:
    """Test robust_checkbox_click function."""
    
    async def test_checkbox_by_label(self, mock_page):
        """Test checkbox click by label."""
        mock_label = AsyncMock()
        mock_checkbox = AsyncMock()
        mock_label.query_selector = AsyncMock(return_value=mock_checkbox)
        
        mock_page.query_selector_all = AsyncMock(return_value=[mock_label])
        
        result = await robust_checkbox_click(mock_page, "I agree")
        
        assert result is True
        mock_checkbox.click.assert_called_once()
    
    async def test_checkbox_select_all(self, mock_page):
        """Test selecting all matching checkboxes."""
        mock_checkbox1 = AsyncMock()
        mock_checkbox2 = AsyncMock()
        
        mock_label = AsyncMock()
        mock_label.query_selector = AsyncMock(side_effect=[mock_checkbox1, mock_checkbox2])
        
        mock_page.query_selector_all = AsyncMock(return_value=[mock_label, mock_label])
        
        result = await robust_checkbox_click(mock_page, "Option", select_all=True)
        
        assert result is True
        mock_checkbox1.click.assert_called_once()
        mock_checkbox2.click.assert_called_once()


@pytest.mark.asyncio
class TestRobustButtonClick:
    """Test robust_button_click function."""
    
    async def test_button_by_exact_text(self, mock_page):
        """Test button click by exact text."""
        mock_button = AsyncMock()
        mock_button.is_visible = AsyncMock(return_value=True)
        mock_button.click = AsyncMock()
        
        mock_page.get_by_role = MagicMock(return_value=mock_button)
        
        result = await robust_button_click(mock_page, ["Submit"])
        
        assert result is True
    
    async def test_button_fallback_selector(self, mock_page):
        """Test button click with fallback selector."""
        mock_page.get_by_role = MagicMock(side_effect=Exception("Not found"))
        mock_page.click = AsyncMock()
        
        result = await robust_button_click(
            mock_page,
            ["Missing"],
            fallback_selector="#submit-btn"
        )
        
        assert result is True
    
    async def test_button_not_found(self, mock_page):
        """Test button not found."""
        mock_locator = AsyncMock()
        mock_locator.is_visible = AsyncMock(return_value=False)
        
        mock_page.get_by_role = MagicMock(return_value=mock_locator)
        
        result = await robust_button_click(mock_page, ["Missing"])
        
        assert result is False


@pytest.mark.asyncio
class TestScrollElementIntoView:
    """Test scroll_element_into_view function."""
    
    async def test_scroll_by_selector(self, mock_page):
        """Test scroll by CSS selector."""
        mock_page.evaluate = AsyncMock()
        
        result = await scroll_element_into_view(mock_page, "#element")
        
        assert result is True
        mock_page.evaluate.assert_called_once()
    
    async def test_scroll_by_locator(self, mock_page):
        """Test scroll by locator object."""
        mock_element = AsyncMock()
        mock_element.scroll_into_view_if_needed = AsyncMock()
        
        mock_locator = MagicMock()
        mock_locator.element_handle = AsyncMock(return_value=mock_element)
        
        result = await scroll_element_into_view(mock_page, mock_locator)
        
        assert result is True
    
    async def test_scroll_exception(self, mock_page):
        """Test scroll with exception."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("Scroll failed"))
        
        result = await scroll_element_into_view(mock_page, "#element")
        
        assert result is False


@pytest.mark.asyncio
class TestDismissBrowserDialogs:
    """Test dismiss_browser_dialogs function."""
    
    async def test_dismiss_setup(self, mock_page):
        """Test dialog dismissal setup."""
        mock_page.on = MagicMock()
        
        result = await dismiss_browser_dialogs(mock_page)
        
        assert result is True
        mock_page.on.assert_called_once()
    
    async def test_dismiss_exception(self, mock_page):
        """Test dialog dismissal with exception."""
        mock_page.on = MagicMock(side_effect=Exception("Setup failed"))
        
        result = await dismiss_browser_dialogs(mock_page)
        
        assert result is False
