"""Unit tests verifying fixes for questions identified in qa_results.csv audit."""

import os
import sys
import pytest
from unittest.mock import MagicMock

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.sentinel.question_fingerprint import FingerprintMatcher
from src.sentinel.question_classifier import QuestionClassifier


@pytest.fixture(scope="module")
def patterns_data():
    json_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "config", "qa_patterns.json"
    )
    return load_patterns(json_path)


@pytest.fixture
def agent(patterns_data):
    agent = SentinelAgent.__new__(SentinelAgent)
    agent._current_platform = "linkedin"
    agent._pattern_matcher = PatternMatcher(patterns_data)
    agent._fingerprint_matcher = FingerprintMatcher()
    agent._pattern_learner = None
    agent._self_healing = MagicMock()
    agent._self_healing.get_learned_answer.return_value = None
    agent._question_classifier = QuestionClassifier(platform="linkedin")
    agent.logger = None
    return agent


def test_claude_ai_agents_workflow(agent):
    q = "Have you worked with Claude/AI agents/orchestrated workflows to compress dev work (scaffolding, code review, debugging, test generation, automation)?"
    ans, conf = agent._fuzzy_match_question(q)
    assert ans == "Yes"
    assert conf >= 0.95


def test_active_pf_account(agent):
    questions = [
        "Do you have an active PF account?",
        "Do you have PF for all companies?",
        "Have you maintained an active PF account throughout your employment?",
    ]
    for q in questions:
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes", f"Failed for question: {q}"
        assert conf >= 0.90


def test_cooling_period_and_prior_applications(agent):
    questions = [
        "Have you applied with Mphasis in last 6/12 months?",
        "Have you applied with Accenture in last 6/12 months?",
        "Have you applied to any of the roles with Mphasis in the past 6 months?",
        "Have you interviewed in the last 6 months?",
        "Applied to any role in the past 6 months?",
    ]
    for q in questions:
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "No", f"Failed for question: {q}"
        assert conf >= 0.95


def test_joining_on_or_before_date(agent):
    questions = [
        "Can You Join on or Before Oct-11?",
        "Can you join on or before 15th October?",
        "Are you able to join by Oct 15?",
        "Can you join on or before Nov-01?",
    ]
    for q in questions:
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes", f"Failed for question: {q}"
        assert conf >= 0.95


def test_sponsorship_not_required(agent):
    questions = [
        "Do you now or will you at any time in the future require sponsorship?",
        "Will you now or in the future require visa sponsorship?",
        "Do you require employer sponsorship to work in India?",
    ]
    for q in questions:
        ans, conf = agent._fuzzy_match_question(q)
        assert ans in ["No", "No, I do not require sponsorship"], f"Failed for question: {q}"
        assert conf >= 0.95


def test_candidate_profile_salary_and_experience(agent):
    # CTC
    ans, conf = agent._fuzzy_match_question("What is your current CTC?")
    assert "23" in ans
    
    ans, conf = agent._fuzzy_match_question("What is your expected CTC?")
    assert "30" in ans
    
    # Notice Period
    ans, conf = agent._fuzzy_match_question("What is your notice period?")
    assert "15" in ans


def test_experience_bracket_resolution():
    import re
    options = ["0-1 yrs", "2-4 yrs", "Skip this question"]
    expVal = 4.2
    
    scores = {}
    for label in options:
        clean = label.lower().strip()
        if "skip" in clean:
            scores[label] = 0
            continue
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–to]|\s+)\s*(\d+(?:\.\d+)?)", clean)
        if m:
            rMin = float(m.group(1))
            rMax = float(m.group(2))
            if expVal >= rMin and expVal <= (rMax + 0.5):
                scores[label] = max(85, 99 - (rMax - rMin) - abs(expVal - min(expVal, rMax)))
            elif expVal > rMax and (expVal - rMax) <= 2.0:
                scores[label] = max(70, 85 - (expVal - rMax) * 8)
            else:
                scores[label] = 0
        else:
            scores[label] = 0
            
    best = max(scores.items(), key=lambda x: x[1])
    assert best[0] == "2-4 yrs"
    assert best[1] > 90

