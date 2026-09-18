"""Unit tests for September 18 QA CSV audit fixes and enhancements.

Covers:
1. DSA experience queries returning experience ('4.2 Years' / '4') rather than rating score ('9').
2. Full time work experience questions returning 'Yes' rather than 'Full-time'.
3. Work authorization in country of job returning 'Yes' rather than country name 'India'.
4. Work mode multi-choice returning 'Hybrid' rather than Notice Period '15'.
5. Production security controls (IAM, encryption, audit logging) returning security answers rather than monitoring.
6. Tools proficiency returning tools stack rather than portfolio URL.
7. Interview time slot requests returning available time window ('Anytime between 10 AM - 4 PM').
8. Capital markets / trading domain experience returning 'Yes'.
9. Fingerprint integrity: Phone number fingerprint does not collide with contact/email.
10. INR CTC format validation accepting raw INR values without failing LPA range.
"""

import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVAuditFixesSept18(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.pattern_matcher = PatternMatcher(cls.patterns)
        cls.agent = SentinelAgent()

    def test_dsa_experience_vs_rating(self):
        # Experience question should return candidate YOE, not rating scale 9
        exp_q = "How many years of experience do you have in Data structure & Algorithms?"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(exp_q)
        self.assertIn("4", ans)
        self.assertNotEqual(ans, "9")

        # Pure rating question should return rating digit (e.g. 5 or 9)
        rating_q = "Rate your proficiency in Data Structures and Algorithms on a scale of 1-10"
        ans_rate, conf_rate = self.agent._fuzzy_match_question(rating_q)
        self.assertTrue(ans_rate in ("5", "8", "9", "10") or ans_rate.isdigit())

    def test_full_time_experience_yes_no(self):
        q = "Do you have minimum 6 years of full time work experience in Full Stack Development ?"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes")

    def test_work_authorization_permitted(self):
        q = "Are you legally permitted to work in the country where the job is located?"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Yes")

    def test_work_mode_multi_choice(self):
        q = "Current work mode 1.Remote 2.Onsite 3.Hybrid 4.Not working 5.Serving Np ?"
        self.agent._current_platform = "linkedin"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "Hybrid")
        self.assertNotEqual(ans, "15")

    def test_production_security_controls(self):
        q = "Have you handled production security controls such as IAM, secrets, encryption, network security or audit logging?"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("IAM", ans)
        self.assertNotIn("Prometheus", ans)

    def test_tools_platforms_proficiency(self):
        q = "Which tools, platforms, or technologies are you proficient in? (e.g., Jira, GitHub, MS Project, AI tools, etc.)"
        self.agent._current_platform = "linkedin"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("Git", ans)
        self.assertNotIn("Portfolio", ans)

    def test_interview_time_slot(self):
        q = "Please give us a time slot for interview on Saturday, 19 Aug in between 9am-4pm"
        self.agent._current_platform = "naukri"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertIn("10 AM", ans)

    def test_capital_markets_domain(self):
        q1 = "Do u have experience in Trading or Capital market domain?"
        q2 = "Any exp in Capital markets?"
        self.agent._current_platform = "naukri"
        ans1, _ = self.agent._fuzzy_match_question(q1)
        ans2, _ = self.agent._fuzzy_match_question(q2)
        self.assertEqual(ans1, "Yes")
        self.assertEqual(ans2, "Yes")

    def test_phone_fingerprint_integrity(self):
        q = "Phone"
        self.agent._current_platform = "linkedin"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "7905828880")

    def test_inr_ctc_validation(self):
        q = "Please enter your current ctc in INR"
        self.agent._current_platform = "linkedin"
        ans, conf = self.agent._fuzzy_match_question(q)
        self.assertEqual(ans, "2300000")


if __name__ == "__main__":
    unittest.main()
