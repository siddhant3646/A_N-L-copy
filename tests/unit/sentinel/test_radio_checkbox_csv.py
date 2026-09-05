import unittest
import os
import tempfile
import csv
import inspect
from src.sentinel.agent import SentinelAgent


class TestRadioCheckboxCSV(unittest.TestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_qa_results_columns_schema(self):
        """Verify QA_RESULTS_COLUMNS contains the two new columns."""
        cols = SentinelAgent.QA_RESULTS_COLUMNS
        self.assertIn("source", cols)
        self.assertIn("job_id_or_url", cols)
        self.assertEqual(cols[-2], "source")
        self.assertEqual(cols[-1], "job_id_or_url")

    def test_log_qa_result_writes_new_columns(self):
        """Verify _log_qa_result persists source and job_id_or_url to CSV file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = os.path.join(tmp_dir, "qa_results.csv")
            with unittest.mock.patch.object(self.agent, "QA_RESULTS_CSV", test_csv), \
                 unittest.mock.patch.object(self.agent, "SCREENSHOT_DIR", tmp_dir):
                
                self.agent._log_qa_result(
                    question="Are you legally authorized to work in India?",
                    answer="Yes",
                    input_type="radio",
                    options=["Yes", "No"],
                    selected_option="Yes",
                    confidence=0.95,
                    status="answered",
                    platform="linkedin",
                    url="https://www.linkedin.com/jobs/view/4123456789/",
                    source="rule",
                    job_id_or_url="4123456789"
                )

                self.assertTrue(os.path.exists(test_csv))
                with open(test_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    self.assertEqual(len(rows), 1)
                    r = rows[0]
                    self.assertEqual(r["question"], "Are you legally authorized to work in India?")
                    self.assertEqual(r["answer"], "Yes")
                    self.assertEqual(r["input_type"], "radio")
                    self.assertEqual(r["options"], "Yes, No")
                    self.assertEqual(r["selected_option"], "Yes")
                    self.assertEqual(r["confidence"], "0.95")
                    self.assertEqual(r["source"], "rule")
                    self.assertEqual(r["job_id_or_url"], "4123456789")

    def test_js_form_results_contain_options_and_source(self):
        """Verify all radio and checkbox handlers in JS fallback populate options, selectedOption, and source."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)

        # Fieldset radios
        self.assertIn("options: radioOptions", src)
        # Custom radios
        self.assertIn("options: customRadioOptions", src)
        # Standalone radios
        self.assertIn("options: standaloneRadioOptions", src)
        # Group checkboxes
        self.assertIn("options: groupOptions", src)
        # Singleton checkbox
        self.assertIn("options: [labelText]", src)
        self.assertIn("selectedOption: 'Checked'", src)
        self.assertIn("source: 'rule'", src)


if __name__ == "__main__":
    unittest.main()
