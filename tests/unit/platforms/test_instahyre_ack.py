import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.agent import SentinelAgent


class TestInstahyreAck(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    async def test_send_ack_success_when_enabled(self):
        """When Send button is enabled, types message, clicks send, and increments metric."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/111"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        # Sequence of evaluate responses:
        # 1. has_editor -> True
        # 2. text_in_editor -> text contains "completed the questionnaire"
        # 3. btn_state -> { found: True, disabled: False }
        # 4. click send -> None
        # 5. verify dispatch -> True
        mock_page.evaluate = AsyncMock(side_effect=[
            True,
            "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you.",
            {"found": True, "disabled": False},
            None,
            True
        ])

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/111",
                "Pallavi Naik"
            )

        self.assertTrue(result)
        self.assertEqual(self.agent.metrics['instahyre_acks_sent'], prev_acks + 1)
        mock_page.keyboard.type.assert_called_once()
        typed_text = mock_page.keyboard.type.call_args[0][0]
        self.assertIn("completed the questionnaire", typed_text)

    async def test_send_ack_skips_when_disabled(self):
        """When Send button is disabled, does NOT click and does not increment metric."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/111"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_page.evaluate = AsyncMock(side_effect=[
            True,
            "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you.",
            {"found": True, "disabled": True}  # Button disabled!
        ])

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/111",
                "Pallavi Naik"
            )

        self.assertFalse(result)
        self.assertEqual(self.agent.metrics.get('instahyre_acks_sent', 0), prev_acks)

    async def test_send_reply_without_questionnaire_success(self):
        """When has_questionnaire=False, types direct interest reply and clicks send."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/222"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_page.evaluate = AsyncMock(side_effect=[
            True,
            "Hi, I'm interested in this opportunity. Looking forward to hearing from you.",
            {"found": True, "disabled": False},
            None,
            True
        ])

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/222",
                "Amit Sharma",
                has_questionnaire=False
            )

        self.assertTrue(result)
        self.assertEqual(self.agent.metrics['instahyre_acks_sent'], prev_acks + 1)
        mock_page.keyboard.type.assert_called_once()
        typed_text = mock_page.keyboard.type.call_args[0][0]
        self.assertIn("interested in this opportunity", typed_text)
        self.assertNotIn("questionnaire", typed_text)

    async def test_send_ack_fails_when_text_not_in_editor(self):
        """When typed text fails verification in editor, returns False and does not click send."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/333"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        mock_page.evaluate = AsyncMock(side_effect=[
            True,
            "",  # empty editor text (verification fails)
        ])

        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/333",
                "Amit Sharma",
                has_questionnaire=True
            )

        self.assertFalse(result)

    async def test_send_ack_fails_open_on_exception(self):
        """When an exception occurs (e.g. navigation timeout), returns False fail-open."""
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Page crashed")

        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/999",
                "Pallavi Naik"
            )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

