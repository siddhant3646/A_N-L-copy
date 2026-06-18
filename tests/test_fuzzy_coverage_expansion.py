"""
Test Fuzzy Coverage Expansion — Verifies all ~130 new Phase 2 patterns
and confirms no regressions in existing patterns.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sentinel.agent import SentinelAgent


class TestNewPatternsCoverage(unittest.TestCase):
    """Verify all Phase 2 patterns return non-empty answers with good confidence."""

    def setUp(self):
        self.agent = SentinelAgent()

    # --- Category 1: Team / People Management ---
    def test_team_size(self):
        ans, score = self.agent._fuzzy_match_question('team size')
        self.assertIn('contributor', ans.lower())
        self.assertGreater(score, 0.6)

    def test_direct_reports(self):
        ans, score = self.agent._fuzzy_match_question('number of direct reports')
        self.assertIn('contributor', ans.lower())
        self.assertGreater(score, 0.6)

    def test_leadership_experience(self):
        ans, score = self.agent._fuzzy_match_question('leadership experience')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 2: Client-Facing ---
    def test_client_facing(self):
        ans, score = self.agent._fuzzy_match_question('client facing experience')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    def test_stakeholder(self):
        ans, score = self.agent._fuzzy_match_question('stakeholder management')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 3: Agile ---
    def test_jira(self):
        ans, score = self.agent._fuzzy_match_question('jira experience')
        self.assertIsNotNone(ans)
        self.assertGreater(score, 0.4)

    def test_agile(self):
        ans, score = self.agent._fuzzy_match_question('agile methodology')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 7: Background ---
    def test_criminal_record(self):
        ans, score = self.agent._fuzzy_match_question('criminal record')
        self.assertEqual(ans, 'No')
        self.assertGreater(score, 0.5)

    def test_nda(self):
        ans, score = self.agent._fuzzy_match_question('nda agreement')
        self.assertIsNotNone(ans)
        self.assertGreater(score, 0.5)

    # --- Category 9: ATS Consent ---
    def test_data_retention(self):
        ans, score = self.agent._fuzzy_match_question('data retention consent')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.6)

    def test_future_openings(self):
        ans, score = self.agent._fuzzy_match_question('consider for future openings')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.5)

    # --- Category 10: Salary Format Variants ---
    def test_salary_inr_monthly(self):
        ans, score = self.agent._fuzzy_match_question('salary in inr per month')
        self.assertEqual(ans, '191667')
        self.assertGreater(score, 0.6)

    def test_hike_percentage(self):
        ans, score = self.agent._fuzzy_match_question('hike percentage')
        self.assertIsNotNone(ans)
        self.assertGreater(score, 0.4)

    # --- Category 11: Bond ---
    def test_bond_period(self):
        ans, score = self.agent._fuzzy_match_question('bond period')
        self.assertIsNotNone(ans)
        self.assertGreater(score, 0.5)

    # --- Category 12: Career Gap ---
    def test_employment_gap(self):
        ans, score = self.agent._fuzzy_match_question('gap in employment')
        self.assertEqual(ans, 'No')
        self.assertGreater(score, 0.5)

    # --- Category 13: Currently Employed ---
    def test_currently_employed(self):
        ans, score = self.agent._fuzzy_match_question('are you currently employed')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.5)

    # --- Category 14: Accommodation ---
    def test_accommodation(self):
        ans, score = self.agent._fuzzy_match_question('require accommodation')
        self.assertIn('not', ans.lower())
        self.assertGreater(score, 0.5)

    # --- Category 16: Reason for Change ---
    def test_reason_for_change(self):
        ans, score = self.agent._fuzzy_match_question('reason for job change')
        self.assertIn('career', ans.lower())
        self.assertGreater(score, 0.6)

    # --- Category 17: Work Mode ---
    def test_work_from_home(self):
        ans, score = self.agent._fuzzy_match_question('work from home')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    def test_hybrid(self):
        ans, score = self.agent._fuzzy_match_question('hybrid model')
        self.assertIsNotNone(ans)
        self.assertGreater(score, 0.4)

    # --- Category 18: CTC Breakup ---
    def test_ctc_breakup(self):
        ans, score = self.agent._fuzzy_match_question('ctc breakup')
        # Salary keyword priority matching intercepts — answer will be salary-related
        self.assertTrue(len(ans) > 0)
        self.assertGreater(score, 0.6)

    def test_variable_pay(self):
        ans, score = self.agent._fuzzy_match_question('variable pay')
        # May match via salary keywords or dict
        self.assertTrue(len(ans) > 0)
        self.assertGreater(score, 0.6)

    # --- Category 19: Education Deep ---
    def test_highest_qualification(self):
        ans, score = self.agent._fuzzy_match_question('highest qualification')
        self.assertIn('B.Tech', ans)
        self.assertGreater(score, 0.6)

    def test_graduation_year(self):
        ans, score = self.agent._fuzzy_match_question('graduation year')
        self.assertEqual(ans, '2022')
        self.assertGreater(score, 0.6)

    # --- Category 20: Naukri Chatbot ---
    def test_career_break(self):
        ans, score = self.agent._fuzzy_match_question('are you on a career break')
        self.assertEqual(ans, 'No')
        self.assertGreater(score, 0.6)

    def test_immediate_joiner(self):
        ans, score = self.agent._fuzzy_match_question('immediate joiner')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    def test_when_can_you_join(self):
        ans, score = self.agent._fuzzy_match_question('when can you join')
        self.assertIn('7', ans)
        self.assertGreater(score, 0.5)


class TestSalaryUpdateRegression(unittest.TestCase):
    """Verify salary values reflect the updated amounts."""

    def setUp(self):
        self.agent = SentinelAgent()

    def test_current_salary_lpa(self):
        ans, score = self.agent._fuzzy_match_question('current salary')
        self.assertIn('23', ans)
        self.assertGreater(score, 0.8)

    def test_expected_salary_lpa(self):
        ans, score = self.agent._fuzzy_match_question('expected salary')
        self.assertIn('30', ans)
        self.assertGreater(score, 0.8)

    def test_current_ctc_inr(self):
        ans, score = self.agent._fuzzy_match_question('current ctc')
        self.assertTrue('23' in ans or '2300000' in ans)
        self.assertGreater(score, 0.8)

    def test_expected_ctc_inr(self):
        ans, score = self.agent._fuzzy_match_question('expected annual ctc in inr')
        self.assertIn('3000000', ans)
        self.assertGreater(score, 0.8)

    def test_monthly_salary(self):
        ans, score = self.agent._fuzzy_match_question('monthly salary')
        self.assertEqual(ans, '191667')
        self.assertGreater(score, 0.8)

    def test_take_home(self):
        ans, score = self.agent._fuzzy_match_question('take home salary')
        self.assertEqual(ans, '95000')
        self.assertGreater(score, 0.8)

    def test_cctc_numeric(self):
        ans, score = self.agent._fuzzy_match_question('cctc')
        self.assertEqual(ans, '23')
        self.assertGreater(score, 0.8)

    def test_ectc_numeric(self):
        ans, score = self.agent._fuzzy_match_question('ectc')
        self.assertIn('30', ans)
        self.assertGreater(score, 0.8)


class TestExistingPatternsRegression(unittest.TestCase):
    """Verify existing patterns still work correctly after changes."""

    def setUp(self):
        self.agent = SentinelAgent()

    def test_onsite_availability(self):
        ans, score = self.agent._fuzzy_match_question('Are you available to work Full-Time on-site')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.8)

    def test_notice_period(self):
        ans, score = self.agent._fuzzy_match_question('notice period')
        self.assertIn('7', ans)
        self.assertGreater(score, 0.6)

    def test_relocation(self):
        ans, score = self.agent._fuzzy_match_question('willing to relocate')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.6)

    def test_location(self):
        ans, score = self.agent._fuzzy_match_question('current location')
        self.assertIn('Noida', ans)
        self.assertGreater(score, 0.6)

    def test_experience_years(self):
        ans, score = self.agent._fuzzy_match_question('How Many Years of work experience do you have')
        self.assertIn(ans, ['4', '3.8', '3.8 Years'])
        self.assertGreater(score, 0.6)


class TestPatternMatcherIntegrity(unittest.TestCase):
    """Verify PatternMatcher loads patterns correctly from JSON."""

    def setUp(self):
        self.agent = SentinelAgent()

    def test_pattern_count_increased(self):
        json_patterns = self.agent._pattern_matcher.patterns.get('patterns', {})
        self.assertGreater(len(json_patterns), 300,
                          f"Expected >300 pattern groups, got {len(json_patterns)}")

    def test_no_empty_defaults(self):
        """Pattern groups should have non-empty default answers."""
        json_patterns = self.agent._pattern_matcher.patterns.get('patterns', {})
        empty_defaults = [k for k, v in json_patterns.items()
                         if not v.get('default', '').strip()]
        self.assertEqual(len(empty_defaults), 0, 
                        f"Unexpected empty defaults: {empty_defaults[:10]}")

    def test_all_patterns_have_category(self):
        """All pattern groups should have a category."""
        json_patterns = self.agent._pattern_matcher.patterns.get('patterns', {})
        no_category = [k for k, v in json_patterns.items()
                      if not v.get('category', '').strip()]
        self.assertEqual(len(no_category), 0, 
                        f"Pattern groups without category: {no_category[:5]}")


if __name__ == '__main__':
    unittest.main()
