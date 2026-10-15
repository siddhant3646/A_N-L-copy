import pytest
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.llm_client import GemmaLLMClient, get_candidate_facts, SYSTEM_INSTRUCTIONS
from src.sentinel.agent import SentinelAgent


class TestLLMPromptAndEnhancements(unittest.TestCase):

    def setUp(self):
        self.client = GemmaLLMClient(api_key="fake-test-key")

    def test_candidate_facts_completeness(self):
        facts = get_candidate_facts()
        # Personal
        assert "Siddhant Singh" in facts
        assert "siddhant3646@gmail.com" in facts
        assert "+91-7905828880" in facts
        assert "Bangalore" in facts
        # Employment
        assert "Everbridge" in facts
        assert "Software Engineer 2 (SDE-2)" in facts
        assert "4.2 Years" in facts
        assert "15 days" in facts
        # Compensation
        assert "23 LPA" in facts
        assert "30 LPA" in facts
        assert "100% Fixed" in facts
        # Education
        assert "VIT Bhopal" in facts
        assert "8.51 CGPA" in facts
        assert "Computer Science" in facts
        # Compliance
        assert "Non-Compete" in facts
        assert "Conflict of Interest" in facts
        assert "Background Check" in facts
        # Architecture & Tech
        assert "Kafka" in facts
        assert "Spring Boot" in facts
        assert "Redis" in facts
        assert "PostgreSQL" in facts
        assert "Kubernetes" in facts
        assert "10M+ daily events" in facts

    def test_system_instructions_rules(self):
        assert "Siddhant Singh" in SYSTEM_INSTRUCTIONS
        assert "NEVER sound like an AI assistant" in SYSTEM_INSTRUCTIONS
        assert "Current CTC: \"23 LPA\"" in SYSTEM_INSTRUCTIONS
        assert "Expected CTC: \"30 LPA\"" in SYSTEM_INSTRUCTIONS
        assert "Notice Period: \"15 days\"" in SYSTEM_INSTRUCTIONS
        assert "Strict Numeric / Integer Fields" in SYSTEM_INSTRUCTIONS

    def test_build_prompt_structure(self):
        prompt = self.client._build_prompt(
            question="Describe how you mitigate traffic surges in production.",
            options=None,
            input_type="textarea",
            context="Candidate profile recommendation: Scale pods and use Redis cache."
        )
        assert "RECOMMENDED CANDIDATE PATTERN / CONTEXT" in prompt
        assert "Input Type: textarea" in prompt
        assert "Question: Describe how you mitigate traffic surges in production." in prompt
        assert "Direct Answer:" in prompt

    def test_match_chosen_option_exact_and_substring(self):
        options = ["Full-time", "Contract", "Internship"]
        assert self.client._match_chosen_option("Full-time", options) == "Full-time"
        assert self.client._match_chosen_option("full-time", options) == "Full-time"
        assert self.client._match_chosen_option("contract role", options) == "Contract"

    def test_match_chosen_option_yes_no(self):
        options = ["Yes, I agree", "No, I decline"]
        assert self.client._match_chosen_option("Yes", options) == "Yes, I agree"
        assert self.client._match_chosen_option("No", options) == "No, I decline"

    def test_match_chosen_option_numeric_range(self):
        exp_options = ["0-2 Years", "3-5 Years", "5+ Years"]
        assert self.client._match_chosen_option("4.2 Years", exp_options) == "3-5 Years"

        notice_options = ["Immediate to 15 days", "15-30 days", "30-60 days"]
        assert self.client._match_chosen_option("15 days", notice_options) in ["Immediate to 15 days", "15-30 days"]

    def test_normalize_uniform_answer_short_fields(self):
        assert self.client._normalize_uniform_answer("23 LPA", "What is your Current CTC?", "text") == "23 LPA"
        assert self.client._normalize_uniform_answer("30 LPA", "What is your Expected CTC?", "text") == "30 LPA"
        assert self.client._normalize_uniform_answer("4.2 Years", "How many years of total experience do you have?", "text") == "4.2 Years"
        assert self.client._normalize_uniform_answer("4.2", "Total experience in years", "number") == "4"

    def test_normalize_uniform_answer_preserves_essays(self):
        essay = (
            "At Everbridge, I designed and built distributed, event-driven notification microservices "
            "handling 10M+ daily events with 99.99% uptime. The backend is built on Java 21 with Spring Boot, "
            "using Apache Kafka for high-throughput event streaming, distributed Redis caching, and PostgreSQL."
        )
        normalized = self.client._normalize_uniform_answer(
            essay,
            "Can you walk us through the architecture of a large-scale backend system you designed?",
            "textarea"
        )
        assert normalized == essay


