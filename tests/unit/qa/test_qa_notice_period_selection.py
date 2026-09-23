"""
Test suite for Notice Period option matching and selection.
Verifies resolution of notice period options such as 'Less than a month',
'2 months', '3 months', 'Serving Notice Period', 'Immediate', etc.
"""

import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from patterns.input_aware_resolver import InputAwareResolver, InputType, Option
from sentinel.agent import SentinelAgent


class TestNoticePeriodOptionMatching(unittest.TestCase):
    """Test resolving notice period options across form controls."""

    def setUp(self):
        self.resolver = InputAwareResolver()

    def test_less_than_a_month_option_resolution(self):
        """Test that '15 days' or '15' notice resolves to 'Less than a month' among ['Less than a month', '2 months', '3 months']."""
        options = [
            Option(label="Less than a month", value="less_than_a_month", index=0),
            Option(label="2 months", value="2_months", index=1),
            Option(label="3 months", value="3_months", index=2),
        ]
        
        result = self.resolver.resolve(
            answer="15 days",
            input_type=InputType.RADIO,
            options=options,
            question="Notice Period"
        )
        self.assertIsNotNone(result.matched_option)
        self.assertEqual(result.matched_option.label, "Less than a month")

    def test_less_than_a_month_with_numeric_answer(self):
        """Test with bare numeric answer '15'."""
        options = [
            Option(label="Less than a month", value="less_than_a_month", index=0),
            Option(label="2 months", value="2_months", index=1),
            Option(label="3 months", value="3_months", index=2),
        ]
        
        result = self.resolver.resolve(
            answer="15",
            input_type=InputType.CHECKBOX,
            options=options,
            question="Notice Period*"
        )
        self.assertIsNotNone(result.matched_option)
        self.assertEqual(result.matched_option.label, "Less than a month")

    def test_serving_notice_option_resolution(self):
        """Test that serving notice options are matched."""
        options = [
            Option(label="Serving Notice Period", value="serving", index=0),
            Option(label="30 Days", value="30", index=1),
            Option(label="60 Days", value="60", index=2),
            Option(label="90 Days", value="90", index=3),
        ]
        
        result = self.resolver.resolve(
            answer="15 Days (Serving Notice Period)",
            input_type=InputType.RADIO,
            options=options,
            question="Select your notice period"
        )
        self.assertIsNotNone(result.matched_option)
        self.assertEqual(result.matched_option.label, "Serving Notice Period")

    def test_agent_fuzzy_match_notice_period(self):
        """Test SentinelAgent Python-side fuzzy matching for notice period."""
        agent = SentinelAgent()
        agent._current_platform = "linkedin"
        
        ans, conf = agent._fuzzy_match_question("Notice Period*")
        self.assertIsNotNone(ans)
        self.assertGreaterEqual(conf, 0.90)
        self.assertTrue("15" in str(ans) or "Notice" in str(ans))


if __name__ == '__main__':
    unittest.main()
