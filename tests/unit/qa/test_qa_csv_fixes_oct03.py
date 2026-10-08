"""
Unit tests for QA CSV audit pattern fixes identified on Oct 3, 2026.

Tests cover all 20 failure modes / incorrectly answered questions from qa_results.csv:
1. Spring Boot modules worked with
2. REST API types developed
3. Complex PostgreSQL query example
4. Database optimization techniques
5. JWT authentication implementations
6. Docker experience descriptive
7. Git repository tools used
8. JavaScript frameworks or libraries worked with
9. Most complex backend application developed
10. Role in designing application architecture
11. Strong fit for Kotlin & Java developer role
12. Endava non-compete agreements
13. Endava competitor/supplier/client financial interest
14. Endava employee/contractor family relationships
15. Reusable software components/libraries example
16. CI/CD pipelines and automated testing contract & quality gates
17. Headline pattern
18. FE fundinfo / Zenith Investment Partners unique ID
19. FE fundinfo / Zenith Investment Partners employment
20. Azure certifications specify
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


class TestQACSVFixesOct03:
    """Test suite for QA CSV audit fixes on Oct 3, 2026."""

    def test_spring_boot_modules_matcher(self, matcher):
        q = "Which Spring Boot modules have you worked with?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "Spring Boot" in ans
        assert "Spring Data JPA" in ans
        assert "Spring Security" in ans
        assert score >= 0.90

    def test_spring_boot_modules_agent(self, agent):
        q = "Which Spring Boot modules have you worked with?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Spring Boot" in ans
        assert "Spring Data JPA" in ans
        assert score >= 0.90

    def test_rest_api_types_matcher(self, matcher):
        q = "What type of REST APIs have you developed?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "RESTful" in ans or "microservices" in ans
        assert score >= 0.90

    def test_rest_api_types_agent(self, agent):
        q = "What type of REST APIs have you developed?"
        ans, score = agent._fuzzy_match_question(q)
        assert "RESTful" in ans or "microservices" in ans
        assert score >= 0.90

    def test_postgresql_complex_query_matcher(self, matcher):
        q = "Share an example of a complex PostgreSQL query you have written."
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "CTEs" in ans or "window functions" in ans
        assert score >= 0.90

    def test_postgresql_complex_query_agent(self, agent):
        q = "Share an example of a complex PostgreSQL query you have written."
        ans, score = agent._fuzzy_match_question(q)
        assert "CTEs" in ans or "window functions" in ans
        assert score >= 0.90

    def test_database_optimization_techniques_matcher(self, matcher):
        q = "What database optimization techniques have you used?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "indexing" in ans.lower()
        assert "explain analyze" in ans.lower()
        assert score >= 0.90

    def test_database_optimization_techniques_agent(self, agent):
        q = "What database optimization techniques have you used?"
        ans, score = agent._fuzzy_match_question(q)
        assert "indexing" in ans.lower()
        assert "explain analyze" in ans.lower()
        assert score >= 0.90

    def test_jwt_authentication_implementations_matcher(self, matcher):
        q = "Which JWT authentication implementations have you worked on?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "stateless authentication" in ans.lower() or "spring security" in ans.lower()
        assert score >= 0.90

    def test_jwt_authentication_implementations_agent(self, agent):
        q = "Which JWT authentication implementations have you worked on?"
        ans, score = agent._fuzzy_match_question(q)
        assert "stateless authentication" in ans.lower() or "spring security" in ans.lower()
        assert score >= 0.90

    def test_docker_experience_descriptive_matcher(self, matcher):
        q = "Describe your experience with Docker in development or deployment."
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "docker" in ans.lower()
        assert "microservices" in ans.lower() or "dockerfiles" in ans.lower()
        assert score >= 0.90

    def test_docker_experience_descriptive_agent(self, agent):
        q = "Describe your experience with Docker in development or deployment."
        ans, score = agent._fuzzy_match_question(q)
        assert "docker" in ans.lower() or "kubernetes" in ans.lower()
        assert score >= 0.90

    def test_git_repository_tools_matcher(self, matcher):
        q = "Which Git repository tools have you used (GitHub, GitLab, Bitbucket, SVN)?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "GitHub" in ans
        assert "GitLab" in ans
        assert score >= 0.90

    def test_git_repository_tools_agent(self, agent):
        q = "Which Git repository tools have you used (GitHub, GitLab, Bitbucket, SVN)?"
        ans, score = agent._fuzzy_match_question(q)
        assert "GitHub" in ans
        assert "GitLab" in ans
        assert score >= 0.90

    def test_javascript_frameworks_libraries_matcher(self, matcher):
        q = "What JavaScript frameworks or libraries have you worked with?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "React.js" in ans
        assert "Node.js" in ans
        assert score >= 0.90

    def test_javascript_frameworks_libraries_agent(self, agent):
        q = "What JavaScript frameworks or libraries have you worked with?"
        ans, score = agent._fuzzy_match_question(q)
        assert "React.js" in ans
        assert "Node.js" in ans
        assert score >= 0.90

    def test_most_complex_backend_application_matcher(self, matcher):
        q = "Describe the most complex backend application you have developed."
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "Everbridge" in ans or "real-time settlement" in ans
        assert score >= 0.90

    def test_most_complex_backend_application_agent(self, agent):
        q = "Describe the most complex backend application you have developed."
        ans, score = agent._fuzzy_match_question(q)
        assert "Everbridge" in ans or "real-time settlement" in ans
        assert score >= 0.90

    def test_role_in_designing_application_architecture_matcher(self, matcher):
        q = "What was your role in designing application architecture?"
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "Software Engineer 2" in ans or "architectural design" in ans
        assert score >= 0.90

    def test_role_in_designing_application_architecture_agent(self, agent):
        q = "What was your role in designing application architecture?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Software Engineer 2" in ans or "architectural design" in ans
        assert score >= 0.90

    def test_why_strong_fit_kotlin_java_role_matcher(self, matcher):
        q = "Describe why you believe you are a strong fit for this Kotlin & Java Developer role."
        ans, score = matcher.fuzzy_match(q, input_type="textarea")
        assert "Kotlin" in ans
        assert "Java" in ans
        assert score >= 0.90

    def test_why_strong_fit_kotlin_java_role_agent(self, agent):
        q = "Describe why you believe you are a strong fit for this Kotlin & Java Developer role."
        ans, score = agent._fuzzy_match_question(q)
        assert "Kotlin" in ans or "Java" in ans
        assert score >= 0.90

    def test_endava_non_compete_matcher(self, matcher):
        q = "Are you currently bound by non-compete agreements with your current or previous employers that would restrict your ability to work for Endava?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "No"
        assert score >= 0.90

    def test_endava_non_compete_agent(self, agent):
        q = "Are you currently bound by non-compete agreements with your current or previous employers that would restrict your ability to work for Endava?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert score >= 0.90

    def test_endava_financial_interest_matcher(self, matcher):
        q = "Do you or a close family member have any financial interest in an Endava competitor, supplier, or client?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "No"
        assert score >= 0.90

    def test_endava_financial_interest_agent(self, agent):
        q = "Do you or a close family member have any financial interest in an Endava competitor, supplier, or client?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert score >= 0.90

    def test_endava_family_relationships_matcher(self, matcher):
        q = "Do you have any personal or family relationships with employees, contractors, suppliers, or clients of Endava?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "No"
        assert score >= 0.90

    def test_endava_family_relationships_agent(self, agent):
        q = "Do you have any personal or family relationships with employees, contractors, suppliers, or clients of Endava?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert score >= 0.90

    def test_reusable_software_components_libraries_matcher(self, matcher):
        q = "Have you developed / owned reusable software components, libraries by multiple applications/teams? Please provide an exp."
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Yes" in ans
        assert "Everbridge" in ans or "libraries" in ans or "reusable" in ans
        assert score >= 0.90

    def test_reusable_software_components_libraries_agent(self, agent):
        q = "Have you developed / owned reusable software components, libraries by multiple applications/teams? Please provide an exp."
        ans, score = agent._fuzzy_match_question(q)
        assert "Yes" in ans
        assert "Everbridge" in ans or "libraries" in ans or "reusable" in ans
        assert score >= 0.90

    def test_cicd_automated_testing_contract_quality_gates_matcher(self, matcher):
        q = "What is your experience in CI/CD pipelines and automated testing? Have you work with unit, integration, contract and quality gates?"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Yes" in ans
        assert "CI/CD" in ans or "testing" in ans or "contract" in ans.lower()
        assert score >= 0.90

    def test_cicd_automated_testing_contract_quality_gates_agent(self, agent):
        q = "What is your experience in CI/CD pipelines and automated testing? Have you work with unit, integration, contract and quality gates?"
        ans, score = agent._fuzzy_match_question(q)
        assert "Yes" in ans
        assert "CI/CD" in ans or "testing" in ans or "contract" in ans.lower()
        assert score >= 0.90

    def test_headline_matcher(self, matcher):
        q = "Headline"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Software Engineer 2 (SDE-2)" in ans
        assert score >= 0.90

    def test_headline_agent(self, agent):
        q = "Headline"
        ans, score = agent._fuzzy_match_question(q)
        assert "Software Engineer 2 (SDE-2)" in ans
        assert score >= 0.90

    def test_fe_fundinfo_unique_id_matcher(self, matcher):
        q = "If currently employed by FE fundinfo or Zenith Investment Partners, please provide your 7-digit Unique ID..."
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert ans == "N/A"
        assert score >= 0.90

    def test_fe_fundinfo_unique_id_agent(self, agent):
        q = "If currently employed by FE fundinfo or Zenith Investment Partners, please provide your 7-digit Unique ID..."
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "N/A"
        assert score >= 0.90

    def test_fe_fundinfo_previous_employment_matcher(self, matcher):
        q = "Have you previously worked for, or are you currently employed by, FE fundinfo or Zenith Investment Partners in any capacity?"
        ans, score = matcher.fuzzy_match(q, input_type="radio")
        assert ans == "No"
        assert score >= 0.90

    def test_fe_fundinfo_previous_employment_agent(self, agent):
        q = "Have you previously worked for, or are you currently employed by, FE fundinfo or Zenith Investment Partners in any capacity?"
        ans, score = agent._fuzzy_match_question(q)
        assert ans == "No"
        assert score >= 0.90

    def test_azure_certifications_specify_matcher(self, matcher):
        q = "Do you have any Azure certifications?(If yes,specify)"
        ans, score = matcher.fuzzy_match(q, input_type="text")
        assert "Azure Fundamentals (AZ-900)" in ans
        assert score >= 0.90

    def test_azure_certifications_specify_agent(self, agent):
        q = "Do you have any Azure certifications?(If yes,specify)"
        ans, score = agent._fuzzy_match_question(q)
        assert "Azure Fundamentals (AZ-900)" in ans
        assert score >= 0.90
