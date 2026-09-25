"""
Unit tests for Q&A audit fixes and pattern enhancements (September 24, 2026).

Covers:
1. CTC / Salary questions with '(Cost to Company)' and curly/straight apostrophes ('what\'s' / 'what’s').
2. Locality questions ('current locality', 'current locality in hyderabad', 'current locality in bangalore').
3. Relocation questions asking for preferred cities and zones.
4. SIEM tools and cybersecurity / SOC threat areas.
5. Notice period status choice ('serving notice period or already left').
6. Input-type-aware defaults for the newly added patterns.
"""

import pytest
from src.patterns.pattern_loader import load_patterns, validate_patterns
from src.patterns.pattern_matcher import PatternMatcher
from src.sentinel.agent import SentinelAgent
from src.sentinel.question_classifier import QuestionClassifier
from src.sentinel.question_fingerprint import FingerprintMatcher


class DummyAgent(SentinelAgent):
    """Test agent instance with loaded patterns."""
    def __init__(self, platform='naukri'):
        self._current_platform = platform
        patterns = load_patterns('config/qa_patterns.json')
        self._pattern_matcher = PatternMatcher(patterns)
        self._fingerprint_matcher = FingerprintMatcher()
        self._question_classifier = QuestionClassifier()
        self._learned_patterns = {}
        self._self_healing = None


class TestQACSVAuditFixesSept24:
    """Test suite verifying all recent QA fixes and patterns."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.patterns = load_patterns('config/qa_patterns.json')
        self.matcher = PatternMatcher(self.patterns)
        self.agent_naukri = DummyAgent(platform='naukri')
        self.agent_linkedin = DummyAgent(platform='linkedin')

    def test_json_patterns_schema_valid(self):
        """Ensure config/qa_patterns.json remains 100% schema valid."""
        errors = validate_patterns(self.patterns)
        assert len(errors) == 0, f"Pattern validation errors: {errors}"

    def test_ctc_cost_to_company_variations(self):
        """Verify CTC questions with '(Cost to Company)' and various apostrophes."""
        current_ctc_questions = [
            "What's your current CTC (Cost to Company)?",
            "What’s your current CTC (Cost to Company)?",
            "What is your current CTC (Cost to Company)?",
            "what's your current ctc (cost to company)",
            "what’s your current ctc (cost to company)",
            "current ctc (cost to company)",
            "Current CTC (Cost to Company)?"
        ]
        for q in current_ctc_questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert ans in ['23 LPA', '2300000', '23'], f"Failed for current CTC question '{q}': got {ans}"
            assert conf >= 0.90

        expected_ctc_questions = [
            "What's your expected CTC (Cost to Company)?",
            "What’s your expected CTC (Cost to Company)?",
            "What is your expected CTC (Cost to Company)?",
            "what's your expected ctc (cost to company)",
            "what’s your expected ctc (cost to company)",
            "expected ctc (cost to company)",
            "Expected CTC (Cost to Company)?"
        ]
        for q in expected_ctc_questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert ans in ['30 LPA', '3000000', '30'], f"Failed for expected CTC question '{q}': got {ans}"
            assert conf >= 0.90

    def test_locality_questions(self):
        """Verify locality questions return appropriate city / address."""
        # Generic / Bangalore locality
        bangalore_locality_questions = [
            "What is your current locality?",
            "What is your locality?",
            "Current locality",
            "Current Locality",
            "What is your current locality in Bangalore?",
            "Current locality in Bengaluru"
        ]
        for q in bangalore_locality_questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert "Bengaluru" in ans or "Bangalore" in ans, f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

        # Hyderabad locality
        hyd_locality_questions = [
            "What is your current locality in Hyderabad?",
            "Current locality in Hyderabad",
            "Locality in Hyderabad",
            "Your locality in Hyderabad"
        ]
        for q in hyd_locality_questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert "Hitec City" in ans or "Hyderabad" in ans, f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

    def test_relocation_preferred_cities_and_zones(self):
        """Verify relocation with preferred cities and zones."""
        relocation_questions = [
            "Are you open to relocation or travel for work? If yes, please specify preferred cities and zones",
            "Open to relocation or travel for work? If yes, please specify preferred cities and zones",
            "Please specify preferred cities and zones for relocation",
            "Specify preferred cities and zones"
        ]
        for q in relocation_questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert "Bangalore" in ans or "Preferred cities" in ans or ans == "Yes", f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

    def test_siem_tools_and_soc_threat_areas(self):
        """Verify SIEM tools and SOC threat areas."""
        siem_questions = [
            "Which SIEM tools have you worked with?",
            "SIEM tools have you worked with",
            "Which SIEM tools?",
            "SIEM tools experience"
        ]
        for q in siem_questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert "Sentinel" in ans or "Splunk" in ans, f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

        soc_questions = [
            "Which of the following areas have you worked on? (Select all that apply)",
            "Which of the following areas have you worked on",
            "SOC threat detection vulnerability management",
            "Security operations center threat detection monitoring"
        ]
        for q in soc_questions:
            ans, conf = self.agent_linkedin._fuzzy_match_question(q)
            assert "Security Operations Center" in ans or "Threat Detection" in ans, f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

    def test_serving_notice_period_status_choice(self):
        """Verify notice period status choice question."""
        np_status_questions = [
            "Are you currently serving notice period? or already left",
            "Currently serving notice period? or already left",
            "Serving notice period or already left",
            "Are you serving notice period or already left"
        ]
        for q in np_status_questions:
            ans, conf = self.agent_naukri._fuzzy_match_question(q)
            assert "serving notice" in ans.lower() or "15" in ans or ans == "Yes", f"Failed for '{q}': got {ans}"
            assert conf >= 0.90

    def test_input_type_defaults_for_sept24_patterns(self):
        """Verify input_type_defaults for the newly added pattern groups."""
        patterns_dict = self.patterns.get('patterns', {})

        # SIEM tools
        siem_pattern = patterns_dict.get('siem_security_tools_experience')
        assert siem_pattern is not None
        assert 'Microsoft Sentinel' in siem_pattern['input_type_defaults']['text']
        assert 'Microsoft Sentinel' in siem_pattern['input_type_defaults']['select']

        # Cybersecurity SOC
        soc_pattern = patterns_dict.get('cybersecurity_soc_threat_areas')
        assert soc_pattern is not None
        assert 'Security Operations Center' in soc_pattern['input_type_defaults']['text']
        assert 'Security Operations Center (SOC)' in soc_pattern['input_type_defaults']['checkbox']

        # Locality
        loc_pattern = patterns_dict.get('current_locality')
        assert loc_pattern is not None
        assert 'Bengaluru' in loc_pattern['input_type_defaults']['text']

        # Locality Hyderabad
        hyd_pattern = patterns_dict.get('current_locality_hyderabad')
        assert hyd_pattern is not None
        assert 'Hitec City' in hyd_pattern['input_type_defaults']['text']

        # Relocation cities/zones
        reloc_pattern = patterns_dict.get('relocation_preferred_cities_zones')
        assert reloc_pattern is not None
        assert 'Bangalore' in reloc_pattern['input_type_defaults']['text']

        # Serving notice choice
        np_choice_pattern = patterns_dict.get('serving_notice_period_status_choice')
        assert np_choice_pattern is not None
        assert 'serving notice' in np_choice_pattern['input_type_defaults']['text'].lower()
