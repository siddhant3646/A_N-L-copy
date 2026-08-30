import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.patterns.pattern_matcher import create_matcher


class TestQAAug27Fixes(unittest.TestCase):
    def setUp(self):
        self.matcher = create_matcher()

    # 1. Location Updated to Bengaluru
    def test_current_location_is_bengaluru(self):
        questions = [
            'Current Location',
            'Where are you currently based?',
            'Where do you currently live',
            'Your current city'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertIn('Bengaluru', ans)

    # 2. Relocation & City Presence Always Returns Yes
    def test_relocation_and_city_questions_always_return_yes(self):
        questions = [
            'Are you currently in Bangalore?',
            'Are you currently living in Bangalore?',
            'Are you currently in Pune/ open to relocation to Pune?',
            'Are you currently living in or ready to relocate to Gurugram ?',
            'Are you currently residing in Gurugram, Haryana or willing to relocate to Gurugram, Haryana?',
            'Are you currently residing in Hyderabad or willing to relocate to Hyderabad?',
            'Are you Local to Hyderabad',
            'are you ok with the Coimbatore, Tamil Nadu location ?',
            'Are you open to an onsite role in Vapi, Gujarat?',
            'Will you be reliably able to commute or relocate to Indiranagar, Bengaluru location for Work form Office?',
            'Are you willing to relocate?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'Yes', f"For '{q}', expected 'Yes', got '{ans}'")

    # 3. Payment Domain Experience (Not Salary 3000000)
    def test_payment_domain_experience_not_salary(self):
        questions = [
            'How many years of experience do you have in Payment Domain?',
            'How many years of experience you have in Payment Domain',
            'Experience in Payment Domain'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = str(res.get('answer', ''))
            self.assertTrue(ans.startswith('4'), f"Expected '4' or '4.2 Years', got '{ans}'")
            self.assertNotIn('3000000', ans)

    # 4. Educational % Above 50 Threshold (Not Bachelor's Degree)
    def test_educational_percentage_above_50_returns_yes(self):
        questions = [
            'Whether your educational % is above 50 in the 10th std/12thstd/UG/PG:',
            'Whether your educational % is above 50',
            'Percentage is above 50'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = res.get('answer', '')
            self.assertEqual(ans, 'Yes')
            self.assertNotEqual(ans, "Bachelor's Degree")

    # 5. Career / Education Gaps Return No
    def test_career_and_education_gaps_return_no(self):
        questions = [
            'Do you have any gaps in education/career? If having gap, mention the duration:',
            'Do you have any gaps in education/career?',
            'Any Career or educational gap',
            'career or educational gap if any?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'No')
            self.assertNotEqual(ans, 'Yes')

    # 6. TCS Offer / Registration Returns No
    def test_tcs_registration_and_offer_returns_no(self):
        questions = [
            'Have you registered/attended interview/received offer letter from TCS? Mention the year and EP number:',
            'Have you registered/attended interview/received offer letter from TCS'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            ans = res.get('answer', '')
            self.assertEqual(ans, 'No')
            self.assertNotEqual(ans, 'Yes')

    # 7. Open-Ended Technical Experience Descriptions
    def test_aws_cloud_experience_description(self):
        q = 'What is your experience in AWS cloud?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('AWS', ans)
        self.assertIn('EC2', ans)
        self.assertNotEqual(ans, 'Yes')

    def test_auth_rbac_oauth_jwt_description(self):
        q = 'What is your implementing authentication and authorization mechanisms such as OAuth2, JWT, and role-based access control. ?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('OAuth', ans)
        self.assertIn('JWT', ans)
        self.assertNotEqual(ans, 'Yes')

    # 8. Compensation: Expected Salary & Lacs Formatting
    def test_how_much_annual_salary_expecting(self):
        q = 'How much annual salary are you expecting?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = str(res.get('answer', ''))
        self.assertIn(ans, ['3000000', '30 LPA', '30'])
        self.assertNotIn(ans, ['2300000', '23'])

    def test_ctc_in_lacs_formatting(self):
        q_curr = 'What is your current CTC in Lacs per annum?'
        res_curr = self.matcher.match_with_details(q_curr)
        self.assertIsNotNone(res_curr)
        self.assertEqual(res_curr.get('answer'), '23')

        q_exp = 'What is your expected CTC in Lacs per annum?'
        res_exp = self.matcher.match_with_details(q_exp)
        self.assertIsNotNone(res_exp)
        self.assertEqual(res_exp.get('answer'), '30')

    def test_current_and_expected_ctc_combined(self):
        q = 'Current & Expected CTC:'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('23', ans)
        self.assertIn('30', ans)

    # 9. Niche Skills Set to 4.2 Years / Yes as Requested
    def test_niche_non_resume_skills(self):
        cases = [
            ('How many years of experience do you have in Calypso?', '4.2'),
            ('Do you have hands-on experience customizing Frappe/ERPNext (DocTypes, server/client scripts, workflows)', 'Yes'),
            ('How many years of experience do you have in Camunda Bpm?', '4.2'),
            ('How many years of experience do you have in Credit Risk ?', '4.2'),
            ('Rel exp in Incorta?', '4.2'),
            ('How many years of experience do you have in Azure Data Factory?', '4.2'),
            ('How many years of experience do you have in Snowflake?', '4.2'),
            ('How many years of experience do you have in Blockchain?', '4.2'),
            ('How many years of experience do you have in Solana?', '4.2')
        ]
        for q, expected in cases:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = str(res.get('answer', ''))
            self.assertTrue(ans.startswith(expected), f"For '{q}', expected '{expected}', got '{ans}'")

    # 10. Behavioral / Childhood Background Question
    def test_childhood_background_question(self):
        questions = [
            "How's your childhood? Explain it with one paragraph.*",
            "How's your childhood? Explain it with one paragraph.",
            "How is your childhood? Explain it with one paragraph",
            "Describe your childhood"
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertIn('curiosity', ans.lower())
            self.assertIn('software engineer', ans.lower())


if __name__ == '__main__':
    unittest.main()
