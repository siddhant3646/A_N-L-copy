import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.agent import SentinelAgent


def create_mock_evaluate(expected_text: str, btn_disabled: bool = False, empty_text: bool = False):
    async def _eval(script, *args):
        # Filter check / Angular scope setConvType
        if 'convTypes.ALL' in script:
            return True
        # Target card selection
        if 'targetData' in script or 'targetName' in script:
            return True
        # Checking editor visibility
        if 'ql-editor' in script and 'offsetParent' in script:
            return True
        # Checking idempotency (already sent)
        if 'messagesToShow' in script and 'is_candidate' in script:
            return False
        # Checking text in editor
        if 'text_in_editor' in script or ('ed.innerText' in script and 'send-email' not in script):
            return "" if empty_text else expected_text
        # Button state check
        if 'send-email' in script or 'btn-send' in script:
            if 'scrollIntoView' in script:
                return None  # Click send
            return {'found': True, 'disabled': btn_disabled}
        # Dispatch verified
        if 'messagesToShow' in script or 'conv-email-row' in script:
            return True
        return True
    return _eval


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

        ack_text = "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you."
        mock_page.evaluate = AsyncMock(side_effect=create_mock_evaluate(ack_text, btn_disabled=False))

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                page=mock_page,
                inbox_url="https://www.instahyre.com/candidate/inbox/111",
                c_name="Pallavi Naik",
                has_questionnaire=True,
                raw_conv_id="conv-111",
                card_index=0
            )

        self.assertTrue(result)
        self.assertEqual(self.agent.metrics['instahyre_acks_sent'], prev_acks + 1)
        mock_page.keyboard.type.assert_called_once()
        typed_text = mock_page.keyboard.type.call_args[0][0]
        self.assertIn("completed the questionnaire", typed_text)

    async def test_send_ack_with_card_reselection(self):
        """When returning from external questionnaire page, navigates to inbox and selects target card."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/questionnaire/118132/6201541231"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        ack_text = "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you."
        mock_page.evaluate = AsyncMock(side_effect=create_mock_evaluate(ack_text, btn_disabled=False))

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                page=mock_page,
                inbox_url="https://www.instahyre.com/candidate/inbox/439288/6201541231/",
                c_name="Taarni Verma",
                has_questionnaire=True,
                raw_conv_id="118132",
                card_index=0
            )

        self.assertTrue(result)
        self.assertEqual(self.agent.metrics['instahyre_acks_sent'], prev_acks + 1)
        mock_page.goto.assert_called_with("https://www.instahyre.com/candidate/inbox/439288/6201541231/", wait_until='domcontentloaded', timeout=30000)

    async def test_send_ack_skips_when_disabled(self):
        """When Send button is disabled, does NOT click and does not increment metric."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/111"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        ack_text = "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you."
        mock_page.evaluate = AsyncMock(side_effect=create_mock_evaluate(ack_text, btn_disabled=True))

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

        reply_text = "Hi, I'm interested in this opportunity. Looking forward to hearing from you."
        mock_page.evaluate = AsyncMock(side_effect=create_mock_evaluate(reply_text, btn_disabled=False))

        prev_acks = self.agent.metrics.get('instahyre_acks_sent', 0)
        with patch("asyncio.sleep", AsyncMock()):
            result = await self.agent._send_instahyre_ack(
                mock_page,
                "https://www.instahyre.com/candidate/inbox/222",
                "Amit Sharma",
                has_questionnaire=False,
                raw_conv_id="conv-222",
                card_index=1
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

        mock_page.evaluate = AsyncMock(side_effect=create_mock_evaluate("", empty_text=True))

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
        mock_page.url = "https://www.instahyre.com/questionnaire/111"
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

