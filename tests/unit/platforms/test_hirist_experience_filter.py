"""Unit tests for Hirist experience filter (4 - 6 yrs) interaction."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestHiristExperienceFilter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        real_sleep = asyncio.sleep

        async def _instant_sleep(delay, *args, **kwargs):
            return await real_sleep(0)

        patcher = patch("asyncio.sleep", new=_instant_sleep)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_experience_filter_page_none_returns_false(self):
        """Returns False if page is None or lacks evaluate."""
        self.assertFalse(await self.agent._hirist_apply_experience_filter(None))
        self.assertFalse(await self.agent._hirist_apply_experience_filter(object()))

    async def test_experience_filter_combobox_not_found_returns_false(self):
        """Returns False if the filter combobox is not on the page."""
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={"found": False})
        res = await self.agent._hirist_apply_experience_filter(mock_page)
        self.assertFalse(res)

    async def test_experience_filter_already_set_returns_true(self):
        """If 4 - 6 yrs is already active, returns True without clicking combobox."""
        mock_page = MagicMock()
        mock_page.evaluate = AsyncMock(return_value={
            "found": True,
            "text": "4 - 6 yrs",
            "isAlreadySet": True
        })
        mock_page.locator = MagicMock()
        res = await self.agent._hirist_apply_experience_filter(mock_page)
        self.assertTrue(res)
        mock_page.locator.assert_not_called()

    async def test_experience_filter_clicks_and_selects_4_to_6_yrs(self):
        """Opens combobox, selects 4 - 6 yrs option, clicks Apply, and verifies."""
        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/k/java-jobs?ref=popular_tag&minexp=4&maxexp=6"

        async def fake_evaluate(script, *args):
            s = str(script)
            if "isAlreadySet" in s:
                return {"found": True, "text": "Any Exp. Level", "isAlreadySet": False}
            if "verify" in s or "return el ?" in s:
                return "4 - 6 yrs"
            return True

        mock_page.evaluate = AsyncMock(side_effect=fake_evaluate)

        # Mock locators
        mock_combobox = AsyncMock()
        mock_combobox.count = AsyncMock(return_value=1)
        mock_combobox.scroll_into_view_if_needed = AsyncMock()
        mock_combobox.click = AsyncMock()

        mock_opt = AsyncMock()
        mock_opt.count = AsyncMock(return_value=1)
        mock_opt.is_visible = AsyncMock(return_value=True)
        mock_opt.click = AsyncMock()

        mock_apply_btn = AsyncMock()
        mock_apply_btn.count = AsyncMock(return_value=1)
        mock_apply_btn.is_visible = AsyncMock(return_value=True)
        mock_apply_btn.click = AsyncMock()

        def fake_locator(sel):
            mock_loc = MagicMock()
            if "lotus-select-experience" in sel and "xpath=" in sel:
                mock_loc.first = mock_apply_btn
            elif "lotus-select-experience" in sel:
                mock_loc.first = mock_combobox
            elif 'data-value="4"' in sel or "4 - 6" in sel:
                mock_loc.first = mock_opt
            else:
                fallback = AsyncMock()
                fallback.count = AsyncMock(return_value=0)
                mock_loc.first = fallback
            return mock_loc

        mock_page.locator = MagicMock(side_effect=fake_locator)
        self.agent._hirist_dismiss_dialogs = AsyncMock()

        res = await self.agent._hirist_apply_experience_filter(mock_page)
        self.assertTrue(res)
        mock_combobox.click.assert_awaited_once()
        mock_opt.click.assert_awaited_once()
        mock_apply_btn.click.assert_awaited_once()

    async def test_experience_filter_handles_js_fallback(self):
        """When locator fails, JS evaluation fallbacks click combobox, option, and Apply."""
        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/k/java-jobs?ref=popular_tag"

        async def fake_evaluate(script, *args):
            s = str(script)
            if "isAlreadySet" in s:
                return {"found": True, "text": "Any Exp. Level", "isAlreadySet": False}
            if "verify" in s or "return el ?" in s:
                return "4 - 6 yrs"
            return True

        mock_page.evaluate = AsyncMock(side_effect=fake_evaluate)

        # Locators count = 0 to trigger JS fallbacks
        empty_loc = AsyncMock()
        empty_loc.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=MagicMock(first=empty_loc))
        self.agent._hirist_dismiss_dialogs = AsyncMock()

        res = await self.agent._hirist_apply_experience_filter(mock_page)
        self.assertTrue(res)
        self.assertGreaterEqual(mock_page.evaluate.await_count, 4)


if __name__ == "__main__":
    unittest.main()
