"""
Unit tests for runtime log fixes identified on Sep 25, 2026.
Tests cover:
- YOE quantity questions (e.g. 'YOE in document parsing / document processing -')
- Compound location + relocation questions
- Role fit rating questions (e.g. 'Rate your fit for this role (1 10)...')
- Technical project walkthrough / strongest backend stack intercepts
- Cloud platforms / Docker / Kubernetes in production
- Salary expectation matching with 'expectation', 'expectations', 'desired'
- Instahyre application metrics tracking
"""

import pytest
from src.sentinel.agent import SentinelAgent


@pytest.fixture
def agent():
    return SentinelAgent()


class TestRuntimeLogFixesSept25:
    """Test suite for runtime log fixes identified across LinkedIn, Naukri, and Instahyre."""

    def test_yoe_document_parsing_linkedin(self, agent):
        """Test that 'YOE in document parsing / document processing -' returns '4' on LinkedIn."""
        agent._current_platform = 'linkedin'
        ans, score = agent._fuzzy_match_question("YOE in document parsing / document processing -")
        assert ans in ('4', '4.2 Years', '4 Years')
        assert score >= 0.90

    def test_yoe_document_parsing_naukri(self, agent):
        """Test that 'YOE in document parsing / document processing -' returns '4.2 Years' on Naukri."""
        agent._current_platform = 'naukri'
        ans, score = agent._fuzzy_match_question("YOE in document parsing / document processing -")
        assert ans == '4.2 Years'
        assert score >= 0.90

    def test_yoe_general_variants(self, agent):
        """Test general YOE phrasings like 'YOE in React', 'Total YOE'."""
        agent._current_platform = 'linkedin'
        ans1, score1 = agent._fuzzy_match_question("YOE in React")
        assert ans1 in ('4', '4.2 Years')
        assert score1 >= 0.90

        ans2, score2 = agent._fuzzy_match_question("Total YOE")
        assert ans2 in ('4', '4 Years')
        assert score2 >= 0.90

    def test_compound_location_relocation(self, agent):
        """Test compound location and relocation questions."""
        q = "Please mention your current location and indicate whether you are open to relocating to other cities (e.g., Pune, Hyderabad, Gurgaon, Bangalore, etc.) if required."
        ans, score = agent._fuzzy_match_question(q)
        assert "Bangalore" in ans
        assert "relocate" in ans.lower()
        assert score >= 0.95

    def test_role_fit_rating(self, agent):
        """Test role fit rating question returns 9."""
        q = "Rate your fit for this role (1 10)..."
        ans, score = agent._fuzzy_match_question(q)
        assert ans == '9'
        assert score >= 0.90

    def test_complex_fullstack_project(self, agent):
        """Test open-ended complex full-stack project description."""
        q = "Tell us about a complex full-stack or backend project you built from scratch"
        ans, score = agent._fuzzy_match_question(q)
        assert "Everbridge" in ans or "microservices" in ans
        assert score >= 0.95

    def test_strongest_backend_technology(self, agent):
        """Test question asking which backend technology the candidate is strongest in."""
        q = "Which backend technology are you strongest in and why?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Java" in ans or "Spring Boot" in ans
        assert score >= 0.95

    def test_cloud_platforms_experience(self, agent):
        """Test question asking for hands-on experience with cloud platforms."""
        q = "Which cloud platforms do you have hands-on experience with?"
        ans, score = agent._fuzzy_match_question(q)
        assert "AWS" in ans
        assert score >= 0.95

    def test_docker_kubernetes_in_production(self, agent):
        """Test question asking about Docker and Kubernetes containerization in production."""
        q = "Have you owned Docker/Kubernetes containerization in production?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Docker" in ans or "Kubernetes" in ans or "Yes" in ans
        assert score >= 0.95

    def test_salary_expectations_with_expectation(self, agent):
        """Test that salary questions with 'expectation' or 'expectations' return expected salary."""
        q = "What are your base salary expectations?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans in ('30', '3000000', '30 LPA')
        assert score >= 0.90
