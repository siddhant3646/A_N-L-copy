import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.patterns.pattern_matcher import create_matcher
from src.patterns.answer_validator import AnswerValidator


class TestQAAuditFixes(unittest.TestCase):
    def setUp(self):
        self.matcher = create_matcher()

    # 1. EEOC Disability & STAR Cross-Contamination Fixes
    def test_disability_status_not_behavioral_essay(self):
        questions = [
            'Disability Status \nRequired',
            'Disability Status',
            'Do you have a disability?',
            'Voluntary self-identification of disability'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertIn("No", ans)
            self.assertNotIn("API response times degraded", ans)
            self.assertNotIn("latency", ans)

    # 2. Compliance & Conflict of Interest Fixes
    def test_conflict_of_interest_returns_no(self):
        questions = [
            'Do you or a close family member have any financial interest in an Endava competitor, supplier, or client? \nRequired',
            'Do you have any conflict of interest?',
            'Financial interest in a competitor'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'No')
            self.assertNotEqual(ans, '4.2')

    # 3. Visa Sponsorship Fixes (Prevent Auto-Rejection)
    def test_visa_sponsorship_returns_no(self):
        questions = [
            'Will you now or in the future require sponsorship for employment visa status? \nRequired\nYes\nNo',
            'Will you now or in the future require sponsorship.',
            'Will you now or at any point in the future require employment visa sponsorship?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertEqual(ans, 'No')

    # 4. Technical Screening & Essay Fixes (Not Digits or Placeholder URLs)
    def test_net_framework_vs_core(self):
        q = 'What is the difference between .NET Framework and .NET Core?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('.NET Core', ans)
        self.assertNotEqual(ans, '4')

    def test_azure_ad_auth(self):
        q = 'Have you implemented Azure AD authentication?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertTrue(ans.startswith('Yes'))
        self.assertNotEqual(ans, '4')

    def test_career_aspirations(self):
        q = 'Tell us why you are interested in this job role. Tell us your career aspirations and where you see yourself in this domain a few years down the line.'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('distributed', ans)
        self.assertNotEqual(ans, '4')

    def test_freshworks_elevator_pitch(self):
        q = 'Take this opportunity to tell us your motivation behind wanting to join Freshworks. You can be as descriptive as you like.'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('Freshworks', ans)
        self.assertNotIn('example.com', ans)

    def test_backend_capability_story(self):
        q = 'Describe a substantial production backend capability you owned: what it did, why it was hard, how you tested it, and how failures were handled.'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('microservices', ans)
        self.assertNotEqual(ans, 'Yes')

    def test_hands_on_vs_management_percentage(self):
        q = 'What % of your time goes into hands-on technical/architecture work vs people management?'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertIn('80%', ans)

    # 5. Compensation & Salary Expectation Fixes
    def test_salary_expectations_return_expected_ctc(self):
        questions = [
            'What are your salary expectations?',
            'What is your salary expectation?',
            'What are your salary expectations in local currency?',
            "What's your CTC expectation ? (Our maximum budget is 18 LPA, Please apply accordingly).",
            'What is your expected compensation?',
            'What is your expected CTC ?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertIn(ans, ['3000000', '30 LPA', '30'])
            self.assertNotIn(ans, ['2300000', '23 LPA', '23'])

    # 6. Notice Period & Date Format Fixes
    def test_notice_period_in_months(self):
        questions = [
            'Notice Period/If ANY? (in months)',
            'Notice period in months',
            'Notice period (in months)'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertEqual(ans, '0.5')
            self.assertNotEqual(ans, '15')

    def test_last_working_day_date_format(self):
        questions = [
            'If you are serving notice, what will be your official last working day?',
            'What is your notice period or last working date?',
            'What is your notice period/Last working date?',
            'What is your official last working day'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"Failed to match {q}")
            ans = res.get('answer', '')
            self.assertIn('Sep', ans)
            self.assertNotEqual(ans, '15')

    def test_join_within_1_month(self):
        q = 'Are you available to join within 1 month? \nRequired'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer', '')
        self.assertEqual(ans, 'Yes')
        self.assertNotEqual(ans, '15')

    # 7. Non-Resume Skills Whitelisting (0 Years / No)
    def test_non_resume_skills_return_zero(self):
        cases = [
            ('How many years of work experience do you have in Fusion/Solidworks/Inventor and other CAD softwares ?', '0'),
            ('How many years of experience do you have in Saviynt Development?', '0'),
            ('How many years of experience do you have in JML?', '0'),
            ('How many years of experience do you have in Blazor?', '0'),
            ('How many years of experience do you have in Sitecore CDP?', '0'),
            ('How many years of experince do you have in PHP & Laravel?', '0'),
            ('How many years of experience as a Business Analyst?', '0'),
            ('Do u have experience in Semi conductor equipment ?? How many years ?', '0'),
            ('How many years of work experience do you have with Go (Programming Language)?', '0'),
            ('How many years of work experience do you have with Salesforce.com?', '0')
        ]
        for q, expected_val in cases:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res, f"For question '{q}'")
            ans = str(res.get('answer', ''))
            self.assertTrue(ans.startswith(expected_val), f"For question '{q}', expected '{expected_val}', got '{ans}'")

    # 8. Profile & Identity Details
    def test_citizenship_and_rsu(self):
        q_cit = 'Please indicate your citizenship'
        res_cit = self.matcher.match_with_details(q_cit)
        self.assertIsNotNone(res_cit)
        self.assertEqual(res_cit.get('answer'), 'Indian')

        q_rsu = 'Please indicate your last RSU'
        res_rsu = self.matcher.match_with_details(q_rsu)
        self.assertIsNotNone(res_rsu)
        self.assertEqual(res_rsu.get('answer'), '0')

    def test_job_title_strict(self):
        q = 'Your title'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        self.assertEqual(res.get('answer'), 'Software Engineer 2')

    def test_social_links_blank_when_not_held(self):
        for q in ['Facebook', 'X (formerly Twitter)']:
            res = self.matcher.match_with_details(q)
            self.assertIsNotNone(res)
            self.assertEqual(res.get('answer'), '__LEAVE_BLANK__')

    # 9. Rating Scale Bounds (1-5)
    def test_rating_scale_bounds(self):
        q = 'Rate your proficiency with data structures, algorithms, and design patterns. (1–5 scale)'
        res = self.matcher.match_with_details(q)
        self.assertIsNotNone(res)
        ans = res.get('answer')
        self.assertEqual(ans, '5')
    # 10. QA Audit fixes: LWD, Requirements, Payroll company, 12th Board %, Portfolio URL, Privacy Policy
    def test_official_last_working_day_date(self):
        q = 'If you are serving notice, what will be your official last working day?'
        ans, score = self.matcher.fuzzy_match(q)
        self.assertIsNotNone(ans)
        self.assertNotEqual(ans, '15')
        self.assertNotEqual(ans, '15 days')
        self.assertRegex(ans, r'\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}')

    def test_meet_position_requirements(self):
        q = 'We have listed qualifications and technical skills and resume you have read them in detail. Do you meet the requirements for this position?'
        ans, score = self.matcher.fuzzy_match(q)
        self.assertEqual(ans, 'Yes')

    def test_current_payroll_company(self):
        for q in [
            'Current Payroll company? As per Aadhar,First Name:Middle name: Last Name:',
            'Which company are you currently working at?'
        ]:
            ans, score = self.matcher.fuzzy_match(q)
            self.assertEqual(ans, 'Everbridge')
            self.assertNotEqual(ans, '2300000')

    def test_12th_board_aggregate_percentage(self):
        q = 'What was your aggregate % in the 12th Board (CBSE or Equivalent)'
        ans, score = self.matcher.fuzzy_match(q)
        self.assertEqual(ans, '85')
        self.assertNotEqual(ans, '4')

    def test_github_portfolio_link_sharing(self):
        q = 'Do you have a GitHub or portfolio link you can share?'
        ans, score = self.matcher.fuzzy_match(q, input_type='text')
        self.assertIn('siddhant3646', ans)
        self.assertNotEqual(ans, 'Yes')

    def test_allow_contact_privacy_policy(self):
        q = 'I am allowing ValGenesis to contact me about future job opportunities for up to 2 years. Privacy Policy'
        ans, score = self.matcher.fuzzy_match(q)
        self.assertEqual(ans, 'Yes')
        self.assertNotEqual(ans, '4')

    # 11. September QA Audit Fixes
    def test_company_work_interest_not_rejected(self):
        questions = [
            'Are You really interested work with TECH Mahindra',
            'Are you interested for Accenture Fulltime Proceedings',
            'Interested to work with Accenture in fulltime proceedings',
            'Are you interested in working with Google?'
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q)
            self.assertEqual(ans, 'Yes', f"Failed on company interest question: {q}")
            self.assertNotEqual(ans, 'No')

    def test_portfolio_link_not_tensorflow(self):
        questions = [
            'Please add your portfolio or best work link here!',
            'Please add your portfolio or best work link here',
            'Portfolio or best work link',
            'Best work link'
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q, input_type='text')
            self.assertIn('siddhant3646.github.io/Portfolio', ans, f"Failed on portfolio link question: {q}")
            self.assertNotEqual(ans, '4.2')
            self.assertNotEqual(ans, '4.2 Years')

    def test_relocation_or_city_presence_returns_yes(self):
        questions = [
            'Are you currently residing in Chennai or willing to relocate to Chennai?',
            'Are you currently residing in Chennai, Tamil Nadu or willing to relocate to Chennai, Tamil Nadu?',
            'Are you currently located in Hyderabad or willing to work from Hyderabad?',
            'Are you currently residing in Chennai or willing to relocate'
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q)
            self.assertEqual(ans, 'Yes', f"Failed on relocation willingness question: {q}")
            self.assertNotEqual(ans, 'No')

    def test_usd_salary_expectations(self):
        q_exp = 'What is your expected salary in USD?'
        ans_exp, score = self.matcher.fuzzy_match(q_exp)
        self.assertEqual(ans_exp, '60000')
        self.assertNotEqual(ans_exp, '3000000')

        q_cur = 'What is your current salary in USD?'
        ans_cur, score = self.matcher.fuzzy_match(q_cur)
        self.assertEqual(ans_cur, '40000')
        self.assertNotEqual(ans_cur, '2300000')

    def test_disability_returns_no(self):
        questions = [
            'Do you have any kind of disability?',
            'Do you have any disability?',
            'Are you a person with disability',
            'Disability of any kind'
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q)
            self.assertIn('No', ans, f"Failed on disability question: {q}")
            self.assertNotEqual(ans, 'Yes')

    def test_textarea_technical_essay(self):
        questions = [
            'Describe your hands-on experience working with Lovable and the applications you’ve built or worked on.',
            'Describe your experience with Supabase, including the backend function...',
            'Describe your experience taking over, troubleshooting, or completing an existing application...'
        ]
        for q in questions:
            ans, score = self.matcher.fuzzy_match(q, input_type='textarea')
            self.assertTrue(len(ans) > 50, f"Answer too short for essay prompt {q}: {ans}")
            self.assertNotIn(ans, ['4.2', '5', '4', 'Yes', 'No'])

    def test_role_seniority_tools_and_mentoring(self):
        q_role = 'How would you best describe your current/most recent role?'
        ans_role, _ = self.matcher.fuzzy_match(q_role)
        self.assertIn('Senior Engineer', ans_role)
        self.assertNotIn('Junior', ans_role)

        q_tools = 'Which of these security/quality scanning tools have you personally integrated into a release pipeline? 1. SonarQube 2. Checkmarx 3. FOSSA'
        ans_tools, _ = self.matcher.fuzzy_match(q_tools)
        self.assertEqual(ans_tools, 'Only one')
        self.assertNotEqual(ans_tools, 'None of these')

        q_mentor = 'Have you mentored engineers or led "Code Guardian"/high-impact code review programs?'
        ans_mentor, _ = self.matcher.fuzzy_match(q_mentor)
        self.assertEqual(ans_mentor, 'Informally mentored 1 2 peers')
        self.assertNotEqual(ans_mentor, 'No experience mentoring')


if __name__ == '__main__':
    unittest.main()

