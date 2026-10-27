"""Unit tests for Hirist QA CSV logging and browser console noise filtering."""

import asyncio
import io
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class _MockConsoleMsg:
    def __init__(self, text: str):
        self.text = text


class TestHiristQALoggingAndConsoleFiltering(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()

    def test_log_js_msg_filters_browser_noise(self):
        """Noisy browser warnings (CORS, font CSP, fontello, magicsort, undefined) are ignored."""
        noisy_texts = [
            "Access to fetch at 'https://js-static.hirist.tech/_next/static/css/bfb1.css' from origin 'https://www.hirist.tech' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.",
            "Loading the font 'fontello' violates the following Content Security Policy directive: \"font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net\".",
            "magicsort: fetching data failed",
            "undefined",
            "null",
            "",
            "Failed to decode downloaded font: OTS parsing error",
            "The resource https://example.com/asset.js was preloaded using link preload but not used",
            "favicon.ico: Failed to load resource: net::ERR_BLOCKED_BY_CLIENT",
        ]

        for text in noisy_texts:
            msg = _MockConsoleMsg(text)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                self.agent._log_js_msg(msg)
                self.assertEqual(mock_out.getvalue(), "", f"Expected noise to be filtered: {text}")

    def test_log_js_msg_prints_real_messages(self):
        """Actionable / real messages should be logged to stdout."""
        msg = _MockConsoleMsg("Sentinel form hook successfully initialized")
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            self.agent._log_js_msg(msg)
            output = mock_out.getvalue()
            self.assertIn("🖥️ JS: Sentinel form hook successfully initialized", output)

    async def test_hirist_fill_questionnaire_logs_radio_to_csv(self):
        """Single-choice radio options log to qa_results.csv with platform='hirist'."""
        questions = [
            {
                'qid': 'sntl_hq_0',
                'question': 'Are you open to relocate to Bangalore?',
                'kind': 'single',
                'options': [{'text': 'Yes'}, {'text': 'No'}],
                'hasTextarea': False,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 0
            }
        ]

        self.agent._hirist_click_option = AsyncMock(return_value=True)
        self.agent._hirist_pick_option = MagicMock(return_value="Yes")
        self.agent._fuzzy_match_question = MagicMock(return_value=("Yes", 0.98))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-123"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 1)
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]

        self.assertEqual(call_kwargs['question'], 'Are you open to relocate to Bangalore?')
        self.assertEqual(call_kwargs['answer'], 'Yes')
        self.assertEqual(call_kwargs['input_type'], 'radio')
        self.assertEqual(call_kwargs['options'], ['Yes', 'No'])
        self.assertEqual(call_kwargs['selected_option'], 'Yes')
        self.assertEqual(call_kwargs['status'], 'submitted')
        self.assertEqual(call_kwargs['platform'], 'hirist')
        self.assertEqual(call_kwargs['url'], 'https://www.hirist.tech/j/backend-engineer-123')

    async def test_hirist_fill_questionnaire_logs_prefilled_to_csv(self):
        """Questions prefilled by Hirist profile log with status='prefilled'."""
        questions = [
            {
                'qid': 'sntl_hq_1',
                'question': 'Current Mobile Number',
                'kind': 'text',
                'options': [],
                'hasTextarea': False,
                'hasInput': True,
                'prefilled': True,
                'prefilledValue': '+91-7905828880',
                'maxChars': 20
            }
        ]

        self.agent.log_qa_result = MagicMock()
        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-123"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 0)  # prefilled is left as is
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]

        self.assertEqual(call_kwargs['question'], 'Current Mobile Number')
        self.assertEqual(call_kwargs['answer'], '+91-7905828880')
        self.assertEqual(call_kwargs['status'], 'prefilled')
        self.assertEqual(call_kwargs['platform'], 'hirist')
        self.assertEqual(call_kwargs['source'], 'profile_prefilled')

    async def test_hirist_fill_questionnaire_logs_text_and_textarea_to_csv(self):
        """Free-text fields log to qa_results.csv with platform='hirist'."""
        questions = [
            {
                'qid': 'sntl_hq_2',
                'question': 'What is your current CTC in Lacs per annum?',
                'kind': 'text',
                'options': [],
                'hasTextarea': True,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 50
            }
        ]

        self.agent._hirist_fill_text = AsyncMock(return_value=True)
        self.agent._fuzzy_match_question = MagicMock(return_value=("23 LPA", 0.95))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-123"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 1)
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]

        self.assertEqual(call_kwargs['question'], 'What is your current CTC in Lacs per annum?')
        self.assertEqual(call_kwargs['answer'], '23')  # Adapted for 'in Lacs per annum'
        self.assertEqual(call_kwargs['input_type'], 'textarea')
        self.assertEqual(call_kwargs['status'], 'submitted')
        self.assertEqual(call_kwargs['platform'], 'hirist')

    async def test_hirist_fill_questionnaire_logs_rejected_click_to_csv(self):
        """A chosen option the form never accepts still leaves a validation_error row."""
        questions = [
            {
                'qid': 'sntl_hq_4',
                'question': 'How many years of Java experience do you have?',
                'kind': 'single',
                'options': [{'text': '3-5'}, {'text': '5-7'}],
                'hasTextarea': False,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 0
            }
        ]

        self.agent._hirist_click_option = AsyncMock(return_value=False)
        self.agent._hirist_pick_option = MagicMock(return_value="3-5")
        self.agent._fuzzy_match_question = MagicMock(return_value=("3-5", 0.95))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-456"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 0)
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]
        self.assertEqual(call_kwargs['status'], 'validation_error')
        self.assertEqual(call_kwargs['error_message'], 'Option click rejected by form')
        self.assertEqual(call_kwargs['answer'], '3-5')
        self.assertEqual(call_kwargs['platform'], 'hirist')

    async def test_hirist_fill_questionnaire_logs_failed_text_fill_to_csv(self):
        """A text field the form refuses to accept still leaves a validation_error row."""
        questions = [
            {
                'qid': 'sntl_hq_5',
                'question': 'What is your current CTC in Lacs per annum?',
                'kind': 'text',
                'options': [],
                'hasTextarea': False,
                'hasInput': True,
                'prefilled': False,
                'maxChars': 50
            }
        ]

        self.agent._hirist_fill_text = AsyncMock(return_value=False)
        self.agent._fuzzy_match_question = MagicMock(return_value=("23 LPA", 0.95))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-456"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 0)
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]
        self.assertEqual(call_kwargs['status'], 'validation_error')
        self.assertEqual(call_kwargs['error_message'], 'Could not fill text/textarea field')
        self.assertEqual(call_kwargs['platform'], 'hirist')

    async def test_hirist_fill_questionnaire_logs_unknown_to_csv(self):
        """Unknown/unmatched questions log to qa_results.csv with status='unknown'."""
        questions = [
            {
                'qid': 'sntl_hq_3',
                'question': 'What is your favorite astronomical observatory?',
                'kind': 'text',
                'options': [],
                'hasTextarea': True,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 100
            }
        ]

        self.agent._fuzzy_match_question = MagicMock(return_value=(None, 0.0))
        self.agent._get_llm_client = MagicMock(return_value=None)
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/j/backend-engineer-123"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 0)
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]

        self.assertEqual(call_kwargs['question'], 'What is your favorite astronomical observatory?')
        self.assertEqual(call_kwargs['status'], 'unknown')
        self.assertEqual(call_kwargs['platform'], 'hirist')

    async def test_hirist_fill_questionnaire_deduplicates_seen_questions(self):
        """Questions already seen in previous steps are not re-answered or double-logged."""
        questions = [
            {
                'qid': 'sntl_hq_4',
                'question': 'Are you currently serving notice period?',
                'kind': 'single',
                'options': [{'text': 'Yes'}, {'text': 'No'}],
                'hasTextarea': False,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 0
            }
        ]

        self.agent._hirist_click_option = AsyncMock(return_value=True)
        self.agent._hirist_pick_option = MagicMock(return_value="Yes")
        self.agent._fuzzy_match_question = MagicMock(return_value=("Yes", 0.98))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        seen = {'are you currently serving notice period?'}

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions, seen_questions=seen)

        self.assertEqual(answered, 0)
        self.agent.log_qa_result.assert_not_called()
        self.agent._hirist_click_option.assert_not_called()

    def test_hirist_option_to_days_serving_notice(self):
        """'Currently Serving Notice Period' and 'serving notice' map to 15 days."""
        self.assertEqual(self.agent._hirist_option_to_days('Currently Serving Notice Period'), 15)
        self.assertEqual(self.agent._hirist_option_to_days('serving notice'), 15)
        self.assertEqual(self.agent._hirist_option_to_days('serving np'), 15)
        self.assertEqual(self.agent._hirist_option_to_days('on notice'), 15)
        self.assertEqual(self.agent._hirist_option_to_days('15 days'), 15)
        self.assertEqual(self.agent._hirist_option_to_days('Immediately Available'), 0)
        self.assertEqual(self.agent._hirist_option_to_days('1 month'), 30)

    def test_hirist_pick_option_notice_period(self):
        """Notice period options resolve correctly for candidate serving 15 days notice."""
        # 1. Accion Labs options with explicit serving notice choice
        accion_opts = [
            'On Bench, Immediate Joiner / Served Notice Period',
            'Currently Serving Notice Period',
            'Upto 30 days, Not Serving Notice Period',
            'Upto 60 days, Not Serving Notice Period',
        ]
        picked = self.agent._hirist_pick_option('Currently Serving Notice Period', accion_opts, 'Notice period')
        self.assertEqual(picked, 'Currently Serving Notice Period')

        # 2. Standard Hirist duration brackets: 15 days covers into 1 month
        standard_opts = ['Immediately Available', '1 month', '2 months', '3 months']
        picked_std = self.agent._hirist_pick_option('Currently Serving Notice Period', standard_opts, 'Notice period')
        self.assertEqual(picked_std, '1 month')

        # 3. Numeric range options
        range_opts = ['Immediate', '15 Days', '30 Days', '60 Days']
        picked_range = self.agent._hirist_pick_option('Currently Serving Notice Period', range_opts, 'Notice period')
        self.assertEqual(picked_range, '15 Days')

    def test_hirist_lwd_fuzzy_match(self):
        """'Last Working Day if serving Notice Period' returns clean date; combined returns composite."""
        from datetime import datetime, timedelta
        self.agent._current_platform = 'hirist'

        # Conditional pure LWD question
        ans, conf = self.agent._fuzzy_match_question('Last Working Day if serving Notice Period')
        expected_date = (datetime.now() + timedelta(days=15)).strftime('%d %b %Y')
        self.assertEqual(ans, expected_date)
        self.assertGreaterEqual(conf, 0.95)

        # Combined Notice Period + LWD question
        ans_comb, conf_comb = self.agent._fuzzy_match_question('Notice period and LWD')
        self.assertEqual(ans_comb, f"15 Days, LWD: {expected_date}")
        self.assertGreaterEqual(conf_comb, 0.95)

    async def test_hirist_fill_questionnaire_checkbox_range_question(self):
        """Checkbox range questions (e.g. Java exp) resolve to best range and log input_type='checkbox'."""
        questions = [
            {
                'qid': 'sntl_hq_cb_0',
                'question': 'How many years of hands-on experience do you have with Java development?',
                'kind': 'single',
                'choiceType': 'checkbox',
                'options': [{'text': '6 to 10 years'}, {'text': '8 to 12 years'}, {'text': '10 to 15 years'}],
                'hasTextarea': False,
                'hasInput': False,
                'prefilled': False,
                'maxChars': 0
            }
        ]

        self.agent._hirist_click_option = AsyncMock(return_value=True)
        self.agent._fuzzy_match_question = MagicMock(return_value=("4.2 Years", 0.98))
        self.agent.log_qa_result = MagicMock()

        mock_page = MagicMock()
        mock_page.url = "https://www.hirist.tech/job/1675905/screening"

        answered = await self.agent._hirist_fill_questionnaire(mock_page, questions)

        self.assertEqual(answered, 1)
        self.agent._hirist_click_option.assert_called_once_with(mock_page, 'sntl_hq_cb_0', '6 to 10 years')
        self.agent.log_qa_result.assert_called_once()
        call_kwargs = self.agent.log_qa_result.call_args[1]

        self.assertEqual(call_kwargs['question'], 'How many years of hands-on experience do you have with Java development?')
        self.assertEqual(call_kwargs['answer'], '6 to 10 years')
        self.assertEqual(call_kwargs['input_type'], 'checkbox')
        self.assertEqual(call_kwargs['selected_option'], '6 to 10 years')
        self.assertEqual(call_kwargs['status'], 'submitted')
        self.assertEqual(call_kwargs['platform'], 'hirist')

    def test_hirist_pick_option_experience_range(self):
        """_hirist_pick_option correctly resolves numeric experience into brackets."""
        q = 'How many years of hands-on experience do you have with Java development?'
        opts = ['6 to 10 years', '8 to 12 years', '10 to 15 years']
        picked = self.agent._hirist_pick_option('4.2 Years', opts, q)
        self.assertEqual(picked, '6 to 10 years')

        picked_4 = self.agent._hirist_pick_option('4', opts, q)
        self.assertEqual(picked_4, '6 to 10 years')

        react_q = 'Experience in React'
        react_opts = ['1 to 3 years', '3 to 5 years', '5 to 8 years', '8+ years']
        picked_react = self.agent._hirist_pick_option('4.2 Years', react_opts, react_q)
        self.assertEqual(picked_react, '3 to 5 years')
