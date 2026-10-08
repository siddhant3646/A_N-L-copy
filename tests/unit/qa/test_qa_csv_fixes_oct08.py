"""
Unit tests for QA pattern fixes and additions identified from qa_results.csv on Oct 8, 2026.

Test cases cover:
1. HackerEarth assessment test attendance (Yes)
2. Detailed Kubernetes experience explanation (descriptive essay)
3. Ex-Amazon employee / candidate compliance check (No)
4. Variable pay with CTC question (0 / No variable pay)
5. Academic percentage questions:
   - 10th % (88%)
   - 12th % (85%)
   - Grad % (85%)
   - PG % with 'write NA if not pursued' (NA, not corrupted by 'rsu')
6. Traffic volume handled by system (10M+ daily events)
7. Contractual role employment arrangement preference (Contract Full-time)
8. Highest team size handled technically (numeric 8 / not long essay)
9. Serving notice period LWD numeric format '19102026' (23102026)
10. Numbered notice period options '(6) --Serving Notice Period'
11. Multi-select prior experience technologies (Java, JavaScript, AWS, MongoDB, MySQL; not corrupted by 'r experience')
12. Why work with Supersourcing (tailored to Supersourcing, not hardcoded Wissen)
13. AI tools & usage with specified tools (4.2 Years with GitHub Copilot, ChatGPT, etc.)
14. Product/platform built from 0 to 1 role description (SDE-2 / Lead Backend Engineer)
15. Data Structures & Algorithm experience brief
16. Instahyre HTML section headers (skipped)
17. Relocate to Gurugram city selection
18. How did you hear about Appian (LinkedIn, not Appian Employee)
19. Ex-Appian employee compliance check (No)
20. Appian visa sponsorship petition requirement (No)
21. LRU cache O(1) design essay (LRU Cache with Doubly Linked List, not stolen by DSA brief)
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


class TestQACSVFixesOct08:
    """Test suite for QA CSV audit fixes on Oct 8, 2026."""

    # 1. HackerEarth assessment attendance
    def test_hackerearth_attendance_matcher(self, matcher):
        q = "Ok to attend HackerEarth test:"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_hackerearth_attendance_agent(self, agent):
        q = "Ok to attend HackerEarth test:"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.85

    # 2. Detailed Kubernetes experience
    def test_kubernetes_in_detail_matcher(self, matcher):
        q = "Explain your experience in Kubernetes in detail"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "production environments" in ans.lower() or "microservices" in ans.lower()
        assert ans not in ("4.2 Years", "4.2", "4", "Yes")
        assert score >= 0.85

    # 3. Ex-Amazon employee check
    def test_ex_amazon_employee_matcher(self, matcher):
        q = "Are you an Ex-Amazon Employee ? (Apply if only ' YES')"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_ex_amazon_employee_agent(self, agent):
        q = "Are you an Ex-Amazon Employee ? (Apply if only ' YES')"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.85

    # 4. Variable pay with CTC
    def test_variable_pay_with_ctc_matcher(self, matcher):
        q = "Please mention if you are having any Variable pay with CTC and the Frequency of recieving it (Monthly/Quarterly/Annually)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "no variable pay" in ans.lower() or "100% fixed" in ans.lower() or ans == "0"
        assert ans not in ("3000000", "30", "30 LPA")
        assert score >= 0.85

    # 5. Academic percentage questions
    def test_tenth_percentage_matcher(self, matcher):
        q = "10th %"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "88" in ans
        assert ans.lower() != "yes"
        assert score >= 0.85

    def test_twelfth_percentage_matcher(self, matcher):
        q = "12th %"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "85" in ans
        assert ans.lower() != "yes"
        assert score >= 0.85

    def test_grad_percentage_matcher(self, matcher):
        q = "Grad %"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "85" in ans
        assert ans.lower() != "yes"
        assert score >= 0.85

    def test_pg_percentage_pursued_not_rsu_matcher(self, matcher):
        q = "PG % (write NA if not pursued)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "NA"
        assert ans.lower() != "yes"
        assert score >= 0.85

    # 6. Traffic volume handled
    def test_traffic_volume_handled_matcher(self, matcher):
        q = "What traffic volume is your system currently handling?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "10m+" in ans.lower() or "rpm" in ans.lower()
        assert ans.lower() not in ("yes", "no", "4.2 years")
        assert score >= 0.85

    # 7. Contractual role employment arrangement
    def test_contractual_employment_arrangement_matcher(self, matcher):
        q = "This is a 6-month contractual role. Which employment arrangement would you be interested in?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "Contract Full-time"
        assert ans != "Temporary / Part-time"
        assert score >= 0.85

    # 8. Highest team size handled technically
    def test_highest_team_size_technically_matcher(self, matcher):
        q = 'What is the Highest team size you handled - Technically? (Not - People Management, if you haven\'t handled, please mark as "0")'
        ans, score = matcher.fuzzy_match(q, input_type="number")
        assert ans == "8"
        assert score >= 0.85

    # 9. Serving notice period numeric LWD format
    def test_serving_notice_lwd_numeric_format_matcher(self, matcher):
        q = 'If you are serving notice period or your last working day is completed, please share the details (Example - last working days is /was 19th Oct, 2026 then enter as 19102026, if not serving enter "0")'
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "23102026"
        assert ans.lower() != "yes"
        assert score >= 0.85

    # 10. Numbered notice period options
    def test_notice_period_numbered_options_matcher(self, matcher):
        q = "What is your Notice Period? Option (1) -- 90 Days, (2) -- 60 Days, (3) -- 45 Days, (4) -- 30 Days, (5) -- less than 15 days, (6) --Serving Notice Period, (7) - Immediate Joiner"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "serving notice period" in ans.lower()
        assert score >= 0.85

    # 11. Multi-select prior experience technologies (not stolen by R)
    def test_select_all_prior_experience_matcher(self, matcher):
        q = "Select all the options you have prior experience with."
        ans, score = matcher.fuzzy_match(q, input_type="checkbox")
        assert "Java" in ans and "AWS" in ans
        assert ans != "4.2 Years"
        assert score >= 0.85

    # 12. Why work with Supersourcing
    def test_why_work_with_supersourcing_matcher(self, matcher):
        q = "What excites you about working with Supersourcing?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "supersourcing" in ans.lower()
        assert "wissen" not in ans.lower()
        assert score >= 0.85

    # 13. AI tools and usage
    def test_ai_tools_and_usage_matcher(self, matcher):
        q = "How many years of experience do you have with AI Tools & usage? Please specify tools you have used"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "copilot" in ans.lower() or "chatgpt" in ans.lower()
        assert ans != "4.2 Years"
        assert score >= 0.85

    # 14. Product from 0 to 1 role
    def test_built_product_zero_to_one_role_matcher(self, matcher):
        q = "Have you built any product or platform from 0 to 1? What was your role?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "sde-2" in ans.lower() or "lead" in ans.lower() or "microservices" in ans.lower()
        assert ans.lower() != "yes"
        assert score >= 0.85

    # 15. DSA experience brief
    def test_dsa_experience_brief_matcher(self, matcher):
        q = "Do you have experience in Data Structures and Algorithm? Give brief on the experience here."
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "algorithms" in ans.lower() or "leetcode" in ans.lower()
        assert ans.lower() != "yes"
        assert score >= 0.85

    # 16. Instahyre section headers skipped
    def test_instahyre_section_header_skip_matcher(self, matcher):
        q = "<p><strong>Behavioral questions</strong></p><p><span>To assess how you have handled specific employment-related situations in your previous jobs.</span></p>"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "N/A"
        assert ans != "4.2 Years"

    # 17. Relocate to Gurugram city selection
    def test_relocate_gurugram_city_matcher(self, matcher):
        q = "Please select the city you are currently residing or willing to relocate to Gurugram"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "gurugram" in ans.lower()
        assert score >= 0.85

    # 18. Hear about Appian
    def test_hear_about_appian_matcher(self, matcher):
        q = "How did you hear about Appian?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "LinkedIn"
        assert ans != "Appian Employee"
        assert score >= 0.85

    # 19. Ex-Appian employee
    def test_ex_appian_employee_matcher(self, matcher):
        q = "Have you been employed by Appian before?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    # 20. Appian visa sponsorship petition
    def test_appian_visa_sponsorship_petition_matcher(self, matcher):
        q = "If yes, will you now or in the future require Appian to file a petition or application for employment-based visa status on your behalf to begin or continue employment with our company?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    # 21. LRU Cache essay not stolen by DSA brief
    def test_lru_cache_essay_matcher(self, matcher):
        q = "Design an LRU Cache with O(1) get and put operations. Briefly explain your approach and data structures used."
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "lru cache" in ans.lower()
        assert "doubly linked list" in ans.lower()
        assert score >= 0.85
