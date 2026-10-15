import os
import sys
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestCheckmateLinkedInQAPatterns(unittest.TestCase):
    """
    Tests for LinkedIn Easy Apply Q&A patterns identified from Checkmate application screenshots:
    1. Headline -> "Software Engineer 2 (SDE-2) | Java, Spring Boot, React, Node.js, AWS"
    2. Summary -> "Software Engineer 2 (SDE-2) at Everbridge with 4.2 years of experience specializing in high-throughput distributed backend systems, Spring Boot, Java, React, Kafka, Redis, and AWS."
    3. Desired salary range -> "28-32 LPA"
    4. Background check -> "Yes"
    5. 100% remote position -> "Yes"
    6. US time zones (for outside US candidates) -> "Yes"
    7. US legal work authorization (outside US roles) -> "Not Applicable"
    8. US visa sponsorship (roles posted in US) -> "Not applicable"
    9. Bring your own device (BYOD) -> "Yes"
    10. Referral check ("Are you a referral?") -> "No"
    11. Source channel ("How did you hear about us?") -> "LinkedIn"
    12. Official notice period / peroid -> "Less than 30 days"
    """

    def setUp(self):
        self.agent = SentinelAgent()

    def test_headline(self):
        questions = [
            "Headline",
            "headline",
            "profile headline",
            "LinkedIn Headline",
            "Headline*"
        ]
        expected = "Software Engineer 2 (SDE-2) | Java, Spring Boot, React, Node.js, AWS"
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, expected, f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_summary(self):
        questions = [
            "Summary",
            "summary",
            "profile summary",
            "Professional Summary",
            "Summary*"
        ]
        expected = "Software Engineer 2 (SDE-2) at Everbridge with 4.2 years of experience specializing in high-throughput distributed backend systems, Spring Boot, Java, React, Kafka, Redis, and AWS."
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, expected, f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_desired_salary_range(self):
        questions = [
            "What is your desired salary range?*",
            "What is your desired salary range?",
            "desired salary range",
            "expected salary range",
            "What is your expected salary range?*"
        ]
        expected = "28-32 LPA"
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, expected, f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_background_check(self):
        questions = [
            "Are you willing to undergo a background check, in accordance with local law/regulations?*",
            "Are you willing to undergo a background check?",
            "willing to undergo background check in accordance with local law"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_remote_comfort(self):
        questions = [
            "Are you comfortable working in a 100% remote position?*",
            "Are you comfortable working in a 100% remote position?",
            "comfortable working in a 100% remote position",
            "comfortable working in a remote position",
            "fully remote position"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_us_time_zones(self):
        questions = [
            "Are you able to work in US time zones?(For candidates outside the US only)*",
            "Are you able to work in US time zones?",
            "able to work in US time zones",
            "willing to work in us time zones"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_us_work_authorization(self):
        questions = [
            "Are you legally authorized to work in the United States? (Only for US based positions)*",
            "Are you legally authorized to work in the United States?",
            "authorized to work in the united states",
            "legally authorized to work in the u.s."
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Not Applicable", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_us_visa_sponsorship(self):
        questions = [
            "Will you now, or in the future, require sponsorship for employment visa status (e.g. H-1B visa status)? (Applicable to roles posted in the US only)*",
            "require sponsorship for employment visa status (e.g. H-1B visa status)",
            "require sponsorship for employment visa status in the us"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Not applicable", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_byod(self):
        questions = [
            "Are you comfortable working in a bring your own device atmosphere?*",
            "Are you comfortable working in a bring your own device atmosphere?",
            "bring your own device",
            "byod atmosphere"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "Yes", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_referral_check(self):
        questions = [
            "Are you a referral?*",
            "Are you a referral?",
            "are you an internal referral",
            "is this a referral"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "No", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_how_did_you_hear_about_us(self):
        questions = [
            "How did you hear about us?*",
            "How did you hear about us?",
            "how did you hear about this opportunity",
            "where did you hear about us"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "LinkedIn", f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_official_notice_period_and_peroid(self):
        questions = [
            "What is your official notice peroid?*",
            "What is your official notice peroid?",
            "What is your official notice period?*",
            "What is your official notice period?",
            "official notice peroid",
            "official notice period"
        ]
        expected = "Less than 30 days"
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, expected, f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")


if __name__ == '__main__':
    unittest.main()
