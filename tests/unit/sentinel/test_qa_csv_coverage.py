"""Every answered question has to reach qa_results.csv.

Answers come from three producers: the Python matchers, the injected LinkedIn
page script, and the Naukri chatbot script. Each one reports its fills in a
different shape, so each shape is recorded and tested here.
"""

import asyncio
import csv
import inspect
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent

LINKEDIN_URL = "https://www.linkedin.com/jobs/view/4400000000/"
NAUKRI_URL = "https://www.naukri.com/mnjuser/profile?id=application&jobId=111"


class _FakePage:
    """Answers only the Python-side QA drain; every other script is a no-op."""

    def __init__(self, url=LINKEDIN_URL, qa_entries=None):
        self.url = url
        self.qa_entries = list(qa_entries or [])
        self.evaluate_calls = []

    async def evaluate(self, script, arg=None):
        self.evaluate_calls.append((script, arg))
        if isinstance(script, str) and "window[globalName]" in script:
            entries, self.qa_entries = self.qa_entries, []
            return entries
        return "NO_ACTION"


class QaCsvCoverageTest(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.agent.SCREENSHOT_DIR = self.tmp.name
        self.agent.QA_RESULTS_CSV = os.path.join(self.tmp.name, "qa_results.csv")
        self.agent._qa_log_job_key = None
        self.agent._qa_logged_keys = set()

    def rows(self):
        with open(self.agent.QA_RESULTS_CSV, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_linkedin_script_payload_is_written(self):
        payload = [{
            "question": "How many years of experience do you have?",
            "answer": "4",
            "inputType": "select",
            "options": ["1", "2", "4"],
            "selectedOption": "4",
            "source": "pattern_match",
        }]
        written = self.agent._log_qa_payload(
            "LINKEDIN_FORM_STEP_CONTINUED|" + json.dumps(payload),
            platform="linkedin", url=LINKEDIN_URL,
        )
        self.assertEqual(written, 1)
        row = self.rows()[0]
        self.assertEqual(row["platform"], "linkedin")
        self.assertEqual(row["question"], "How many years of experience do you have?")
        self.assertEqual(row["answer"], "4")
        self.assertEqual(row["input_type"], "select")
        self.assertEqual(row["options"], "1, 2, 4")
        self.assertEqual(row["selected_option"], "4")
        self.assertEqual(row["source"], "pattern_match")
        self.assertEqual(row["status"], "submitted")
        self.assertEqual(row["job_id_or_url"], LINKEDIN_URL)

    def test_prefill_and_retrigger_flags_are_attributed(self):
        self.agent._log_qa_entries([
            {"question": "current location", "answer": "Bengaluru", "inputType": "text", "prefilled": True},
            {"question": "notice period", "answer": "15", "inputType": "text", "retriggered": True},
        ], platform="linkedin", url=LINKEDIN_URL)
        sources = {r["question"]: r["source"] for r in self.rows()}
        self.assertEqual(sources["current location"], "profile_prefilled")
        self.assertEqual(sources["notice period"], "resync_retype")

    def test_repeat_fill_of_same_control_is_logged_once(self):
        entry = {"question": "Are you legally authorized to work in India?",
                 "answer": "Yes", "inputType": "radio"}
        self.agent._log_qa_entries([entry], platform="linkedin", url=LINKEDIN_URL)
        self.agent._log_qa_entries([entry], platform="linkedin", url=LINKEDIN_URL)
        self.assertEqual(len(self.rows()), 1)

        rejected = dict(entry, status="validation_error")
        self.agent._log_qa_entries([rejected], platform="linkedin", url=LINKEDIN_URL)
        self.assertEqual([r["status"] for r in self.rows()], ["submitted", "validation_error"])

    def test_new_application_relogs_the_same_question(self):
        entry = {"question": "What is your current CTC?", "answer": "2300000", "inputType": "number"}
        self.agent._current_job_url = "https://www.linkedin.com/jobs/view/111/"
        self.agent._log_qa_entries([entry], platform="linkedin", url=LINKEDIN_URL)
        self.agent._current_job_url = "https://www.linkedin.com/jobs/view/222/"
        self.agent._log_qa_entries([entry], platform="linkedin", url=LINKEDIN_URL)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["job_id_or_url"] for r in rows],
                         ["https://www.linkedin.com/jobs/view/111/", "https://www.linkedin.com/jobs/view/222/"])

    def test_unanswered_control_is_logged_as_unknown(self):
        self.agent._log_qa_entries(
            [{"question": "Which notice duration can you commit to?", "answer": "", "inputType": "select"}],
            platform="linkedin", url=LINKEDIN_URL)
        self.assertEqual(self.rows()[0]["status"], "unknown")

    def test_junk_payloads_are_ignored(self):
        self.assertEqual(self.agent._log_qa_payload("NO_ACTION", platform="linkedin"), 0)
        self.assertEqual(self.agent._log_qa_payload("GENERIC_FORM_FILLED|not-json", platform="linkedin"), 0)
        self.assertEqual(self.agent._log_qa_entries("[]", platform="linkedin"), 0)
        self.assertEqual(self.agent._log_qa_entries([{"answer": "Yes"}], platform="linkedin"), 0)
        self.assertFalse(os.path.exists(self.agent.QA_RESULTS_CSV))

    def test_naukri_chatbot_short_keys_are_mapped(self):
        self.agent._page = _FakePage(url=NAUKRI_URL)
        self.agent._current_job_url = NAUKRI_URL
        written = self.agent._log_qa_entries(
            {"q": "Total years of experience?", "a": "4.2 Years", "t": "radio",
             "s": "4.2 Years", "options": ["3-5 Years", "5-8 Years"]},
            platform="naukri", url=NAUKRI_URL, default_source="naukri_chatbot_fuzzy")
        self.assertEqual(written, 1)
        row = self.rows()[0]
        self.assertEqual((row["platform"], row["input_type"], row["answer"], row["selected_option"]),
                         ("naukri", "radio", "4.2 Years", "4.2 Years"))
        self.assertEqual(row["options"], "3-5 Years, 5-8 Years")
        self.assertEqual(row["source"], "naukri_chatbot_fuzzy")

    def test_drain_reads_and_clears_the_page_side_log(self):
        page = _FakePage(url=LINKEDIN_URL, qa_entries=[
            {"question": "What is your expected CTC?", "answer": "3000000", "inputType": "text"}
        ])
        self.agent._page = page
        written = asyncio.run(self.agent._drain_js_qa_log(platform="linkedin", url=LINKEDIN_URL))
        self.assertEqual(written, 1)
        self.assertEqual(page.evaluate_calls[0][1], SentinelAgent.QA_JS_LOG_GLOBAL)
        self.assertEqual(asyncio.run(self.agent._drain_js_qa_log(platform="linkedin", url=LINKEDIN_URL)), 0)
        self.assertEqual(len(self.rows()), 1)

    def test_drain_survives_a_dead_page(self):
        self.agent._page = None
        self.assertEqual(asyncio.run(self.agent._drain_js_qa_log(platform="linkedin")), 0)

    def test_naukri_chatbot_markers_are_all_recorded(self):
        self.agent._page = _FakePage(url=NAUKRI_URL)
        self.agent._current_job_url = NAUKRI_URL
        self.agent._pattern_matcher = None
        self.agent._log_naukri_chatbot_result(
            "CHATBOT_RADIO_AND_SAVE|" + json.dumps({"q": "Notice period in days?", "a": "15", "t": "radio"}),
            {"q": "Notice period in days?", "a": "15", "t": "radio"})
        self.agent._log_naukri_chatbot_result("CHATBOT_SKIPPED_QUESTION: Upload your resume", None)
        self.agent._log_naukri_chatbot_result("CHATBOT_SUBMISSION_ERROR: Select an option to continue", None)
        rows = self.rows()
        self.assertEqual([r["status"] for r in rows], ["submitted", "skipped", "validation_error"])
        self.assertEqual({r["platform"] for r in rows}, {"naukri"})
        self.assertEqual(rows[0]["source"], "naukri_chatbot_fuzzy")
        self.assertEqual(rows[1]["question"], "Upload your resume")
        self.assertEqual(rows[2]["error_message"], "Select an option to continue")

    def test_naukri_chatbot_answer_counted_once_per_control(self):
        self.agent._page = _FakePage(url=NAUKRI_URL)
        self.agent._pattern_matcher = None
        before = self.agent.metrics.get("questions_answered", 0)
        payload = {"q": "Total experience?", "a": "4.2 Years", "t": "text"}
        self.agent._log_naukri_chatbot_result("CHATBOT_ANSWERED|" + json.dumps(payload), payload)
        self.agent._log_naukri_chatbot_result("CHATBOT_ANSWERED|" + json.dumps(payload), payload)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.agent.metrics["questions_answered"], before + 1)

    def test_scripted_fallback_mirrors_every_fill_into_the_page_log(self):
        source = inspect.getsource(SentinelAgent._handle_scripted_fallback)
        self.assertIn("const attachQaLog = (arr) => {", source)
        self.assertIn("const formResults = attachQaLog([]);", source)
        self.assertIn("const genericResults = attachQaLog([]);", source)
        self.assertIn("await self._drain_js_qa_log(", source)

    def test_scripted_fallback_logs_after_each_step(self):
        calls = []
        self.agent._page = _FakePage(url=LINKEDIN_URL, qa_entries=[
            {"question": "Are you authorized to work in India?", "answer": "Yes", "inputType": "radio"}
        ])
        with patch.object(SentinelAgent, "_inject_patterns_once", new=AsyncMock()), \
             patch.object(SentinelAgent, "_handle_linkedin_resume_upload", new=AsyncMock()), \
             patch.object(SentinelAgent, "_get_instahyre_skills", return_value=["Java"]), \
             patch.object(SentinelAgent, "_is_intersession_task", return_value=False), \
             patch.object(SentinelAgent, "_log_qa_result", side_effect=lambda **kw: calls.append(kw)):
            result = asyncio.run(SentinelAgent._handle_scripted_fallback(self.agent))
        self.assertEqual(result, "NO_ACTION")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["question"], "Are you authorized to work in India?")
        self.assertEqual(calls[0]["platform"], "linkedin")


    def test_indeed_logs_every_question_it_scans(self):
        questions = [
            {"qid": "sntlq_0", "question": "What is your total experience?", "hasInput": True,
             "hasSelect": False, "hasRadios": False, "hasCheckboxes": False,
             "options": [], "inputType": "text", "placeholder": ""},
            {"qid": "sntlq_1", "question": "Are you authorized to work in India?",
             "hasInput": False, "hasSelect": False, "hasRadios": True, "hasCheckboxes": False,
             "options": [{"value": "Yes", "text": "Yes"}, {"value": "No", "text": "No"}],
             "inputType": "", "placeholder": ""},
            {"qid": "sntlq_2", "question": "How many years of notice period do you have?",
             "hasInput": False, "hasSelect": True, "hasRadios": False, "hasCheckboxes": False,
             "options": [{"value": "0", "text": "Immediate"}, {"value": "15", "text": "15 Days"}],
             "inputType": "", "placeholder": ""},
        ]

        class _FakeFrame:
            def __init__(self):
                self.calls = []
                self._first = True

            async def evaluate(self, script, arg=None):
                self.calls.append((script, arg))
                if self._first:
                    self._first = False
                    return questions
                return None

            async def query_selector_all(self, selector):
                return []

        calls = []
        self.agent._page = _FakePage(url="https://in.indeed.com/jobs")
        with patch.object(SentinelAgent, "_log_qa_result", side_effect=lambda **kw: calls.append(kw)), \
             patch.object(SentinelAgent, "_get_llm_client", return_value=None), \
             patch.object(SentinelAgent, "_indeed_set_text", new=AsyncMock()), \
             patch.object(SentinelAgent, "_indeed_set_select", new=AsyncMock()), \
             patch.object(SentinelAgent, "_indeed_set_radio", new=AsyncMock()), \
             patch.object(SentinelAgent, "_indeed_set_checkboxes", new=AsyncMock()):
            asyncio.run(self.agent._indeed_answer_questions(_FakeFrame()))

        self.assertEqual([c["question"] for c in calls], [q["question"] for q in questions])
        self.assertEqual({c["platform"] for c in calls}, {"indeed"})
        for call in calls:
            self.assertIn(call["status"], ("submitted", "unknown", "validation_error"))
            if call["status"] == "submitted":
                self.assertTrue(str(call["answer"]).strip())
            self.assertTrue(call["input_type"])


if __name__ == "__main__":
    unittest.main()
