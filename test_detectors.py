import json
import unittest
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from detectors import BaseDetector, MovingAverageDetector, ZScoreDetector


@dataclass(frozen=True)
class Record:
    date: date
    district_code: str
    district_name: str
    total_population: float


def series(values, code="11110", name="종로구", start=date(2024, 1, 1)):
    return [Record(start + timedelta(days=i), code, name, value) for i, value in enumerate(values)]


class DetectorTests(unittest.TestCase):
    def test_base_is_abstract(self):
        with self.assertRaises(TypeError):
            BaseDetector(7, 0.1)

    def test_moving_average_spike_and_drop(self):
        detector = MovingAverageDetector(window=3)
        for value, expected in [(111, True), (89, True), (105, False)]:
            with self.subTest(value=value):
                result = detector.detect(series([100, 100, 100, value]))[-1]
                self.assertEqual(result.expected, 100)
                self.assertEqual((result.lower_bound, result.upper_bound), (90, 110))
                self.assertIs(result.is_anomaly, expected)
                self.assertAlmostEqual(result.score, (value - 100) / 100)

    def test_moving_average_threshold_is_strict(self):
        for value in (90, 110):
            result = MovingAverageDetector(window=3).detect(series([100, 100, 100, value]))[-1]
            self.assertFalse(result.is_anomaly)

    def test_z_score_uses_population_std_and_excludes_current_day(self):
        result = ZScoreDetector(window=2).detect(series([90, 110, 140]))[-1]
        self.assertEqual(result.expected, 100)
        self.assertEqual(result.score, 4)
        self.assertEqual((result.lower_bound, result.upper_bound), (70, 130))
        self.assertTrue(result.is_anomaly)

    def test_z_score_spike_drop_and_strict_threshold(self):
        for actual, anomaly in [(140, True), (60, True), (130, False), (70, False)]:
            with self.subTest(actual=actual):
                result = ZScoreDetector(window=2).detect(series([90, 110, actual]))[-1]
                self.assertIs(result.is_anomaly, anomaly)

    def test_zero_baseline_has_finite_json_and_explicit_status(self):
        for actual, anomaly in [(0, False), (1, True)]:
            result = MovingAverageDetector(window=2).detect(series([0, 0, actual]))[-1]
            self.assertEqual(result.status, "zero_baseline")
            self.assertIs(result.is_anomaly, anomaly)
            self.assertIsNone(result.score)
            self.assertIsNone(result.deviation_ratio)
            json.dumps(result.to_dict(), allow_nan=False)

    def test_zero_variance_detects_any_change(self):
        for actual, anomaly in [(100, False), (101, True), (99, True)]:
            result = ZScoreDetector(window=2).detect(series([100, 100, actual]))[-1]
            self.assertEqual(result.status, "zero_variance")
            self.assertIs(result.is_anomaly, anomaly)
            self.assertIsNone(result.score)
            self.assertEqual((result.lower_bound, result.upper_bound), (100, 100))
            json.dumps(result.to_dict(), allow_nan=False)

    def test_insufficient_history_is_not_normal(self):
        for detector in (MovingAverageDetector(window=3), ZScoreDetector(window=3)):
            results = detector.detect(series([100, 100, 100, 100]))
            self.assertEqual([r.history_size for r in results], [0, 1, 2, 3])
            for result in results[:3]:
                self.assertEqual(result.status, "insufficient_history")
                self.assertIsNone(result.is_anomaly)
                self.assertIsNone(result.expected)
            self.assertIs(results[-1].is_anomaly, False)

    def test_gap_requires_new_continuous_history(self):
        records = series([100] * 3) + series([100] * 4, start=date(2024, 1, 5))
        for detector in (MovingAverageDetector(window=3), ZScoreDetector(window=3)):
            results = detector.detect(records)
            self.assertEqual([r.history_size for r in results], [0, 1, 2, 0, 1, 2, 3])
            self.assertTrue(all(r.is_anomaly is None for r in results[:-1]))
            self.assertFalse(results[-1].is_anomaly)

    def test_regions_are_sorted_and_never_mixed(self):
        records = series([100, 100, 111]) + series([1000, 1000, 1000], "11140", "중구")
        records.reverse()
        original = list(records)
        results = MovingAverageDetector(window=2).detect(iter(records))
        self.assertEqual(records, original)
        self.assertEqual([r.district_code for r in results], ["11110"] * 3 + ["11140"] * 3)
        self.assertEqual([r.actual for r in results], [100, 100, 111, 1000, 1000, 1000])
        self.assertTrue(results[2].is_anomaly)
        self.assertFalse(results[5].is_anomaly)

    def test_future_data_cannot_change_past_results_and_calls_are_independent(self):
        records = series([90, 110, 140, 80, 100])
        for detector in (MovingAverageDetector(window=2), ZScoreDetector(window=2)):
            original = detector.detect(records)
            extended = detector.detect(records + series([999999], start=date(2024, 1, 6)))
            self.assertEqual(original, extended[:len(records)])
            self.assertEqual(original, detector.detect(records))

    def test_window_rolls_forward(self):
        result = MovingAverageDetector(window=2).detect(series([100, 100, 200, 150]))[-1]
        self.assertEqual(result.expected, 150)
        self.assertFalse(result.is_anomaly)

    def test_empty_input(self):
        for detector in (MovingAverageDetector(), ZScoreDetector()):
            self.assertEqual(detector.detect([]), [])

    def test_duplicate_region_date_rejected(self):
        record = series([100])[0]
        with self.assertRaisesRegex(ValueError, "중복"):
            MovingAverageDetector().detect([record, record])

    def test_inconsistent_region_names_rejected(self):
        records = series([100, 100])
        records[-1] = replace(records[-1], district_name="중구")
        with self.assertRaisesRegex(ValueError, "이름"):
            MovingAverageDetector().detect(records)

    def test_invalid_population_rejected(self):
        for value in (-1, float("nan"), float("inf"), -float("inf"), True, "100", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MovingAverageDetector().detect(series([value]))

    def test_invalid_date_or_region_rejected(self):
        record = series([100])[0]
        for changes in (
            {"date": "2024-01-01"}, {"date": datetime(2024, 1, 1)},
            {"district_code": 11110}, {"district_code": " "}, {"district_name": ""},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                MovingAverageDetector().detect([replace(record, **changes)])

    def test_invalid_parameters_rejected(self):
        for cls in (MovingAverageDetector, ZScoreDetector):
            for window in (0, -1, 1.5, True):
                with self.subTest(cls=cls, window=window), self.assertRaises(ValueError):
                    cls(window=window)
            for threshold in (0, -1, float("nan"), float("inf"), True, "3"):
                with self.subTest(cls=cls, threshold=threshold), self.assertRaises(ValueError):
                    cls(threshold=threshold)
        with self.assertRaises(ValueError):
            ZScoreDetector(window=1)

    def test_json_contract(self):
        result = MovingAverageDetector(window=2).detect(series([100, 100, 150]))[-1]
        payload = json.loads(json.dumps(result.to_dict(), allow_nan=False))
        self.assertEqual(payload["date"], "2024-01-03")
        self.assertEqual(payload["method"], "moving_average")
        self.assertIs(payload["is_anomaly"], True)


if __name__ == "__main__":
    unittest.main()
