"""Unit tests for QA patterns and logic fixes from qa_results.csv audit."""

import os
import unittest
from unittest.mock import MagicMock

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.sentinel.question_fingerprint import FingerprintMatcher
from src.sentinel.question_classifier import QuestionClassifier


class TestQACSVAuditFixesSept21P2(unittest.TestCase):
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
        cls.agent._fingerprint_matcher.build_from_patterns(cls.patterns_data.get("patterns", {}))
        cls.agent._pattern_learner = None
        cls.agent._self_healing = MagicMock()
        cls.agent._self_healing.get_learned_answer.return_value = None
        cls.agent._question_classifier = QuestionClassifier(platform="linkedin")
        cls.agent.logger = None

    def test_city_fingerprint_and_exact_match(self):
        """Verify 'City' returns city name ('Bengaluru') and does not get overwritten by yes/no questions."""
        ans, conf = self.agent._fuzzy_match_question("City")
        self.assertIn("bengaluru", ans.lower())
        self.assertGreaterEqual(conf, 0.90)

        ans, conf = self.agent._fuzzy_match_question("Current City")
        self.assertTrue("bengaluru" in ans.lower() or "bangalore" in ans.lower())
        self.assertGreaterEqual(conf, 0.90)

    def test_location_confirmation_questions(self):
        """Verify location confirmation questions distinguish candidate's city (Bangalore) from other cities."""
        no_questions = [
            "Your Current Location is Chennai?",
            "Your Current Location is Hyderabad?",
            "Your Current Location is Pune?",
            "Your Current Location is Mumbai?",
            "Is your current location Chennai?",
            "Current location is Chennai",
            "Current location is Hyderabad",
        ]
        for q in no_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Failed for question: {q} (got {ans})")
            self.assertGreaterEqual(conf, 0.90)

        yes_questions = [
            "Your Current Location is Bangalore?",
            "Your Current Location is Bengaluru?",
            "Is your current location Bangalore?",
            "Is your current location Bengaluru?",
            "Current location is Bangalore",
            "Current location is Bengaluru",
        ]
        for q in yes_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q} (got {ans})")
            self.assertGreaterEqual(conf, 0.90)

    def test_notice_period_in_months(self):
        """Verify questions asking for notice in months return '0.5' (15 days)."""
        month_questions = [
            "Notice periods in months",
            "Notice periods (in months)",
            "Notice in months",
            "Notice period in months",
            "Notice period (in months)",
            "Notice in month",
        ]
        for q in month_questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIn("0.5", ans, f"Failed for question: {q} (got {ans})")
            self.assertGreaterEqual(conf, 0.90)

    def test_ex_employer_and_applied_before(self):
        """Verify ex-employer ID and previous application questions return compliant 'No' / 'No, this is my first application'."""
        q1 = "Have you applied to Termgrid for a role before?"
        ans, conf = self.agent._fuzzy_match_question(q1)
        self.assertTrue(
            "No" in ans and "first application" in ans,
            f"Expected first application statement, got: {ans}",
        )
        self.assertGreaterEqual(conf, 0.90)

        q2 = "Have you previously worked in infosys?(If yes provide ex-infy id)"
        ans, conf = self.agent._fuzzy_match_question(q2)
        self.assertIn(ans, ["NA", "No"], f"Failed for question: {q2} (got {ans})")
        self.assertGreaterEqual(conf, 0.90)

    def test_backend_and_aws_skills(self):
        """Verify technical skill questions resolve to valid affirmative/technical answers."""
        q1 = "Do you have hands-on experience developing REST APIs?"
        ans, conf = self.agent._fuzzy_match_question(q1)
        self.assertTrue(
            "Yes" in ans or "REST" in ans or "Spring Boot" in ans,
            f"Failed for {q1}, got: {ans}",
        )

        q2 = "Do you have expertise in at least one major backend stack (e.g. Node.js, Python, Java, Go, or Rust)?"
        ans, conf = self.agent._fuzzy_match_question(q2)
        self.assertTrue(
            "Yes" in ans or "Java" in ans or "Spring Boot" in ans,
            f"Failed for {q2}, got: {ans}",
        )

        q3 = "Experience with a product-based company?"
        ans, conf = self.agent._fuzzy_match_question(q3)
        self.assertTrue(
            "Yes" in ans or "Everbridge" in ans,
            f"Failed for {q3}, got: {ans}",
        )

        q4 = "Which AWS services do you have hands-on experience with?"
        ans, conf = self.agent._fuzzy_match_question(q4)
        self.assertTrue(
            "EC2" in ans or "S3" in ans or "Lambda" in ans,
            f"Failed for {q4}, got: {ans}",
        )

    def test_fingerprint_matcher_collision_resolution(self):
        """Verify FingerprintMatcher resolves exact matches and handles priority/length collisions."""
        matcher = FingerprintMatcher()
        matcher.add_pattern("City", "Bengaluru", priority=10, category="location")
        matcher.add_pattern("Are you from this city", "Yes", priority=10, category="location")

        res_city = matcher.match("City")
        self.assertIsNotNone(res_city)
        self.assertEqual(res_city[0], "Bengaluru")

        res_yn = matcher.match("Are you from this city")
        self.assertIsNotNone(res_yn)
        self.assertEqual(res_yn[0], "Yes")


if __name__ == "__main__":
    unittest.main()
