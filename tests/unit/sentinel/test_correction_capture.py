from unittest.mock import MagicMock
from src.sentinel.correction_capture import CorrectionCapture, Correction


class TestCorrectionDataclass:
    def test_correction_creation(self):
        c = Correction(
            timestamp="2024-01-01T00:00:00",
            field_label="salary",
            wrong_answer="20 LPA",
            correct_answer="23 LPA",
            available_options=[],
            platform="naukri",
            url="https://naukri.com",
            capture_method="auto",
        )
        assert c.field_label == "salary"
        assert c.wrong_answer == "20 LPA"
        assert c.correct_answer == "23 LPA"
        assert c.capture_method == "auto"


class TestCorrectionCaptureInit:
    def test_init_with_mock_store(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        assert cc.learning_store == store
        assert cc.propagate_to_similar is True
        assert cc.corrections == []
        assert cc.last_failed_field is None

    def test_init_no_propagation(self):
        store = MagicMock()
        cc = CorrectionCapture(store, propagate_to_similar=False)
        assert cc.propagate_to_similar is False


class TestCorrectionCaptureRecordFailure:
    def test_record_failure_context(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        cc.record_failure_context("salary", "20 LPA", ["10 LPA", "23 LPA"])
        assert cc.last_failed_field == "salary"
        assert cc.last_failed_value == "20 LPA"
        assert cc.last_failed_options == ["10 LPA", "23 LPA"]


class TestCorrectionCaptureCaptureCorrection:
    def test_capture_correction_returns_pattern_id(self):
        store = MagicMock()
        store.patterns = {}
        store.add_pattern.return_value = "learned_salary"
        cc = CorrectionCapture(store)
        pattern_id = cc.capture_correction(
            field_label="salary",
            wrong_answer="20 LPA",
            correct_answer="23 LPA",
        )
        assert pattern_id is not None

    def test_capture_correction_skips_identical(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        pattern_id = cc.capture_correction(
            field_label="salary",
            wrong_answer="20 LPA",
            correct_answer="20 LPA",
        )
        assert pattern_id is None

    def test_capture_correction_skips_empty(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        pattern_id = cc.capture_correction(
            field_label="salary",
            wrong_answer="20 LPA",
            correct_answer="",
        )
        assert pattern_id is None

    def test_capture_correction_stores_correction(self):
        store = MagicMock()
        store.patterns = {}
        store.add_pattern.return_value = "learned_salary"
        cc = CorrectionCapture(store)
        cc.capture_correction("salary", "20", "23", capture_method="console")
        assert len(cc.corrections) == 1
        assert cc.corrections[0].correct_answer == "23"
        assert cc.corrections[0].capture_method == "console"

    def test_capture_correction_with_options(self):
        store = MagicMock()
        store.patterns = {}
        store.add_pattern.return_value = "learned_salary"
        cc = CorrectionCapture(store)
        cc.capture_correction(
            "salary", "20", "23",
            available_options=["10", "23", "30"],
            platform="linkedin",
        )
        assert len(cc.corrections) == 1
        assert cc.corrections[0].platform == "linkedin"


class TestCorrectionCaptureFindMatchingOption:
    def test_find_exact_option(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        result = cc._find_matching_option("23", ["10", "23", "30"])
        assert result == "23"

    def test_find_partial_option(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        result = cc._find_matching_option("23 LPA", ["10 LPA", "23 LPA", "30 LPA"])
        assert result == "23 LPA"

    def test_no_matching_option(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        result = cc._find_matching_option("zzz", ["10", "23", "30"])
        assert result is None

    def test_empty_options(self):
        store = MagicMock()
        cc = CorrectionCapture(store)
        result = cc._find_matching_option("23", [])
        assert result is None


class TestCorrectionCaptureLearnCorrection:
    def test_learn_correction_calls_add_pattern(self):
        store = MagicMock()
        store.patterns = {}
        cc = CorrectionCapture(store)
        cc._learn_correction(Correction(
            timestamp="now", field_label="salary",
            wrong_answer="20", correct_answer="23",
            available_options=[], platform="naukri",
            url="", capture_method="manual",
        ))
        store.add_pattern.assert_called_once()

    def test_learn_correction_boosts_confidence(self):
        store = MagicMock()
        mock_pattern = MagicMock()
        mock_pattern.confidence = 0.5
        store.patterns = {"test_id": mock_pattern}
        store.add_pattern.return_value = "test_id"
        cc = CorrectionCapture(store)
        cc._learn_correction(Correction(
            timestamp="now", field_label="salary",
            wrong_answer="20", correct_answer="23",
            available_options=[], platform="naukri",
            url="", capture_method="manual",
        ))
        assert mock_pattern.confidence >= 0.7
