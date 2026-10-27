import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType


class TestQACSVFixesOct19(unittest.TestCase):
    """Unit tests for QA pattern fixes identified in CSV audit across platforms (Oct 19)."""

    def setUp(self):
        self.agent = SentinelAgent()
        patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(patterns_data)
        self.resolver = InputAwareResolver()

    def test_01_fixed_variable_salary_breakup(self):
        q = "What is your current CTC in lakhs per annum. Pls provide breakups of Fixed, Variable & ESOPs."
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("23 LPA", ans)
        self.assertIn("0 LPA", ans)
        self.assertNotIn("21 LPA", ans)
        self.assertGreaterEqual(conf, 0.95)

    def test_02_location_current_checkbox_default(self):
        patterns = self.matcher.patterns.get("patterns", self.matcher.patterns)
        self.assertIn("location_current", patterns)
        loc_cur = patterns["location_current"]
        itd = loc_cur.get("input_type_defaults", {})
        self.assertEqual(itd.get("checkbox"), "Bengaluru")

    def test_03_numeric_range_matcher_18_lpa_plus(self):
        options = [
            Option(value="opt1", label="Upto 10 LPA", index=0),
            Option(value="opt2", label="10-15 LPA", index=1),
            Option(value="opt3", label="15-18 LPA", index=2),
            Option(value="opt4", label="18 LPA+", index=3),
        ]
        # Candidate expected CTC is 30 LPA
        res = self.resolver.resolve("30 LPA", InputType.SELECT, options, "How much annual salary are you expecting?")
        self.assertEqual(res.selected_option, "18 LPA+")

    def test_04_multicity_living_including_bangalore(self):
        questions = [
            "Are you currently living in Chennai/Bangalore/Pune/Noida?",
            "Are you currently residing in Hyderabad/Bangalore?",
            "Are you currently living in Chennai/Bangalore/Pune/Noida",
            "Are you currently residing in Hyderabad/Bangalore",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed on: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_05_non_bangalore_residing_without_relocation(self):
        questions = [
            "Are you in Pune",
            "Are you in Hyderabad",
            "Are you in Chennai",
            "Are you in Mumbai",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Failed on: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_06_open_for_city_location(self):
        questions = [
            "Are you open for Mumbai location?",
            "Are you open for Pune location?",
            "Are you open for Hyderabad location?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed on: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_07_join_from_office(self):
        questions = [
            "Will you be able to join from the office?",
            "Will you be able to join from office?",
            "Able to join from the office?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed on: {q}")
            self.assertNotEqual(ans, "15")
            self.assertGreaterEqual(conf, 0.95)

    def test_08_job_type_comfortable_with(self):
        q = "What kind of job are you comfortable with?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("Full", ans)
        self.assertGreaterEqual(conf, 0.95)

    def test_09_in_how_many_days_can_you_join_buyout(self):
        q = "In how many days can you join if selected? Also state earliest joining thru any buyout/negotiation/serving notice/leave adjustments, etc.?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("15 days", ans)
        self.assertNotEqual(ans, "Yes")
        self.assertGreaterEqual(conf, 0.95)

    def test_10_notice_period_status(self):
        q = "What is the status of your notice period ?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Serving notice period")
        self.assertNotEqual(ans, "15")
        self.assertGreaterEqual(conf, 0.95)

    def test_11_skill_expert_brief(self):
        q = "Which skill are you an expert in? Brief about you experience."
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("Java", ans)
        self.assertIn("Spring Boot", ans)
        self.assertNotEqual(ans, "4.2 Years")
        self.assertGreaterEqual(conf, 0.95)

    def test_12_llms_and_frameworks_used(self):
        q = "Which LLMs and frameworks have you used in projects (e.g., GPT, Azure OpenAI, Claude, LangChain, or LlamaIndex)?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("GPT-4", ans)
        self.assertIn("LangChain", ans)
        self.assertNotEqual(ans, "4.2 Years")
        self.assertGreaterEqual(conf, 0.95)

    def test_13_rag_pipeline_experience(self):
        q = "Explain your experience with document ingestion, chunking, embeddings, vector databases, retrieval, and response generation."
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("RAG pipelines", ans)
        self.assertNotEqual(ans, "4.2 Years")
        self.assertGreaterEqual(conf, 0.95)

    def test_14_years_of_experience_frontend_architecture(self):
        q = "How many years of experience do you have in Solid understanding of frontend architecture, design patterns, and performance at scale?"
        self.agent._current_platform = "linkedin"
        ans_li, conf_li = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_li, "4")
        self.assertGreaterEqual(conf_li, 0.90)

        self.agent._current_platform = "naukri"
        ans_nk, conf_nk = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans_nk, "4.2 Years")
        self.assertGreaterEqual(conf_nk, 0.90)

    def test_15_azure_devops_git_cicd_boolean(self):
        q = "Have you worked with Azure DevOps, Git, CI/CD pipelines, and automated deployments?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes")
        self.assertNotEqual(ans, "4")
        self.assertGreaterEqual(conf, 0.95)

    def test_16_serving_notice_days_remaining(self):
        q = 'Kindly mention your official notice period. if serving, please mention number of days remaining and if you are immediate joiner please mention "0".'
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "15")
        self.assertNotEqual(ans, "Less than 30 days")
        self.assertGreaterEqual(conf, 0.95)

    def test_17_city_and_pin_code(self):
        q = "Please mention your city and city PIN code for uploading purpose"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Bangalore 560001")
        self.assertGreaterEqual(conf, 0.95)

    def test_18_backend_programming_language(self):
        q = "Which programming language do you use most extensively for backend/application development?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Java")
        self.assertNotEqual(ans, "Python")
        self.assertGreaterEqual(conf, 0.95)

    def test_19_relevant_backend_software_engineering_experience(self):
        q = "Select relevant backend software engineering experience:"
        options = ["0-2 Years", "3-5 Years", "5+ Years"]
        ans, conf = self.matcher.fuzzy_match(q)
        self.assertEqual(ans, "3-5 Years")
        res = self.resolver.resolve(ans, InputType.SELECT, options, q)
        self.assertEqual(res.selected_option, "3-5 Years")

    def test_20_ctc_fixed_variable_ectc_offers(self):
        q = "Can you gave me the brief idea of your - CTC(Fixed + Variable ) , ECTC , Offer(If Any ) ?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("23 LPA", ans)
        self.assertIn("30 LPA", ans)
        self.assertIn("Offers", ans)
        self.assertGreaterEqual(conf, 0.95)

    def test_21_select_fallback_school_vit(self):
        import re
        school_options = ["Stanford University", "Yeshiva University", "Vellore Institute of Technology", "Other"]
        # Regex boundary check ensuring 'Yeshiva University' doesn't match word boundary '\byes\b'
        is_yes_match = [opt for opt in school_options if re.search(r'\byes\b', opt, re.I)]
        self.assertEqual(len(is_yes_match), 0)
        # Check VIT preference
        vit_match = [opt for opt in school_options if re.search(r'vellore|\bvit\b', opt, re.I)]
        self.assertEqual(len(vit_match), 1)
        self.assertEqual(vit_match[0], "Vellore Institute of Technology")

    def test_22_highest_education_degree(self):
        q = "What is the highest level of education you have completed?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Bachelor's Degree")
        self.assertNotEqual(ans, "Yes")
        self.assertGreaterEqual(conf, 0.95)

    def test_23_empty_question_fast_return(self):
        ans, conf = self.agent._fuzzy_match_question("")
        self.assertIsNone(ans)
        self.assertEqual(conf, 0.0)

        ans_ws, conf_ws = self.agent._fuzzy_match_question("   ")
        self.assertIsNone(ans_ws)
        self.assertEqual(conf_ws, 0.0)


if __name__ == '__main__':
    unittest.main()
