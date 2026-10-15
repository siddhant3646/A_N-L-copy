"""Tests for Hirist QA pattern priority and Indeed reCAPTCHA & card improvements."""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.sentinel.llm_client import GemmaLLMClient


class TestHiristIndeedEnhancements(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()

    async def test_hirist_fill_questionnaire_prioritizes_qa_pattern_over_llm(self):
        """Standard questions like CTC and experience should use pattern answers directly without LLM."""
        questions = [
            {
                'qid': 'sntl_hq_0',
                'question': 'What is your current CTC in Lacs per annum?',
                'kind': 'text',
                'options': [],
                'hasTextarea': True,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 50
            },
            {
                'qid': 'sntl_hq_1',
                'question': 'What is your expected CTC in Lacs per annum?',
                'kind': 'text',
                'options': [],
                'hasTextarea': True,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 50
            },
            {
                'qid': 'sntl_hq_2',
                'question': 'What is your notice period in days?',
                'kind': 'text',
                'options': [],
                'hasTextarea': True,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 50
            }
        ]

        filled = {}
        async def fake_fill(page, qid, answer):
            filled[qid] = answer
            return True

        self.agent._hirist_fill_text = fake_fill
        mock_llm = MagicMock()
        mock_llm.answer_question = AsyncMock()
        self.agent._get_llm_client = MagicMock(return_value=mock_llm)

        mock_page = MagicMock()
        answered_count = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered_count, 3)
        # Verify LLM was NOT called for standard profile questions with matched patterns
        mock_llm.answer_question.assert_not_called()
        self.assertIn('23', filled['sntl_hq_0'])
        self.assertIn('30', filled['sntl_hq_1'])
        self.assertIn('15', filled['sntl_hq_2'])

    async def test_llm_client_selects_gemini_flash_lite(self):
        """Model discovery prioritizes gemini-3.5-flash-lite over gemma models."""
        client = GemmaLLMClient(api_key="fake_key")
        fake_models_resp = {
            "models": [
                {"name": "models/gemma-4-31b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
            ]
        }
        client._http_get = AsyncMock(return_value=(200, str(fake_models_resp).replace("'", '"')))
        selected = await client.verify_and_select_model()
        self.assertEqual(selected, "gemini-3.5-flash-lite")

    async def test_indeed_open_card_fallback_on_invisible(self):
        """When standard locator click fails, fallback to force click or JS evaluate."""
        mock_page = MagicMock()
        mock_card = MagicMock()
        mock_link = MagicMock()
        mock_link.first = mock_link
        mock_card.first = mock_card

        mock_link.count = AsyncMock(return_value=1)
        mock_link.scroll_into_view_if_needed = AsyncMock()
        mock_link.click = AsyncMock(side_effect=Exception("Element is not visible"))
        mock_link.evaluate = AsyncMock(return_value=None)

        mock_card.count = AsyncMock(return_value=1)
        mock_card.locator = MagicMock(return_value=mock_link)
        mock_page.locator = MagicMock(return_value=mock_card)
        mock_page.evaluate = AsyncMock(return_value=None)

        job = {'jk': 'test_job_key', 'title': 'Software Engineer'}
        success = await self.agent._indeed_open_card(mock_page, job)
        self.assertTrue(success)
        mock_link.evaluate.assert_called_once()
