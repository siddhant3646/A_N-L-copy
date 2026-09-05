import unittest
import os
import tempfile
import csv
from unittest.mock import AsyncMock, MagicMock, patch
from src.sentinel.agent import SentinelAgent
from src.sentinel.llm_client import GemmaLLMClient


class TestInstahyreGemmaAnswers(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    async def test_instahyre_answers_with_gemma(self):
        """When Gemma client returns an answer, source is llm_gemma and confidence is 0.95."""
        mock_llm = MagicMock(spec=GemmaLLMClient)
        mock_llm.answer_question = AsyncMock(return_value="Yes")

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=[
            # wait_for_questions
            True,
            # questions_info
            [
                {
                    "index": 0,
                    "question": "Are you comfortable working hybrid in Bangalore?",
                    "inputType": "radio",
                    "options": ["Yes", "No"]
                }
            ],
            # fill_result
            "CLICKED_RADIO",
            # submit_res
            "SUBMIT_CLICKED",
            # confirmation
            True
        ])

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = os.path.join(tmp_dir, "qa_results.csv")
            with patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
                 patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir), \
                 patch.object(self.agent, "_get_llm_client", return_value=mock_llm), \
                 patch("asyncio.sleep", AsyncMock()):
                
                success = await self.agent._answer_instahyre_questionnaire(
                    mock_page, "https://www.instahyre.com/questionnaire/123/456"
                )
                self.assertTrue(success)

                # Verify CSV log
                with open(test_csv, "r", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["source"], "llm_gemma")
                    self.assertEqual(rows[0]["answer"], "Yes")
                    self.assertEqual(rows[0]["job_id_or_url"], "https://www.instahyre.com/questionnaire/123/456")

    async def test_instahyre_fallback_to_pattern(self):
        """When Gemma returns None, falls back to pattern matcher with pattern_fallback source."""
        mock_llm = MagicMock(spec=GemmaLLMClient)
        mock_llm.answer_question = AsyncMock(return_value=None)

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=[
            # wait_for_questions
            True,
            # questions_info
            [
                {
                    "index": 0,
                    "question": "What is your Current CTC?",
                    "inputType": "text",
                    "options": []
                }
            ],
            # fill_result
            "FILLED_TEXT",
            # submit_res
            "SUBMIT_CLICKED",
            # confirmation
            True
        ])

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = os.path.join(tmp_dir, "qa_results.csv")
            with patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
                 patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir), \
                 patch.object(self.agent, "_get_llm_client", return_value=mock_llm), \
                 patch("asyncio.sleep", AsyncMock()):
                
                success = await self.agent._answer_instahyre_questionnaire(
                    mock_page, "https://www.instahyre.com/questionnaire/123/456"
                )
                self.assertTrue(success)

                with open(test_csv, "r", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["source"], "pattern_fallback")
                    self.assertIn("23", rows[0]["answer"])

    async def test_instahyre_unmatched_fallback(self):
        """When both Gemma and pattern matcher return None, uses fallback default."""
        mock_llm = MagicMock(spec=GemmaLLMClient)
        mock_llm.answer_question = AsyncMock(return_value=None)

        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=[
            # wait_for_questions
            True,
            # questions_info
            [
                {
                    "index": 0,
                    "question": "Unknown futuristic technology experience level?",
                    "inputType": "text",
                    "options": []
                }
            ],
            # fill_result
            "FILLED_TEXT",
            # submit_res
            "SUBMIT_CLICKED",
            # confirmation
            True
        ])

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = os.path.join(tmp_dir, "qa_results.csv")
            with patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
                 patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir), \
                 patch.object(self.agent, "_get_llm_client", return_value=mock_llm), \
                 patch.object(self.agent, "_fuzzy_match_question", return_value=(None, 0.0)), \
                 patch("asyncio.sleep", AsyncMock()):
                
                success = await self.agent._answer_instahyre_questionnaire(
                    mock_page, "https://www.instahyre.com/questionnaire/123/456"
                )
                self.assertTrue(success)

                with open(test_csv, "r", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["source"], "unmatched_fallback")
                    self.assertEqual(rows[0]["answer"], "4.2 Years")


if __name__ == "__main__":
    unittest.main()
