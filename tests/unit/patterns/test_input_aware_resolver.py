"""Tests for InputAwareResolver module."""

from src.patterns.input_aware_resolver import (
    InputType, Option, MatchResult, NumericRangeMatcher,
    InputAwareResolver
)


class TestInputTypeEnum:
    def test_has_expected_members(self):
        assert InputType.TEXT.value == "text"
        assert InputType.NUMBER.value == "number"
        assert InputType.SELECT.value == "select"
        assert InputType.RADIO.value == "radio"
        assert InputType.CHECKBOX.value == "checkbox"
        assert InputType.TEXTAREA.value == "textarea"
        assert InputType.DATE.value == "date"
        assert InputType.EMAIL.value == "email"
        assert InputType.TEL.value == "tel"


class TestOptionDataclass:
    def test_default_values(self):
        opt = Option(value="val", label="Label")
        assert opt.value == "val"
        assert opt.label == "Label"
        assert opt.index == 0
        assert opt.is_selected is False

    def test_custom_values(self):
        opt = Option(value="v", label="L", index=2, is_selected=True)
        assert opt.index == 2
        assert opt.is_selected is True


class TestMatchResultDataclass:
    def test_default_alternatives(self):
        result = MatchResult(
            matched_option=None, confidence=0.0,
            match_type="none", original_answer="test"
        )
        assert result.alternatives == []

    def test_with_alternatives(self):
        opt = Option(value="v", label="L")
        result = MatchResult(
            matched_option=opt, confidence=0.95,
            match_type="exact", original_answer="test",
            alternatives=[(opt, 0.9)]
        )
        assert len(result.alternatives) == 1


class TestNumericRangeMatcher:
    def test_extract_range_dash(self):
        result = NumericRangeMatcher.extract_range("3-5 years")
        assert result is not None
        assert result[0] == 3.0
        assert result[1] == 5.0
        assert result[2] == "range"

    def test_extract_range_to_keyword(self):
        result = NumericRangeMatcher.extract_range("3 to 5 years")
        assert result is not None
        assert result[0] == 3.0

    def test_extract_min_plus(self):
        result = NumericRangeMatcher.extract_range("5+ years")
        assert result is not None
        assert result[0] == 5.0
        assert result[1] == float('inf')
        assert result[2] == "min"

    def test_extract_max_less_than(self):
        result = NumericRangeMatcher.extract_range("less than 3 years")
        assert result is not None
        assert result[0] == 0
        assert result[1] == 3.0
        assert result[2] == "max"

    def test_extract_range_no_match(self):
        result = NumericRangeMatcher.extract_range("Any experience")
        assert result is None

    def test_extract_range_empty(self):
        result = NumericRangeMatcher.extract_range("")
        assert result is None

    def test_extract_range_none(self):
        result = NumericRangeMatcher.extract_range(None)
        assert result is None

    def test_value_in_range_exact_match(self):
        result = NumericRangeMatcher.extract_range("3-5 years")
        assert NumericRangeMatcher.value_in_range(4.0, result)

    def test_value_in_range_boundary_low(self):
        result = NumericRangeMatcher.extract_range("3-5 years")
        assert NumericRangeMatcher.value_in_range(3.0, result)

    def test_value_in_range_boundary_high(self):
        result = NumericRangeMatcher.extract_range("3-5 years")
        assert NumericRangeMatcher.value_in_range(5.0, result)

    def test_value_in_range_outside(self):
        result = NumericRangeMatcher.extract_range("3-5 years")
        assert not NumericRangeMatcher.value_in_range(6.0, result)

    def test_value_in_range_min(self):
        result = NumericRangeMatcher.extract_range("5+ years")
        assert NumericRangeMatcher.value_in_range(7.0, result)
        assert not NumericRangeMatcher.value_in_range(3.0, result)

    def test_value_in_range_max(self):
        result = NumericRangeMatcher.extract_range("less than 3")
        assert NumericRangeMatcher.value_in_range(2.0, result)
        assert not NumericRangeMatcher.value_in_range(4.0, result)


class TestInputAwareResolver:
    def test_init_defaults(self):
        resolver = InputAwareResolver()
        assert resolver is not None

    def test_resolve_exact_match(self):
        resolver = InputAwareResolver()
        options = [
            Option(value="yes", label="Yes"),
            Option(value="no", label="No"),
        ]
        result = resolver.resolve("Yes", InputType.RADIO, options)
        assert result.matched_option is not None
        assert result.confidence > 0.8
        assert result.match_type == "exact"

    def test_resolve_no_match(self):
        resolver = InputAwareResolver()
        options = [
            Option(value="a", label="Alpha"),
            Option(value="b", label="Beta"),
        ]
        result = resolver.resolve("zzz", InputType.RADIO, options)
        assert result.matched_option is None
        assert result.match_type == "none"

    def test_resolve_text_type_no_options(self):
        resolver = InputAwareResolver()
        result = resolver.resolve("Hello World", InputType.TEXT)
        assert result.matched_option is not None
        assert result.confidence == 1.0
        assert result.match_type == "text"

    def test_resolve_number_type(self):
        resolver = InputAwareResolver()
        result = resolver.resolve("4 years", InputType.NUMBER)
        assert result.matched_option is not None
        assert result.match_type == "numeric"

    def test_resolve_empty_options_fallback(self):
        resolver = InputAwareResolver()
        result = resolver.resolve("Yes", InputType.RADIO, [])
        assert result.matched_option is not None
        assert result.match_type == "fallback"
        assert result.confidence == 0.5

    def test_resolve_numeric_range_match(self):
        resolver = InputAwareResolver()
        options = [
            Option(value="3-5", label="3-5 years"),
            Option(value="5-7", label="5-7 years"),
        ]
        result = resolver.resolve("4", InputType.SELECT, options)
        assert result.matched_option is not None
        assert result.match_type == "numeric_range"

    def test_resolve_synonym_match(self):
        resolver = InputAwareResolver()
        options = [
            Option(value="yes", label="Yes, I agree"),
        ]
        result = resolver.resolve("Yep", InputType.RADIO, options)
        assert result.matched_option is not None
        assert result.match_type == "synonym"

    def test_resolve_fuzzy_match(self):
        resolver = InputAwareResolver(threshold=0.5)
        options = [
            Option(value="opt1", label="Option one"),
            Option(value="opt2", label="Option two"),
        ]
        result = resolver.resolve("Option one!", InputType.SELECT, options)
        assert result.matched_option is not None

    def test_resolve_email_type(self):
        resolver = InputAwareResolver()
        result = resolver.resolve("test@example.com", InputType.EMAIL)
        assert result.match_type == "text"
