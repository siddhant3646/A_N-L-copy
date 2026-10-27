import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.sentinel.agent import SentinelAgent

class TestQAUpdates(unittest.TestCase):
    """QA pattern matching tests.

    Note: Tests use assertGreater(score, 0.8) which exceeds
    PatternMatcher.DEFAULT_THRESHOLD (0.65). They pass because PHASE 1
    hardcoded interceptions in agent.py return 0.90-0.98 confidence.
    See IMPLEMENTATION_SUMMARY.md 'Two-Tier Matching Architecture' for details.
    """
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
            self.assertIn(ans, ['4.2', '4.2'], f"Failed for question: {q}") 
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
            self.assertIn('Bangalore', ans, f"Failed for question: {q}")
            self.assertGreater(score, 0.8, f"Low confidence for question: {q}")

    def test_career_break(self):
        questions = [
            "Are you on a career break?*",
            "Are you on a career break?",
            "Are you currently on a career break?",
            "Do you have a gap in employment?",
            "Do you have any break in career?",
            "career break",
            "break in career",
            "gap in employment",
            "period of unemployment"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'No', f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_career_break_reason(self):
        questions = [
            "What is the reason for the break?*",
            "What is the reason for the break?",
            "What is the reason for the career break?",
            "What is the reason for the career gap?",
            "What is the reason for the employment gap?",
            "reason for break",
            "reason for career break",
            "reason for career gap",
            "reason for employment gap",
            "reason for gap in career",
            "reason for gap in employment",
            "why did you take a break"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'Personal', f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_military_service_patterns_agent(self):
        questions = [
            "Have you ever served in the military?",
            "Have you ever served in the military",
            "Have you served in the military?",
            "Are you currently serving in the military?",
            "Served in the armed forces",
            "Have you ever served in the armed forces?"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertEqual(ans, 'No', f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95, f"Low confidence for question: {q}")

    def test_ai_tools_and_genai_experience(self):
        # 1. AI tools Yes/No usage questions must return "Yes"
        yn_questions = [
            "Have you used AI-assisted development tools (GitHub Copilot, Cursor, Gemini Code Assist, Claude, ChatGPT, etc.) for software development?",
            "Do you have hands-on experience setting up and managing CI/CD pipelines?",
            "Do you use AI coding assistants like Claude or ChatGPT?",
            "Have you worked with AI agents or orchestrated workflows?"
        ]
        for q in yn_questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes', f"Failed for question: {q}")
            self.assertGreaterEqual(score, 0.95)

        # 2. GenAI experience duration / quantity questions must NEVER return "Yes"
        qty_questions = [
            "How many years of experience do you have in Generative AI (in Years)?",
            "years of experience in generative ai",
            "how many years of experience do you have in generative ai",
            "how many years of experience do you have in generative ai in years",
            "generative ai experience (in years)"
        ]
        for q in qty_questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertNotEqual(ans, 'Yes', f"Quantity question should not return 'Yes': {q}")
            self.assertTrue(any(ch.isdigit() for ch in str(ans)), f"Expected numeric experience: {ans}")
            self.assertGreaterEqual(score, 0.90)

    def test_recent_ai_feature_production(self):
        questions = [
            "What s the most recent AI feature/system you shipped to production?",
            "What is the most recent AI feature/system you shipped to production?",
            "What's the most recent AI feature/system you shipped to production?",
            "most recent AI feature shipped to production",
            "recent AI feature shipped to production",
            "ai feature/system you shipped to production"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIsNotNone(ans, f"Failed for question: {q}")
            self.assertTrue(
                any(term in ans.lower() for term in ["document intelligence", "gpt-4", "nlp", "ai-powered"]),
                f"Unexpected answer: {ans}"
            )
            self.assertGreaterEqual(score, 0.95, f"Low confidence for: {q}")

    def test_agentic_ai_solution_essay(self):
        questions = [
            "Can you explain an agentic AI solution you implemented and your contribution?",
            "Describe an AI agent use case and your contribution",
            "Please explain your agentic AI project and use case",
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIsNotNone(ans, f"Failed for question: {q}")
            self.assertTrue(
                "agentic ai" in ans.lower() or "langchain" in ans.lower(),
                f"Unexpected answer: {ans}"
            )
            self.assertGreaterEqual(score, 0.95, f"Low confidence for: {q}")

    def test_naukri_experience_range_option_matching(self):
        from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType
        resolver = InputAwareResolver()
        options = [
            Option("1", "No experience"),
            Option("2", "<3 years"),
            Option("3", "3-6 years"),
            Option("4", "6-10 years"),
            Option("5", ">10 years")
        ]
        res = resolver.resolve(
            answer="4.2",
            input_type=InputType.RADIO,
            options=options,
            question="How many years of experience do you have in \"Java\" ?"
        )
        self.assertIsNotNone(res.matched_option)
        self.assertEqual(res.matched_option.label, "3-6 years")
        self.assertGreaterEqual(res.confidence, 0.9)

        # Another range test with different splits
        options2 = [
            Option("1", "0 years"),
            Option("2", "1-3 years"),
            Option("3", "4-7 years"),
            Option("4", "8+ years")
        ]
        res2 = resolver.resolve(
            answer="4.2",
            input_type=InputType.RADIO,
            options=options2,
            question="How many years of experience do you have as Java Full Stack Developer?"
        )
        self.assertIsNotNone(res2.matched_option)
        self.assertEqual(res2.matched_option.label, "4-7 years")

    def test_linkedin_agentic_essay_regex(self):
        # Verify the regex used for isAgenticEssayQ in agent.py handleLinkedInForm
        regex_ai = r'(agentic\s*ai|ai\s*agent)'
        regex_essay = r'(explain|use\s*case|contribution|describe)'
        import re
        sample_questions = [
            "Please explain an agentic AI solution you worked on",
            "Describe an AI agent use case you developed and your contribution",
            "Can you describe your agentic AI architecture?"
        ]
        for q in sample_questions:
            self.assertTrue(re.search(regex_ai, q, re.I), f"Failed AI match for: {q}")
            self.assertTrue(re.search(regex_essay, q, re.I), f"Failed essay match for: {q}")

    def test_ai_technologies_worked_with(self):
        questions = [
            "Which of the following AI technologies, tools, or concepts have you worked with? (Select all that apply)*",
            "Which of the following AI technologies, tools, or concepts have you worked with?",
            "Which of the following AI tools have you worked with",
            "Which of the following AI concepts have you worked with",
            "ai technologies, tools, or concepts have you worked with"
        ]
        for q in questions:
            ans, score = self.agent._fuzzy_match_question(q)
            print(f"Q: '{q}' -> A: '{ans}' (Score: {score})")
            self.assertIsNotNone(ans)
            self.assertIn("Open AI", ans)
            self.assertIn("Claude", ans)
            self.assertIn("Retrieval-Augmented Generation (RAG)", ans)
            self.assertGreater(score, 0.8)

    def test_linkedin_ai_tech_regex(self):
        import re
        regex = r'(which of the following )?ai (technologies|tools|concepts)'
        sample_questions = [
            "Which of the following AI technologies, tools, or concepts have you worked with? (Select all that apply)*",
            "Which of the following AI tools have you worked with?",
            "AI technologies, tools, or concepts have you worked with"
        ]
        for q in sample_questions:
            self.assertTrue(re.search(regex, q, re.I), f"Failed AI tech match for: {q}")
            self.assertTrue(re.search(r'worked with', q, re.I), f"Failed worked with match for: {q}")

class TestNewPatternsReliability(unittest.TestCase):
    """Tests for the 2026-08-04 pattern additions.

    Uses PatternMatcher directly (like test_known_qa_reliability.py) since
    these patterns are verified at the JSON pattern layer (0.98 confidence).
    """
    def setUp(self):
        from src.patterns.pattern_matcher import create_matcher
        self.matcher = create_matcher()

    def check(self, question, expected, hint=None):
        ans, score = self.matcher.fuzzy_match(question)
        print(f"Q: '{question}' -> A: '{ans}' (Score: {score})")
        self.assertIsNotNone(ans, f"No match for question: {question}")
        self.assertIn(expected.lower(), str(ans).lower(), f"Failed for question: {question}" + (f" ({hint})" if hint else ""))
        self.assertGreater(score, 0.8, f"Low confidence for question: {question}")

    def test_bare_email(self):
        for q in ["Email", "Email*", "Your Email Address"]:
            self.check(q, "siddhant3646@gmail.com")

    def test_pf_history(self):
        for q in [
            "Do you have PF for all companies which you have worked?",
            "Do you have PF for all companies which you have worked?*",
            "Do you have provident fund for all companies?",
        ]:
            self.check(q, "Yes")

    def test_policy_opcodes(self):
        for q in ["Have you developed Policy Opcodes? (Yes/No)", "Have you developed Policy Opcodes?"]:
            self.check(q, "Yes")

    def test_fresher_check(self):
        for q in ["Are you a fresher?", "Are you a fresher or experienced professional?", "Fresher"]:
            self.check(q, "No")

    def test_has_work_experience(self):
        for q in ["Do you have any work experience?", "Do you have any prior work experience?"]:
            self.check(q, "Yes")

    def test_relatives_at_company(self):
        for q in ["Do you have any relatives working in our company?", "Do you have any family member working with us?"]:
            self.check(q, "No")

    def test_ex_employee_check(self):
        for q in [
            "Have you ever worked for our company?",
            "Have you previously worked for our company?",
            "Have you ever worked for?",
            "as an employee, intern, or contractor",
            "as an employee, intern, or contractor?",
            "(as an employee, intern, or contractor)",
            "have you ever worked for (as an employee, intern, or contractor)",
            "Have you ever worked for as an employee, intern, or contractor?",
        ]:
            self.check(q, "No")

    def test_azure_experience(self):
        for q in [
            "Do you have azure cloud experience? if yes how many years?",
            "azure cloud experience",
            "years of experience in azure",
        ]:
            self.check(q, "4")

    def test_gcp_experience(self):
        for q in [
            "how many years of experience do you have in gcp",
            "google cloud experience",
            "gcp experience",
        ]:
            self.check(q, "4")

    def test_laid_off_check(self):
        for q in ["Have you ever been laid off?", "Have you ever been terminated from a job?"]:
            self.check(q, "No")

    def test_noc_relieving_letter(self):
        for q in ["Can you provide NOC from current employer?", "Can you provide a relieving letter?", "experience letter available"]:
            self.check(q, "Yes")

    def test_laptop_availability(self):
        for q in ["Do you have your own laptop?", "Do you have a laptop and internet connection?"]:
            self.check(q, "Yes")

    def test_expected_hike_percent(self):
        for q in ["What is your expected hike percentage?", "Expected hike %", "What salary hike are you expecting?"]:
            self.check(q, "30")

    def test_salary_slips(self):
        for q in ["Can you provide salary slips?", "Please provide your payslip", "Can you provide form 16?"]:
            self.check(q, "Yes")

    def test_db_experience(self):
        for q in [
            "How many years of experience do you have with PostgreSQL?",
            "years of experience with mongodb",
            "years of experience with mysql",
            "sonarqube experience",
            "memcached experience",
        ]:
            self.check(q, "4")

    def test_distributed_system_concepts(self):
        for q in [
            "Do you have experience with circuit breaker patterns?",
            "Have you implemented idempotency in your APIs?",
            "Do you have load testing experience?",
            "Have you implemented rate limiting?",
        ]:
            self.check(q, "Yes")

    def test_redux_state_management(self):
        for q in ["Do you use Redux for state management?", "Do you use Redux Toolkit?", "Which state management library do you use?"]:
            self.check(q, "Yes")

    def test_oauth_jwt_sso(self):
        for q in ["Have you implemented OAuth 2.0 or JWT based auth?", "Do you have single sign on experience?", "Have you implemented token based authentication?"]:
            self.check(q, "Yes")

    def test_feature_flags_ab_testing(self):
        for q in ["Do you have experience with feature flags?", "Do you use feature toggles?", "Do you have A/B testing experience?"]:
            self.check(q, "Yes")

    def test_oncall_availability(self):
        for q in ["Are you available for on-call support?", "Are you available for on-call?", "Are you available for production support?"]:
            self.check(q, "Yes")

    def test_startup_comfort(self):
        for q in ["Are you comfortable working in a startup environment?", "Are you comfortable with a fast paced environment?"]:
            self.check(q, "Yes")

    def test_industry_domain(self):
        for q in [
            "Do you have experience in the insurance domain?",
            "Do you have experience in the healthcare domain?",
            "Do you have experience in the telecom domain?",
            "Do you have experience in the retail domain?",
        ]:
            self.check(q, "Yes")

    def test_monolith_migration(self):
        for q in [
            "Have you worked on monolith to microservices migration?",
            "Have you done monolithic to microservices migration?",
            "Do you have microservices migration experience?",
        ]:
            self.check(q, "Yes")

    def test_site_visit_availability(self):
        for q in ["Are you available for site visits?", "Can you visit client site?", "Are you available for onsite visits?"]:
            self.check(q, "Yes")

    def test_terms_consent(self):
        for q in ["Do you agree to the terms and conditions?", "Do you accept the terms and conditions?", "Do you consent to data processing?"]:
            self.check(q, "Yes")

    def test_career_break_patterns(self):
        for q in [
            "are you on a career break",
            "are you currently on a career break",
            "career break",
            "break in career",
            "gap in employment",
            "career gap",
            "employment gap"
        ]:
            self.check(q, "No")

    def test_career_break_reason_patterns(self):
        for q in [
            "what is the reason for the break",
            "reason for break",
            "reason for the break",
            "reason for career break",
            "reason for the career break",
            "reason for career gap",
            "reason for the career gap",
            "reason for employment gap",
            "reason for the employment gap",
            "reason for gap in career",
            "reason for the gap in career"
        ]:
            self.check(q, "Personal")

    def test_military_service_patterns(self):
        for q in [
            "Have you ever served in the military?",
            "Have you ever served in the military",
            "Have you served in the military",
            "Are you currently serving in the military",
            "military service",
            "served in the armed forces"
        ]:
            self.check(q, "No")

    def test_military_service_input_types(self):
        q = "Have you ever served in the military?"
        ans_btn, score = self.matcher.fuzzy_match(q, input_type="button")
        self.assertEqual(ans_btn, "Never served")
        self.assertGreater(score, 0.8)

        ans_sel, score = self.matcher.fuzzy_match(q, input_type="select")
        self.assertEqual(ans_sel, "Never served")
        self.assertGreater(score, 0.8)

        ans_rad, score = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_rad, "No")
        self.assertGreater(score, 0.8)

    def test_recent_ai_feature_production_matcher(self):
        q = "What s the most recent AI feature/system you shipped to production?"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertIsNotNone(ans)
        self.assertTrue(any(term in ans.lower() for term in ["document intelligence", "gpt-4", "ai"]))
        self.assertGreaterEqual(score, 0.8)

    def test_ai_technologies_tools_concepts_matcher(self):
        q = "Which of the following AI technologies, tools, or concepts have you worked with? (Select all that apply)*"
        ans, score = self.matcher.fuzzy_match(q)
        self.assertIsNotNone(ans)
        self.assertIn("open ai", ans.lower())
        self.assertIn("claude", ans.lower())
        self.assertIn("retrieval-augmented generation (rag)", ans.lower())
        self.assertGreaterEqual(score, 0.8)

        # Input type tests
        ans_cb, _ = self.matcher.fuzzy_match(q, input_type="checkbox")
        self.assertIn("open ai", ans_cb.lower())
        self.assertIn("gemini", ans_cb.lower())

        ans_rad, _ = self.matcher.fuzzy_match(q, input_type="radio")
        self.assertEqual(ans_rad, "Open AI")

        ans_sel, _ = self.matcher.fuzzy_match(q, input_type="select")
        self.assertEqual(ans_sel, "Open AI")


if __name__ == '__main__':
    unittest.main()
