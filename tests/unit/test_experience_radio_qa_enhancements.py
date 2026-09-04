import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.patterns.pattern_matcher import create_matcher


class TestExperienceRadioAndQAEnhancements(unittest.TestCase):
    def setUp(self):
        self.matcher = create_matcher()

    def test_architecture_walkthrough_system_design(self):
        ans, score = self.matcher.fuzzy_match("Can you walk us through the architecture of a large-scale backend system you designed?")
        self.assertIsNotNone(ans)
        self.assertIn("microservices", ans.lower())
        self.assertIn("kafka", ans.lower())

    def test_sync_vs_async_decision(self):
        ans, score = self.matcher.fuzzy_match("In a high-traffic system, how would you decide between synchronous vs asynchronous communication?")
        self.assertIsNotNone(ans)
        self.assertIn("synchronous", ans.lower())
        self.assertIn("asynchronous", ans.lower())

    def test_microservices_from_scratch(self):
        ans, score = self.matcher.fuzzy_match("Have you designed and built microservices-based applications from scratch?")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.startswith("Yes"))

    def test_rest_api_openapi_swagger(self):
        ans, score = self.matcher.fuzzy_match("Have you designed and developed production-grade REST APIs using OpenAPI/Swagger?")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.startswith("Yes"))

    def test_api_gateway_integrations(self):
        ans, score = self.matcher.fuzzy_match("Have you worked on API Gateway integrations (Apigee, GCP API Gateway, etc.)?")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.startswith("Yes"))

    def test_small_and_large_scale_projects(self):
        ans, score = self.matcher.fuzzy_match("Have you worked on both small-scale and large-scale projects/products? Please provide examples.")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.startswith("Yes"))

    def test_java_experience_question(self):
        ans, score = self.matcher.fuzzy_match("How many years of experience do you have in Java ?")
        self.assertIsNotNone(ans)
        self.assertIn("4", ans)

    def test_experience_radio_matching_js_logic(self):
        # Python test simulating the updated scoreRadio logic with candidate experience 4.2 years
        import re

        def score_radio(label: str, answer: str = "4.2", exp_val: float = 4.2) -> float:
            clean_label = label.lower().strip()
            answer_lower = answer.lower().strip()

            # Yes/No matching
            is_label_yes = bool(re.search(r'\byes\b', clean_label)) or 'serving' in clean_label or 'agree' in clean_label or 'consent' in clean_label
            is_label_no = (bool(re.search(r'\bno\b', clean_label)) or 'disagree' in clean_label) and not is_label_yes
            is_ans_yes = bool(re.search(r'\byes\b', answer_lower)) or 'serving' in answer_lower or answer_lower == 'true'
            is_ans_no = (bool(re.search(r'\bno\b', answer_lower)) or answer_lower == 'false') and not is_ans_yes

            if is_label_yes and is_ans_yes: return 95
            if is_label_no and is_ans_no: return 95
            if is_label_yes and is_ans_no: return 0
            if is_label_no and is_ans_yes: return 0

            # 1. Range format: "X-Y", "X to Y", "X – Y" (e.g., "3-5", "4-5", "5-7", "7-9")
            range_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)', clean_label)
            if range_match:
                r_min = float(range_match.group(1))
                r_max = float(range_match.group(2))
                if exp_val >= r_min and exp_val <= r_max:
                    return max(85, 99 - (r_max - r_min) - abs(exp_val - r_min))
                return 0

            # 2. Upper bound: "< X", "Less than X", "Under X", "Below X" (e.g., "< 5", "Less than 5")
            less_match = re.search(r'(?:less\s+than|under|fewer\s+than|below|<|^<\s*)\s*(\d+(?:\.\d+)?)', clean_label)
            if less_match:
                bound = float(less_match.group(1))
                if exp_val < bound:
                    return max(75, 88 - (bound - exp_val))
                return 0

            # 3. Lower bound: "> X", "More than X", "Above X", "Over X", "X+" (e.g., "> 5", "5+", "4+", "> 3")
            more_match = re.search(r'(?:more\s+than|over|above|>|^\s*>\s*)\s*(\d+(?:\.\d+)?)', clean_label) or re.search(r'(\d+(?:\.\d+)?)\s*\+', clean_label)
            if more_match:
                bound = float(more_match.group(1))
                if exp_val >= bound:
                    return max(75, 91 - (exp_val - bound) * 2)
                return 0

            # 4. Single discrete number (e.g., "4", "4 years")
            single_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:years?|yrs?|months?|days?)?$', clean_label)
            if single_match:
                val = float(single_match.group(1))
                return max(0, 92 - abs(exp_val - val) * 15)

            return 0

        # Scenario 1: Options are ['<5', '5-7', '7-9', '>9'] -> '<5' must win!
        options1 = ['<5', '5-7', '7-9', '>9']
        scores1 = {opt: score_radio(opt) for opt in options1}
        self.assertGreater(scores1['<5'], 0)
        self.assertEqual(scores1['5-7'], 0)
        self.assertEqual(scores1['7-9'], 0)
        self.assertEqual(scores1['>9'], 0)
        self.assertEqual(max(scores1, key=scores1.get), '<5')

        # Scenario 2: Options are ['0-3', '3-5', '5-7', '>7'] -> '3-5' must win!
        options2 = ['0-3', '3-5', '5-7', '>7']
        scores2 = {opt: score_radio(opt) for opt in options2}
        self.assertEqual(scores2['0-3'], 0)
        self.assertGreater(scores2['3-5'], 85)
        self.assertEqual(scores2['5-7'], 0)
        self.assertEqual(scores2['>7'], 0)
        self.assertEqual(max(scores2, key=scores2.get), '3-5')

        # Scenario 3: Options are ['4+', '>5', '5-7'] -> '4+' must win!
        options3 = ['4+', '>5', '5-7']
        scores3 = {opt: score_radio(opt) for opt in options3}
        self.assertGreater(scores3['4+'], 85)
        self.assertEqual(scores3['>5'], 0)
        self.assertEqual(scores3['5-7'], 0)
        self.assertEqual(max(scores3, key=scores3.get), '4+')

        # Scenario 4: Discrete options ['3', '4', '5', '6'] -> '4' must win!
        options4 = ['3', '4', '5', '6']
        scores4 = {opt: score_radio(opt) for opt in options4}
        self.assertEqual(max(scores4, key=scores4.get), '4')

    def test_json_action_result_logging(self):
        import json
        from unittest.mock import MagicMock
        from src.sentinel.agent import SentinelAgent

        # Mock agent to test _log_question_detailed integration with structured JSON result
        agent = MagicMock(spec=SentinelAgent)
        agent._log_question_detailed = MagicMock()
        agent._detect_platform = MagicMock(return_value="naukri")
        agent._page = MagicMock()
        agent._page.url = "https://www.naukri.com/apply"

        result = 'NAUKRI_CHAT_RADIO_SAVED|{"q":"How many years of experience do you have in Java ?","a":"3-5","t":"radio","s":"3-5"}'
        
        # Test simulated parsing logic from agent.py line 2450
        parts = result.split('|', 1)
        action = parts[0]
        question_data_json = parts[1]
        question_data = json.loads(question_data_json)
        if isinstance(question_data, dict):
            question_data = [question_data]
        for q_data in question_data:
            if isinstance(q_data, dict):
                q_text = q_data.get('question', '') or q_data.get('q', '')
                a_text = q_data.get('answer', '') or q_data.get('a', '')
                t_type = q_data.get('inputType', '') or q_data.get('t', '') or 'radio'
                s_opt = q_data.get('selectedOption', '') or q_data.get('s', '') or a_text
                opts = q_data.get('options', [])
                if q_text and a_text:
                    agent._log_question_detailed({
                        'question': q_text,
                        'answer': a_text,
                        'input_type': t_type,
                        'match_phase': 'aggressive' if 'aggressive' in str(t_type) else 'pattern_match',
                        'options': opts,
                        'selected_option': s_opt,
                        'context': agent._detect_platform(),
                        'url': agent._page.url,
                        'confidence': 'form_filled'
                    })

        self.assertEqual(action, 'NAUKRI_CHAT_RADIO_SAVED')
        agent._log_question_detailed.assert_called_once()
        logged_data = agent._log_question_detailed.call_args[0][0]
        self.assertEqual(logged_data['question'], "How many years of experience do you have in Java ?")
        self.assertEqual(logged_data['answer'], "3-5")
        self.assertEqual(logged_data['input_type'], "radio")
        self.assertEqual(logged_data['selected_option'], "3-5")


    def test_company_question_matching(self):
        # 1. Company questions must match Everbridge with high confidence
        ans, score = self.matcher.fuzzy_match("Which company are you currently working at?")
        self.assertEqual(ans, "Everbridge")
        self.assertGreaterEqual(score, 0.90)

        ans2, score2 = self.matcher.fuzzy_match("Current Company?")
        self.assertEqual(ans2, "Everbridge")
        self.assertGreaterEqual(score2, 0.90)

        # 2. General employment questions must match Yes
        ans3, score3 = self.matcher.fuzzy_match("Are you currently employed?")
        self.assertEqual(ans3, "Yes")
        self.assertGreaterEqual(score3, 0.90)

        ans4, score4 = self.matcher.fuzzy_match("Are you currently working?")
        self.assertEqual(ans4, "Yes")
        self.assertGreaterEqual(score4, 0.90)

    def test_checkbox_yes_no_mutual_exclusion(self):
        # Verify that when answering Yes to a Yes/No checkbox question, only Yes is checked and No is never checked
        answer = "Yes"
        answer_lower = answer.lower()
        is_ans_yes = bool("yes" in answer_lower)
        is_ans_no = bool("no" in answer_lower) and not is_ans_yes

        checkboxes = [
            {"id": "Yes", "label": "Yes", "checked": False},
            {"id": "No", "label": "No", "checked": False}
        ]

        cb_infos = []
        for cb in checkboxes:
            lbl_lower = cb["label"].lower()
            is_lbl_yes = bool("yes" in lbl_lower or cb["id"] == "Yes")
            is_lbl_no = bool("no" in lbl_lower or cb["id"] == "No") and not is_lbl_yes
            cb_infos.append({"cb": cb, "is_lbl_yes": is_lbl_yes, "is_lbl_no": is_lbl_no})

        has_yes_no_pair = any(i["is_lbl_yes"] for i in cb_infos) and any(i["is_lbl_no"] for i in cb_infos)
        self.assertTrue(has_yes_no_pair)

        if is_ans_yes and has_yes_no_pair:
            for info in cb_infos:
                if info["is_lbl_yes"]:
                    info["cb"]["checked"] = True
                elif info["is_lbl_no"]:
                    info["cb"]["checked"] = False

        checked_ids = [c["id"] for c in checkboxes if c["checked"]]
        self.assertEqual(checked_ids, ["Yes"])
        self.assertNotIn("No", checked_ids)

    def test_options_in_qa_results_logging(self):
        import tempfile
        import csv
        from src.sentinel.agent import SentinelAgent

        with tempfile.TemporaryDirectory() as tmp_dir:
            agent = SentinelAgent()
            agent.SCREENSHOT_DIR = tmp_dir
            agent.QA_RESULTS_CSV = os.path.join(tmp_dir, "qa_results.csv")

            agent._log_qa_result(
                question="Are you available for the walk-in at the Gurugram location on 5th September?",
                answer="Yes",
                input_type="radio",
                options=["Yes", "No"],
                selected_option="Yes",
                confidence="pattern_match",
                status="submitted",
                platform="naukri"
            )

            with open(agent.QA_RESULTS_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["question"], "Are you available for the walk-in at the Gurugram location on 5th September?")
                self.assertEqual(rows[0]["answer"], "Yes")
                self.assertEqual(rows[0]["options"], "Yes, No")
                self.assertEqual(rows[0]["selected_option"], "Yes")


    def test_location_and_notice_resolution(self):
        # 1. Bangalore presence questions must answer Yes
        ans, score = self.matcher.fuzzy_match("Are you based in Bangalore?")
        self.assertEqual(ans, "Yes")
        self.assertGreaterEqual(score, 0.90)

        ans2, score2 = self.matcher.fuzzy_match("Are you located in Bangalore?")
        self.assertEqual(ans2, "Yes")
        self.assertGreaterEqual(score2, 0.90)

        ans3, score3 = self.matcher.fuzzy_match("Are you currently in Bangalore?")
        self.assertEqual(ans3, "Yes")
        self.assertGreaterEqual(score3, 0.90)

        # 2. Notice period yes/no questions must answer Yes
        ans4, score4 = self.matcher.fuzzy_match("Are you on notice period?")
        self.assertEqual(ans4, "Yes")
        self.assertGreaterEqual(score4, 0.90)

        ans5, score5 = self.matcher.fuzzy_match("Are you currently on notice period?")
        self.assertTrue(ans5.startswith("Yes"))
        self.assertGreaterEqual(score5, 0.90)

    def test_skill_intent_resolution(self):
        # Yes/No vs Numeric skill questions
        skills = ['React', 'Angular', 'Spring Boot', 'Docker', 'AWS', 'Kafka', 'Python', 'Java']
        for s in skills:
            yn_q = f"Do you have experience in {s}?"
            num_q = f"How many years of experience do you have in {s}?"
            yn_ans, _ = self.matcher.fuzzy_match(yn_q)
            num_ans, _ = self.matcher.fuzzy_match(num_q)
            self.assertEqual(yn_ans, "Yes", f"Expected Yes for '{yn_q}', got '{yn_ans}'")
            self.assertTrue("4" in num_ans or "4.2" in num_ans, f"Expected numeric years for '{num_q}', got '{num_ans}'")


if __name__ == '__main__':
    unittest.main()
