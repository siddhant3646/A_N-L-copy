import unittest
import os
import sys
import inspect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts


class TestInstahyreNewUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SentinelAgent()
        cls.js_src = inspect.getsource(cls.agent._handle_scripted_fallback)

    def test_skills_input_selectors(self):
        """Verify new skills input selector is present in JS fallback script."""
        self.assertIn("skills-drop-select-job-search-selectized", self.js_src)
        self.assertIn("skills-selectized", self.js_src)

    def test_company_size_checkbox_selectors(self):
        """Verify new company size checkbox selectors and click handlers are present."""
        self.assertIn("ui-checkbox", self.js_src)
        self.assertIn("company_size", self.js_src)
        self.assertIn("ALL", self.js_src)
        self.assertIn("INSTAHYRE_SET_COMPANY_SIZE", self.js_src)

    def test_locations_and_job_functions_selectors(self):
        """Verify location and job function 'All' checkbox selectors are present."""
        self.assertIn("jobLocations", self.js_src)
        self.assertIn("job_functions", self.js_src)
        self.assertIn("INSTAHYRE_SET_LOCATIONS", self.js_src)
        self.assertIn("INSTAHYRE_SET_JOB_FUNCTIONS", self.js_src)

    def test_search_button_selectors(self):
        """Verify search button selectors and ng-click handlers are present."""
        self.assertIn("skills-search-btn", self.js_src)
        self.assertIn("searchCustomJobs", self.js_src)

    def test_view_job_button_selectors(self):
        """Verify View job button selectors are present."""
        self.assertIn("btn-interested", self.js_src)
        self.assertIn("btn-success", self.js_src)
        self.assertIn("INSTAHYRE_VIEW_CLICKED", self.js_src)

    def test_modal_apply_button_selectors(self):
        """Verify modal Apply button selectors are present."""
        self.assertIn("new-btn", self.js_src)
        self.assertIn("btn-primary", self.js_src)
        self.assertIn("INSTAHYRE_APPLY_CLICKED", self.js_src)

    def test_prompts_match_new_ui_elements(self):
        """Verify prompt templates match new UI element IDs and classes."""
        for name, p in [
            ("INSTAHYRE_SEARCH_TASK", prompts.INSTAHYRE_SEARCH_TASK),
            ("INSTAHYRE_INTERSESSION_TASK", prompts.INSTAHYRE_INTERSESSION_TASK)
        ]:
            self.assertIn("skills-drop-select-job-search-selectized", p, f"Missing skills ID in {name}")
            self.assertIn("skills-search-btn", p, f"Missing search button class in {name}")
            self.assertIn("jobLocations", p, f"Missing locations 'All' selector in {name}")
            self.assertIn("job_functions", p, f"Missing job functions 'All' selector in {name}")

    def test_no_jobs_detection_phrases(self):
        """Verify no matching opportunities detection phrases in JS fallback script."""
        self.assertIn("no matching opportunities", self.js_src)
        self.assertIn("couldn't find any matching", self.js_src)
        self.assertIn("INSTAHYRE_NO_MORE_JOBS", self.js_src)

    def test_open_modal_selector_safety(self):
        """Verify open modal selector does not broadly match passive modal elements."""
        self.assertIn(".modal.in, .modal.show", self.js_src)
        self.assertNotIn('querySelectorAll(\'.modal, [class*="modal"]', self.js_src)

    def test_flow_sequence_skills_then_search_then_filters(self):
        """Verify the JS fallback sequence is: 1. Skills -> 2. Search -> 3. Filters."""
        pos_skills = self.js_src.find("1. Skills - First enter skills")
        pos_search = self.js_src.find("2. Click \"Search\" / \"Show Results\" button")
        pos_filters = self.js_src.find("3. Configure Filters (Company Size, Job Functions, Locations)")
        pos_view_apply = self.js_src.find("4. View & Apply (The Main Loop)")

        self.assertNotEqual(pos_skills, -1, "Skills section not found")
        self.assertNotEqual(pos_search, -1, "Search button section not found")
        self.assertNotEqual(pos_filters, -1, "Filters configuration section not found")
        self.assertNotEqual(pos_view_apply, -1, "View & Apply section not found")

        self.assertTrue(pos_skills < pos_search < pos_filters < pos_view_apply,
                        "Flow order mismatch: expected skills -> search -> filters -> view & apply")


if __name__ == '__main__':
    unittest.main()


