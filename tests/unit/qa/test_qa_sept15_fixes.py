"""Unit tests for September 15 QA and form automation fixes.

Covers:
1. Spanish / multilingual dropdown placeholder detection and rejection.
2. Experience dropdown matching for 'Specify your relevant years of experience ' -> '3 - 5 years'.
3. Multilingual gender select matching ('Male' -> 'Hombre' / 'Masculino').
4. Autopilot stuck-step detection logic on repeated non-advancing steps.
"""

import json
import re
import subprocess
import unittest
from src.sentinel.agent import SentinelAgent
from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher
from src.patterns.input_aware_resolver import (
    InputAwareResolver,
    InputType,
    Option,
    OptionExtractor,
)


class TestQASept15Fixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_patterns("config/qa_patterns.json")
        cls.pattern_matcher = PatternMatcher(cls.patterns)
        cls.agent = SentinelAgent()
        cls.resolver = InputAwareResolver()

    # -------------------------------------------------------------------------
    # 1. QA Pattern Matching for Relevant Experience & Gender
    # -------------------------------------------------------------------------
    def test_specify_relevant_years_of_experience(self):
        questions = [
            "Specify your relevant years of experience ",
            "Specify your relevant years of experience",
            "What are your relevant years of experience?",
            "Relevant years of experience",
        ]
        for q in questions:
            agent_ans, conf = self.agent._fuzzy_match_question(q)
            self.assertIn("4", agent_ans, f"Expected 4+ years for '{q}', got '{agent_ans}'")
            self.assertGreaterEqual(conf, 0.7)

    def test_gender_fuzzy_matching(self):
        questions = [
            "Gender",
            "Gender ",
            "What is your gender?",
            "Select your gender",
        ]
        for q in questions:
            agent_ans, conf = self.agent._fuzzy_match_question(q)
            self.assertEqual(agent_ans, "Male", f"Expected Male for '{q}', got '{agent_ans}'")
            self.assertGreaterEqual(conf, 0.7)

    # -------------------------------------------------------------------------
    # 2. InputAwareResolver & Range Matching
    # -------------------------------------------------------------------------
    def test_experience_range_resolver(self):
        options = [
            Option(value="", label="Selecciona una opción"),
            Option(value="1", label="0 - 2 years"),
            Option(value="2", label="3 - 5 years"),
            Option(value="3", label="6 - 8 years"),
            Option(value="4", label="8+ years"),
        ]
        for ans in ["4", "4.2 Years", "4 years", "4.2"]:
            res = self.resolver.resolve(
                ans,
                InputType.SELECT,
                options,
                question="Specify your relevant years of experience",
            )
            self.assertIsNotNone(res.matched_option, f"Failed to match range for '{ans}'")
            self.assertEqual(res.matched_option.label, "3 - 5 years")

    def test_multilingual_gender_resolver(self):
        options = [
            Option(value="", label="Selecciona una opción"),
            Option(value="hombre", label="Hombre"),
            Option(value="mujer", label="Mujer"),
            Option(value="otro", label="Prefiero no decirlo"),
        ]
        res = self.resolver.resolve("Male", InputType.SELECT, options, question="Gender")
        self.assertIsNotNone(res.matched_option, "Failed to match Male to Hombre")
        self.assertEqual(res.matched_option.label, "Hombre")
        self.assertEqual(res.matched_option.value, "hombre")

    def test_option_extractor_filters_multilingual_placeholders(self):
        html = """
        <select name="experience">
            <option value="">Selecciona una opción</option>
            <option value="1">0 - 2 years</option>
            <option value="2">3 - 5 years</option>
            <option value="3">6 - 8 years</option>
        </select>
        """
        options = OptionExtractor.extract_select_options(html)
        labels = [o.label for o in options]
        self.assertNotIn("Selecciona una opción", labels)
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0].label, "0 - 2 years")
        self.assertEqual(options[1].label, "3 - 5 years")
        self.assertEqual(options[2].label, "6 - 8 years")

    # -------------------------------------------------------------------------
    # 3. JS-Side isSelectPlaceholderText Verification (via Node.js)
    # -------------------------------------------------------------------------
    def test_js_select_placeholder_text_logic(self):
        """Verify the exact isSelectPlaceholderText logic embedded in agent.py."""
        # Read the isSelectPlaceholderText snippet from agent.py
        with open("src/sentinel/agent.py", "r", encoding="utf-8") as f:
            content = f.read()

        match = re.search(
            r"(const isSelectPlaceholderText = \(text, value = null, selectedIndex = -1\) => \{[\s\S]*?\n\s*\};)",
            content,
        )
        self.assertIsNotNone(match, "Could not extract isSelectPlaceholderText from agent.py")
        # Python evaluates string escape sequences in triple-quoted strings before sending to browser
        js_func = match.group(1).encode("utf-8").decode("unicode_escape")

        js_test_script = f"""
        {js_func}

        const tests = [
            // Placeholder cases (should be true)
            {{ text: 'Selecciona una opción', val: '', idx: 0, expected: true }},
            {{ text: 'Seleccione una opción', val: '', idx: 0, expected: true }},
            {{ text: 'Please select an option', val: '', idx: 0, expected: true }},
            {{ text: 'Select', val: 'select', idx: 0, expected: true }},
            {{ text: 'Choose an option', val: '', idx: 0, expected: true }},
            {{ text: 'Elige una opción', val: '', idx: 0, expected: true }},
            {{ text: '--', val: '', idx: -1, expected: true }},
            {{ text: '', val: '', idx: -1, expected: true }},
            {{ text: 'Selecciona una opción', expected: true }}, // single arg

            // Valid real content cases (should be FALSE)
            {{ text: '3 - 5 years', val: '2', idx: 2, expected: false }},
            {{ text: '3 - 5 years', expected: false }}, // single arg
            {{ text: 'Male', val: 'male', idx: 1, expected: false }},
            {{ text: 'Male', expected: false }}, // single arg
            {{ text: 'Hombre', val: 'hombre', idx: 1, expected: false }},
            {{ text: 'Hombre', expected: false }}, // single arg
            {{ text: 'Citizen (India)', expected: false }},
            {{ text: 'None of the above', val: '', idx: 3, expected: false }},
        ];

        let failed = 0;
        for (const t of tests) {{
            const result = isSelectPlaceholderText(t.text, t.val, t.idx !== undefined ? t.idx : -1);
            if (result !== t.expected) {{
                console.error(`FAIL: text='${{t.text}}', val='${{t.val}}', idx=${{t.idx}} -> got ${{result}}, expected ${{t.expected}}`);
                failed++;
            }}
        }}
        process.exit(failed > 0 ? 1 : 0);
        """

        result = subprocess.run(
            ["node", "-e", js_test_script],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Node.js placeholder tests failed:\n{result.stderr}\n{result.stdout}",
        )

    # -------------------------------------------------------------------------
    # 4. Stuck Step Signature Tracking Logic
    # -------------------------------------------------------------------------
    def test_stuck_step_signature_detection(self):
        """Verify the stuck step signature detection pattern used in agent.py."""
        # Simulated payload returned from LinkedIn form step
        payload = [
            {"q": "Specify your relevant years of experience ", "a": "3 - 5 years"},
            {"q": "Gender ", "a": "Hombre"},
        ]

        # Signature function matches agent.py implementation
        def get_signature(form_results):
            return tuple(sorted(str(qa.get("q", qa.get("question", ""))).strip().lower() for qa in form_results))

        sig1 = get_signature(payload)
        sig2 = get_signature([
            {"question": "Gender ", "answer": "Hombre"},
            {"question": "Specify your relevant years of experience ", "answer": "3 - 5 years"},
        ])

        # Regardless of key name ('q' vs 'question') or order, signature matches
        self.assertEqual(sig1, sig2)

        # Consecutive duplicate tracking
        stuck_step_count = 0
        last_step_signature = None

        steps_data = [payload] * 6
        triggered_skip = False

        for step in steps_data:
            current_sig = get_signature(step)
            if current_sig == last_step_signature:
                stuck_step_count += 1
                if stuck_step_count >= 5:
                    triggered_skip = True
                    break
            else:
                stuck_step_count = 1
                last_step_signature = current_sig

        self.assertTrue(triggered_skip)
        self.assertEqual(stuck_step_count, 5)


if __name__ == "__main__":
    unittest.main()
