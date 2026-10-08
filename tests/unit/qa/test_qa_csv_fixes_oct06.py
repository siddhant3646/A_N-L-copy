"""
Unit tests for QA CSV audit pattern fixes identified on Oct 6, 2026.

Tests cover all failure modes / incorrectly answered questions from qa_results.csv:
1. Hands-on experience in Java/J2EE (Yes/No)
2. Experience with React (Yes/No)
3. Experience with Angular (Yes/No)
4. Experience developing REST APIs (Yes/No)
5. Experience working with microservices (Yes/No)
6. Fastest ETA from BRD to live in Days
7. Role / Roles applying for
8. Employee's referral name (N/A)
9. Relevant full-time experience excluding internship
10. Deloitte independent auditor association
11. Agoda employee personal relationship
12. Booking Holdings group current employment
13. Strategy former employee / subsidiary affiliation
14. Veteran status self-identification
15. Visa sponsorship requirement
16. Flexibility working from Hyderabad location
17. Discipline / Field of Study
18. Currently attend this institution
19. Current or former Nextiva / Simplify360 employee
20. Nextiva Bengaluru office location alignment
21. Cloud & AI Platform Architecture worked on
22. Team adoption and impact of AI coding tools
23. Willingness to relocate locations list
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


class TestQACSVFixesOct06:
    """Test suite for QA CSV audit fixes on Oct 6, 2026."""

    # 1. Hands-on experience in Java/J2EE
    def test_hands_on_java_j2ee_matcher(self, matcher):
        q = "Do you have strong hands-on experience in Java/J2EE?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_hands_on_java_j2ee_agent(self, agent):
        q = "Do you have strong hands-on experience in Java/J2EE?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 2. Experience with React
    def test_experience_react_matcher(self, matcher):
        q = "Do you have experience with React?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_experience_react_agent(self, agent):
        q = "Do you have experience with React?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 3. Experience with Angular
    def test_experience_angular_matcher(self, matcher):
        q = "Do you have experience with Angular?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_experience_angular_agent(self, agent):
        q = "Do you have experience with Angular?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 4. Experience developing REST APIs
    def test_experience_rest_apis_matcher(self, matcher):
        q = "Do you have experience developing REST APIs?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_experience_rest_apis_agent(self, agent):
        q = "Do you have experience developing REST APIs?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 5. Experience working with microservices
    def test_experience_microservices_matcher(self, matcher):
        q = "Do you have experience working with microservices?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_experience_microservices_agent(self, agent):
        q = "Do you have experience working with microservices?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 6. Fastest ETA from BRD to live in Days
    def test_fastest_eta_matcher(self, matcher):
        q = "From BRD to product live what is the fastest ETA you have achieved in Days?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "14" in ans
        assert score >= 0.85

    def test_fastest_eta_agent(self, agent):
        q = "From BRD to product live what is the fastest ETA you have achieved in Days?"
        ans, score = agent._fuzzy_match_question(q)
        assert "14" in ans
        assert score >= 0.90

    # 7. Role / Roles applying for
    def test_roles_applying_for_matcher(self, matcher):
        q = "What Role / Roles you are applying for?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Software Engineer" in ans or "SDE" in ans
        assert score >= 0.85

    def test_roles_applying_for_agent(self, agent):
        q = "What Role / Roles you are applying for?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Software Engineer" in ans or "SDE" in ans
        assert score >= 0.90

    # 8. Employee Referral Name (N/A)
    def test_employee_referral_name_matcher(self, matcher):
        q = "What is the employee's name?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "N/A"
        assert score >= 0.85

    def test_employee_referral_name_agent(self, agent):
        q = "What is the employee’s name?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "N/A"
        assert score >= 0.90

    # 9. Relevant experience excluding internship
    def test_relevant_exp_excluding_internship_matcher(self, matcher):
        q = "How many years of relevant full-time experience do you have? (Excluding internship)"
        ans, score = matcher.fuzzy_match(q, input_type="select")
        assert "3-5" in ans or "4" in ans
        assert score >= 0.85

    def test_relevant_exp_excluding_internship_agent(self, agent):
        q = "How many years of relevant full-time experience do you have? (Excluding internship)"
        ans, score = agent._fuzzy_match_question(q)
        assert "3-5" in ans or "4" in ans
        assert score >= 0.90

    # 10. Deloitte independent auditor association
    def test_deloitte_auditor_matcher(self, matcher):
        q = "Please indicate if you are currently, or have previously been, associated with Deloitte (e.g. as a partner, principal, director, employee or independent contractor) or have family members who are so associated."
        ans, score = matcher.fuzzy_match(q, input_type="select")
        assert "No" in ans or "never" in ans.lower()
        assert score >= 0.85

    def test_deloitte_auditor_agent(self, agent):
        q = "Deloitte independent auditor association: partner, director, employee or contractor"
        ans, score = agent._fuzzy_match_question(q)
        assert "No" in ans or "never" in ans.lower()
        assert score >= 0.90

    # 11. Agoda personal relationship
    def test_agoda_relationship_matcher(self, matcher):
        q = "Do you as a candidate have a personal relationship with a current Agoda employee?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_agoda_relationship_agent(self, agent):
        q = "Do you as a candidate have a personal relationship with a current Agoda employee?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 12. Booking Holdings group employment
    def test_booking_holdings_matcher(self, matcher):
        q = "Are you presently employed by any company within the Booking Holdings group of companies?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_booking_holdings_agent(self, agent):
        q = "Are you presently employed by any company within the Booking Holdings group of companies?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 13. Strategy former employee
    def test_strategy_former_employee_matcher(self, matcher):
        q = "Are you a former employee of Strategy or any of its past or present subsidiaries or affiliates?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_strategy_former_employee_agent(self, agent):
        q = "Are you a former employee of Strategy or any of its past or present subsidiaries or affiliates?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 14. Veteran status
    def test_veteran_status_matcher(self, matcher):
        q = "Are you a veteran?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_veteran_status_agent(self, agent):
        q = "Are you a protected veteran?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 15. Visa sponsorship
    def test_sponsorship_matcher(self, matcher):
        q = "Will you now or in the future require sponsorship for employment visa status?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_sponsorship_agent(self, agent):
        q = "Will you now or in the future require sponsorship for employment visa status?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 16. Hyderabad location flexibility
    def test_hyderabad_location_flexibility_matcher(self, matcher):
        q = "Are you flexible working from Hyderabad Location ?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "yes"
        assert score >= 0.85

    def test_hyderabad_location_flexibility_agent(self, agent):
        q = "Are you flexible working from Hyderabad Location ?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "yes"
        assert score >= 0.90

    # 17. Discipline / Field of Study
    def test_discipline_field_of_study_matcher(self, matcher):
        q = "Discipline"
        ans, score = matcher.fuzzy_match(q, input_type="select")
        assert "Computer Science" in ans
        assert score >= 0.85

    def test_discipline_field_of_study_agent(self, agent):
        q = "Discipline"
        ans, score = agent._fuzzy_match_question(q)
        assert "Computer Science" in ans
        assert score >= 0.90

    # 18. Currently attend institution
    def test_currently_attend_institution_matcher(self, matcher):
        q = "I currently attend this institution"
        ans, score = matcher.fuzzy_match(q, input_type="checkbox")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_currently_attend_institution_agent(self, agent):
        q = "I currently attend this institution"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 19. Nextiva former employee
    def test_nextiva_former_employee_matcher(self, matcher):
        q = "Are you a current or former Nextiva/Simplify360 employee?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans.lower() == "no"
        assert score >= 0.85

    def test_nextiva_former_employee_agent(self, agent):
        q = "Are you a current or former Nextiva/Simplify360 employee?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans.lower() == "no"
        assert score >= 0.90

    # 20. Nextiva Bengaluru office location alignment
    def test_bengaluru_office_alignment_matcher(self, matcher):
        q = "Nextiva Bengaluru office location alignment"
        ans, score = matcher.fuzzy_match(q, input_type="select")
        assert "Bengaluru" in ans or "onsite" in ans.lower()
        assert "outside" not in ans.lower()
        assert score >= 0.85

    def test_bengaluru_office_alignment_agent(self, agent):
        q = "Nextiva Bengaluru office location alignment"
        ans, score = agent._fuzzy_match_question(q)
        assert "Bengaluru" in ans or "onsite" in ans.lower()
        assert "outside" not in ans.lower()
        assert score >= 0.90

    # 21. Cloud & AI Platform Architecture worked on
    def test_cloud_ai_architecture_matcher(self, matcher):
        q = "What Cloud & AI Platform Architecture you have worked on?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "AWS" in ans
        assert "microservices" in ans.lower()
        assert score >= 0.85

    def test_cloud_ai_architecture_agent(self, agent):
        q = "What Cloud & AI Platform Architecture you have worked on?"
        ans, score = agent._fuzzy_match_question(q)
        assert "AWS" in ans
        assert "microservices" in ans.lower()
        assert score >= 0.90

    # 22. Team adoption of AI coding tools
    def test_ai_coding_tools_adoption_matcher(self, matcher):
        q = "How has your team adopted AI coding tools, and what impact have they had on development speed and code quality?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "GitHub Copilot" in ans or "AI" in ans
        assert "velocity" in ans.lower() or "quality" in ans.lower()
        assert score >= 0.85

    def test_ai_coding_tools_adoption_agent(self, agent):
        q = "How has your team adopted AI coding tools, and what impact have they had on development speed and code quality?"
        ans, score = agent._fuzzy_match_question(q)
        assert "GitHub Copilot" in ans or "AI" in ans
        assert "velocity" in ans.lower() or "quality" in ans.lower()
        assert score >= 0.90

    # 23. Relocation locations list
    def test_relocate_locations_matcher(self, matcher):
        q = "Which of these locations are you willing to relocate to?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Bangalore" in ans
        assert "Hyderabad" in ans
        assert score >= 0.85

    def test_relocate_locations_agent(self, agent):
        q = "Which of these locations are you willing to relocate to?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Bangalore" in ans
        assert "Hyderabad" in ans
        assert score >= 0.90

    # 24. Experience in Java / Go / Rust
    def test_experience_java_go_rust_matcher(self, matcher):
        q = "How many Years of Experience do you have in Java/ Go/ Rust ?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "4.2" in ans
        assert score >= 0.85

    def test_experience_java_go_rust_agent(self, agent):
        q = "How many Years of Experience do you have in Java/ Go/ Rust ?"
        ans, score = agent._fuzzy_match_question(q)
        assert "4.2" in ans
        assert score >= 0.90

    # 25. WFO opportunity in Bangalore HSR + F2F interview + current location readiness
    def test_wfo_bangalore_f2f_interview_location_matcher(self, matcher):
        q = "This is a WFO opportunity in Bangalore Office (HSR layout) , interviews will be Face to face round ONLY, are you ready for it? Where are you currently located? (Apply only if you are ready for F2F round of interview)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Yes" in ans or "ready" in ans.lower()
        assert "Bangalore" in ans
        assert score >= 0.85

    def test_wfo_bangalore_f2f_interview_location_agent(self, agent):
        q = "This is a WFO opportunity in Bangalore Office (HSR layout) , interviews will be Face to face round ONLY, are you ready for it? Where are you currently located? (Apply only if you are ready for F2F round of interview)"
        ans, score = agent._fuzzy_match_question(q)
        assert "Yes" in ans or "ready" in ans.lower()
        assert "Bangalore" in ans
        assert score >= 0.90

    # 26. DSA experience brief
    def test_dsa_experience_brief_matcher(self, matcher):
        q = "Do you have experience in Data Structures and Algorithm? Give brief on the experience here."
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Data Structures" in ans or "Trees" in ans or "Algorithms" in ans
        assert len(ans) > 20
        assert score >= 0.85

    def test_dsa_experience_brief_agent(self, agent):
        q = "Do you have experience in Data Structures and Algorithm? Give brief on the experience here."
        ans, score = agent._fuzzy_match_question(q)
        assert "Data Structures" in ans or "Trees" in ans or "Algorithms" in ans
        assert len(ans) > 20
        assert score >= 0.90

    # 27. Expected CTC in number - LPA (example: 7 if its 7 LPA)
    def test_expected_ctc_in_number_lpa_matcher(self, matcher):
        q = "What is your expected Ctc ? (Answer in number- LPA, example- 7 if its 7 LPA)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "30"
        assert score >= 0.85

    def test_expected_ctc_in_number_lpa_agent(self, agent):
        q = "What is your expected Ctc ? (Answer in number- LPA, example- 7 if its 7 LPA)"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "30"
        assert score >= 0.90

    # 28. How soon can you join (Mention in days)
    def test_how_soon_join_mention_in_days_matcher(self, matcher):
        q = "How soon can you join ? (Mention in days)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "15"
        assert score >= 0.85

    def test_how_soon_join_mention_in_days_agent(self, agent):
        q = "How soon can you join ? (Mention in days)"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "15"
        assert score >= 0.90

    # 29. Expected CTC standard question
    def test_expected_ctc_standard_matcher(self, matcher):
        q = "What is your expected CTC?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "30" in ans
        assert score >= 0.85

    def test_expected_ctc_standard_agent(self, agent):
        q = "What is your expected CTC?"
        ans, score = agent._fuzzy_match_question(q)
        assert "30" in ans
        assert score >= 0.90

