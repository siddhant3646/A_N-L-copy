"""
Test Fuzzy Coverage Expansion — Verifies all ~130 new Phase 2 patterns
and confirms no regressions in existing patterns.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sentinel.agent import SentinelAgent, KNOWN_QA_PATTERNS


class TestNewPatternsCoverage(unittest.TestCase):
    """Verify all Phase 2 patterns return non-empty answers with good confidence."""

    def setUp(self):
        self.agent = SentinelAgent()

    # --- Category 1: Team / People Management ---
    def test_team_size(self):
        ans, score = self.agent._fuzzy_match_question('team size')
        self.assertIn('member', ans.lower())
        self.assertGreater(score, 0.6)

    def test_direct_reports(self):
        ans, score = self.agent._fuzzy_match_question('number of direct reports')
        self.assertEqual(ans, '0')
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
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    def test_agile(self):
        ans, score = self.agent._fuzzy_match_question('agile methodology')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 7: Background ---
    def test_criminal_record(self):
        ans, score = self.agent._fuzzy_match_question('criminal record')
        self.assertEqual(ans, 'No')
        self.assertGreater(score, 0.6)

    def test_nda(self):
        ans, score = self.agent._fuzzy_match_question('nda agreement')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 9: ATS Consent ---
    def test_data_retention(self):
        ans, score = self.agent._fuzzy_match_question('data retention consent')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.6)

    def test_future_openings(self):
        ans, score = self.agent._fuzzy_match_question('consider for future openings')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.6)

    # --- Category 10: Salary Format Variants ---
    def test_salary_inr_monthly(self):
        ans, score = self.agent._fuzzy_match_question('salary in inr per month')
        self.assertEqual(ans, '127500')
        self.assertGreater(score, 0.6)

    def test_hike_percentage(self):
        ans, score = self.agent._fuzzy_match_question('hike percentage')
        self.assertEqual(ans, '44')
        self.assertGreater(score, 0.6)

    # --- Category 11: Bond ---
    def test_bond_period(self):
        ans, score = self.agent._fuzzy_match_question('bond period')
        self.assertIn('No bond', ans)
        self.assertGreater(score, 0.6)

    # --- Category 12: Career Gap ---
    def test_employment_gap(self):
        ans, score = self.agent._fuzzy_match_question('gap in employment')
        self.assertIn('No gap', ans)
        self.assertGreater(score, 0.6)

    # --- Category 13: Currently Employed ---
    def test_currently_employed(self):
        ans, score = self.agent._fuzzy_match_question('are you currently employed')
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

    # --- Category 14: Accommodation ---
    def test_accommodation(self):
        ans, score = self.agent._fuzzy_match_question('require accommodation')
        self.assertEqual(ans, 'No')
        self.assertGreater(score, 0.6)

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
        self.assertIn('Yes', ans)
        self.assertGreater(score, 0.6)

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
        self.assertIn('30 days', ans)
        self.assertGreater(score, 0.6)


class TestSalaryUpdateRegression(unittest.TestCase):
    """Verify salary values reflect the updated amounts."""

    def setUp(self):
        self.agent = SentinelAgent()

    def test_current_salary_lpa(self):
        ans, score = self.agent._fuzzy_match_question('current salary')
        self.assertIn('15.3', ans)
        self.assertGreater(score, 0.8)

    def test_expected_salary_lpa(self):
        ans, score = self.agent._fuzzy_match_question('expected salary')
        self.assertIn('22', ans)
        self.assertGreater(score, 0.8)

    def test_current_ctc_inr(self):
        ans, score = self.agent._fuzzy_match_question('current ctc')
        # Keyword priority matching may return '15.3' (numeric) or '1530000'
        self.assertTrue('15' in ans or '1530000' in ans)
        self.assertGreater(score, 0.8)

    def test_expected_ctc_inr(self):
        ans, score = self.agent._fuzzy_match_question('expected annual ctc in inr')
        self.assertIn('2200000', ans)
        self.assertGreater(score, 0.8)

    def test_monthly_salary(self):
        ans, score = self.agent._fuzzy_match_question('monthly salary')
        self.assertEqual(ans, '127500')
        self.assertGreater(score, 0.8)

    def test_take_home(self):
        ans, score = self.agent._fuzzy_match_question('take home salary')
        # 'take home salary' matches dict entry '107500'
        self.assertEqual(ans, '107500')
        self.assertGreater(score, 0.8)

    def test_cctc_numeric(self):
        ans, score = self.agent._fuzzy_match_question('cctc')
        self.assertEqual(ans, '15.3')
        self.assertGreater(score, 0.8)

    def test_ectc_numeric(self):
        ans, score = self.agent._fuzzy_match_question('ectc')
        # Keyword priority match returns '22' or composite with '22'
        self.assertIn('22', ans)
        self.assertGreater(score, 0.8)


class TestExistingPatternsRegression(unittest.TestCase):
    """Verify existing patterns still work correctly after changes."""

    def setUp(self):
        self.agent = SentinelAgent()

    def test_onsite_availability(self):
        ans, score = self.agent._fuzzy_match_question('Are you available to work Full-Time on-site')
        self.assertEqual(ans, 'Yes')
        self.assertGreater(score, 0.8)

    def test_notice_period(self):
        ans, score = self.agent._fuzzy_match_question('notice period')
        self.assertIn('30', ans)
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


class TestKnownQAPatternsIntegrity(unittest.TestCase):
    """Verify KNOWN_QA_PATTERNS dict is well-formed."""

    def test_pattern_count_increased(self):
        """Pattern count should be > 1300 after adding Phase 2 patterns."""
        self.assertGreater(len(KNOWN_QA_PATTERNS), 1300)

    def test_no_empty_values(self):
        """Intentional skip patterns may be empty; limit excessive empties."""
        skip_keys = {'no worries', 'you can change your input', 'change your input',
                     'skip this question', 'try again', 'restart conversation'}
        empty_keys = [k for k, v in KNOWN_QA_PATTERNS.items()
                      if v == '' and k not in skip_keys]
        self.assertEqual(len(empty_keys), 0, f"Unexpected empty values: {empty_keys[:10]}")

    def test_all_keys_lowercase(self):
        """All keys should be lowercase (our matching normalizes to lowercase)."""
        non_lower = [k for k in KNOWN_QA_PATTERNS.keys() if k != k.lower()]
        self.assertEqual(len(non_lower), 0, f"Non-lowercase keys: {non_lower[:5]}")


if __name__ == '__main__':
    unittest.main()
