import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sentinel.agent import SentinelAgent

class TestQAUpdates(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_onsite_availability(self):
        questions = [
            "Are you available to work Full-Time on-site*",
            "Are you available to work Full-Time on-site",
            "available for full-time on-site work"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn('Yes', ans, f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_experience_years(self):
        questions = [
            "How Many Years of work experience do you have in your chosen engineering field*",
            "years of work experience in chosen engineering field"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn(ans, ['4', '4'], f"Failed for question: {q}") 
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_area_of_experience(self):
        questions = [
            "What area have you most experience in?*",
            "What area have you most experience in"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Full-stack', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_leetcode_questions(self):
        questions = [
            "How many questions you have solved in Leetcode?*",
            "Number of Leetcode problems solved"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, '500+', f"Failed for question: {q}")
    def test_commuting_availability(self):
        questions = [
            "Are you comfortable commuting to this job's location?*",
            "Are you comfortable commuting to this job's location",
            "comfortable commuting to this job"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Yes', f"Failed for question: {q}")
            self.assertGreater(score, 0.7, f"Low confidence for question: {q}")

    def test_ex_amazon_candidate(self):
        questions = [
            "Are you an Ex- Amazon candidate?*",
            "Are you an Ex-Amazon candidate?",
            "ex-amazon candidate"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'No', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_join_immediately_serving_np(self):
        questions = [
            "Can you Join Immediately or Currently Serving NP?*",
            "Can you Join Immediately or Currently Serving NP?",
            "can you join immediately or currently serving np"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Yes', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_based_in_mumbai_or_pune(self):
        questions = [
            "Are you Currently based in Mumbai or Pune*",
            "Are you Currently based in Mumbai or Pune",
            "currently based in mumbai or pune"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIn('Noida', ans, f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_azure_experience(self):
        questions = [
            "Do you have azure cloud experience? if yes how many years?",
            "azure cloud experience",
            "years of experience in azure"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, '2', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_gcp_experience(self):
        questions = [
            "how many years of experience do you have in gcp",
            "google cloud experience",
            "gcp experience"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, '1', f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")


if __name__ == '__main__':
    unittest.main()
