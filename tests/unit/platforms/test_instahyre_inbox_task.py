import unittest
import os
import sys
import tempfile
import csv
import json
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.patterns.pattern_matcher import create_matcher
from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts
from src.sentinel.run import main


class TestInstahyreInboxTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher()
        cls.agent = SentinelAgent()

    def test_prompt_definition(self):
        """Verify Task 1 prompt is defined and has required elements."""
        self.assertTrue(hasattr(prompts, 'INSTAHYRE_INBOX_QUESTIONNAIRE_TASK'))
        prompt = prompts.INSTAHYRE_INBOX_QUESTIONNAIRE_TASK
        self.assertIn("https://www.instahyre.com/candidate/inbox/", prompt)
        self.assertIn("convTypes.ALL", prompt)
        self.assertIn("conv-candidate", prompt)
        self.assertIn("completed the questionnaire", prompt)
        self.assertIn("submitQuestionnaire", prompt)
        self.assertIn("Questionnaire has been sent", prompt)

    def test_instahyre_intersession_company_size_all(self):
        """Verify Instahyre Intersession task selects All for company size."""
        prompt = prompts.INSTAHYRE_INTERSESSION_TASK
        self.assertIn("Company Size: All", prompt)
        self.assertNotIn("Company Size: Large", prompt)

    def test_instahyre_search_company_size_large(self):
        """Verify Instahyre standard search task preserves Large company size."""
        prompt = prompts.INSTAHYRE_SEARCH_TASK
        self.assertIn("Company Size: Large", prompt)

    def test_task_in_runner_list(self):
        """Verify Task 1 is included in tasks in run.py with direct target inbox URL."""
        import inspect
        src = inspect.getsource(main)
        self.assertIn("Instahyre Inbox Questionnaire", src)
        self.assertIn("https://www.instahyre.com/candidate/inbox/", src)
        self.assertIn("prompts.INSTAHYRE_INBOX_QUESTIONNAIRE_TASK", src)

    def test_questionnaire_question_patterns(self):
        """Verify that all questions from the user's questionnaire match accurately."""
        test_cases = [
            ("What is your Current CTC?", "23", 0.90),
            ("What is your Expected CTC?", "30", 0.90),
            ("what is your Notice Period?", "15", 0.90),
            ("Are you an Individual contributor ?", "Yes", 0.90),
            ("Do you have architectural designing and full stack experience?", "Yes", 0.90),
        ]
        for q, expected_sub, min_conf in test_cases:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIsNotNone(ans, f"Failed to match question: {q}")
            self.assertIn(expected_sub.lower(), ans.lower(), f"Expected '{expected_sub}' in answer '{ans}' for '{q}'")
            self.assertGreaterEqual(conf, min_conf, f"Confidence {conf} was less than {min_conf} for '{q}'")

    def test_qa_csv_logging(self):
        """Verify QA result is logged to qa_results.csv correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = os.path.join(tmp_dir, "qa_results.csv")
            with patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
                 patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir):
                self.agent.log_qa_result(
                    question="What is your Current CTC?",
                    answer="23 LPA",
                    input_type="text",
                    options=[],
                    selected_option="23 LPA",
                    confidence=0.98,
                    status="submitted",
                    platform="instahyre",
                    url="https://www.instahyre.com/questionnaire/112329/6204425826"
                )

                self.assertTrue(os.path.exists(test_csv))
                with open(test_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    self.assertEqual(len(rows), 1)
                    r = rows[0]
                    self.assertEqual(r["platform"], "instahyre")
                    self.assertEqual(r["question"], "What is your Current CTC?")
                    self.assertEqual(r["answer"], "23 LPA")
                    self.assertEqual(r["input_type"], "text")
                    self.assertEqual(r["status"], "submitted")

    async def _async_test_inbox_flow_direct_url(self):
        """Simulate workflow starting directly at candidate inbox URL -> All filter -> click first card -> questionnaire -> ack -> move to next card."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/"

        # Mock evaluate calls:
        # 1. All filter confirmed -> 'ALL_RADIO_CONFIRMED'
        # 2. conv count -> 2
        # Card 1:
        # 3. click conv 1 -> Sanoop
        # 4. polling readiness -> True
        # 5. inspect message card 1 -> no ack, has qUrl
        # 6. questionnaire render -> True
        # 7. extract questions on questionnaire page
        # 8. fill questions -> 'FILLED_ALL'
        # 9. submit button -> 'SUBMIT_CLICKED'
        # 10. confirmation -> True
        # Card 2 (Mamata -> already acknowledged -> stops task):
        # 11. click conv 2 -> Mamata
        # 12. polling readiness -> True
        # 13. inspect message card 2 -> has ack -> STOPS TASK!
        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            2,
            # Card 1
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Sanoop Kannoli', 'job': 'Enlyft - Principal Software'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': 'https://www.instahyre.com/questionnaire/112329/6204425826'},
            True,
            [
                {'index': 0, 'question': 'What is your Current CTC?', 'inputType': 'text', 'options': []},
                {'index': 1, 'question': 'What is your Expected CTC?', 'inputType': 'text', 'options': []},
            ],
            'FILLED_ALL',
            'SUBMIT_CLICKED',
            True,
            # Card 2
            {'status': 'CLICKED', 'id': 'card-2', 'rawId': 'raw-2', 'name': 'Mamata Padhan', 'job': 'Cubic Corporation'},
            True,
            {'hasCompletedAckEntry': True, 'qUrl': None}
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_send_instahyre_ack', new=AsyncMock(return_value=True)) as mock_ack, \
             patch.object(agent, '_get_llm_client', return_value=None), \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        self.assertEqual(agent.metrics['applications_submitted'], 1)
        self.assertEqual(agent.metrics['questions_answered'], 2)
        mock_ack.assert_called_once()
        self.assertGreaterEqual(mock_page.goto.await_count, 1)

    def test_inbox_execution_flow(self):
        """Run async inbox execution flow."""
        import asyncio
        asyncio.run(self._async_test_inbox_flow_direct_url())

    async def _async_test_inbox_first_card_acknowledged_stops_immediately(self):
        """Verify inspecting first conversation stops immediately (Rule 7) if already acknowledged."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/"

        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            5,
            {'status': 'CLICKED', 'id': 'conv-123', 'rawId': 'raw-123', 'name': 'Sanoop Kannoli', 'job': 'Enlyft'},
            True,
            {'hasCompletedAckEntry': True, 'qUrl': None}
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_answer_instahyre_questionnaire', new=AsyncMock()) as mock_ans, \
             patch.object(agent, '_send_instahyre_ack', new=AsyncMock()) as mock_ack, \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        self.assertEqual(agent.metrics.get('instahyre_acks_sent', 0), 0)
        mock_ans.assert_not_called()
        mock_ack.assert_not_called()

    def test_inbox_first_card_acknowledged_stops_immediately(self):
        """Run async test for stopping at first card when already acknowledged."""
        import asyncio
        asyncio.run(self._async_test_inbox_first_card_acknowledged_stops_immediately())

    async def _async_test_inbox_multi_cards_processed_until_acknowledged(self):
        """Verify sequential processing of multiple unacknowledged cards until reaching an acknowledged card."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/"

        # Mock evaluate calls for 3 cards:
        # 1. All filter confirmed -> 'ALL_RADIO_CONFIRMED'
        # 2. conv_count -> 3
        # Card 1 (no questionnaire, interest reply):
        # 3. click card 1 -> Sanoop
        # 4. readiness -> True
        # 5. inspect card 1 -> no ack, no qUrl
        # Card 2 (questionnaire link):
        # 6. click card 2 -> Thejaswini
        # 7. readiness -> True
        # 8. inspect card 2 -> no ack, has qUrl
        # Card 3 (already acknowledged):
        # 9. click card 3 -> Mamata
        # 10. readiness -> True
        # 11. inspect card 3 -> HAS ACK -> STOPS!
        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            3,
            # Card 1
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Sanoop Kannoli', 'job': 'Enlyft'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': None},
            # Card 2
            {'status': 'CLICKED', 'id': 'card-2', 'rawId': 'raw-2', 'name': 'Thejaswini K T', 'job': 'Curl Analytics'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': 'https://www.instahyre.com/questionnaire/999/111'},
            # Card 3
            {'status': 'CLICKED', 'id': 'card-3', 'rawId': 'raw-3', 'name': 'Mamata Padhan', 'job': 'Cubic Corporation'},
            True,
            {'hasCompletedAckEntry': True, 'qUrl': None},
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_answer_instahyre_questionnaire', new=AsyncMock(return_value=True)) as mock_answer, \
             patch.object(agent, '_send_instahyre_ack', new=AsyncMock(return_value=True)) as mock_ack, \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        # Card 1 had no questionnaire -> 0 questionnaire answers, 1 ack
        # Card 2 had questionnaire -> 1 questionnaire answer, 1 ack
        # Total acks sent: 2
        self.assertEqual(mock_ack.call_count, 2)
        self.assertEqual(mock_answer.call_count, 1)

    def test_inbox_multi_cards_processed_until_acknowledged(self):
        """Run async test for processing multiple cards until acknowledged card reached."""
        import asyncio
        asyncio.run(self._async_test_inbox_multi_cards_processed_until_acknowledged())

    async def _async_test_inbox_ack_failure_reporting(self):
        """Verify that when sending an ack fails, task continues checking remaining cards."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/"

        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            1,
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Pallavi Naik', 'job': 'Infosys'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': None},
            {'status': 'NO_MORE_CONVERSATIONS'},
            False
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_send_instahyre_ack', new=AsyncMock(return_value=False)) as mock_ack, \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        self.assertEqual(agent.metrics['instahyre_acks_sent'], 0)

    def test_inbox_ack_failure_reporting(self):
        """Run async test for ack failure handling."""
        import asyncio
        asyncio.run(self._async_test_inbox_ack_failure_reporting())


if __name__ == '__main__':
    unittest.main()
