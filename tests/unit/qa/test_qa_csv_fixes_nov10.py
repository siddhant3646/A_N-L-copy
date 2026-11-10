import sys
import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher


class TestQACSVFixesNov10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = SentinelAgent()
        cls.matcher = cls.agent._pattern_matcher

    def test_multi_skill_experience_breakdown(self):
        q = "Frontend & Backend Technical Expertise Do you have strong hands-on experience with React.js, Angular, Java, Spring Boot and Hibernate? Please specify your experience across these technologies."
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.95)
        self.assertIn("React.js:", ans)
        self.assertIn("Java:", ans)
        self.assertIn("Spring Boot:", ans)
        self.assertNotIn(ans, ("4", "4.2", "4.2 Years", "Yes"))

    def test_backend_technologies_hands_on(self):
        q = "Which backend technologies have you worked with hands-on?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.95)
        self.assertNotEqual(ans, "Yes")
        self.assertTrue("Java" in ans and "Spring Boot" in ans)

    def test_preferred_location_misspelling(self):
        q = "PREFERRRED LOCATION"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.65)
        self.assertNotEqual(ans, "Karnataka")
        self.assertIn("Bangalore", ans)
        self.assertIn("Delhi", ans)

    def test_low_code_rad_description(self):
        q = "Do you have hands-on experience designing, developing or leading the development of Low-Code/No-Code platforms, RAD tools, workflow builders or visual editors? Please describe the platform and your contribution."
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.95)
        self.assertNotEqual(ans, "Yes")
        self.assertIn("Everbridge", ans)
        self.assertTrue("workflow" in ans.lower() or "json" in ans.lower())

    def test_metadata_driven_architecture(self):
        q = "Metadata-Driven / Schema-Driven Architecture Do you have practical experience designing metadata/schema-driven execution engines, JSON-based configuration contracts or dynamic configuration interpretation?"
        ans, score = self.agent._fuzzy_match_question(q)
        self.assertGreaterEqual(score, 0.95)
        self.assertNotIn(ans, ("4", "4.2", "4.2 Years", "4 Years"))
        self.assertIn("metadata-driven", ans.lower())

    def test_pattern_matcher_intent_guard(self):
        # A question with 'Do you have' and experience should never return '4.2 Years' when quantity isn't asked
        ans, score = self.matcher._resolve_question_intent(
            "Do you have practical experience in microservices development?",
            "4.2 Years",
            0.90,
            input_type="radio"
        )
        self.assertEqual(ans, "Yes")

    def test_hirist_essay_classification(self):
        # Verify the logic used in Hirist questionnaire
        essay_prompts = [
            "Do you have hands-on experience designing, developing or leading the development of Low-Code/No-Code platforms, RAD tools, workflow builders or visual editors? Please describe the platform and your contribution.",
            "Metadata-Driven / Schema-Driven Architecture Do you have practical experience designing metadata/schema-driven execution engines, JSON-based configuration contracts or dynamic configuration interpretation?",
            "Frontend & Backend Technical Expertise Do you have strong hands-on experience with React.js, Angular, Java, Spring Boot and Hibernate? Please specify your experience across these technologies.",
        ]
        standard_prompts = [
            "What is your current CTC in Lacs per annum?",
            "What is your expected CTC in Lacs per annum?",
            "What is your notice period?",
            "How many years of experience do you have in Java?",
        ]

        def classify(qtext):
            q_lower = qtext.lower()
            is_essay_keyword = any(k in q_lower for k in [
                'explain', 'describe', 'why should', 'why do you', 'architecture',
                'system design', 'cover letter', 'project details', 'challenging problem',
                'walk us through', 'tell us about', 'details of your', 'write a brief',
                'specify your experience across', 'specify the tool', 'what was your contribution',
                'your contribution', 'how did you', 'how would you'
            ])
            is_standard_profile = not is_essay_keyword and any(k in q_lower for k in [
                'current ctc', 'expected ctc', 'in lacs', 'lpa', 'fixed ctc', 'variable ctc',
                'notice period', 'lwd', 'last working day', 'last working date',
                'how many years', 'years of experience', 'total experience', 'total exp',
                'current company', 'current organization', 'highest qualification',
                'current location', 'preferred location'
            ])
            is_essay = (is_essay_keyword or (not is_standard_profile and any(k in q_lower for k in [
                'design', 'project', 'implement', 'approach', 'solution'
            ])))
            return is_essay, is_standard_profile

        for ep in essay_prompts:
            is_essay, is_std = classify(ep)
            self.assertTrue(is_essay, f"Expected {ep[:40]} to be classified as essay")
            self.assertFalse(is_std, f"Expected {ep[:40]} not to be standard profile")

        for sp in standard_prompts:
            is_essay, is_std = classify(sp)
            self.assertFalse(is_essay, f"Expected {sp[:40]} not to be essay")
            self.assertTrue(is_std, f"Expected {sp[:40]} to be standard profile")


if __name__ == '__main__':
    unittest.main()
