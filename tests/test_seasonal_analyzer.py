"""Synthetic-data tests; these are not real population analysis results."""

import json
import random
import unittest
from dataclasses import fields, replace
from datetime import date, datetime, timedelta
from statistics import fmean

from detectors import BaseDetector, DetectionResult, MovingAverageDetector
from seasonal_analyzer import SeasonalAnalyzer
from test_detectors import series


def pattern(start=date(2024, 1, 1), days=35, weekday=100, weekend=200):
    return series([
        weekend if (start + timedelta(days=i)).weekday() >= 5 else weekday
        for i in range(days)
    ], start=start)


class SeasonalAnalyzerTests(unittest.TestCase):
    def test_defaults_and_inherited_detect(self):
        detector = SeasonalAnalyzer()
        self.assertEqual((detector.window, detector.threshold, detector.min_samples),
                         (28, 0.10, 4))
        self.assertIs(SeasonalAnalyzer.detect, BaseDetector.detect)

    def test_different_weekday_weekend_levels_are_normal(self):
        results = SeasonalAnalyzer().detect(pattern())
        self.assertTrue(all(r.is_anomaly is None for r in results[:28]))
        for r in results[28:]:
            self.assertEqual(r.expected, 200 if r.date.weekday() >= 5 else 100)
            self.assertFalse(r.is_anomaly)
            self.assertEqual(r.status, "evaluated")

    def test_weekday_and_weekend_spikes_drops_and_strict_boundary(self):
        for start in (date(2024, 1, 1), date(2024, 1, 6), date(2024, 1, 7)):
            records = pattern(start, days=29)
            baseline = records[-1].total_population
            for delta, anomaly in ((11, True), (-11, True), (10, False),
                                   (-10, False), (5, False)):
                actual = baseline + baseline * delta / 100
                with self.subTest(start=start, delta=delta):
                    changed = records[:-1] + [replace(records[-1], total_population=actual)]
                    result = SeasonalAnalyzer().detect(changed)[-1]
                    self.assertEqual(result.expected, baseline)
                    self.assertAlmostEqual(result.score, delta / 100)
                    self.assertIs(result.is_anomaly, anomaly)
                    self.assertAlmostEqual(result.lower_bound, baseline * 0.9)
                    self.assertAlmostEqual(result.upper_bound, baseline * 1.1)

    def test_min_samples_and_total_history_size_are_distinct(self):
        records = pattern(date(2024, 1, 6), days=8)
        history = tuple(r.total_population for r in records[:-1])
        for minimum, expected in ((2, 200), (3, None)):
            detector = SeasonalAnalyzer(window=7, min_samples=minimum)
            self.assertEqual(detector.calculate_baseline(records[-1], history),
                             (expected, 2))
            result = detector.detect(records)[-1]
            self.assertEqual(result.history_size, 7)
            self.assertEqual(result.expected, expected)
            if expected is None:
                self.assertEqual(result.status, "insufficient_history")
                self.assertIsNone(result.is_anomaly)
                self.assertIsNone(result.score)
                self.assertIsNone(result.lower_bound)
                self.assertIsNone(result.upper_bound)

    def test_parent_requires_full_window_even_if_group_has_enough_samples(self):
        results = SeasonalAnalyzer(window=7, min_samples=1).detect(pattern(days=7))
        self.assertEqual([r.history_size for r in results], list(range(7)))
        self.assertTrue(all(r.is_anomaly is None for r in results))

    def test_zero_baseline_matches_existing_moving_average_policy(self):
        for actual in (0, 1):
            records = series([0] * 28 + [actual])
            seasonal = SeasonalAnalyzer().detect(records)[-1]
            moving = MovingAverageDetector(window=28).detect(records)[-1]
            self.assertEqual(replace(seasonal, method=moving.method), moving)
            self.assertEqual(seasonal.status, "zero_baseline")
            self.assertIsNone(seasonal.score)
            json.dumps(seasonal.to_dict(), allow_nan=False)

    def test_calendar_boundaries_and_every_weekday_mapping(self):
        # Distinct daily values make reversed/off-by-one history mapping visible.
        for start in (date(2023, 1, 20), date(2023, 12, 15), date(2024, 2, 10)):
            records = series(range(100, 142), start=start)
            results = SeasonalAnalyzer().detect(records)
            for i in range(28, len(records)):
                target = records[i]
                samples = [r.total_population for r in records[i - 28:i]
                           if (r.date.weekday() >= 5) == (target.date.weekday() >= 5)]
                with self.subTest(day=target.date):
                    self.assertEqual(results[i].expected, fmean(samples))
                    self.assertEqual(results[i].history_size, 28)

    def test_short_window_mapping_and_rolling_expiry(self):
        records = series(range(100, 131), start=date(2024, 2, 20))
        results = SeasonalAnalyzer(window=9, min_samples=1).detect(records)
        for i in range(9, len(records)):
            samples = [r.total_population for r in records[i - 9:i]
                       if (r.date.weekday() >= 5) == (records[i].date.weekday() >= 5)]
            self.assertEqual(results[i].expected, fmean(samples))

    def test_gap_clears_history_and_requires_full_new_window(self):
        before = pattern(days=29)
        after = pattern(date(2024, 1, 31), days=29, weekday=300, weekend=600)
        results = SeasonalAnalyzer().detect(before + after)
        self.assertEqual([r.history_size for r in results[29:]], list(range(28)) + [28])
        self.assertTrue(all(r.is_anomaly is None for r in results[29:-1]))
        self.assertEqual(results[-1].expected, after[-1].total_population)
        self.assertFalse(results[-1].is_anomaly)

    def test_duplicate_district_date_is_rejected(self):
        records = pattern()
        with self.assertRaisesRegex(ValueError, "중복"):
            SeasonalAnalyzer().detect(records + [records[0]])

    def test_shuffled_districts_are_separate_and_input_is_unchanged(self):
        first = pattern()
        second = [replace(r, district_code="11140", district_name="중구",
                          total_population=r.total_population * 10) for r in first]
        records = first + second
        random.Random(7).shuffle(records)
        original = list(records)
        detector = SeasonalAnalyzer()
        self.assertEqual(detector.detect(iter(records)),
                         detector.detect(first) + detector.detect(second))
        self.assertEqual(records, original)

    def test_current_and_future_values_do_not_change_baseline(self):
        detector = SeasonalAnalyzer()
        records = pattern(days=29)
        original = detector.detect(records)
        changed = records[:-1] + [replace(records[-1], total_population=999999)]
        self.assertEqual(detector.detect(changed)[-1].expected, original[-1].expected)
        extended = records + series([999999], start=records[-1].date + timedelta(days=1))
        self.assertEqual(detector.detect(extended)[:len(records)], original)
        self.assertEqual(detector.detect(records), original)

    def test_result_and_json_contract_for_all_states(self):
        result_sets = [SeasonalAnalyzer().detect(pattern()),
                       SeasonalAnalyzer(window=7, min_samples=3).detect(
                           pattern(date(2024, 1, 6), days=8)),
                       SeasonalAnalyzer().detect(series([0] * 29))]
        for results in result_sets:
            for result in results:
                self.assertIsInstance(result, DetectionResult)
                payload = json.loads(json.dumps(result.to_dict(), allow_nan=False))
                self.assertEqual(set(payload), {f.name for f in fields(DetectionResult)})
                self.assertEqual(payload["date"], result.date.isoformat())
                self.assertEqual(payload["method"], "seasonal")
                self.assertEqual(payload["is_anomaly"], result.is_anomaly)

    def test_invalid_settings(self):
        for window in (0, -1, 1.5, True, "28", None):
            with self.subTest(window=window), self.assertRaises(ValueError):
                SeasonalAnalyzer(window=window)
        for threshold in (0, -1, float("nan"), float("inf"), True, "0.1", None):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                SeasonalAnalyzer(threshold=threshold)
        for minimum in (0, -1, 1.5, True, "4", None, 29):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                SeasonalAnalyzer(min_samples=minimum)

    def test_invalid_dates_and_record_values_use_parent_validation(self):
        record = pattern(days=1)[0]
        for changes in ({"date": "2024-01-01"}, {"date": datetime(2024, 1, 1)},
                        {"date": None}, {"district_code": ""},
                        {"district_name": " "}, {"total_population": -1},
                        {"total_population": float("nan")},
                        {"total_population": float("inf")},
                        {"total_population": True}, {"total_population": "100"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SeasonalAnalyzer().detect([replace(record, **changes)])

    def test_inconsistent_district_names_are_rejected(self):
        records = pattern(days=2)
        records[-1] = replace(records[-1], district_name="중구")
        with self.assertRaises(ValueError):
            SeasonalAnalyzer().detect(records)

    def test_empty_input(self):
        self.assertEqual(SeasonalAnalyzer().detect([]), [])


if __name__ == "__main__":
    unittest.main()
