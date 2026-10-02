"""
Unit tests for CSV audit pattern fixes identified on Sep 28, 2026.
Tests cover:
- Expected monthly fixed compensation in INR (e.g. 'What are your expected fixed monthly compensation expectations (in INR)') -> 250000
- SQL skills rating on a scale of 1-5 (e.g. 'This interview process will involve a lot of questions on SQL databases. How would you rate your SQL skills on a scale of 1-5?') -> 4
- CTC prompt with explicit raw INR example (e.g. 'Kindly mention your current CTC in LPA, Example if your CTC is 7LPA, Mention as 700000') -> 2300000
- Combined Email and Contact/Phone questions (e.g. 'Your Email and contact Number?') -> contains both email and phone
"""

import pytest
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher
from src.sentinel.agent import SentinelAgent


@pytest.fixture
def agent():
    return SentinelAgent()


@pytest.fixture
def matcher():
    patterns = load_patterns('config/qa_patterns.json')
    return PatternMatcher(patterns)


class TestQACSVFixesSept28:
    """Test suite for QA CSV audit fixes on Sep 28, 2026."""

    def test_expected_monthly_compensation_matcher(self, matcher):
        q = "What are your expected fixed monthly compensation expectations (in INR)"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "250000"
        assert score >= 0.90

    def test_expected_monthly_compensation_agent(self, agent):
        q = "What are your expected fixed monthly compensation expectations (in INR)"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "250000"
        assert score >= 0.90

    def test_sql_rating_scale_1_to_5_matcher(self, matcher):
        q = "This interview process will involve a lot of questions on SQL databases. How would you rate your SQL skills on a scale of 1-5?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "4"
        assert score >= 0.90

    def test_sql_rating_scale_1_to_5_agent(self, agent):
        q = "This interview process will involve a lot of questions on SQL databases. How would you rate your SQL skills on a scale of 1-5?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans in ("4", "5")
        assert score >= 0.90

    def test_current_ctc_mention_as_700000_matcher(self, matcher):
        q = "Kindly mention your current CTC in LPA, Example if your CTC is 7LPA, Mention as 700000"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "2300000"
        assert score >= 0.90

    def test_current_ctc_mention_as_700000_agent(self, agent):
        q = "Kindly mention your current CTC in LPA, Example if your CTC is 7LPA, Mention as 700000"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "2300000"
        assert score >= 0.90

    def test_email_and_contact_number_matcher(self, matcher):
        q = "Your Email and contact Number?"
        ans, score = matcher.fuzzy_match(q)
        assert "siddhant3646@gmail.com" in ans
        assert "7905828880" in ans
        assert score >= 0.90

    def test_email_and_contact_number_agent(self, agent):
        q = "Your Email and contact Number?"
        ans, score = agent._fuzzy_match_question(q)
        assert "siddhant3646@gmail.com" in ans
        assert "7905828880" in ans
        assert score >= 0.90

    def test_interview_time_slot_matcher(self, matcher):
        q = "Please mention the time slot in between 10 AM to 4 PM when you will be available for interview"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Anytime between 10 AM - 4 PM"
        assert score >= 0.90

    def test_interview_time_slot_agent(self, agent):
        q = "Please mention the time slot in between 10 AM to 4 PM when you will be available for interview"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "Anytime between 10 AM - 4 PM"
        assert score >= 0.90

    def test_drug_test_consent_matcher(self, matcher):
        q = "are you willing to take a drug test, in accordance with local law/regulations?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_drug_test_consent_agent(self, agent):
        q = "are you willing to take a drug test, in accordance with local law/regulations?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_restrictive_covenants_noncompete_matcher(self, matcher):
        q = "Do you have any restrictive covenants e.g.noncompete/confidentiality agreements with current/previous employer,which restrict you performing this job?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "No"
        assert score >= 0.90

    def test_restrictive_covenants_noncompete_agent(self, agent):
        q = "Do you have any restrictive covenants e.g.noncompete/confidentiality agreements with current/previous employer,which restrict you performing this job?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert score >= 0.90

    def test_career_education_gaps_matcher(self, matcher):
        q = "you should not have much gaps from education to job and between jobs. What are your gap?"
        ans, score = matcher.fuzzy_match(q)
        assert "None of the above" in ans or ans == "No"
        assert score >= 0.90

    def test_career_education_gaps_agent(self, agent):
        q = "you should not have much gaps from education to job and between jobs. What are your gap?"
        ans, score = agent._fuzzy_match_question(q)
        assert "None of the above" in ans or ans == "No"
        assert score >= 0.90

    def test_monthly_salary_usd_matcher(self, matcher):
        q = "What are your monthly salary expectations (in USD per Month)?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "5000"
        assert score >= 0.90

    def test_monthly_salary_usd_agent(self, agent):
        q = "What are your monthly salary expectations (in USD per Month)?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "5000"
        assert score >= 0.90

    def test_interview_time_slot_9_to_3_matcher(self, matcher):
        q = "Kindly mention the time slot in between 9- 3 pm at what time you will be available?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Anytime between 10 AM - 2 PM"
        assert score >= 0.90

    def test_interview_time_slot_9_to_3_agent(self, agent):
        q = "Kindly mention the time slot in between 9- 3 pm at what time you will be available?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "Anytime between 10 AM - 2 PM"
        assert score >= 0.90

    def test_current_city_and_state_matcher(self, matcher):
        q = "Please share your current city and state of residence"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Bangalore, Karnataka"
        assert score >= 0.90

    def test_current_city_and_state_agent(self, agent):
        q = "Please share your current city and state of residence"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "Bangalore, Karnataka"
        assert score >= 0.90

    def test_referral_employee_name_na_matcher(self, matcher):
        q = "If you were referred by a Kobie employee, please list their name. If not referred, put N/A"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "N/A"
        assert score >= 0.90

    def test_referral_employee_name_na_agent(self, agent):
        q = "If you were referred by a Kobie employee, please list their name. If not referred, put N/A"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "N/A"
        assert score >= 0.90

    def test_yn_experience_screening_matcher(self, matcher):
        q = "Do you have 3–4+ years of hands-on experience building and deploying AI/ML or intelligent-platform solutions?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_yn_experience_screening_agent(self, agent):
        q = "Do you have 3–4+ years of hands-on experience building and deploying AI/ML or intelligent-platform solutions?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert score >= 0.90

    def test_tech_experience_database_matcher(self, matcher):
        q = "Experience in PostgreSQL / MySQL / SQL Server"
        ans, score = matcher.fuzzy_match(q)
        assert "4" in ans
        assert score >= 0.90

    def test_tech_experience_database_agent(self, agent):
        q = "Experience in PostgreSQL / MySQL / SQL Server"
        ans, score = agent._fuzzy_match_question(q)
        assert "4" in ans
        assert score >= 0.90

    def test_tech_experience_linux_typo_matcher(self, matcher):
        q = "Linux experince"
        ans, score = matcher.fuzzy_match(q)
        assert "4" in ans or "Linux" in ans
        assert score >= 0.80

    def test_agentic_ai_use_case_essay_matcher(self, matcher):
        q = "Have you built or implemented Agentic AI / AI Agent solutions? Please explain the use case and your contribution."
        ans, score = matcher.fuzzy_match(q)
        assert "Agentic AI" in ans or "LangChain" in ans or "workflow" in ans
        assert len(ans) > 100
        assert score >= 0.90

    def test_agentic_ai_use_case_essay_agent(self, agent):
        q = "Have you built or implemented Agentic AI / AI Agent solutions? Please explain the use case and your contribution."
        ans, score = agent._fuzzy_match_question(q)
        assert "Agentic AI" in ans or "LangChain" in ans or "workflow" in ans
        assert len(ans) > 100
        assert score >= 0.90

    def test_total_working_expr_software_engineering_matcher(self, matcher):
        q = "What is your total working expr in Software Engineering?"
        ans, score = matcher.fuzzy_match(q)
        assert ans == "4.2 Years"
        assert score >= 0.90

    def test_total_working_expr_software_engineering_agent_naukri(self, agent):
        agent._current_platform = "naukri"
        q = "What is your total working expr in Software Engineering?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "4.2 Years"
        assert score >= 0.90

    def test_total_working_expr_software_engineering_agent_linkedin(self, agent):
        agent._current_platform = "linkedin"
        q = "What is your total working expr in Software Engineering?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans in ("4", "4.2 Years")
        assert score >= 0.90

    def test_total_working_expr_variants(self, matcher, agent):
        variants = [
            "total working expr in software engineering",
            "working expr in software engineering",
            "total working expr",
            "working expr",
            "What is your total working expr?",
            "total working experience in software engineering",
            "working experience in software engineering",
            "total working experience",
            "working expr in software",
            "working experience in software"
        ]
        agent._current_platform = "naukri"
        for v in variants:
            ans, score = agent._fuzzy_match_question(v)
            assert ans == "4.2 Years", f"Failed for variant: {v} -> {ans}"
            assert score >= 0.90

    def test_expr_synonym_in_fingerprint(self):
        from src.sentinel.question_fingerprint import create_fingerprint, SYNONYM_MAP
        assert "expr" in SYNONYM_MAP
        assert SYNONYM_MAP["expr"] == "experience"
        fp1 = create_fingerprint("total working expr in software engineering")
        fp2 = create_fingerprint("total working experience in software engineering")
        assert fp1 == fp2

    def test_question_classifier_total_working_expr(self):
        from src.sentinel.question_classifier import QuestionClassifier, QuestionCategory
        classifier = QuestionClassifier()
        cat, conf = classifier.classify("What is your total working expr in Software Engineering?")
        assert cat == QuestionCategory.EXPERIENCE
        assert conf >= 0.90

