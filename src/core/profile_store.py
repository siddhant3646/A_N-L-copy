"""ProfileStore - single source of truth for candidate profile data.

Loads profiles/resume.json and exposes typed, validated access to the
candidate's personal information for both Python and injected-JS consumers.
"""

import json
import os


class ProfileStoreError(Exception):
    """Raised when the profile file is missing or structurally invalid."""


REQUIRED_PERSONAL_KEYS = ("name", "email", "phone")

# Flat keys exposed to the JS side via window.__SENTINEL_PROFILE__.
_JS_PROFILE_KEYS = (
    "name", "email", "phone", "location", "city", "zip",
    "dob", "gender", "nationality", "pan",
    "linkedin", "github", "portfolio",
)


class ProfileStore:
    """Loads and validates the candidate profile from resume.json."""

    def __init__(self, path: str = None):
        if path is None:
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "profiles", "resume.json",
            )
        self.path = os.path.abspath(path)
        self._data = None

    def load(self) -> dict:
        """Parse and validate resume.json. Cached after first call."""
        if self._data is not None:
            return self._data
        if not os.path.exists(self.path):
            raise ProfileStoreError(f"Profile file not found: {self.path}")
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProfileStoreError(f"Profile file is not valid JSON: {e}")
        if not isinstance(data, dict):
            raise ProfileStoreError("Profile root must be an object")
        personal = data.get("personal")
        if not isinstance(personal, dict):
            raise ProfileStoreError("Profile is missing the 'personal' object")
        missing = [k for k in REQUIRED_PERSONAL_KEYS if not str(personal.get(k, "")).strip()]
        if missing:
            raise ProfileStoreError(f"Profile personal section missing: {', '.join(missing)}")
        self._data = data
        return data

    @property
    def data(self) -> dict:
        return self.load()

    @property
    def personal(self) -> dict:
        return self.data.get("personal", {})

    @property
    def preferences(self) -> dict:
        return self.data.get("preferences", {})

    def get(self, dotted_path: str, default=None):
        """Dotted-path accessor, e.g. get('personal.email')."""
        node = self.data
        for part in dotted_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def to_js_dict(self) -> dict:
        """Flat dict of JS-relevant personal fields (None values dropped)."""
        personal = self.personal
        out = {}
        for key in _JS_PROFILE_KEYS:
            val = personal.get(key)
            if val is not None and str(val).strip():
                out[key] = str(val)
        return out
