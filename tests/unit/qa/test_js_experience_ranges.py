"""Unit tests verifying JS form-filling functions in agent.py select 4-6 over 2-4 for candidate with 4.2 years experience."""

import ast
import json
import subprocess
import unittest


class TestJSExperienceRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def test_js_find_best_match_select_dropdown(self):
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');
        const fnMatch = code.match(/const findBestMatch = \\([\\s\\S]*?\\n                \\};/);
        if (!fnMatch) {
            console.log(JSON.stringify({ error: "findBestMatch not found" }));
            process.exit(1);
        }
        global.window = {};
        const isSelectPlaceholderText = () => false;
        const resolveDynamic = (x) => x;
        eval(fnMatch[0].replace(/^const /, 'global.'));

        const options = [
            { text: "2-4 years", value: "opt1", index: 1 },
            { text: "4-6 years", value: "opt2", index: 2 }
        ];

        const match4_2 = findBestMatch("4.2", options);
        const match4 = findBestMatch("4", options);
        const match4Years = findBestMatch("4 Years", options);

        console.log(JSON.stringify({
            match4_2: match4_2 ? match4_2.text : null,
            match4: match4 ? match4.text : null,
            match4Years: match4Years ? match4Years.text : null
        }));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["match4_2"], "4-6 years")
        self.assertEqual(res["match4"], "4-6 years")
        self.assertEqual(res["match4Years"], "4-6 years")

    def test_js_find_best_radio_match(self):
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');
        const fnMatch = code.match(/const findBestRadioMatch = \\([\\s\\S]*?\\n                \\};/);
        if (!fnMatch) {
            console.log(JSON.stringify({ error: "findBestRadioMatch not found" }));
            process.exit(1);
        }
        
        global.getInputLabelText = (r) => r.getAttribute('data-label') || '';
        global.CSS = { escape: (s) => s };
        const resolveDynamic = (x) => x;
        
        eval(fnMatch[0].replace(/^const /, 'global.'));

        const r1 = { id: 'r1', value: '2-4', getAttribute: () => '2-4 years', closest: () => null, parentElement: null };
        const r2 = { id: 'r2', value: '4-6', getAttribute: () => '4-6 years', closest: () => null, parentElement: null };
        const radios = [r1, r2];

        const match4_2 = findBestRadioMatch("4.2", radios);
        const match4 = findBestRadioMatch("4", radios);
        const match4Years = findBestRadioMatch("4 Years", radios);

        console.log(JSON.stringify({
            match4_2: match4_2 ? match4_2.value : null,
            match4: match4 ? match4.value : null,
            match4Years: match4Years ? match4Years.value : null
        }));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["match4_2"], "4-6")
        self.assertEqual(res["match4"], "4-6")
        self.assertEqual(res["match4Years"], "4-6")

    def test_js_find_best_custom_radio_match(self):
        script = """
        const fs = require('fs');
        const code = fs.readFileSync(0, 'utf-8');
        const fnMatch = code.match(/const findBestCustomRadioMatch = \\([\\s\\S]*?\\n                \\};/);
        if (!fnMatch) {
            console.log(JSON.stringify({ error: "findBestCustomRadioMatch not found" }));
            process.exit(1);
        }
        
        global.getInputLabelText = (r) => r.getAttribute('data-label') || '';
        
        eval(fnMatch[0].replace(/^const /, 'global.'));

        const r1 = {
            id: 'r1',
            value: '2-4',
            getAttribute: () => '2-4 years',
            querySelector: () => ({ innerText: '2-4 years' }),
            innerText: '2-4 years'
        };
        const r2 = {
            id: 'r2',
            value: '4-6',
            getAttribute: () => '4-6 years',
            querySelector: () => ({ innerText: '4-6 years' }),
            innerText: '4-6 years'
        };
        const radios = [r1, r2];

        const match4_2 = findBestCustomRadioMatch("4.2", radios);
        const match4 = findBestCustomRadioMatch("4", radios);
        const match4Years = findBestCustomRadioMatch("4 Years", radios);

        console.log(JSON.stringify({
            match4_2: match4_2 ? match4_2.value : null,
            match4: match4 ? match4.value : null,
            match4Years: match4Years ? match4Years.value : null
        }));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["match4_2"], "4-6")
        self.assertEqual(res["match4"], "4-6")
        self.assertEqual(res["match4Years"], "4-6")

    def test_js_code_syntax_and_location_matching(self):
        script = r"""
        const fs = require('fs');
        let code = fs.readFileSync(0, 'utf-8');
        code = code.replace(/\x08/g, '\\b');

        // 1. Verify entire script compiles cleanly
        try {
            new Function(code);
        } catch (e) {
            console.error("SyntaxError in js_code:", e.message);
            process.exit(1);
        }

        // 2. Extract fuzzyMatch function to verify location matching
        const fnMatch = code.match(/const fuzzyMatch = \([\s\S]*?\n                \};/);
        if (!fnMatch) {
            console.error("fuzzyMatch not found in js_code");
            process.exit(1);
        }

        global.window = { location: { hostname: 'www.linkedin.com' }, __SENTINEL_PATTERNS__: {} };
        global.KNOWN_PATTERNS = {};
        global.SYNONYMS = {};
        global.STOP_WORDS_SET = new Set();
        global.extractKeywords = (text) => new Set((text || '').toLowerCase().split(/\s+/));
        const resolveDynamic = (x) => x;
        eval(fnMatch[0].replace(/^const /, 'global.'));

        const checks = {
            bangalore: fuzzyMatch("Are you currently located in Bangalore?"),
            bengaluru: fuzzyMatch("Is your current location Bengaluru?"),
            ahmedabad: fuzzyMatch("Are you currently located in Ahmedabad?"),
            gandhinagar: fuzzyMatch("Is your current location Gandhinagar?"),
            hyderabad: fuzzyMatch("Are you currently living in Hyderabad?"),
            pune: fuzzyMatch("Are you currently residing in Pune?"),
            delhi: fuzzyMatch("Are you currently based in Delhi?"),
            mumbai: fuzzyMatch("Is your current location Mumbai?"),
            jaipur: fuzzyMatch("Are you currently located in Jaipur?"),
            kochi: fuzzyMatch("Are you currently located in Kochi?"),
            chennai: fuzzyMatch("Are you currently located in Chennai?"),
            kolkata: fuzzyMatch("Are you currently located in Kolkata?"),
            relocate_pune: fuzzyMatch("Are you willing to relocate to Pune?")
        };

        console.log(JSON.stringify(checks));
        """
        proc = subprocess.run(["node", "-e", script], input=self.js_code, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(proc.stdout)
        self.assertEqual(res["bangalore"], "Yes")
        self.assertEqual(res["bengaluru"], "Yes")
        self.assertEqual(res["ahmedabad"], "No")
        self.assertEqual(res["gandhinagar"], "No")
        self.assertEqual(res["hyderabad"], "No")
        self.assertEqual(res["pune"], "No")
        self.assertEqual(res["delhi"], "No")
        self.assertEqual(res["mumbai"], "No")
        self.assertEqual(res["jaipur"], "No")
        self.assertEqual(res["kochi"], "No")
        self.assertEqual(res["chennai"], "No")
        self.assertEqual(res["kolkata"], "No")
        # Relocation questions should not be intercepted as 'No' by the location check
        self.assertNotEqual(res["relocate_pune"], "No")


if __name__ == "__main__":
    unittest.main()
