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
        """Verify Task 8 prompt is defined and has required elements."""
        self.assertTrue(hasattr(prompts, 'INSTAHYRE_INBOX_QUESTIONNAIRE_TASK'))
        prompt = prompts.INSTAHYRE_INBOX_QUESTIONNAIRE_TASK
        self.assertIn("https://www.instahyre.com/candidate/opportunities/?matching=true", prompt)
        self.assertIn("nav-candidates-inbox", prompt)
        self.assertIn("convTypes.UNREAD", prompt)
        self.assertIn("conv-candidate", prompt)
        self.assertIn("questionnaire", prompt)
        self.assertIn("submitQuestionnaire", prompt)
        self.assertIn("Questionnaire has been sent", prompt)

    def test_task_in_runner_list(self):
        """Verify Task 8 is included in tasks in run.py with opportunities URL."""
        import inspect
        src = inspect.getsource(main)
        self.assertIn("Instahyre Inbox Questionnaire", src)
        self.assertIn("https://www.instahyre.com/candidate/opportunities/?matching=true", src)
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

    async def _async_test_inbox_flow_from_opportunities(self):
        """Simulate workflow starting from opportunities URL -> click inbox link -> click unread radio -> questionnaire -> ack."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
        mock_editor = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.first = mock_editor
        mock_page.locator = MagicMock(return_value=mock_locator)

        # Mock evaluate calls for opportunities -> inbox -> unread radio -> questionnaire -> ack -> end:
        # 1. clicked inbox nav link -> 'INBOX_CLICKED'
        # 2. unread radio clicked -> 'UNREAD_RADIO_CLICKED'
        # 3. conv count -> 1
        # 4. click conv -> {'status': 'CLICKED', 'name': 'Pallavi Naik', 'job': 'Infosys - Software Developer'}
        # 5. find q_url -> 'https://www.instahyre.com/questionnaire/112329/6204425826'
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
        # 16. loop turn 1: click next conv -> NO_MORE_UNREAD
        # 17. scroll check -> False
        mock_page.evaluate.side_effect = [
            'INBOX_CLICKED',
            'UNREAD_RADIO_CLICKED',
            1,
            {'status': 'CLICKED', 'name': 'Pallavi Naik', 'job': 'Infosys - Software Developer'},
            'https://www.instahyre.com/questionnaire/112329/6204425826',
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
            {'status': 'NO_MORE_UNREAD'},
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
        # Verify in-place goto call to questionnaire
        self.assertGreaterEqual(mock_page.goto.await_count, 1)

    def test_inbox_execution_flow(self):
        """Run async inbox execution flow."""
        import asyncio
        asyncio.run(self._async_test_inbox_flow_from_opportunities())

    async def _async_test_inbox_multiple_unread_conversations(self):
        """Verify processing multiple unread messages: one with questionnaire, one without."""
        mock_page = AsyncMock()
        mock_page.url = "https://www.instahyre.com/candidate/inbox/"

        # Mock evaluate calls:
        # 1. unread radio clicked -> 'UNREAD_RADIO_CLICKED'
        # 2. conv_count -> 2
        # 3. turn 0: click card 1 -> {'status': 'CLICKED', 'id': 'card-1', 'name': 'Pallavi Naik', 'job': 'Infosys'}
        # 4. turn 0: q_url scan -> 'https://www.instahyre.com/questionnaire/112329/6204425826'
        # 5. turn 1: click card 2 -> {'status': 'CLICKED', 'id': 'card-2', 'name': 'Rohan Gupta', 'job': 'Google'}
        # 6. turn 1: q_url scan -> None
        # 7. turn 2: click card 3 -> {'status': 'NO_MORE_UNREAD'}
        # 8. scroll check -> False
        mock_page.evaluate.side_effect = [
            'UNREAD_RADIO_CLICKED',
            2,
            {'status': 'CLICKED', 'id': 'card-1', 'name': 'Pallavi Naik', 'job': 'Infosys'},
            'https://www.instahyre.com/questionnaire/112329/6204425826',
            {'status': 'CLICKED', 'id': 'card-2', 'name': 'Rohan Gupta', 'job': 'Google'},
            None,
            {'status': 'NO_MORE_UNREAD'},
            False
        ]

        agent = SentinelAgent()
        agent._page = mock_page

        with patch.object(agent, '_answer_instahyre_questionnaire', new=AsyncMock(return_value=True)) as mock_answer, \
             patch.object(agent, '_send_instahyre_ack', new=AsyncMock(return_value=True)) as mock_ack, \
             patch("asyncio.sleep", AsyncMock()):
            result = await agent._handle_instahyre_inbox_task()

        self.assertTrue(result)
        self.assertTrue(agent.state.task_complete)
        # Verify questionnaire answered for card 1
        mock_answer.assert_called_once_with(mock_page, 'https://www.instahyre.com/questionnaire/112329/6204425826')
        # Verify two acks sent: card 1 with has_questionnaire=True, card 2 with has_questionnaire=False
        self.assertEqual(mock_ack.await_count, 2)
        mock_ack.assert_any_await(mock_page, "https://www.instahyre.com/candidate/inbox/", "Pallavi Naik", has_questionnaire=True)
        mock_ack.assert_any_await(mock_page, "https://www.instahyre.com/candidate/inbox/", "Rohan Gupta", has_questionnaire=False)

    def test_inbox_multiple_unread_conversations(self):
        """Run async multiple unread conversations execution flow."""
        import asyncio
        asyncio.run(self._async_test_inbox_multiple_unread_conversations())


if __name__ == '__main__':
    unittest.main()
