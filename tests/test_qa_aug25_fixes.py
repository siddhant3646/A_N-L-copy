import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.patterns.pattern_matcher import create_matcher


class TestQAAug25Fixes(unittest.TestCase):
    def setUp(self):
        self.matcher = create_matcher()

    # 1. Adobe Target Experience (User requested 4 years, not DOB 17/12/2000)
    def test_adobe_target_experience_is_4_years(self):
        questions = [
            'How many years of experience do you have in Adobe Target?',
            'Adobe Target experience',
            'How many years of experience in Adobe Target?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertTrue(ans.startswith('4'), f"Expected '4' or '4 Years', got '{ans}'")
            self.assertNotIn('17/12/2000', ans)
            self.assertNotIn('2000', ans)

    # 2. Word Boundary Collisions: DOB vs Adobe, Age vs Languages, Pay vs Payroll
    def test_dob_does_not_collide_with_adobe(self):
        q = 'How many years of experience do you have in Adobe Target?'
        res = self.matcher.match_with_details(q)
        self.assertNotEqual(res.get('answer'), '17/12/2000')

    def test_age_does_not_collide_with_languages(self):
        questions = [
            'Do you code? What languages?',
            'What languages do you code?',
            'Which programming languages do you use?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = res.get('answer', '')
            self.assertIn('Java', ans)
            self.assertNotEqual(ans, 'Please provide')

    def test_current_pay_does_not_collide_with_payroll_company(self):
        q = 'Current Payroll company? As per Aadhar,First Name:Middle name: Last Name:'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertEqual(ans, 'Everbridge')
        self.assertNotEqual(ans, '2300000')

    # 3. Qualification vs Employment Type
    def test_highest_full_time_qualification(self):
        q = 'What is your highest full-time qualification?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('B.Tech', ans)
        self.assertNotEqual(ans, 'Full-time')

    # 4. Cloud Technologies (Not '4' from C++/C# normalization)
    def test_cloud_technologies_description(self):
        questions = [
            'Do you have experience with Cloud technologies? Which ones?',
            'Do you have experience with cloud technologies',
            'Which cloud technologies have you worked on?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = res.get('answer', '')
            self.assertIn('AWS', ans)
            self.assertNotEqual(ans, '4')

    # 5. Compensation: ECTC and Requirements return 30L / 3000000 (Not 23L)
    def test_ectc_and_compensation_requirements(self):
        cases = [
            ('What is your ECTC in Lakhs per annum?', ['3000000', '30']),
            ('What is your CTC expectation?', ['3000000', '30']),
            ('What are your compensation requirements?', ['3000000', '30'])
        ]
        for q, expected_options in cases:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = str(res.get('answer', ''))
            self.assertIn(ans, expected_options, f"For '{q}', expected one of {expected_options}, got '{ans}'")
            self.assertNotIn(ans, ['23', '2300000'])

    # 6. Unit: Months of Experience returns 50 (Not 5)
    def test_months_of_experience(self):
        questions = [
            'How many months of software development experience do you have?',
            'Months of software development experience'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = res.get('answer', '')
            self.assertEqual(ans, '50')
            self.assertNotEqual(ans, '5')

    # 7. Compound Experience Queries
    def test_compound_experience_with_years(self):
        q_java = 'Do you have experience in Java. If yes then please share number of years.'
        res_java = self.matcher.match_with_details(q_java)
        self.assertIsNotNone(res_java)
        self.assertIn('4.2', str(res_java.get('answer')))

        q_k8s = 'Do You have hands on exp in Kubernetes, If yes then please share number of years of exp.'
        res_k8s = self.matcher.match_with_details(q_k8s)
        self.assertIsNotNone(res_k8s)
        self.assertIn('4', str(res_k8s.get('answer')))

    # 8. Unheld Certifications and Prior Offers return No
    def test_f5_certification_returns_no(self):
        q = 'Do you currently hold an active F5 BIG-IP Administrator (F5-CA) 201 Certification?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        self.assertEqual(res.get('answer'), 'No')

    def test_tcs_offer_returns_no(self):
        q = 'Have you received TCS Offer letter(TCS Offer released)before?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        self.assertEqual(res.get('answer'), 'No')

    # 9. Location Specifics
    def test_location_specifics(self):
        q_pune = 'Is your current location Pune?'
        res_pune = self.matcher.match_with_details(q_pune)
        self.assertIsNotNone(res_pune)
        self.assertEqual(res_pune.get('answer'), 'No')

        q_hyd = 'Work from the office in Hyderabad is mandatory, Are you comfortable?'
        res_hyd = self.matcher.match_with_details(q_hyd)
        self.assertIsNotNone(res_hyd)
        self.assertEqual(res_hyd.get('answer'), 'Yes')


if __name__ == '__main__':
    unittest.main()
