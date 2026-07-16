"""Tests for Smart Element Handler module."""

import pytest
from unittest.mock import AsyncMock
from src.sentinel.smart_element_handler import SmartElementHandler
from src.patterns.input_aware_resolver import Option


@pytest.mark.asyncio
class TestFillText:
    """Test _fill_text method - React-safe filling with event dispatch."""

    async def test_fill_text_returns_true_on_success(self):
        """Test _fill_text returns True when evaluate succeeds."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value=None)
        option = Option(value="4", label="4", index=0)

        result = await handler._fill_text(mock_element, option)

        assert result is True

    async def test_fill_text_uses_evaluate_not_fill(self):
        """Test _fill_text uses React-safe evaluate, not bare fill."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value=None)
        mock_element.fill = AsyncMock()
        option = Option(value="4", label="4", index=0)

        await handler._fill_text(mock_element, option)

        mock_element.evaluate.assert_called_once()
        mock_element.fill.assert_not_called()

    async def test_fill_text_dispatches_input_change_blur(self):
        """Test _fill_text JS dispatches input, change, and blur events."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value=None)
        option = Option(value="4", label="4", index=0)

        await handler._fill_text(mock_element, option)

        js_content = mock_element.evaluate.call_args.args[0]
        assert "dispatchEvent" in js_content
        assert "input" in js_content
        assert "change" in js_content
        assert "blur" in js_content

    async def test_fill_text_uses_native_setter(self):
        """Test _fill_text JS uses nativeSetter for React compatibility."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(return_value=None)
        option = Option(value="4", label="4", index=0)

        await handler._fill_text(mock_element, option)

        js_content = mock_element.evaluate.call_args.args[0]
        assert "nativeSetter" in js_content

    async def test_fill_text_falls_back_to_fill_on_exception(self):
        """Test _fill_text falls back to element.fill() when evaluate fails."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(side_effect=Exception("JS error"))
        mock_element.fill = AsyncMock()
        option = Option(value="4", label="4", index=0)

        result = await handler._fill_text(mock_element, option)

        assert result is True
        mock_element.fill.assert_called_once_with("4")

    async def test_fill_text_returns_false_when_both_paths_fail(self):
        """Test _fill_text returns False when both evaluate and fill fail."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(side_effect=Exception("JS error"))
        mock_element.fill = AsyncMock(side_effect=Exception("Fill error"))
        option = Option(value="4", label="4", index=0)

        result = await handler._fill_text(mock_element, option)

        assert result is False

    async def test_fill_text_returns_false_for_none_option(self):
        """Test _fill_text returns False when option is None."""
        handler = SmartElementHandler()
        mock_element = AsyncMock()

        result = await handler._fill_text(mock_element, None)

        assert result is False
        mock_element.evaluate.assert_not_called()
