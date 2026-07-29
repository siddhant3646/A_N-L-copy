"""
Enhanced Answer Validator Module - Platform-specific and input-aware validation.

Extends basic validation with:
  - Platform-specific formatting rules (LinkedIn numeric vs Naukri text)
  - Input-type compatibility (radio/select must match provided options)
  - Cross-checking against platform rules defined in qa_patterns.json
"""

import re
from typing import Optional, List, Tuple

from .answer_validator import AnswerValidator


class EnhancedAnswerValidator:
    @classmethod
    def validate(
        cls,
        answer: str,
        category: str,
        input_type: str,
        platform: str = "default",
        options: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        # 1. Delegate to base validator
        valid, err = AnswerValidator.validate(answer, category, "")
        if not valid:
            return valid, err

        # 2. Input-type compatibility
        if options and input_type in ("radio", "select"):
            opts_norm = [str(o).strip().lower() for o in options]
            ans_norm = str(answer).strip().lower()
            if ans_norm not in opts_norm:
                return False, f"Answer '{answer}' not in options {options}"

        # 3. Platform-specific format checks
        fmt_err = cls._check_platform_format(answer, category, platform)
        if fmt_err:
            return False, fmt_err

        return True, None

    @classmethod
    def fix(
        cls,
        answer: str,
        category: str,
        input_type: str,
        platform: str = "default",
        options: Optional[List[str]] = None,
    ) -> str:
        if not answer:
            return answer

        # Try base fix first
        fixed = AnswerValidator.fix(answer, category, "", platform)
        if not fixed:
            fixed = answer

        # Map to closest option if provided
        if options and input_type in ("radio", "select"):
            closest = cls._closest_option(fixed, options)
            if closest is not None:
                return closest

        # Apply platform formatting if needed
        fmt_fixed = cls._apply_platform_format(fixed, category, platform)
        return fmt_fixed if fmt_fixed is not None else fixed

    @classmethod
    def _check_platform_format(cls, answer: str, category: str, platform: str) -> Optional[str]:
        pl = platform.lower()
        val = str(answer).strip()

        if category == "salary":
            if pl == "linkedin":
                # Should be numeric (e.g., 2300000)
                if not re.fullmatch(r"\d+", val.replace(",", "").replace(" ", "")):
                    return "LinkedIn salary must be numeric only"
            else:
                # Naukri / instahyre typically text with LPA
                if not re.search(r"\d+\.?\d*", val):
                    return "Salary must contain a number"

        elif category == "experience":
            if pl == "linkedin":
                # Should be numeric only
                digits = re.search(r"(\d+)", val)
                if not digits:
                    return "LinkedIn experience must be numeric only"
            else:
                if not re.search(r"\d+\.?\d*", val):
                    return "Experience must contain a number"

        elif category == "notice_period":
            if pl == "linkedin":
                digits = re.search(r"(\d+)", val)
                if not digits:
                    return "LinkedIn notice period must be numeric days"
            else:
                if not re.search(r"\d+", val):
                    return "Notice period must contain a number"

        return None

    @classmethod
    def _apply_platform_format(cls, answer: str, category: str, platform: str) -> Optional[str]:
        pl = platform.lower()
        val = str(answer).strip()

        if category == "salary":
            if pl == "linkedin":
                match = re.search(r"(\d+)", val.replace(",", ""))
                return match.group(1) if match else None
            else:
                match = re.search(r"(\d+\.?\d*)", val)
                if match:
                    return f"{match.group(1)} LPA"
                return None

        elif category == "experience":
            match = re.search(r"(\d+\.?\d*)", val)
            if not match:
                return None
            num = match.group(1)
            if pl == "linkedin":
                return num
            return f"{num} Years"

        elif category == "notice_period":
            match = re.search(r"(\d+)", val)
            if not match:
                return None
            num = match.group(1)
            if pl == "linkedin":
                return num
            return f"{num} Days"

        return None

    @classmethod
    def _closest_option(cls, answer: str, options: List[str]) -> Optional[str]:
        ans_norm = str(answer).strip().lower()
        best = None
        best_score = 0.0
        for opt in options:
            opt_norm = str(opt).strip().lower()
            if ans_norm == opt_norm:
                return opt
            # Simple substring score
            if ans_norm in opt_norm or opt_norm in ans_norm:
                score = len(set(ans_norm) & set(opt_norm)) / max(len(ans_norm), 1)
                if score > best_score:
                    best_score = score
                    best = opt
        return best if best_score >= 0.5 else None
