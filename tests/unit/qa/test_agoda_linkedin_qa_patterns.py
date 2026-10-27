"""
Unit tests for Agoda LinkedIn Easy Apply Q&A patterns and form interactions.
Covers:
- Hybrid Gurgaon relocation and office policy
- Relevant full-time experience excluding internship (dropdown range matching)
- Leading large-scale technical initiatives
- Agoda employee personal relationship and name/referral follow-up
- Recruitment personal data processing consent
- Deloitte independent auditor association compliance select
- Booking Holdings group employment check
- SMS/Text interview updates consent
- Booking Holdings job openings & recruitment newsletters opt-in
- Country/Region currently based select
- LinkedIn profile link text
"""

import pytest
from src.sentinel.agent import SentinelAgent
from src.patterns.input_aware_resolver import InputAwareResolver


class DummyAgent(SentinelAgent):
    def __init__(self, platform='linkedin'):
        self._current_platform = platform
        self.profile = {}
        self.patterns = None
        self._norm_pattern_cache = {}
        self._category_index = {}
        self._compiled_regexes = {}
        self._exact_patterns = set()


@pytest.fixture
def agent():
    return DummyAgent('linkedin')


@pytest.fixture
def resolver():
    return InputAwareResolver()


class TestAgodaLinkedInQAPatterns:

    def test_agoda_relocate_work_gurgaon(self, agent):
        q = (
            "This role is based in Gurgaon and follows a hybrid model (3 days in office, 2 days WFH). "
            "Relocation support will be provided (as per policy) — would you be open to relocate and working from Gurgaon if selected?"
        )
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert conf >= 0.95

    def test_relevant_full_time_experience_excluding_internship(self, agent, resolver):
        q = "How many years of relevant full-time experience do you have? (Excluding internship)*"
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "4.2 Years"
        assert conf >= 0.95

        options = ["0-4 Years", "4-8 Years", "8-10 Years", "10-12 Years", "12+ Years"]
        res = resolver.resolve_answer(ans, "select", options, q)
        assert res.selected_option == "4-8 Years"

    def test_exp_leading_large_scale_technical_initiatives(self, agent, resolver):
        q = (
            "How many years of experience do you have leading large-scale technical initiatives across "
            "multiple teams or services (including architecture decisions, system design, stakeholder alignment, and end-to-end delivery)?*"
        )
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "2-4 Years of technical initiatives"
        assert conf >= 0.95

        options = [
            "0-2 Years of technical initiatives",
            "2-4 Years of technical initiatives",
            "4+ Years of technical initiatives"
        ]
        res = resolver.resolve_answer(ans, "select", options, q)
        assert res.selected_option == "2-4 Years of technical initiatives"

    def test_agoda_employee_personal_relationship(self, agent):
        q = "Do you as a candidate have a personal relationship with a current Agoda employee?*"
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert conf >= 0.95

    def test_agoda_employee_referral_follow_ups(self, agent):
        q_rel = "If yes, please indicate how you know the employee?"
        ans_rel, conf_rel = agent._fuzzy_match_question(q_rel)
        assert ans_rel == "N/A"
        assert conf_rel >= 0.95

        q_name = "What is the employee’s name?"
        ans_name, conf_name = agent._fuzzy_match_question(q_name)
        assert ans_name == "N/A"
        assert conf_name >= 0.95

    def test_agoda_recruitment_data_consent(self, agent):
        q = (
            "Do you agree to Agoda’s use of personal data from your application to improve our recruitment experience? "
            "We may collaborate and share your data with third-party providers for recruitment purposes and you may ask to remove your data at any time.*"
        )
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert conf >= 0.95

    def test_deloitte_auditor_association(self, agent, resolver):
        q = (
            "To avoid actual or perceived impairment of our parent company’s independent auditor – Deloitte and to comply "
            "with applicable regulations of Securities and Exchange Commission of the United States, we need to seek approvals "
            "from our parent company before starting the interview process. With this, please confirm if you are currently or formerly "
            "have been associated with Deloitte or any of its subsidiary entities at any time including but not limited to any time "
            "as a direct employee, director, contractor, major shareholder, intern etc.?*"
        )
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"
        assert conf >= 0.95

        options = [
            "Yes, I am a current/an ex-employee of Deloitte (or its Subsidiary companies)",
            "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"
        ]
        res = resolver.resolve_answer(ans, "select", options, q)
        assert res.selected_option == "No, I am not a current/an ex-employee of Deloitte (or its Subsidiary companies)"

    def test_booking_holdings_group_employed(self, agent):
        q = (
            "Are you presently employed by any company within the Booking Holdings group, including but not limited to "
            "Kayak, OpenTable, Booking.com, Rental Cars, RocketMiles, FareHarbor, HotelsCombined, CheapFlights, Momondo, Priceline, or Getaroom?*"
        )
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert conf >= 0.95

    def test_sms_text_updates_consent(self, agent):
        q = "Do you allow us to provide you TEXT/SMS updates of your interview process? We may engage with a service provider to do so."
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert conf >= 0.95

    def test_booking_holdings_recruitment_newsletter(self, agent):
        q = "Email me about other job openings within the Booking Holding’s entities and recruitment-related newsletters*"
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "Yes"
        assert conf >= 0.95

    def test_country_currently_based(self, agent, resolver):
        q = "In which country/region are you currently based?*"
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "India"
        assert conf >= 0.95

        options = ["United States", "India", "United Kingdom", "Singapore", "Thailand"]
        res = resolver.resolve_answer(ans, "select", options, q)
        assert res.selected_option == "India"

    def test_linkedin_profile_link(self, agent):
        q = "LinkedIn Profile Link*"
        ans, conf = agent._fuzzy_match_question(q)
        assert ans == "https://www.linkedin.com/in/siddhant-singh/"
        assert conf >= 0.95
