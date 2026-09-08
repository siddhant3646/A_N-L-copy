import pytest
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver, InputType, Option


@pytest.fixture(scope="module")
def pattern_matcher():
    patterns = load_patterns("config/qa_patterns.json")
    return PatternMatcher(patterns)


@pytest.fixture(scope="module")
def resolver():
    return InputAwareResolver()


class TestFixedQAResults:
    """Validate that the historical QA errors from qa_results.csv are properly resolved."""

    def test_brevo_privacy_policy_consent(self, pattern_matcher, resolver):
        q = "I am allowing Brevo to contact me about future job opportunities for up to 2 years. Privacy Policy \nRequired"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="radio")
        assert ans == "Yes"
        assert score >= 0.95

        # Test with input resolver against [yes, no] options
        options = [Option(value="yes", label="yes"), Option(value="no", label="no")]
        match = resolver.resolve(ans, InputType.RADIO, options, question=q)
        assert match.matched_option is not None
        assert match.matched_option.value.lower() == "yes"

    def test_offers_in_hand_not_hijacked_by_ctc(self, pattern_matcher):
        q = "Offers in hand, mention if any with CTC offered, location, date of joining, etc:"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="textarea")
        assert ans != "23"
        assert ans != "23 LPA"
        assert "no other offers in hand" in ans.lower() or ans == "None"

    def test_industry_projects_not_hijacked_by_ctc(self, pattern_matcher):
        q = "Industry - Life Science/Banking/Insurance mention name of projects"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="text")
        assert "23" not in ans
        assert "BFSI" in ans

    def test_system_design_tinyurl_not_bio(self, pattern_matcher):
        q = "How would you design a URL shortener system (like TinyURL) at a high level?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="text")
        assert "4+ years of professional full-stack software engineering" not in ans
        assert "TinyURL" in ans or "Base62" in ans or "shortCode" in ans

    def test_python_coding_radio_boolean(self, pattern_matcher, resolver):
        q = "Do you have 4+ years of coding experience in Python?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="radio")
        assert ans == "Yes"

        options = [Option(value="yes", label="yes"), Option(value="no", label="no")]
        match = resolver.resolve("4.2", InputType.RADIO, options, question=q)
        assert match.matched_option.value.lower() == "yes"

    def test_llm_langchain_radio_boolean(self, pattern_matcher, resolver):
        q = "Do you have 2+ years hands on working experience in latest technologies like Langchain, LLM, NLP?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="radio")
        assert ans == "Yes"

        options = [Option(value="yes", label="yes"), Option(value="no", label="no")]
        match = resolver.resolve("4.2", InputType.RADIO, options, question=q)
        assert match.matched_option.value.lower() == "yes"

    def test_ai_llm_technologies_list(self, pattern_matcher):
        q = "Which AI/LLM technologies have you worked with?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="text")
        assert "OpenAI" in ans or "LangChain" in ans
        assert "React, Node.js" not in ans

    def test_salary_cut_rejection(self, pattern_matcher, resolver):
        q = "Are you ok with upto 12 to 13 lpa ?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="select")
        assert ans == "No"

        options = [Option(value="Yes", label="Yes"), Option(value="No", label="No")]
        match = resolver.resolve("Yes", InputType.SELECT, options, question=q)
        assert match.matched_option.label == "No"

    def test_fresher_graduation_2025_2026_rejection(self, pattern_matcher, resolver):
        q = "Are you completing Bachelor's in Computer Engineering or related field in 2025/2026?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="select")
        assert "No" in ans

        options = [Option(value="Yes", label="Yes"), Option(value="No", label="No")]
        match = resolver.resolve("Yes", InputType.SELECT, options, question=q)
        assert match.matched_option.label == "No"

    def test_reason_for_job_change(self, pattern_matcher):
        q = "What is your reason for seeking a job change?"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="text")
        assert ans != "Yes"
        assert "challenges" in ans.lower() or "growth" in ans.lower() or "advancement" in ans.lower()

    def test_consumer_journey_improvement(self, pattern_matcher):
        q = "How you improved Consumer journey"
        ans, score = pattern_matcher.fuzzy_match(q, input_type="textarea")
        assert ans != "4.2 Years"
        assert "dispute" in ans.lower() or "latency" in ans.lower() or "performance" in ans.lower()

    def test_unlisted_technologies_default_zero_or_no(self, pattern_matcher):
        unlisted = [
            ("How many years of experience do you have in Oracle Cpq Cloud?", "0"),
            ("How many years of experience do you have in .Net core?", "0"),
            ("How many years of work experience do you have with Shopify?", "0"),
            ("How many years of work experience do you have with Azure Databricks?", "0"),
            ("How many years of experience do you have in Google Dialogflow cx?", "0"),
            ("How many years of experience do you have in ccai?", "0"),
            ("How many years of experience do you have in Glue?", "0"),
            ("Do you have experience in NMS (Network Management System)?", "No"),
        ]
        for q, expected in unlisted:
            ans, score = pattern_matcher.fuzzy_match(q)
            assert expected.lower() in ans.lower(), f"Failed for question: {q}, got: {ans}"

    def test_multi_part_commercial_experience(self, pattern_matcher):
        q1 = "How much experience do you have in each (Java, AWS, leading or managing team)?"
        ans1, _ = pattern_matcher.fuzzy_match(q1, input_type="textarea")
        assert "Java" in ans1 and "AWS" in ans1

        q2 = "Briefly describe your hands-on experience with React, Next.js, TypeScript, and Node.js in commercial projects ?"
        ans2, _ = pattern_matcher.fuzzy_match(q2, input_type="text")
        assert "React" in ans2 and ("commercial" in ans2.lower() or "experience" in ans2.lower())
        assert ans2 != "4.2 Years"

    def test_linkedin_url_canonical(self, pattern_matcher):
        q = "LinkedIn Profile"
        ans, _ = pattern_matcher.fuzzy_match(q, input_type="text")
        assert ans.startswith("https://www.linkedin.com/in/siddhant3646")
        assert "example.com" not in ans
