"""Tests for ProfileStore and window.__SENTINEL_PROFILE__ injection."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.core.profile_store import ProfileStore, ProfileStoreError


class TestProfileStore(unittest.TestCase):
    def test_loads_real_profile(self):
        store = ProfileStore()
        data = store.load()
        self.assertIn("personal", data)
        personal = store.personal
        for key in ("name", "email", "phone"):
            self.assertTrue(str(personal.get(key, "")).strip(), f"missing {key}")

    def test_missing_file_raises(self):
        store = ProfileStore("/tmp/definitely_missing_profile_12345.json")
        with self.assertRaises(ProfileStoreError):
            store.load()

    def test_invalid_json_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not json")
            path = f.name
        try:
            store = ProfileStore(path)
            with self.assertRaises(ProfileStoreError):
                store.load()
        finally:
            os.unlink(path)

    def test_missing_personal_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"education": {}}, f)
            path = f.name
        try:
            store = ProfileStore(path)
            with self.assertRaises(ProfileStoreError):
                store.load()
        finally:
            os.unlink(path)

    def test_missing_required_key_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"personal": {"name": "X"}}, f)
            path = f.name
        try:
            store = ProfileStore(path)
            with self.assertRaises(ProfileStoreError):
                store.load()
        finally:
            os.unlink(path)

    def test_dotted_get(self):
        store = ProfileStore()
        email = store.get("personal.email")
        self.assertTrue("@" in str(email))
        self.assertIsNone(store.get("personal.nonexistent_key"))
        self.assertEqual(store.get("personal.nonexistent_key", "fallback"), "fallback")

    def test_to_js_dict_flat_and_string(self):
        store = ProfileStore()
        js = store.to_js_dict()
        self.assertIn("name", js)
        self.assertIn("email", js)
        self.assertIn("linkedin", js)
        for k, v in js.items():
            self.assertIsInstance(v, str, f"{k} should be a string")


class TestAgentProfileInjection(unittest.TestCase):
    def test_agent_has_profile_store(self):
        from src.sentinel.agent import SentinelAgent
        agent = SentinelAgent()
        self.assertIsNotNone(agent._profile_store)
        self.assertTrue(agent._profile_store.personal.get("email"))

    def test_injection_script_contains_profile(self):
        from src.sentinel.agent import SentinelAgent
        agent = SentinelAgent()
        # _inject_patterns_once requires a page; verify via source instead
        import inspect
        src = inspect.getsource(agent._inject_patterns_once)
        self.assertIn("__SENTINEL_PROFILE__", src)
        self.assertIn("to_js_dict", src)


if __name__ == "__main__":
    unittest.main()
