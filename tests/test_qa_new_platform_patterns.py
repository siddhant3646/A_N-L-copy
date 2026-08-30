import unittest
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.patterns.pattern_matcher import create_matcher
from src.patterns.input_aware_resolver import InputAwareResolver, Option, InputType as ResolverInputType
from src.sentinel.agent import SentinelAgent


class TestQANewPlatformPatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = create_matcher()
        cls.agent = SentinelAgent()
        cls.resolver = InputAwareResolver()

    # ==========================================
    # 1. Academic Eligibility & Screening (Naukri)
    # ==========================================
    def test_academic_60_percent_criteria(self):
        questions = [
            'Have you scored 60% or above in 10th, 12th, and Graduation?',
            '60% throughout academics (10th, 12th, Graduation)',
            'Do you have 60% and above throughout academics (10th, 12th, B.Tech)?',
            'Minimum 60 percent throughout academics',
            'First class throughout academics'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    def test_academic_backlogs_returns_no(self):
        questions = [
            'Do you have any active backlogs?',
            'Do you have any standing arrears/backlogs',
            'Any live backlogs',
            'History of backlogs/arrears',
            'Active backlogs or arrears'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'No')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'No')
            self.assertGreaterEqual(score, 0.90)

    def test_academic_gap_returns_no(self):
        questions = [
            'Do you have any educational gap?',
            'Have you had any educational gap?',
            'Any gap in education or career',
            'Gap in graduation',
            'More than 1 year education gap'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'No')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'No')
            self.assertGreaterEqual(score, 0.90)

    def test_education_mode_regular(self):
        questions = [
            'Is your graduation regular full time?',
            'Education mode regular or correspondence',
            'Is your degree regular / full-time',
            'Full time regular degree'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertIn('Full-time', res['answer'])

    # ==========================================
    # 2. Employment, Payroll & Compensation
    # ==========================================
    def test_employment_type_permanent(self):
        questions = [
            'Are you a permanent employee or on third-party contract?',
            'What is your employment type (Permanent/Contract)?',
            'Nature of employment (Permanent/Contractual)',
            'Are you on direct company payroll',
            'Are you a permanent employee'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Permanent')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Permanent')
            self.assertGreaterEqual(score, 0.90)

    def test_current_payroll_company(self):
        questions = [
            'Current payroll company name',
            'Who is your current payroll company',
            'Current payroll employer',
            'Name of your payroll organization',
            'Current payroll company'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Everbridge')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Everbridge')
            self.assertGreaterEqual(score, 0.90)

    def test_fixed_variable_breakup(self):
        questions = [
            'Fixed CTC and Variable CTC breakup',
            'What is your current fixed salary?',
            'What is your current variable component?',
            'Breakup of current compensation'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertIn('21 LPA', res['answer'])
            self.assertIn('2 LPA', res['answer'])

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn('21 LPA', ans)
            self.assertIn('2 LPA', ans)

    def test_holding_offers_competing(self):
        questions = [
            'Do you have any offer in hand?',
            'Any holding offers?',
            'What is your holding offer CTC?',
            'Do you have any existing offer?',
            'Holding offer details if any'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'No')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'No')
            self.assertGreaterEqual(score, 0.90)

    def test_notice_period_buyout_and_negotiable(self):
        questions = [
            'Can you buy out your notice period if required?',
            'Is your notice period negotiable?',
            'What is your negotiated notice period?',
            'Can you join in 15 days or less?',
            'Can you join within 15 days or less'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

    # ==========================================
    # 3. Shift Flexibility & Work Schedule
    # ==========================================
    def test_shift_timings_rotational(self):
        questions = [
            'Are you open for rotational shifts?',
            'Are you willing to work in rotational shifts',
            'Comfortable with 24/7 rotational shifts',
            'Are you willing to work in night shifts?',
            'Are you willing to work 24/7 rotational shifts?'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    def test_shift_us_uk_timing(self):
        questions = [
            'Are you comfortable working in US shift / UK shift?',
            'Comfortable with US shift',
            'Comfortable with UK shift',
            'Are you comfortable working in US time zone'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    def test_work_mode_wfo_and_hybrid(self):
        questions = [
            'Are you comfortable working from office 5 days a week?',
            'Comfortable with 5 days WFO',
            'Are you comfortable with 6 days working?',
            'Willing to work from office full time',
            'Work mode preference: Remote/Hybrid/Onsite'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

    # ==========================================
    # 4. Interview Availability & Drives
    # ==========================================
    def test_interview_f2f_availability(self):
        questions = [
            'Can you attend face to face interview in Bangalore?',
            'Can you attend face to face interview in Noida',
            'Are you available for F2F interview this weekend?',
            'Are you available for in-person interview'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    def test_interview_walkin_drive(self):
        questions = [
            'Are you available for walk-in interview on Saturday?',
            'Can you attend walk-in drive this weekend',
            'Available for weekend hiring drive',
            'Can you attend offline drive on Saturday'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    # ==========================================
    # 5. LinkedIn EEO, Demographics & Compliance
    # ==========================================
    def test_eeo_legal_age_18(self):
        questions = [
            'Are you 18 years of age or older?',
            'Are you at least 18 years old',
            'Are you 18 years old or older'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')
            self.assertGreaterEqual(score, 0.90)

    def test_eeo_pronouns(self):
        questions = [
            'What are your preferred pronouns?',
            'Preferred pronouns',
            'What pronouns do you use'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'He/Him/His')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'He/Him/His')
            self.assertGreaterEqual(score, 0.90)

    def test_compliance_non_compete(self):
        questions = [
            'Are you bound by any non-compete or confidentiality agreement?',
            'Are you subject to any non-compete clause',
            'Non-compete or non-solicitation agreement',
            'Do you have any post-employment restrictions'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'No')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'No')
            self.assertGreaterEqual(score, 0.90)

    def test_work_auth_and_sponsorship(self):
        # Work Auth -> Yes
        for q in ['Are you legally authorized to work in India', 'Are you currently legally authorized to work in the country of this job?']:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'Yes')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'Yes')

        # Sponsorship -> No
        for q in ['Will you require employer sponsorship now or in the future?', 'Will you now or in the future require visa sponsorship']:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertEqual(res['answer'], 'No')

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, 'No')

    # ==========================================
    # 6. Technical & Domain Screening
    # ==========================================
    def test_domain_bfsi_fintech(self):
        questions = [
            'Do you have experience in BFSI / Banking domain?',
            'Do you have Fintech domain experience?',
            'Experience in banking, financial services or insurance (BFSI)'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertIn('BFSI', res['answer'])

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn('BFSI', ans)
            self.assertGreaterEqual(score, 0.90)

    def test_kafka_event_streaming(self):
        questions = [
            'Have you worked with Kafka event streaming?',
            'Years of experience in Apache Kafka / Event streaming?',
            'Real-time streaming pipelines with Kafka'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertIn('Kafka', res['answer'])

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn('Kafka', ans)
            self.assertGreaterEqual(score, 0.90)

    def test_production_oncall_support(self):
        questions = [
            'Do you have production on-call / L3 support experience?',
            'Have you handled P1/P2 production incidents?',
            'Experience diagnosing thread dumps and heap dumps in Java'
        ]
        for q in questions:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed on: {q}")
            self.assertIn('production support', res['answer'].lower())

            ans, score = self.agent._fuzzy_match_question(q)
            self.assertIn('production support', ans.lower())
            self.assertGreaterEqual(score, 0.90)

    # ==========================================
    # 7. Advanced Screening Patterns & Caching
    # ==========================================
    def test_notice_resignation_and_early_release(self):
        res1 = self.matcher.match_with_details('Have you formally submitted your resignation?')
        self.assertTrue(res1['matched'])
        self.assertEqual(res1['answer'], 'Yes')

        res2 = self.matcher.match_with_details('Can you get early release from current company?')
        self.assertTrue(res2['matched'])
        self.assertEqual(res2['answer'], 'Yes')

    def test_salary_in_hand_and_minimum_acceptable(self):
        res1 = self.matcher.match_with_details('What is your monthly in-hand / take home salary?')
        self.assertTrue(res1['matched'])
        self.assertEqual(res1['answer'], '160000')

        res2 = self.matcher.match_with_details('What is the minimum CTC you would accept?')
        self.assertTrue(res2['matched'])
        self.assertEqual(res2['answer'], '27 LPA')

    def test_bangalore_zones_and_3_days_wfo(self):
        res1 = self.matcher.match_with_details('Comfortable working from our Bangalore office in Bellandur / Whitefield / Electronic City / Koramangala / Manyata / HSR Layout')
        self.assertTrue(res1['matched'])
        self.assertEqual(res1['answer'], 'Yes')

        res2 = self.matcher.match_with_details('Are you comfortable with 3 days work from office and 2 days work from home')
        self.assertTrue(res2['matched'])
        self.assertEqual(res2['answer'], 'Yes')

    def test_bgv_documents_and_uan(self):
        res1 = self.matcher.match_with_details('Can you provide Form 16, last 3 months salary slips, and bank statement during BGV?')
        self.assertTrue(res1['matched'])
        self.assertEqual(res1['answer'], 'Yes')

        res2 = self.matcher.match_with_details('Do you have an active UAN / PF account?')
        self.assertTrue(res2['matched'])
        self.assertEqual(res2['answer'], 'Yes')

    def test_distributed_caching_and_saga_transactions(self):
        res1 = self.matcher.match_with_details('Experience with Distributed Caching (Redis / Memcached) for session management and rate limiting')
        self.assertTrue(res1['matched'])
        self.assertIn('Redis', res1['answer'])

        res2 = self.matcher.match_with_details('Have you implemented Distributed Transactions (Saga pattern / 2PC / Event Choreography)?')
        self.assertTrue(res2['matched'])
        self.assertIn('Saga', res2['answer'])

    # ==========================================
    # 8. Dynamic Date Markers & Today's Date
    # ==========================================
    def test_dynamic_today_date_resolution(self):
        today_us = datetime.now().strftime('%m/%d/%Y')
        res = self.matcher.match_with_details("Today's date")
        self.assertTrue(res['matched'])
        self.assertEqual(res['answer'], today_us)

    # ==========================================
    # 9. Input Type Defaults & Boolean Resolution
    # ==========================================
    def test_input_type_formatting(self):
        # Academic 60 criteria for radio vs text
        ans_radio, _ = self.matcher.fuzzy_match('60% throughout academics', input_type='radio')
        self.assertEqual(ans_radio, 'Yes')

        # Holding offers for number vs text
        ans_num, _ = self.matcher.fuzzy_match('What is your holding offer CTC?', input_type='number')
        self.assertEqual(ans_num, '0')

        # Monthly take-home for number vs select
        ans_num, _ = self.matcher.fuzzy_match('Monthly take-home salary', input_type='number')
        self.assertEqual(ans_num, '160000')
        ans_sel, _ = self.matcher.fuzzy_match('Monthly take-home salary', input_type='select')
        self.assertEqual(ans_sel, '1.6 Lakhs')

        # Work auth for select vs radio
        ans_sel, _ = self.matcher.fuzzy_match('Are you legally authorized to work in India', input_type='select')
        self.assertEqual(ans_sel, 'Citizen (India)')
        ans_rad, _ = self.matcher.fuzzy_match('Are you legally authorized to work in India', input_type='radio')
        self.assertEqual(ans_rad, 'Yes')

    def test_numeric_to_boolean_option_resolution(self):
        opts = [Option(label='Yes', value='Yes'), Option(label='No', value='No')]
        
        # When candidate has 4.2 years of Java, asking as Yes/No radio group resolves to Yes
        res = self.resolver.resolve('4.2', ResolverInputType.RADIO, opts)
        self.assertEqual(res.matched_option.label, 'Yes')

        # When candidate has 0 years of experience, resolves to No
        res0 = self.resolver.resolve('0', ResolverInputType.RADIO, opts)
        self.assertEqual(res0.matched_option.label, 'No')

        # When candidate has Advanced proficiency, resolves to Yes
        res_adv = self.resolver.resolve('Advanced', ResolverInputType.RADIO, opts)
        self.assertEqual(res_adv.matched_option.label, 'Yes')

    # ==========================================
    # 10. Advanced Distributed Systems & Protocols
    # ==========================================
    def test_advanced_backend_and_architecture_screening(self):
        cases = [
            ('Experience building RPC services using gRPC and Protocol Buffers?', 'gRPC'),
            ('Experience with GraphQL APIs (schemas, resolvers, mutations)?', 'GraphQL'),
            ('Experience building real-time event streaming with WebSockets / SSE?', 'WebSocket'),
            ('Experience tuning JVM memory (Heap, Metaspace, GC tuning with G1GC/ZGC)?', 'JVM'),
            ('Experience with Java concurrency utilities (CompletableFuture, ExecutorService)?', 'CompletableFuture'),
            ('Experience analyzing thread dumps, heap dumps, or using JProfiler / VisualVM?', 'VisualVM'),
            ('Experience managing Kafka consumer groups, partition rebalancing, and commit offsets?', 'Kafka'),
            ('Have you implemented DLQ, exponential backoff retries, and idempotency in message processing?', 'DLQ'),
            ('Experience configuring database connection pooling (HikariCP / DBCP)?', 'HikariCP'),
            ('Experience with database read replicas, master-slave replication, or sharding?', 'replica'),
            ('Experience with Elasticsearch / OpenSearch for full-text search?', 'Elasticsearch'),
            ('Experience with Kubernetes resources (Deployments, Services, Ingress, HPA) and Helm?', 'Kubernetes'),
            ('Experience with distributed tracing (OpenTelemetry, Jaeger, Zipkin)?', 'OpenTelemetry'),
            ('Experience configuring Prometheus metrics (Micrometer) and Grafana dashboards?', 'Prometheus'),
            ('Experience using APM tools (Datadog / New Relic / Dynatrace / Splunk)?', 'Datadog'),
            ('Experience managing secrets with AWS Secrets Manager or HashiCorp Vault?', 'Vault'),
            ('Experience addressing OWASP Top 10 vulnerabilities (SQLi, XSS, CSRF, IDOR)?', 'OWASP'),
            ('Experience setting up code quality gates with SonarQube?', 'SonarQube'),
            ('Experience with Next.js (SSR, SSG, App Router)?', 'Next.js'),
            ('Experience with JUnit 5, Mockito, and Testcontainers for integration tests?', 'JUnit'),
            ('Experience with API testing using RestAssured or Spring MockMvc?', 'RestAssured')
        ]
        for q, substr in cases:
            res = self.matcher.match_with_details(q)
            self.assertTrue(res['matched'], f"PatternMatcher failed for: {q}")
            ans = res.get('answer', '')
            self.assertIn(substr.lower(), ans.lower(), f"Expected '{substr}' in answer for '{q}', got '{ans}'")

    # ==========================================
    # 11. Advanced HR, BGV & Operational Models
    # ==========================================
    def test_advanced_hr_and_compliance_models(self):
        # Resignation acceptance email
        res1 = self.matcher.match_with_details('Can you share resignation acceptance email from current HR?')
        self.assertTrue(res1['matched'])
        self.assertIn('resignation acceptance email', res1['answer'].lower())

        # Driving license
        res2 = self.matcher.match_with_details('Do you have a valid driving license?')
        self.assertTrue(res2['matched'])
        self.assertEqual(res2['answer'], 'Yes')

        # Referral source
        res3 = self.matcher.match_with_details('How did you hear about this position?')
        self.assertTrue(res3['matched'])
        self.assertEqual(res3['answer'], 'LinkedIn')

        # ESOPs / RSUs held -> No
        res4 = self.matcher.match_with_details('Do you currently hold any vested/unvested ESOPs or RSUs?')
        self.assertTrue(res4['matched'])
        self.assertEqual(res4['answer'], 'No')

        # Salary credit matches payslips -> Yes
        res5 = self.matcher.match_with_details('Does your monthly salary credit match your payslips exactly?')
        self.assertTrue(res5['matched'])
        self.assertEqual(res5['answer'], 'Yes')

        # Dual employment / moonlighting -> No
        res6 = self.matcher.match_with_details('Are you engaged in any dual employment, freelancing, or moonlighting?')
        self.assertTrue(res6['matched'])
        self.assertEqual(res6['answer'], 'No')

        # International client visits -> Yes
        res7 = self.matcher.match_with_details('Are you willing and eligible to travel internationally for client visits?')
        self.assertTrue(res7['matched'])
        self.assertEqual(res7['answer'], 'Yes')

        # Work OS preference -> Mac / Linux
        res8 = self.matcher.match_with_details('Preference of work OS (Mac / Linux / Windows)?')
        self.assertTrue(res8['matched'])
        self.assertIn('Mac', res8['answer'])


if __name__ == '__main__':
    unittest.main()
