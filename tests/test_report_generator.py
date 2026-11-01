"""ReportGenerator의 응답 구성과 API 계약 검증을 확인한다. 합성 자료이며 실제 분석 결과가 아니다."""

import copy
import json
import math
import unittest
from datetime import date, timedelta
from types import SimpleNamespace

from anomaly_explainer import AnomalyExplainer
from detectors import MovingAverageDetector, ZScoreDetector
from migration_indicators import MigrationIndicators
from report_generator import PayloadValidationError, ReportGenerator
from seasonal_analyzer import SeasonalAnalyzer

DETECTORS = {"moving_average": MovingAverageDetector, "z_score": ZScoreDetector,
             "seasonal": SeasonalAnalyzer}
SETTINGS = {"moving_average": {"window": 7, "threshold": 0.1},
            "z_score": {"window": 28, "threshold": 3.0},
            "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}}
START, END = date(2024, 2, 1), date(2024, 3, 10)   # 39일, 앞의 31일은 계산용 이력


def make_records(days=70, spikes=(40, 55), base=None):
    """평일 260,000명·주말 205,000명 패턴에 급증일을 넣은 종로구 기록"""
    records = []
    for i in range(days):
        day = date(2024, 1, 1) + timedelta(days=i)
        value = base(i) if base else (260000 if day.weekday() < 5 else 205000) + (90000 if i in spikes else 0)
        records.append(SimpleNamespace(
            date=day, district_code="11110", district_name="종로구", total_population=float(value),
            indicators=MigrationIndicators(25000.0 if i in spikes else 20000.0, 40000.0)))
    return records


def make_generator(records, start=START, end=END, explanations=None):
    """API와 같은 순서로 탐지·설명을 실행한다. 설명은 일부러 조회 기간 밖 날짜까지 넘긴다."""
    explainer = AnomalyExplainer()
    results, details = {}, {}
    for name, cls in DETECTORS.items():
        results[name] = cls(**SETTINGS[name]).detect(records)
        details[name] = {r.date.isoformat(): info for r in results[name]
                         if (info := explainer.explain(r, records)) is not None}
    return ReportGenerator(records, results, explanations if explanations is not None else details,
                           SETTINGS, start, end)


class BuildPayloadTests(unittest.TestCase):
    def setUp(self):
        self.payload = make_generator(make_records()).build_payload()
        self.blocks = {block["method"]: block for block in self.payload["methods"]}

    def test_three_blocks_echo_requested_settings(self):
        self.assertEqual(self.payload["schema_version"], 1)
        self.assertEqual(set(self.blocks), set(SETTINGS))
        for name, block in self.blocks.items():
            with self.subTest(method=name):
                self.assertEqual(block["settings"], SETTINGS[name])
                self.assertTrue(all(row["method"] == name for row in block["results"]))

    def test_warmup_history_is_excluded(self):
        expected_days = (END - START).days + 1
        for name, block in self.blocks.items():
            with self.subTest(method=name):
                dates = [row["date"] for row in block["results"]]
                self.assertEqual(len(dates), expected_days)
                self.assertEqual((dates[0], dates[-1]), (START.isoformat(), END.isoformat()))

    def test_details_keep_only_result_dates_and_contract_keys(self):
        explained = 0
        for name, block in self.blocks.items():
            dates = {row["date"] for row in block["results"]}
            for day, info in block["details"].items():
                with self.subTest(method=name, date=day):
                    self.assertIn(day, dates)
                    # AnomalyExplainer의 comparison 키는 계약에 없어 전달하지 않는다.
                    self.assertEqual(set(info), set(ReportGenerator.DETAIL_KEYS))
                    explained += 1
        self.assertGreater(explained, 0)

    def test_payload_is_strict_json(self):
        json.dumps(self.payload, allow_nan=False)


class EdgeCaseTests(unittest.TestCase):
    def test_insufficient_history_rows_are_kept_as_null(self):
        payload = make_generator(make_records(), start=date(2024, 1, 1)).build_payload()
        for block in payload["methods"]:
            with self.subTest(method=block["method"]):
                first = block["results"][0]
                self.assertEqual(len(block["results"]), 70)
                self.assertEqual(first["status"], "insufficient_history")
                self.assertIsNone(first["is_anomaly"])
                self.assertIsNone(first["expected"])

    def test_zero_baseline_and_zero_variance_pass_validation(self):
        records = make_records(base=lambda i: 0 if i < 50 else 120000)
        payload = make_generator(records, explanations={}).build_payload()
        statuses = {row["status"] for block in payload["methods"] for row in block["results"]}
        self.assertIn("zero_baseline", statuses)
        self.assertIn("zero_variance", statuses)

    def test_period_without_records_returns_empty_blocks(self):
        payload = make_generator(make_records(), start=date(2025, 1, 1),
                                 end=date(2025, 1, 31)).build_payload()
        self.assertEqual(len(payload["methods"]), 3)
        for block in payload["methods"]:
            self.assertEqual((block["results"], block["details"]), ([], {}))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.generator = make_generator(make_records())
        self.payload = self.generator.build_payload()

    def assertRejected(self, mutate):
        broken = copy.deepcopy(self.payload)
        mutate(broken)
        with self.assertRaises(PayloadValidationError):
            self.generator.validate_payload(broken)

    def rows(self, payload, index=0):
        return payload["methods"][index]["results"]

    def test_error_is_value_error(self):
        self.assertTrue(issubclass(PayloadValidationError, ValueError))

    def test_valid_payload_passes(self):
        self.generator.validate_payload(self.payload)

    def test_rejects_contract_violations(self):
        cases = {
            "중복 날짜": lambda p: self.rows(p).append(self.rows(p)[0]),
            "NaN 점수": lambda p: self.rows(p, 1)[5].update(score=math.nan),
            "조회 기간 밖 날짜": lambda p: self.rows(p)[3].update(date="2024-01-15"),
            "날짜 형식": lambda p: self.rows(p)[3].update(date="20240204"),
            "원자료와 다른 actual": lambda p: self.rows(p)[3].update(actual=1.0),
            "숫자로 된 is_anomaly": lambda p: self.rows(p)[3].update(is_anomaly=1),
            "기준값 없는 판정": lambda p: self.rows(p)[3].update(expected=None),
            "window 초과 history_size": lambda p: self.rows(p)[3].update(history_size=99),
            "결과 필드 누락": lambda p: self.rows(p)[3].pop("status"),
            "settings 불일치": lambda p: p["methods"][2]["settings"].update(window=7),
            "블록 누락": lambda p: p["methods"].pop(),
            "블록 중복": lambda p: p["methods"].append(p["methods"][0]),
            "schema_version": lambda p: p.update(schema_version=2),
            "결과 없는 details 날짜": lambda p: p["methods"][0]["details"].update(
                {"2023-12-01": {"explanation": "x", "indicators": {}}}),
            "숫자가 아닌 지표": lambda p: p["methods"][0]["details"].update(
                {START.isoformat(): {"explanation": None, "indicators": {"external_inflow": "많음"}}}),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label):
                self.assertRejected(mutate)


if __name__ == "__main__":
    unittest.main()
