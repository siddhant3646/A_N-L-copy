"""
Form State Validator Module - Snapshot and validate form field states.

Captures before/after snapshots of form values via page JS evaluation,
then verifies that expected fields actually changed and required fields are non-empty.
"""

import json
from typing import Dict, List, Any, Optional
from playwright.async_api import Page


class FormStateValidator:
    async def snapshot(self, page: Page, form_selector: str = "form") -> Dict[str, Any]:
        """
        Capture a snapshot of all input/select/textarea values within the given form.

        Returns a dict: { identifier: { "tag": str, "type": str, "value": str, "required": bool } }
        """
        js = """
            (formSelector) => {
                const form = document.querySelector(formSelector) || document.body;
                const inputs = form.querySelectorAll('input, select, textarea');
                const result = {};
                inputs.forEach(el => {
                    const key = el.id || el.name || el.placeholder || el.outerText || el.tagName;
                    if (!key) return;
                    result[key] = {
                        tag: el.tagName.toLowerCase(),
                        type: (el.type || '').toLowerCase(),
                        value: el.value,
                        checked: el.checked,
                        required: el.required,
                    };
                });
                return result;
            }
        """
        try:
            raw = await page.evaluate(js, form_selector)
            return raw or {}
        except Exception as e:
            return {"_error": str(e)}

    def validate_change(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        expected_changes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Validate that the form state changed as expected.

        Returns a dict with:
            unchanged: list of expected keys that didn't change
            empty_required: list of required keys that are still empty
            changed: list of keys that did change
            errors: list of error strings
        """
        unchanged = []
        empty_required = []
        changed = []
        errors = []

        for key, after_state in after.items():
            if key.startswith("_"):
                continue
            before_state = before.get(key)
            val = after_state.get("value", "")
            is_empty = val == "" or val is None
            if after_state.get("required") and is_empty:
                empty_required.append(key)

            if before_state is not None:
                if before_state.get("value") != after_state.get("value"):
                    changed.append(key)
                elif before_state.get("checked") != after_state.get("checked"):
                    changed.append(key)

        if expected_changes:
            for key in expected_changes:
                if key not in changed:
                    unchanged.append(key)

        if unchanged:
            errors.append(f"Fields did not change: {', '.join(unchanged)}")
        if empty_required:
            errors.append(f"Required fields are empty: {', '.join(empty_required)}")

        return {
            "unchanged": unchanged,
            "empty_required": empty_required,
            "changed": changed,
            "errors": errors,
            "valid": len(errors) == 0,
        }

    def describe_diff(self, before: Dict[str, Any], after: Dict[str, Any]) -> str:
        """Return a human-readable summary of changes."""
        out = []
        for key in set(before) | set(after):
            bv = before.get(key, {}).get("value", "")
            av = after.get(key, {}).get("value", "")
            if bv != av:
                out.append(f"  {key}: '{bv}' -> '{av}'")
        return "\n".join(out) if out else "  (no visible changes)"
