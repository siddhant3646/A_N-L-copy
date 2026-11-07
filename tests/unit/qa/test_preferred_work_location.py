"""Unit tests verifying preferred work location matching in Python and JS."""

import ast
import json
import subprocess
import unittest
from unittest.mock import MagicMock

from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


class TestPreferredWorkLocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.agent = SentinelAgent.__new__(SentinelAgent)
        cls.agent._pattern_matcher = PatternMatcher(cls.patterns)
        cls.agent._fingerprint_matcher = None
        cls.agent._pattern_learner = None
        cls.agent._classifier = None
        cls.agent._self_healing = None
        cls.agent._current_platform = "linkedin"
        cls.agent._detect_platform = lambda: "linkedin"
        cls.agent._detect_negation = lambda q: False

        # Extract js_code for JS unit testing
        with open("src/sentinel/agent.py") as f:
            content = f.read()
        tree = ast.parse(content)
        cls.js_code = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "js_code":
                        if isinstance(node.value, ast.Constant):
                            cls.js_code = node.value.value
                            break
        assert cls.js_code is not None, "js_code not found in agent.py"

    def test_python_preferred_work_location_does_not_trigger_referral(self):
        """Questions containing 'preferred' must not be intercepted by 'referred' in is_referral_question."""
        ans, conf = self.agent._fuzzy_match_question("Select Your Preferred Work Location*")
        self.assertNotEqual(ans, "No")
        self.assertIn("Bangalore", ans)

        ans2, conf2 = self.agent._fuzzy_match_question("Choose the location where you would prefer to work.")
        self.assertNotEqual(ans2, "No")

    def test_python_referral_questions_still_answer_no(self):
        """Legitimate referral questions must still answer 'No'."""
        ans, conf = self.agent._fuzzy_match_question("Are you an employee referral?")
        self.assertEqual(ans, "No")
        ans2, conf2 = self.agent._fuzzy_match_question("Were you referred by someone at the company?")
        self.assertEqual(ans2, "No")

    def test_js_radio_matching_selects_bengaluru(self):
        """findBestRadioMatch and findLocationRadioMatch must select 'Bengaluru, Karnataka, India'."""
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');

        // Extract findBestRadioMatch and findLocationRadioMatch
        const rMatch = code.match(/const findBestRadioMatch = \\([\\s\\S]*?\\n                \\};/);
        const lMatch = code.match(/const findLocationRadioMatch = \\([\\s\\S]*?\\n                \\};/);
        if (!rMatch || !lMatch) {
            console.error('Functions not found');
            process.exit(1);
        }

        global.window = {};
        global.getInputLabelText = (r) => r.label;
        global.resolveDynamic = (x) => x;
        eval(rMatch[0].replace(/^const /, 'global.'));
        eval(lMatch[0].replace(/^const /, 'global.'));

        const createMockRadio = (label, value, id) => ({
            label: label,
            value: value,
            id: id,
            closest: () => null,
            getAttribute: (a) => null,
            querySelector: () => null
        });

        const radios = [
            createMockRadio('Bengaluru, Karnataka, India', 'opt0', 'opt0'),
            createMockRadio('Delhi, India', 'opt1', 'opt1'),
            createMockRadio('Pune District, Maharashtra, India', 'opt2', 'opt2'),
            createMockRadio('Hyderabad, Telangana, India', 'opt3', 'opt3')
        ];

        // Case 1: Pattern answer is multi-city string from location_preferred default
        const multiCityAnswer = "Bangalore, Delhi NCR, Hyderabad, Mumbai, Pune, Gurgaon, Chennai, Kolkata, Ahmedabad, Noida";
        const bestRadioFromAnswer = findBestRadioMatch(multiCityAnswer, radios);

        // Case 2: findLocationRadioMatch fallback
        const bestRadioFromLocation = findLocationRadioMatch(radios);

        console.log(JSON.stringify({
            bestRadioFromAnswer: bestRadioFromAnswer ? bestRadioFromAnswer.label : null,
            bestRadioFromLocation: bestRadioFromLocation ? bestRadioFromLocation.label : null
        }));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["bestRadioFromAnswer"], "Bengaluru, Karnataka, India")
        self.assertEqual(res["bestRadioFromLocation"], "Bengaluru, Karnataka, India")

    def test_js_radio_matching_falls_back_to_relocation_city_when_bengaluru_missing(self):
        """When Bengaluru is not in options, findLocationRadioMatch picks top preferred relocation city."""
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');
        const lMatch = code.match(/const findLocationRadioMatch = \\([\\s\\S]*?\\n                \\};/);
        global.window = {};
        global.getInputLabelText = (r) => r.label;
        eval(lMatch[0].replace(/^const /, 'global.'));

        const radiosNoBlr = [
            { label: 'Chennai, India', value: 'c' },
            { label: 'Pune District, Maharashtra, India', value: 'p' },
            { label: 'Delhi, India', value: 'd' }
        ];

        const match = findLocationRadioMatch(radiosNoBlr);
        console.log(JSON.stringify({ matchedLabel: match ? match.label : null }));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["matchedLabel"], "Delhi, India")

    def test_js_should_default_to_no_for_preferred_locations(self):
        """JS shouldDefaultToNo must not falsely flag preferred location questions as 'No'."""
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');
        const m = code.match(/const shouldDefaultToNo = \\([\\s\\S]*?\\n                \\};/);
        if (!m) {
            console.error('shouldDefaultToNo not found');
            process.exit(1);
        }
        eval(m[0].replace(/^const /, 'global.'));

        const results = {
            preferredWorkLocation: shouldDefaultToNo("Select Your Preferred Work Location*"),
            preferToWork: shouldDefaultToNo("Choose the location where you would prefer to work."),
            preferredLocation: shouldDefaultToNo("preferred location"),
            preferredBaseLocation: shouldDefaultToNo("What is your preferred base location?"),
            referredByEmployee: shouldDefaultToNo("Were you referred by an employee?"),
            employeeReferral: shouldDefaultToNo("Are you an employee referral?"),
            conflictOfInterest: shouldDefaultToNo("Do you have any conflict of interest?"),
            visaSponsorship: shouldDefaultToNo("Do you require visa sponsorship?")
        };
        console.log(JSON.stringify(results));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertFalse(res["preferredWorkLocation"])
        self.assertFalse(res["preferToWork"])
        self.assertFalse(res["preferredLocation"])
        self.assertFalse(res["preferredBaseLocation"])
        self.assertTrue(res["referredByEmployee"])
        self.assertTrue(res["employeeReferral"])
        self.assertTrue(res["conflictOfInterest"])
        self.assertTrue(res["visaSponsorship"])

    def test_js_work_experience_date_select_label_cleans_currently_work_here(self):
        """Work experience End Month dropdown must not be labeled 'I currently work here'."""
        self.assertIn("!/currently work here/i.test(labelText)", self.js_code)

