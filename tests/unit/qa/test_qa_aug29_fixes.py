import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.patterns.pattern_matcher import create_matcher


class TestQAAug29Fixes(unittest.TestCase):
    def setUp(self):
        self.matcher = create_matcher()

    # 1. Company Motivation Essay - Dodo Payments (Not Salary 2300000)
    def test_why_join_company_motivation_essay(self):
        questions = [
            'Why do you want to be a part of Dodo Payments?',
            'Why do you want to be a part of Payments Platform?',
            'Why do you want to join our company?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match '{q}'")
            ans = res.get('answer', '')
            self.assertIn('excited', ans.lower())
            self.assertNotIn('2300000', ans)
            self.assertNotIn('3000000', ans)

    # 2. Future Contact & Privacy Policy Consent (Returns Yes, not 4)
    def test_future_contact_consent_returns_yes(self):
        questions = [
            'I am allowing ValGenesis to contact me about future job opportunities for up to 2 years. Privacy Policy Required',
            'I am allowing ValGenesis to contact me about future job opportunities for up to 2 years.',
            'Contact me about future job opportunities for up to 2 years',
            'Allow us to contact you for future opportunities'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match '{q}'")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'Yes')
            self.assertNotEqual(ans, '4')
            self.assertNotEqual(ans, '5')

    # 3. Cooling Period Rejection Safeguard (Returns No)
    def test_cooling_period_returns_no(self):
        questions = [
            'Have you applied to any of the roles with Mphasis in the past 6 months?',
            'Have you applied to any roles with Mphasis in the past 6 months?',
            'Have you applied in the past 6 months?',
            'Have you interviewed in the last 6 months?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match '{q}'")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'No')
            self.assertNotEqual(ans, 'Yes')

    # 4. Technical Lead / Architect Role Description (Not Bare 4.2)
    def test_technical_lead_architect_summary(self):
        questions = [
            'Have you worked as a Technical Lead / Architect?',
            'Have you worked as a Technical Lead',
            'Have you worked as an Architect'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match '{q}'")
            ans = res.get('answer', '')
            self.assertIn('microservices', ans.lower())
            self.assertNotEqual(ans, '4.2')

    # 5. Kafka / Confluent Production Summary (Not Bare 4)
    def test_kafka_confluent_production_summary(self):
        questions = [
            'Have you worked with Kafka/Confluent in a production environment?',
            'Have you worked with Kafka in a production environment?',
            'Have you worked with Kafka/Confluent'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match '{q}'")
            ans = res.get('answer', '')
            self.assertIn('kafka', ans.lower())
            self.assertNotEqual(ans, '4')


if __name__ == '__main__':
    unittest.main()
