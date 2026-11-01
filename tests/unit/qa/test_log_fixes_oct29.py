import pytest
from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType
from src.sentinel.question_fingerprint import detect_expected_format, validate_answer
from src.sentinel.agent import SentinelAgent


def test_salary_range_matching_raw_inr_to_lakhs():
    resolver = InputAwareResolver()
    opts = [
        Option(value="25 to 30 lakhs", label="25 to 30 lakhs"),
        Option(value="30-35 lakhs", label="30-35 lakhs"),
        Option(value="35 - 40 lakhs", label="35 - 40 lakhs"),
        Option(value="40 + lakhs", label="40 + lakhs"),
    ]
    # Expected CTC in raw INR (3000000 = 30 Lakhs) should match 30-35 lakhs or 25 to 30 lakhs, NEVER 40+ lakhs
    res = resolver.resolve("3000000", InputType.RADIO, opts, question="How much annual salary are you expecting?")
    assert res.matched_option is not None
    assert res.matched_option.label in ["30-35 lakhs", "25 to 30 lakhs"]
    assert res.matched_option.label != "40 + lakhs"


def test_salary_range_matching_lpa_options():
    resolver = InputAwareResolver()
    opts = [
        Option(value="10 to 20 lakhs", label="10 to 20 lakhs"),
        Option(value="20 to 30 lakhs", label="20 to 30 lakhs"),
        Option(value="30 to 40 lakhs", label="30 to 40 lakhs"),
        Option(value="40 + lakhs", label="40 + lakhs"),
    ]
    # 2300000 (Current CTC = 23 LPA) should match 20 to 30 lakhs
    res = resolver.resolve("2300000", InputType.RADIO, opts, question="What is your current salary?")
    assert res.matched_option is not None
    assert res.matched_option.label == "20 to 30 lakhs"


def test_fingerprint_salary_lpa_format_validation():
    q = "How much annual salary are you expecting?"
    fmt = detect_expected_format(q)
    assert fmt == "salary_lpa"

    # Raw INR 3000000 should be accepted as valid (converted to 30 LPA in check)
    is_valid, msg = validate_answer("3000000", fmt)
    assert is_valid is True
    assert msg == ""


def test_agent_fuzzy_match_annual_salary():
    agent = SentinelAgent()
    ans, conf = agent._fuzzy_match_question("How much annual salary are you expecting?")
    assert conf >= 0.90
    assert "30" in ans
