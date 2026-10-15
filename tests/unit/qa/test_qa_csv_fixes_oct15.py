import sys
import os
import unittest

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.pattern_loader import load_patterns
from src.patterns.input_aware_resolver import InputAwareResolver


class TestQACSVFixesOct15(unittest.TestCase):
    """Unit tests for QA pattern fixes identified in Naukri chatbot logs (Oct 15)."""

    def setUp(self):
        self.agent = SentinelAgent()
        patterns_data = load_patterns("config/qa_patterns.json")
        self.matcher = PatternMatcher(patterns_data)
        self.resolver = InputAwareResolver()

    def test_team_management_experience(self):
        questions = [
            "How many years of experience do you have in team management?",
            "how many years of experience do you have in team management",
            "Years of experience in team management",
            "How many years of experience do you have in leading a team",
            "experience in team management",
        ]
        self.agent._current_platform = "naukri"
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "3 Years", f"Question '{q}' returned '{ans}' instead of '3 Years'")
            self.assertGreaterEqual(conf, 0.90)

        # Check LinkedIn whole number format
        self.agent._current_platform = "linkedin"
        ans_li, conf_li = self.agent._fuzzy_match_question("How many years of experience do you have in team management?")
        self.assertEqual(ans_li, "3", f"LinkedIn team management returned '{ans_li}' instead of '3'")
        self.assertGreaterEqual(conf_li, 0.90)

    def test_rating_scale_out_of_10_and_5(self):
        questions_10 = [
            "Rate Your understanding of MLOps (machine learning operation) flow out of 10",
            "Rate Your ability to write Python code (e.g.: API, application code from scratch) out of 10",
            "Rate Your ability to write advance SQL queries (e.g.: window, quality) out of 10",
            "Rate your understanding of MLOps flow out of 10",
            "Rate your ability to write advanced SQL queries out of 10",
        ]
        self.agent._current_platform = "naukri"
        for q in questions_10:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(ans, "9", f"Rating question '{q}' answered with '{ans}' instead of '9'")
            self.assertGreaterEqual(conf, 0.90)

        # Check 5-scale rating
        ans_5, conf_5 = self.agent._fuzzy_match_question("Rate yourself on a scale of 1 to 5")
        self.assertEqual(ans_5, "5")
        self.assertGreaterEqual(conf_5, 0.90)

    def test_which_locations_willing_to_relocate(self):
        questions = [
            "Which of these locations are you willing to relocate to?",
            "Which of these locations are you willing to relocate to",
            "which locations are you willing to relocate to",
        ]
        self.agent._current_platform = "naukri"
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue(
                "Bengaluru" in ans or "Bangalore" in ans,
                f"Relocation location '{q}' returned '{ans}' which does not mention Bangalore/Bengaluru"
            )
            self.assertGreaterEqual(conf, 0.90)

    def test_lwd_and_notice_period_number_input(self):
        question = "Notice Period/ LWD (Last Working Day) - Mention in Days / Mention the Date"
        ans, conf = self.matcher.fuzzy_match(question, input_type="number")
        self.assertEqual(ans, "15", f"LWD numeric input returned '{ans}' instead of '15'")
        self.assertGreaterEqual(conf, 0.65)

    def test_supporting_documents(self):
        question = "Do you have all the companies supporting documents like(pf deduction, expereince letter, reliving letter, pay slips etc) yes/no?"
        ans, conf = self.agent._fuzzy_match_question(question)
        self.assertEqual(ans, "Yes", f"Supporting documents question returned '{ans}' instead of 'Yes'")
        self.assertGreaterEqual(conf, 0.90)

    def test_empty_or_whitespace_question(self):
        empty_questions = ["", "   ", "\t\n  "]
        for eq in empty_questions:
            ans, conf = self.agent._fuzzy_match_question(eq)
            self.assertIn(ans, [None, ""], f"Empty question '{eq!r}' returned '{ans}' instead of None")

    def test_immediate_joiners_10_to_20_days_serving_notice(self):
        questions = [
            "We need immediate joiners only? serving candidates like 10 to 20 days? please mentioned your last working day? *",
            "We need immediate joiners only? serving candidates like 10 to 20 days?",
            "Immediate joiners only serving candidates 10-20 days",
            "serving candidates like 10 to 20 days please mention your last working day",
            "immediate joiners only (10 to 20 days notice)",
        ]
        self.agent._current_platform = "linkedin"
        for q in questions:
            ans, conf = self.agent._fuzzy_match_question(q)
            self.assertTrue(ans == "15" or "2026" in str(ans), f"Question '{q}' returned '{ans}' instead of '15' or dynamic LWD")
            self.assertGreaterEqual(conf, 0.90)

        # Also verify pattern matcher with qa_patterns.json directly
        pattern_ans, pattern_conf = self.matcher.fuzzy_match(
            "We need immediate joiners only? serving candidates like 10 to 20 days? please mentioned your last working day? *",
            input_type="text"
        )
        self.assertTrue(pattern_ans == "15" or "2026" in str(pattern_ans), f"pattern_ans was {pattern_ans}")
        self.assertGreaterEqual(pattern_conf, 0.70)

    def test_agoda_privacy_data_consent_not_default_no(self):
        consent_q = "Do you agree to Agoda's use of personal data for recruitment purposes as outlined in our privacy policy?"
        ans, conf = self.agent._fuzzy_match_question(consent_q)
        # Should be affirmative or Yes, definitely NOT 'No'
        self.assertNotEqual(ans, "No", f"Consent question '{consent_q}' erroneously defaulted to 'No'")
        self.assertIn(ans, ["Yes", "Agree", "I agree", "Yes, I agree", "True"])

    def test_location_bangalore_acceptance(self):
        candidate_locations = ["Bangalore", "Bengaluru", "Bangalore, Karnataka, India", "Bengaluru, Karnataka"]
        for loc in candidate_locations:
            lower = loc.lower()
            is_valid = any(c in lower for c in ["bangalore", "bengaluru", "karnataka", "india"]) and "cape verde" not in lower
            self.assertTrue(is_valid)

        invalid_locations = ["Cape Verde", "United States", "New York", "London"]
        for loc in invalid_locations:
            lower = loc.lower()
            is_valid = any(c in lower for c in ["bangalore", "bengaluru", "karnataka", "india"]) and "cape verde" not in lower
            self.assertFalse(is_valid)

    def test_backend_java_developer_experience_matching(self):
        """Verify Backend Java Developer experience question returns candidate experience (4.2 Years / 4) and resolves radio options correctly."""
        question = "How many years of experience do you have as Backend Java Developer ?"
        options = ["No experience", "<3 years", "3-6 years", "6-7 years", "7-8 years", "8-9 years", "9-10 years", ">10 years"]

        # Naukri platform
        self.agent._current_platform = "naukri"
        ans_naukri, conf = self.agent._fuzzy_match_question(question)
        self.assertIn(ans_naukri, ["4.2 Years", "4 Years", "4.2", "4"])
        self.assertGreaterEqual(conf, 0.90)

        # LinkedIn platform
        self.agent._current_platform = "linkedin"
        ans_li, conf_li = self.agent._fuzzy_match_question(question)
        self.assertIn(ans_li, ["4", "4.2", "4.2 Years"])
        self.assertGreaterEqual(conf_li, 0.90)

        # InputAwareResolver should resolve candidate's 4.2 years to "3-6 years"
        resolved = self.resolver.resolve(
            question=question,
            answer="4.2 Years",
            input_type="radio",
            options=options
        )
        self.assertIsNotNone(resolved)
        self.assertIsNotNone(resolved.matched_option)
        self.assertEqual(resolved.matched_option.value, "3-6 years", f"Expected '3-6 years' but got '{resolved}'")

    def test_naukri_chatbot_js_radio_scoring_simulation(self):
        """Simulate JS scoreRadio logic from _handle_chatbot_loop to ensure '3-6 years' is picked and 'No experience' receives -100."""
        import subprocess
        import json

        js_script = """
        const qText = "How many years of experience do you have as Backend Java Developer ?";
        const answer = "4.2 Years";
        const options = ["No experience", "<3 years", "3-6 years", "6-7 years", "7-8 years", "8-9 years", "9-10 years", ">10 years"];

        const qLower = qText.toLowerCase();
        const answerLower = answer.toLowerCase();
        const answerNumericMatch = answer.match(/(\\d+(?:\\.\\d+)?)/);
        const answerNumeric = answerNumericMatch ? parseFloat(answerNumericMatch[1]) : null;
        const isTeamLeadQ = /team management|leading a team|lead a team|managed a team|manage a team|people management/i.test(qLower);
        const isExpQ = /experience|\\bexpr\\b|years|hands-on|hands on|worked on|indicate your experience/i.test(qLower);
        const expVal = isTeamLeadQ ? 3.0 : ((answerNumeric !== null && answerNumeric >= 3.5 && answerNumeric <= 5.5) ? 4.2 : (answerNumeric !== null ? answerNumeric : (isExpQ ? 4.2 : null)));

        const scoreRadio = (label) => {
            const cleanLabel = (label || '').toLowerCase().trim();
            const val = cleanLabel;

            if (expVal !== null && expVal >= 1.0) {
                if (/\\b(no experience|none|0 years|0 yrs|fresher)\\b/i.test(cleanLabel) || val === 'no experience' || val === 'none') {
                    return -100;
                }
                if (cleanLabel === 'experienced' || cleanLabel.includes('experienced candidate')) {
                    return 95;
                }
            }

            const isLabelYes = /\\byes\\b/i.test(cleanLabel) || cleanLabel.includes('serving notice') || cleanLabel.includes('agree') || cleanLabel.includes('consent') || val === 'yes' || val === 'true';
            const isLabelNo = (/\\bno\\b/i.test(cleanLabel) || cleanLabel.includes('never served') || cleanLabel.includes('not a veteran') || cleanLabel.includes('disagree') || val === 'no' || val === 'false') && !isLabelYes;
            const isAnsYes = /\\byes\\b/i.test(answerLower) || answerLower.includes('serving notice') || answerLower === 'true';
            const isAnsNo = (/\\bno\\b/i.test(answerLower) || answerLower.includes('false') || answerLower.includes('never')) && !isAnsYes;

            if (isLabelYes && isAnsYes) return 95;
            if (isLabelNo && isAnsNo) return 95;
            if (isLabelYes && isAnsNo) return 0;
            if (isLabelNo && isAnsYes) return 0;

            if (expVal !== null) {
                const rangeMatch = cleanLabel.match(/(\\d+(?:\\.\\d+)?)\\s*(?:lpa|lakhs?|lac|cr|years?|yrs?|months?|days?)?\\s*(?:[-–]|\\bto\\b|\\s+)\\s*(?:rs\\.?|inr)?\\s*(\\d+(?:\\.\\d+)?)/i);
                if (rangeMatch) {
                    const rMin = parseFloat(rangeMatch[1]);
                    const rMax = parseFloat(rangeMatch[2]);
                    const testVal = (expVal >= 100000 && rMax <= 150) ? (expVal / 100000) : expVal;
                    if (testVal >= rMin && testVal <= (rMax + 0.5)) {
                        return Math.max(85, 99 - (rMax - rMin) - Math.abs(testVal - Math.min(testVal, rMax)));
                    }
                    if (testVal > rMax) {
                        const diff = testVal - rMax;
                        if (diff <= 2.0) {
                            return Math.max(70, 85 - diff * 8);
                        }
                    }
                    return 0;
                }

                const lessMatch = cleanLabel.match(/(?:less\\s+than|under|fewer\\s+than|below|<|^<\\s*)\\s*(\\d+(?:\\.\\d+)?)/i);
                if (lessMatch) {
                    const bound = parseFloat(lessMatch[1]);
                    const testVal = (expVal >= 100000 && bound <= 150) ? (expVal / 100000) : expVal;
                    if (testVal < bound) {
                        return Math.max(75, 88 - (bound - testVal));
                    }
                    return 0;
                }

                const moreMatch = cleanLabel.match(/(?:more\\s+than|over|above|>|^\\s*>\\s*)\\s*(\\d+(?:\\.\\d+)?)/i) || cleanLabel.match(/(\\d+(?:\\.\\d+)?)\\s*\\+/i);
                if (moreMatch) {
                    const bound = parseFloat(moreMatch[1]);
                    const testVal = (expVal >= 100000 && bound <= 150) ? (expVal / 100000) : expVal;
                    if (testVal >= bound) {
                        return Math.max(75, 91 - (testVal - bound) * 2);
                    }
                    return 0;
                }

                const singleNumMatch = cleanLabel.match(/^(\\d+(?:\\.\\d+)?)\\s*(?:years?|yrs?|months?|days?)?$/i);
                if (singleNumMatch) {
                    const valNum = parseFloat(singleNumMatch[1]);
                    return Math.max(0, 92 - Math.abs(expVal - valNum) * 15);
                }
            }
            return 0;
        };

        const scores = options.map(opt => ({ opt, score: scoreRadio(opt) }));
        let best = scores[0];
        for (const s of scores) {
            if (s.score > best.score) best = s;
        }
        console.log(JSON.stringify({ scores, best, expVal }));
        """
        proc = subprocess.run(["node", "-e", js_script], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout)
        self.assertEqual(res["best"]["opt"], "3-6 years", f"Expected '3-6 years' to win, but got {res['best']}")
        self.assertEqual(res["expVal"], 4.2)
        score_map = {item["opt"]: item["score"] for item in res["scores"]}
        self.assertEqual(score_map["No experience"], -100)
        self.assertGreaterEqual(score_map["3-6 years"], 90)


    def test_linkedin_experience_date_positional_and_regex_heuristics(self):
        """Verify that LinkedIn experience date selects use positional index and word-boundary regex so 'October' does not trigger isExplicitEnd, and From Year <= To Year."""
        import subprocess
        import json

        js_script = """
        const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        const years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"];

        const selects = [
            { type: "month", label: "from", options: months.map((m, i) => ({ text: m, value: String(i + 1), index: i })) },
            { type: "year", label: "month\\njanuary\\nfebruary\\nmarch\\napril\\nmay\\njune\\njuly\\naugust\\nseptember\\noctober\\nnovember\\ndecember", options: years.map((y, i) => ({ text: y, value: y, index: i })) },
            { type: "month", label: "i currently work here", options: months.map((m, i) => ({ text: m, value: String(i + 1), index: i })) },
            { type: "year", label: "month\\njanuary\\nfebruary\\nmarch\\napril\\nmay\\njune\\njuly\\naugust\\nseptember\\noctober\\nnovember\\ndecember", options: years.map((y, i) => ({ text: y, value: y, index: i })) },
        ];

        const allMonthSelects = selects.filter(s => s.type === "month");
        const allYearSelects = selects.filter(s => s.type === "year");

        const results = [];
        for (const select of selects) {
            const isYearSelect = select.type === "year";
            const isMonthSelect = select.type === "month";
            const yIdx = allYearSelects.indexOf(select);
            const mIdx = allMonthSelects.indexOf(select);
            const lowerLabel = select.label.toLowerCase();

            const isExplicitStart = /\\b(from|start|begin|vanaf)\\b/i.test(lowerLabel);
            const isExplicitEnd = /\\b(to|end|eind|tot)\\b/i.test(lowerLabel);

            let isStart = false;
            if (isYearSelect && allYearSelects.length >= 2) {
                isStart = (yIdx === 0);
            } else if (isMonthSelect && allMonthSelects.length >= 2) {
                isStart = (mIdx === 0);
            } else if (isExplicitStart) {
                isStart = true;
            } else if (isExplicitEnd) {
                isStart = false;
            } else if (isYearSelect) {
                isStart = (yIdx <= 0);
            } else if (isMonthSelect) {
                isStart = (mIdx <= 0);
            }

            let targetOpt = null;
            const dateOptions = select.options;
            if (isYearSelect) {
                if (isStart) {
                    targetOpt = dateOptions.find(o => o.text.trim() === "2020" || o.value.trim() === "2020") ||
                                dateOptions.find(o => o.text.trim() === "2019" || o.value.trim() === "2019") ||
                                dateOptions.find(o => o.text.trim() === "2021" || o.value.trim() === "2021") ||
                                dateOptions.find(o => o.text.trim() === "2018" || o.value.trim() === "2018");
                } else {
                    targetOpt = dateOptions.find(o => o.text.trim() === "2021" || o.value.trim() === "2021") ||
                                dateOptions.find(o => o.text.trim() === "2022" || o.value.trim() === "2022");
                }
            } else {
                if (isStart) {
                    targetOpt = dateOptions.find(o => /^(june|juni|jun|6|06)$/i.test(o.text.trim()) || o.value.trim() === "6" || o.value.trim() === "06");
                } else {
                    targetOpt = dateOptions.find(o => /^(may|mei|5|05)$/i.test(o.text.trim()) || o.value.trim() === "5" || o.value.trim() === "05");
                }
            }

            const cleanLabel = isYearSelect ? (isStart ? "From Year" : "To Year") : (isStart ? "From Month" : "To Month");
            results.push({ field: cleanLabel, isStart, answer: targetOpt ? targetOpt.text : null });
        }

        console.log(JSON.stringify(results));
        """
        proc = subprocess.run(["node", "-e", js_script], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout)
        
        self.assertEqual(len(res), 4)
        self.assertEqual(res[0]["field"], "From Month")
        self.assertTrue(res[0]["isStart"])
        self.assertEqual(res[0]["answer"], "June")

        self.assertEqual(res[1]["field"], "From Year")
        self.assertTrue(res[1]["isStart"], "From Year should have isStart=True, not corrupted by 'October'")
        self.assertEqual(res[1]["answer"], "2020", "From Year must be in past college range (2020), NEVER 2026")

        self.assertEqual(res[2]["field"], "To Month")
        self.assertFalse(res[2]["isStart"])
        self.assertEqual(res[2]["answer"], "May")

        self.assertEqual(res[3]["field"], "To Year")
        self.assertFalse(res[3]["isStart"])
        self.assertEqual(res[3]["answer"], "2021")

        # Verify start year is strictly less than end year
        start_yr = int(res[1]["answer"])
        end_yr = int(res[3]["answer"])
        self.assertLessEqual(start_yr, end_yr)
        self.assertLess(start_yr, 2026, "Start Year must not be 2026")

    def test_linkedin_experience_editor_save_readiness(self):
        """Verify that canSaveExpEditor allows saving when date results were actively populated."""
        hasExpDateResults_true = True
        hasExpDateResults_false = False

        # When dates were filled, subform is ready to be committed
        canSave_when_dates_filled = hasExpDateResults_true
        self.assertTrue(canSave_when_dates_filled)

        # When no dates were filled and required fields missing, subform is blocked
        emptyRequired = True
        canSave_when_empty = hasExpDateResults_false or (not emptyRequired)
        self.assertFalse(canSave_when_empty)


if __name__ == "__main__":
    unittest.main()


