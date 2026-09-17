import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import inspect
from src.sentinel.agent import SentinelAgent


class TestLinkedInCustomDropdown(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.agent = SentinelAgent()

    def test_custom_dropdown_prefill_check_in_script(self):
        """Verify _handle_scripted_fallback checks for prefilled custom dropdowns using multi-source reading."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        
        # Check that isUnselected does not use flawed !dropdown.getAttribute('aria-expanded')
        self.assertNotIn("!dropdown.getAttribute('aria-expanded')", src)
        
        # Check that multi-source prefill checking is present
        self.assertIn("readFieldValue(dropdown)", src)
        self.assertIn("isChildFilled", src)
        self.assertIn("isDirectFilled", src)
        self.assertIn("data-sentinel-handled", src)

    def test_custom_dropdown_synchronous_option_selection(self):
        """Verify custom dropdown attempts synchronous option selection before falling back."""
        src = inspect.getsource(self.agent._handle_scripted_fallback)
        
        # Check that options are queried and matched synchronously
        self.assertIn("custom-dropdown", src)
        self.assertIn("matchedOpt.click()", src)
        self.assertIn("shouldSelectYes", src)


if __name__ == "__main__":
    unittest.main()
