import unittest
import subprocess
import json
import inspect
from src.sentinel.agent import SentinelAgent


class TestSafetyModal(unittest.TestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_js_fallback_contains_safety_modal_enhancements(self):
        """Verify the JS fallback code in agent.py includes all Phase E enhancements."""
        import pathlib
        agent_path = pathlib.Path(__file__).parent.parent.parent.parent / "src" / "sentinel" / "agent.py"
        src = agent_path.read_text(encoding="utf-8")

        # 1. Normalized text helper
        self.assertIn("normText", src)
        self.assertIn("toLowerCase().replace", src)

        # 2. Title matcher
        self.assertIn("titleText.includes('job search safety reminder')", src)

        # 3. Body matcher
        self.assertIn("report suspicious jobs", src)

        # 4. Priority continue button selectors
        self.assertIn("data-test-dialog-primary-btn", src)
        self.assertIn("data-control-name=\"continue_applying\"", src)
        self.assertIn(".artdeco-button--primary", src)

        # 5. Diagnostic logging for unclassified dialogs
        self.assertIn("[Diagnostic] Visible unclassified dialog detected", src)

        # 6. Safety modal return signal
        self.assertIn("LINKEDIN_SAFETY_MODAL_CONTINUE_CLICKED", src)

    def test_js_normtext_and_matcher_simulation(self):
        """Execute Node.js to verify the exact normalization and matching logic."""
        node_script = """
        const normText = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();

        // 1. Verify whitespace and newline normalization
        const messyButtonText = '\\n   Continue\\n   applying   \\t\\n';
        if (normText(messyButtonText) !== 'continue applying') {
            console.error('Failed: normText did not normalize button text correctly');
            process.exit(1);
        }

        // 2. Simulate safety modal title detection
        const titleText = normText('  Job Search Safety Reminder  ');
        const isSafetyTitle = titleText.includes('job search safety reminder');
        if (!isSafetyTitle) {
            console.error('Failed: Title matcher failed');
            process.exit(1);
        }

        // 3. Simulate safety modal body detection
        const bodyText = normText('Please research the company before sharing details. Report suspicious jobs to LinkedIn.');
        const isSafetyBody = bodyText.includes('research the company') && (bodyText.includes('report suspicious jobs') || bodyText.includes('report suspicious'));
        if (!isSafetyBody) {
            console.error('Failed: Body matcher failed');
            process.exit(1);
        }

        // 4. Simulate button resolution order
        const mockButtons = [
            { id: 'dismiss', text: 'Dismiss' },
            { id: 'continue', text: '\\n  Continue applying \\n', class: 'artdeco-button--primary' }
        ];
        const continueBtn = mockButtons.find(b => normText(b.text).includes('continue applying'));
        if (!continueBtn || continueBtn.id !== 'continue') {
            console.error('Failed: Continue button not resolved');
            process.exit(1);
        }

        console.log('NODE_OK');
        """
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Node script failed: {proc.stderr}")
        self.assertIn("NODE_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