class TestAgentQuestionnaireIntegration(unittest.IsolatedAsyncioTestCase):

    async def test_hirist_single_choice_llm_fallback(self):
        agent = SentinelAgent()
        mock_llm = MagicMock()
        mock_llm.answer_question = AsyncMock(return_value="3-5 Years")

        mock_page = AsyncMock()
        # mock click_option evaluate to return True
        mock_page.evaluate = AsyncMock(return_value=True)

        questions = [
            {
                "qid": "hq_1",
                "question": "Select relevant backend software engineering experience:",
                "kind": "single",
                "options": [{"text": "0-2 Years"}, {"text": "3-5 Years"}, {"text": "5+ Years"}]
            }
        ]

        with patch.object(agent, "_get_llm_client", return_value=mock_llm), \
             patch.object(agent, "_fuzzy_match_question", return_value=(None, 0.0)):
            answered = await agent._hirist_fill_questionnaire(mock_page, questions)
            assert answered == 1
            mock_llm.answer_question.assert_called_once()


class TestMultiAPIKeyFailover(unittest.IsolatedAsyncioTestCase):

    def test_multi_key_initialization(self):
        client = GemmaLLMClient()
        assert len(client.api_keys) >= 6
        assert client.get_current_api_key() == client.api_keys[0]

    def test_key_rotation_round_robin(self):
        keys = ["key-alpha", "key-beta", "key-gamma"]
        client = GemmaLLMClient(api_keys=keys)
        assert client.get_current_api_key() == "key-alpha"
        assert client.rotate_to_next_key("test 1") == "key-beta"
        assert client.get_current_api_key() == "key-beta"
        assert client.rotate_to_next_key("test 2") == "key-gamma"
        assert client.get_current_api_key() == "key-gamma"
        assert client.rotate_to_next_key("test 3") == "key-alpha"
        assert client.get_current_api_key() == "key-alpha"

    async def test_answer_question_failover_on_429_rate_limit(self):
        keys = ["key-1", "key-2"]
        client = GemmaLLMClient(api_keys=keys)
        client._discovery_completed = True
        client._fallback_chain = ["gemini-3.5-flash-lite"]

        # First call on key-1 returns 429, second call on key-2 returns 200 OK
        resp_429 = (429, '{"error": {"code": 429, "message": "Resource exhausted"}}')
        resp_200 = (200, '{"candidates": [{"content": {"parts": [{"text": "23 LPA"}]}}]}')

        with patch.object(client, "_http_post", AsyncMock(side_effect=[resp_429, resp_200])) as mock_post:
            ans = await client.answer_question("Current CTC?", input_type="text")
            assert ans == "23 LPA"
            assert mock_post.call_count == 2
            # Key 1 was tried first, then key-2 was tried
            assert "key=key-1" in mock_post.call_args_list[0][0][0]
            assert "key=key-2" in mock_post.call_args_list[1][0][0]
            # Current key is now key-2
            assert client.get_current_api_key() == "key-2"

    async def test_answer_question_failover_on_500_server_error(self):
        keys = ["key-1", "key-2"]
        client = GemmaLLMClient(api_keys=keys)
        client._discovery_completed = True
        client._fallback_chain = ["gemini-3.5-flash-lite"]

        resp_500 = (500, '{"error": {"code": 500, "message": "Internal error"}}')
        resp_200 = (200, '{"candidates": [{"content": {"parts": [{"text": "30 LPA"}]}}]}')

        with patch.object(client, "_http_post", AsyncMock(side_effect=[resp_500, resp_200])) as mock_post:
            ans = await client.answer_question("Expected CTC?", input_type="text")
            assert ans == "30 LPA"
            assert mock_post.call_count == 2
            assert "key=key-1" in mock_post.call_args_list[0][0][0]
            assert "key=key-2" in mock_post.call_args_list[1][0][0]
            assert client.get_current_api_key() == "key-2"

    async def test_transcribe_audio_failover(self):
        keys = ["key-1", "key-2"]
        client = GemmaLLMClient(api_keys=keys)

        resp_429 = (429, '{"error": {"code": 429, "message": "Resource exhausted"}}')
        resp_200 = (200, '{"candidates": [{"content": {"parts": [{"text": "4 2 9 8"}]}}]}')

        with patch.object(client, "_http_post", AsyncMock(side_effect=[resp_429, resp_200])) as mock_post:
            res = await client.transcribe_audio(b"fake_mp3_bytes")
            assert res == "4 2 9 8"
            assert mock_post.call_count == 2
            assert "key=key-1" in mock_post.call_args_list[0][0][0]
            assert "key=key-2" in mock_post.call_args_list[1][0][0]


if __name__ == "__main__":
    unittest.main()

