import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.llm_client import GemmaLLMClient


class TestGemmaLLMClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.client = GemmaLLMClient(api_key="test-api-key")

    async def asyncTearDown(self):
        if self.client._session and isinstance(self.client._session.close, AsyncMock):
            await self.client.close()
        elif self.client._session and hasattr(self.client._session, 'closed') and not self.client._session.closed:
            if hasattr(self.client._session, 'close') and asyncio.iscoroutinefunction(self.client._session.close):
                await self.client.close()

    def test_init_without_key_does_not_crash(self):
        client = GemmaLLMClient(api_key="")
        self.assertEqual(client.api_key, "")
        self.assertFalse(client.is_configured())

    def test_init_with_key_is_configured(self):
        self.assertTrue(self.client.is_configured())

    async def test_fail_open_when_not_configured(self):
        client = GemmaLLMClient(api_key="")
        ans = await client.answer_question("What is your experience?", input_type="text")
        self.assertIsNone(ans)

    async def test_discover_models_selects_31b(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "models": [
                {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-3-27b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-2-31b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-2-9b-it", "supportedGenerationMethods": ["generateContent"]}
            ]
        })

        mock_session = MagicMock()
        get_cm = MagicMock()
        get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        get_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = get_cm
        mock_session.closed = False
        mock_session.close = AsyncMock()

        self.client._session = mock_session
        model = await self.client.verify_and_select_model()
        self.assertEqual(model, "gemma-2-31b-it")

    async def test_discover_models_selects_26b_when_no_31b(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "models": [
                {"name": "models/gemma-3-27b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-26b-moe-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-2-9b-it", "supportedGenerationMethods": ["generateContent"]}
            ]
        })

        mock_session = MagicMock()
        get_cm = MagicMock()
        get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        get_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = get_cm
        mock_session.closed = False
        mock_session.close = AsyncMock()

        client = GemmaLLMClient(api_key="test-key")
        client._session = mock_session
        model = await client.verify_and_select_model()
        self.assertEqual(model, "gemma-26b-moe-it")

    async def test_discover_models_fallback_when_discovery_fails(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Network unreachable")
        mock_session.closed = False
        mock_session.close = AsyncMock()

        client = GemmaLLMClient(api_key="test-key")
        client._session = mock_session
        model = await client.verify_and_select_model()
        self.assertEqual(model, "gemma-3-27b-it")

    def test_prompt_constraints(self):
        prompt = self.client._build_prompt(
            question="Do you have experience with Python?",
            options=["Yes", "No"],
            input_type="radio",
            context="Pattern suggestion: Yes (confidence: 0.95)"
        )
        prompt_lower = prompt.lower()
        self.assertIn("first-person", prompt_lower)
        self.assertIn("never mention or disclose", prompt_lower)
        self.assertIn("ai", prompt_lower)
        self.assertIn("hedging", prompt_lower)
        self.assertIn("exact string", prompt_lower)
        self.assertIn("do you have experience with python?", prompt_lower)
        self.assertIn("yes", prompt_lower)
        self.assertIn("no", prompt_lower)

    async def test_mcq_matching_exact(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "candidates": [{
                "content": {
                    "parts": [{"text": "Yes"}]
                }
            }]
        })

        mock_session = MagicMock()
        post_cm = MagicMock()
        post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = post_cm
        mock_session.closed = False
        mock_session.close = AsyncMock()

        self.client._session = mock_session
        self.client._selected_model = "gemma-3-27b-it"
        self.client._discovery_completed = True

        ans = await self.client.answer_question(
            question="Are you willing to relocate?",
            options=["Yes", "No"],
            input_type="radio"
        )
        self.assertEqual(ans, "Yes")

    async def test_fail_open_on_http_error(self):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        mock_session = MagicMock()
        post_cm = MagicMock()
        post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = post_cm
        mock_session.closed = False
        mock_session.close = AsyncMock()

        self.client._session = mock_session
        self.client._selected_model = "gemma-3-27b-it"
        self.client._discovery_completed = True
        self.client._fallback_chain = ["gemma-3-27b-it"]

        with patch("asyncio.sleep", AsyncMock()):
            ans = await self.client.answer_question(
                question="What is your notice period?",
                input_type="text"
            )
            self.assertIsNone(ans)

    async def test_filters_out_thought_parts_and_returns_clean_answer(self):
        """When response contains thought: True part and non-thought part, returns ONLY clean non-thought answer."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "text": "* Role: Job applicant (Siddhant Singh).\n* Constraint 1: First-person voice.\n* Current CTC: 23 LPA.",
                            "thought": True
                        },
                        {
                            "text": "23 LPA"
                        }
                    ]
                }
            }]
        })

        mock_session = MagicMock()
        post_cm = MagicMock()
        post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        post_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = post_cm
        mock_session.closed = False
        mock_session.close = AsyncMock()

        self.client._session = mock_session
        self.client._selected_model = "gemma-4-31b-it"
        self.client._discovery_completed = True

        ans = await self.client.answer_question(
            question="What is your current ctc?",
            input_type="text"
        )
        self.assertEqual(ans, "23 LPA")
        self.assertNotIn("Role:", ans)
        self.assertNotIn("Constraint", ans)


if __name__ == "__main__":
    unittest.main()
