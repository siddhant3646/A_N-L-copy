import pytest
from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType
from src.sentinel.agent import SentinelAgent
import json
from pathlib import Path


def test_expected_compensation_patterns():
    agent = SentinelAgent()
    # Explicit agreement question returns Yes
    ans_agree, conf_agree = agent._fuzzy_match_question("Are you comfortable with the expected compensation?")
    assert conf_agree >= 0.95
    assert ans_agree == "Yes"

    # Salary question returns expected salary (30 LPA / 3000000)
    ans_salary, conf_salary = agent._fuzzy_match_question("Expected Compensation?*")
    assert conf_salary >= 0.90
    assert "30" in ans_salary

    # InputAwareResolver resolves binary Yes/No radio options to Yes even when raw answer is salary
    resolver = InputAwareResolver()
    radio_opts = [Option(value="Yes", label="Yes"), Option(value="No", label="No")]
    res = resolver.resolve(ans_salary, InputType.RADIO, radio_opts, question="Expected Compensation?*")
    assert res.matched_option is not None
    assert res.matched_option.label == "Yes"


def test_work_authorization_status_india():
    agent = SentinelAgent()
    q = "What is your work authorization status for India?"
    ans, conf = agent._fuzzy_match_question(q)
    assert conf >= 0.95
    assert ans == "I can work here without any restrictions"

    resolver = InputAwareResolver()
    radio_opts = [
        Option(value="I can work here without any restrictions", label="I can work here without any restrictions"),
        Option(value="I can work here, but only for a limited time", label="I can work here, but only for a limited time"),
        Option(value="I can work here, but only for my current employer", label="I can work here, but only for my current employer"),
        Option(value="I can't work here yet", label="I can't work here yet"),
    ]
    res = resolver.resolve(ans, InputType.RADIO, radio_opts, question=q)
    assert res.matched_option is not None
    assert res.matched_option.label == "I can work here without any restrictions"


def test_when_can_you_start_range():
    agent = SentinelAgent()
    q = "When can you start?*"
    ans, conf = agent._fuzzy_match_question(q)
    assert conf >= 0.95
    assert ans == "Within two weeks"

    resolver = InputAwareResolver()
    radio_opts = [
        Option(value="Immediately", label="Immediately"),
        Option(value="Within two weeks", label="Within two weeks"),
        Option(value="Within one month", label="Within one month"),
        Option(value="Within two months", label="Within two months"),
        Option(value="Within three months", label="Within three months"),
        Option(value="In more than three months", label="In more than three months"),
    ]
    res = resolver.resolve(ans, InputType.RADIO, radio_opts, question=q)
    assert res.matched_option is not None
    assert res.matched_option.label == "Within two weeks"


def test_location_scoring_ranks_city_above_sublocalities():
    def score_location(text: str) -> int:
        t = (text or "").lower().strip()
        if not t or "cape verde" in t:
            return -1000
        is_sub = any(
            sub in t
            for sub in [
                "indiranagar",
                "indira nagar",
                "koramangala",
                "whitefield",
                "hsr",
                "marathahalli",
                "jp nagar",
                "jayanagar",
                "electronic city",
                "bellandur",
                "hebbal",
                "btm",
            ]
        )
        if "bengaluru, karnataka" in t or "bangalore, karnataka" in t:
            score = 1000
        elif t.startswith("bengaluru") or t.startswith("bangalore"):
            score = 800
        elif "bengaluru" in t or "bangalore" in t:
            score = 600
        elif "karnataka" in t or "india" in t:
            score = 400
        else:
            return -1000
        if is_sub:
            score -= 600
        return score

    bengaluru_score = score_location("Bengaluru, Karnataka, India")
    bangalore_score = score_location("Bangalore, Karnataka, India")
    indiranagar_score = score_location("Indiranagar, Bangalore")
    koramangala_score = score_location("Koramangala, Bangalore, Karnataka")
    cape_verde_score = score_location("Cape Verde, India")

    assert bengaluru_score == 1000
    assert bangalore_score == 1000
    assert indiranagar_score < bengaluru_score
    assert koramangala_score < bengaluru_score
    assert cape_verde_score == -1000

    # Ensure sorting picks Bengaluru, Karnataka, India first
    candidates = [
        "Indiranagar, Bangalore",
        "Bengaluru, Karnataka, India",
        "Whitefield, Bangalore",
        "Bangalore Urban, Karnataka, India",
    ]
    sorted_candidates = sorted(candidates, key=score_location, reverse=True)
    assert sorted_candidates[0] == "Bengaluru, Karnataka, India"


def test_qa_patterns_json_entries():
    patterns_file = Path("config/qa_patterns.json")
    with open(patterns_file, "r") as f:
        data = json.load(f)
    patterns = data.get("patterns", {})

    assert "expected_compensation_agreement" in patterns
    exp_comp = patterns["expected_compensation_agreement"]
    assert exp_comp["category"] in ["salary", "compensation"]
    assert exp_comp["default"] == "Yes"
    assert exp_comp["input_type_defaults"]["number"] == "1"

    assert "work_authorization_status_india" in patterns
    work_auth = patterns["work_authorization_status_india"]
    assert work_auth["category"] == "work_authorization"
    assert work_auth["default"] == "I can work here without any restrictions"
    assert work_auth["input_type_defaults"]["number"] == "1"

    assert "when_can_you_start_range" in patterns
    when_start = patterns["when_can_you_start_range"]
    assert when_start["category"] == "notice_period"
    assert when_start["default"] == "Within two weeks"
