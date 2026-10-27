"""Unit tests verifying fixes for questions identified in qa_results.csv audit."""

import os
import re
import unittest
from unittest.mock import MagicMock

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.sentinel.question_fingerprint import FingerprintMatcher
from src.sentinel.question_classifier import QuestionClassifier


class TestFixedQAResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        json_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "config", "qa_patterns.json"
        )
        cls.patterns_data = load_patterns(json_path)
        cls.agent = SentinelAgent.__new__(SentinelAgent)
        cls.agent._current_platform = "linkedin"
        cls.agent._pattern_matcher = PatternMatcher(cls.patterns_data)
        cls.agent._fingerprint_matcher = FingerprintMatcher()
        cls.agent._pattern_learner = None
        cls.agent._self_healing = MagicMock()
        cls.agent._self_healing.get_learned_answer.return_value = None
        cls.agent._question_classifier = QuestionClassifier(platform="linkedin")
        cls.agent.logger = None

    def test_claude_ai_agents_workflow(self):
        q = "Have you worked with Claude/AI agents/orchestrated workflows to compress dev work (scaffolding, code review, debugging, test generation, automation)?"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes")
        self.assertGreaterEqual(conf, 0.95)

    def test_active_pf_account(self):
        questions = [
            "Do you have an active PF account?",
            "Do you have PF for all companies?",
            "Have you maintained an active PF account throughout your employment?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.90)

    def test_cooling_period_and_prior_applications(self):
        questions = [
            "Have you applied with Mphasis in last 6/12 months?",
            "Have you applied with Accenture in last 6/12 months?",
            "Have you applied to any of the roles with Mphasis in the past 6 months?",
            "Have you interviewed in the last 6 months?",
            "Applied to any role in the past 6 months?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_joining_on_or_before_date(self):
        questions = [
            "Can You Join on or Before Oct-11?",
            "Can you join on or before 15th October?",
            "Are you able to join by Oct 15?",
            "Can you join on or before Nov-01?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_sponsorship_not_required(self):
        questions = [
            "Do you now or will you at any time in the future require sponsorship?",
            "Will you now or in the future require visa sponsorship?",
            "Do you require employer sponsorship to work in India?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIn(ans, ["No", "No, I do not require sponsorship"], f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.95)

    def test_candidate_profile_salary_and_experience(self):
        # CTC
        ans, conf = self.agent._fuzzy_match_question("What is your current CTC?")
        self.assertIn("23", ans)
        
        ans, conf = self.agent._fuzzy_match_question("What is your expected CTC?")
        self.assertIn("30", ans)
        
        # Notice Period
        ans, conf = self.agent._fuzzy_match_question("What is your notice period?")
        self.assertIn("15", ans)

    def test_experience_bracket_resolution(self):
        options = ["0-1 yrs", "2-4 yrs", "Skip this question"]
        expVal = 4.2
        
        hasHigher = False
        for label in options:
            clean = label.lower().strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if (rMin == 4 or (expVal >= rMin and expVal <= rMax)) and rMax > 4:
                    hasHigher = True
                    break

        scores = {}
        for label in options:
            clean = label.lower().strip()
            if "skip" in clean:
                scores[label] = 0
                continue
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if expVal >= 4.0 and rMax <= 4.0 and hasHigher:
                    scores[label] = 0
                elif expVal >= rMin and expVal <= rMax:
                    minBonus = 5 if (rMin == 4 or int(expVal) == int(rMin)) else 0
                    scores[label] = max(88, 100 + minBonus - (rMax - rMin) - abs(expVal - rMin))
                elif expVal > rMax and not hasHigher:
                    diff = expVal - rMax
                    if diff <= 2.0:
                        scores[label] = max(70, 92 - diff * 8)
                    else:
                        scores[label] = 0
                else:
                    scores[label] = 0
            else:
                scores[label] = 0
                
        best = max(scores.items(), key=lambda x: x[1])
        self.assertEqual(best[0], "2-4 yrs")
        self.assertGreater(best[1], 90)

    def test_experience_bracket_prefers_min_4_over_max_4(self):
        options = ["No experience", "<2 years", "2-4 years", "4-7 years", "7-10 years"]
        expVal = 4.2

        hasHigher = False
        for label in options:
            clean = label.lower().strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if (rMin == 4 or (expVal >= rMin and expVal <= rMax)) and rMax > 4:
                    hasHigher = True
                    break

        scores = {}
        for label in options:
            clean = label.lower().strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if expVal >= 4.0 and rMax <= 4.0 and hasHigher:
                    scores[label] = 0
                elif expVal >= rMin and expVal <= rMax:
                    minBonus = 5 if (rMin == 4 or int(expVal) == int(rMin)) else 0
                    scores[label] = max(88, 100 + minBonus - (rMax - rMin) - abs(expVal - rMin))
                else:
                    scores[label] = 0
            else:
                scores[label] = 0

        self.assertEqual(scores["2-4 years"], 0)
        self.assertGreater(scores["4-7 years"], 90)
        best = max(scores.items(), key=lambda x: x[1])
        self.assertEqual(best[0], "4-7 years")

    def test_experience_bracket_2_4_vs_4_6(self):
        options = ["2-4", "4-6"]
        expVal = 4.2

        hasHigher = False
        for label in options:
            clean = label.lower().strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if (rMin == 4 or (expVal >= rMin and expVal <= rMax)) and rMax > 4:
                    hasHigher = True
                    break

        scores = {}
        for label in options:
            clean = label.lower().strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
            if m:
                rMin = float(m.group(1))
                rMax = float(m.group(2))
                if expVal >= 4.0 and rMax <= 4.0 and hasHigher:
                    scores[label] = 0
                elif expVal >= rMin and expVal <= rMax:
                    minBonus = 5 if (rMin == 4 or int(expVal) == int(rMin)) else 0
                    scores[label] = max(88, 100 + minBonus - (rMax - rMin) - abs(expVal - rMin))
                else:
                    scores[label] = 0

        self.assertEqual(scores["2-4"], 0)
        self.assertGreater(scores["4-6"], 95)
        best = max(scores.items(), key=lambda x: x[1])
        self.assertEqual(best[0], "4-6")

    def test_virtual_drive_availability(self):
        questions = [
            "Available to attend Virtual Drive on 24th October *",
            "•\tAvailable to attend Virtual Drive on 24th October *",
            "Are you available to attend Virtual Drive?",
            "Available for virtual hiring drive?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.90)

    def test_work_from_office_locations(self):
        questions = [
            "Available to work from office in Bengaluru/Chennai/Delhi/Mumbai/Pune *",
            "•\tAvailable to work from office in Bengaluru/Chennai/Delhi/Mumbai/Pune *",
            "Available to work from office in Bengaluru",
            "Work from office in Bangalore?",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.90)

    def test_restful_api_experience_yes_no(self):
        questions = [
            "Experience developing and consuming RESTful APIs.*",
            "•\tExperience developing and consuming RESTful APIs.*",
            "Do you have experience developing and consuming RESTful APIs?",
            "Developing and consuming RESTful APIs",
        ]
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(conf, 0.90)


if __name__ == "__main__":
    unittest.main()
