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
        self.assertIn("https://www.instahyre.com/candidate/inbox/439288/6201541231/", prompt)
        self.assertIn("convTypes.ALL", prompt)
        self.assertIn("conv-candidate", prompt)
        self.assertIn("completed the questionnaire", prompt)
        self.assertIn("submitQuestionnaire", prompt)
        self.assertIn("Questionnaire has been sent", prompt)

    def test_task_in_runner_list(self):
        """Verify Task 1 is included in tasks in run.py with direct target inbox URL."""
        import inspect
        src = inspect.getsource(main)
        self.assertIn("Instahyre Inbox Questionnaire", src)
        self.assertIn("https://www.instahyre.com/candidate/inbox/439288/6201541231/", src)
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
        """Simulate workflow starting directly at target inbox URL -> All filter -> click first card -> questionnaire -> ack."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/439288/6201541231/"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        # Mock evaluate calls:
        # 1. All filter confirmed -> 'ALL_RADIO_CONFIRMED'
        # 2. conv count -> 1
        # 3. click conv 1 -> {'status': 'CLICKED', 'name': 'Pallavi Naik', 'job': 'Infosys - Software Developer'}
        # 4. polling readiness -> True
        # 5. inspect message -> {'hasCompletedAckEntry': False, 'qUrl': 'https://www.instahyre.com/questionnaire/112329/6204425826'}
        # 6. wait for questions render -> True
        # 7. extract questions on questionnaire page
        # 8. fill question 1 -> 'FILLED_TEXT'
        # 9. fill question 2 -> 'FILLED_TEXT'
        # 10. submit button -> 'SUBMIT_CLICKED'
        # 11. confirmation -> True
        # 12. _send_instahyre_ack: editor found -> True
        # 13. _send_instahyre_ack: text verified in editor
        # 14. _send_instahyre_ack: button state -> enabled
        # 15. _send_instahyre_ack: click send -> None
        # 16. _send_instahyre_ack: dispatch verified -> True
        # 17. loop turn 1: click next conv -> NO_MORE_CONVERSATIONS
        # 18. scroll check -> False
        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            1,
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Pallavi Naik', 'job': 'Infosys - Software Developer'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': 'https://www.instahyre.com/questionnaire/112329/6204425826'},
            True,
            [
                {'index': 0, 'question': 'What is your Current CTC?', 'inputType': 'text', 'options': []},
                {'index': 1, 'question': 'What is your Expected CTC?', 'inputType': 'text', 'options': []},
            ],
            'FILLED_TEXT',
            'FILLED_TEXT',
            'SUBMIT_CLICKED',
            True,
            True,
            "Hi, I'm interested in this opportunity and have completed the questionnaire. Looking forward to hearing from you.",
            {'found': True, 'disabled': False},
            None,
            True,
            {'status': 'NO_MORE_CONVERSATIONS'},
            False
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        self.assertEqual(agent.metrics['applications_submitted'], 1)
        self.assertEqual(agent.metrics['questions_answered'], 2)
        self.assertEqual(agent.metrics['instahyre_acks_sent'], 1)
        self.assertGreaterEqual(mock_page.goto.await_count, 1)

    def test_inbox_execution_flow(self):
        """Run async inbox execution flow."""
        import asyncio
        asyncio.run(self._async_test_inbox_flow_direct_url())

    async def _async_test_inbox_first_card_acknowledged_stops_immediately(self):
        """Verify inspecting first conversation stops immediately if already acknowledged."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/439288/6201541231/"

        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            5,
            {'status': 'CLICKED', 'id': 'conv-123', 'rawId': 'raw-123', 'name': 'Pallavi Naik', 'job': 'Infosys'},
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
        mock_ans.assert_not_called()
        mock_ack.assert_not_called()

    def test_inbox_first_card_acknowledged_stops_immediately(self):
        """Run async test for stopping at first card when already acknowledged."""
        import asyncio
        asyncio.run(self._async_test_inbox_first_card_acknowledged_stops_immediately())

    async def _async_test_inbox_stops_at_first_acknowledged_conversation(self):
        """Verify that encountering an already-acknowledged conversation stops immediately
        since conversations are ordered chronologically newest-first."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/439288/6201541231/"

        # Mock evaluate calls:
        # 1. All filter confirmed -> 'ALL_RADIO_CONFIRMED'
        # 2. conv_count -> 2
        # 3. click card 1 -> {'status': 'CLICKED', 'id': 'card-1', 'name': 'Pallavi Naik', 'job': 'Infosys'}
        # 4. readiness -> True
        # 5. inspect card 1 -> {'hasCompletedAckEntry': True, 'qUrl': None} (ALREADY ACKED -> COMPLETE IMMEDIATELY)
        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            2,
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Pallavi Naik', 'job': 'Infosys'},
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
        # Verify card 2 was never opened and no ack was sent since card 1 was already acknowledged
        mock_answer.assert_not_called()
        mock_ack.assert_not_called()

    def test_inbox_stops_at_first_acknowledged_conversation(self):
        """Run async test for stopping at first acknowledged conversation."""
        import asyncio
        asyncio.run(self._async_test_inbox_stops_at_first_acknowledged_conversation())

    async def _async_test_inbox_ack_failure_reporting(self):
        """Verify that when sending an ack fails, honest failure is returned instead of false success."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/439288/6201541231/"

        mock_page.evaluate.side_effect = [
            'ALL_RADIO_CONFIRMED',
            1,
            {'status': 'CLICKED', 'id': 'card-1', 'rawId': 'raw-1', 'name': 'Pallavi Naik', 'job': 'Infosys'},
            True,
            {'hasCompletedAckEntry': False, 'qUrl': None},
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_send_instahyre_ack', new=AsyncMock(return_value=False)) as mock_ack, \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertFalse(result)
        self.assertTrue(agent.state.task_complete)
        self.assertEqual(agent.metrics['instahyre_acks_sent'], 0)

    def test_inbox_ack_failure_reporting(self):
        """Run async test for honest failure reporting on ack failure."""
        import asyncio
        asyncio.run(self._async_test_inbox_ack_failure_reporting())


if __name__ == '__main__':
    unittest.main()
