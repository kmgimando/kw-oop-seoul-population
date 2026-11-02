"""Synthetic sample only: actual Repository -> Flask -> ReportGenerator tests."""

import copy
import csv
import hashlib
import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app import create_app
from csv_population_repository import CsvPopulationRepository
from detectors import MovingAverageDetector, ZScoreDetector
from migration_indicators import MigrationIndicators
from run_sample_dashboard import create_sample_app
from seasonal_analyzer import SeasonalAnalyzer


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data/sample_population.csv"
SETTINGS = {"moving_average": {"window": 7, "threshold": 0.1},
            "z_score": {"window": 28, "threshold": 3.0},
            "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}}
DETECTORS = {"moving_average": MovingAverageDetector, "z_score": ZScoreDetector,
             "seasonal": SeasonalAnalyzer}


def sample_repository(path=SAMPLE):
    repository = CsvPopulationRepository(path, indicators_factory=MigrationIndicators)
    repository.load()
    return repository


def query(code="11110", start="2026-01-01", end="2026-02-09", settings=None):
    return {"district_code": code, "start_date": start, "end_date": end,
            "selected_method": "seasonal", "methods": copy.deepcopy(settings or SETTINGS)}


def api_response(client, request_query):
    params = {key: request_query[key] for key in ("district_code", "start_date", "end_date")}
    params["methods"] = json.dumps(request_query["methods"])
    return client.get("/api/analysis", query_string=params)


def direct_results(repository, request_query):
    start = date.fromisoformat(request_query["start_date"])
    end = date.fromisoformat(request_query["end_date"])
    records = repository.get_records(request_query["district_code"])
    return {name: [row.to_dict() for row in cls(**request_query["methods"][name]).detect(records)
                   if start <= row.date <= end] for name, cls in DETECTORS.items()}


def summarize(rows):
    anomaly = sum(row["is_anomaly"] is True for row in rows)
    normal = sum(row["is_anomaly"] is False for row in rows)
    unavailable = sum(row["is_anomaly"] is None for row in rows)
    evaluated = anomaly + normal
    return {"total": len(rows), "anomaly": anomaly, "normal": normal,
            "unavailable": unavailable, "evaluated": evaluated,
            "rate": anomaly / evaluated if evaluated else None}


class SampleDashboardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
        cls.repository = sample_repository()
        cls.client = create_app(cls.repository).test_client()

    @classmethod
    def tearDownClass(cls):
        if cls.before != hashlib.sha256(SAMPLE.read_bytes()).hexdigest():
            raise AssertionError("Sample source was modified")

    def test_both_districts_three_methods_match_direct_python(self):
        for code in ("11110", "11680"):
            q = query(code)
            response = api_response(self.client, q)
            self.assertEqual(response.status_code, 200, response.get_json())
            expected = direct_results(self.repository, q)
            payload = response.get_json()
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(len(payload["methods"]), 3)
            for block in payload["methods"]:
                self.assertEqual(block["results"], expected[block["method"]])
                self.assertEqual(block["settings"], q["methods"][block["method"]])
                self.assertEqual(len(block["results"]), 40)
            json.dumps(payload, allow_nan=False)

    def test_period_uses_previous_history_but_does_not_return_it(self):
        q = query(start="2026-01-29")
        payload = api_response(self.client, q).get_json()
        expected = direct_results(self.repository, q)
        for block in payload["methods"]:
            self.assertEqual(len(block["results"]), 12)
            self.assertEqual(block["results"], expected[block["method"]])
            self.assertTrue(all(row["date"] >= q["start_date"] for row in block["results"]))
            self.assertEqual(block["results"][0]["history_size"], q["methods"][block["method"]]["window"])

    def test_initial_missing_history_is_not_normal_or_zero(self):
        payload = api_response(self.client, query()).get_json()
        for block in payload["methods"]:
            row = block["results"][0]
            self.assertIsNone(row["is_anomaly"])
            self.assertEqual(row["status"], "insufficient_history")
            for key in ("expected", "lower_bound", "upper_bound", "score", "deviation_ratio"):
                self.assertIsNone(row[key])

    def test_seasonal_window_threshold_min_samples_are_applied(self):
        settings = copy.deepcopy(SETTINGS)
        settings["seasonal"] = {"window": 7, "threshold": 0.2, "min_samples": 6}
        q = query(settings=settings)
        response = api_response(self.client, q)
        self.assertEqual(response.status_code, 200)
        block = next(b for b in response.get_json()["methods"] if b["method"] == "seasonal")
        self.assertEqual(block["settings"], settings["seasonal"])
        self.assertEqual(block["results"], direct_results(self.repository, q)["seasonal"])
        self.assertTrue(all(row["is_anomaly"] is None for row in block["results"]))
        self.assertEqual(block["results"][-1]["history_size"], 7)

    def test_anomaly_explanation_and_indicators_match_sample_source(self):
        payload = api_response(self.client, query()).get_json()
        count = 0
        for block in payload["methods"]:
            by_date = {row["date"]: row for row in block["results"]}
            for day, info in block["details"].items():
                self.assertTrue(by_date[day]["is_anomaly"])
                source = self.repository.get_records("11110", date.fromisoformat(day), date.fromisoformat(day))[0]
                self.assertEqual(info["indicators"], source.to_dict()["indicators"])
                self.assertIn("단정할 수 없습니다", info["explanation"])
                count += 1
        self.assertGreater(count, 0)

    def test_bounds_and_scores_use_existing_detector_semantics(self):
        payload = api_response(self.client, query()).get_json()
        for block in payload["methods"]:
            for row in block["results"]:
                if row["status"] != "evaluated":
                    continue
                expected = row["expected"]
                self.assertAlmostEqual(row["deviation_ratio"], (row["actual"] - expected) / expected)
                scale = expected if block["method"] != "z_score" else (row["upper_bound"] - expected) / row["threshold"]
                self.assertAlmostEqual(row["score"], (row["actual"] - expected) / scale)
                self.assertAlmostEqual(row["lower_bound"], max(0, expected - row["threshold"] * scale))
                self.assertEqual(row["is_anomaly"], abs(row["score"]) > row["threshold"])

    def test_empty_period_is_200_with_three_empty_blocks(self):
        response = api_response(self.client, query(start="2027-01-01", end="2027-01-10"))
        self.assertEqual(response.status_code, 200)
        for block in response.get_json()["methods"]:
            self.assertEqual(block["results"], [])
            self.assertIsNone(summarize(block["results"])["rate"])

    def test_unsupported_district_and_invalid_period_are_400(self):
        for q in (query(code="11440"), query(start="2026-02-10"), query(start="bad-date")):
            response = api_response(self.client, q)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"]["code"], "INVALID_PARAMETER")

    def test_missing_settings_are_400_instead_of_internal_error(self):
        for name in SETTINGS:
            for key in SETTINGS[name]:
                settings = copy.deepcopy(SETTINGS)
                settings[name].pop(key)
                response = api_response(self.client, query(settings=settings))
                self.assertEqual(response.status_code, 400, (name, key))
                self.assertEqual(response.get_json()["error"]["code"], "INVALID_PARAMETER")

    def test_launcher_profile_advertises_only_loaded_synthetic_sample(self):
        response = create_sample_app().test_client().get("/")
        self.assertEqual(response.status_code, 200)
        text = re.search(r'<script id="dashboard-profile" type="application/json">(.*?)</script>',
                         response.get_data(as_text=True), re.S).group(1)
        profile = json.loads(text)
        self.assertEqual(profile["districts"], [["11110", "종로구"], ["11680", "강남구"]])
        self.assertEqual((profile["start_date"], profile["end_date"]), ("2026-01-01", "2026-02-09"))
        self.assertEqual(profile["source"]["kind"], "synthetic_sample")
        response.close()

    def test_zero_baseline_and_zero_variance_are_evaluated(self):
        # Separate, clearly synthetic edge fixture, never replaces sample CSV.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zeros.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([*CsvPopulationRepository.REQUIRED_COLUMNS,
                                 *CsvPopulationRepository.INDICATOR_COLUMNS.values()])
                for i in range(40):
                    day = date(2026, 1, 1) + timedelta(days=i)
                    writer.writerow([day.strftime("%Y%m%d"), "11110", "종로구", 100 if i == 35 else 0, 0, 0])
            client = create_app(sample_repository(path)).test_client()
            payload = api_response(client, query()).get_json()
            for block in payload["methods"]:
                status = "zero_variance" if block["method"] == "z_score" else "zero_baseline"
                rows = [row for row in block["results"] if row["status"] == status]
                self.assertTrue(any(row["is_anomaly"] is False for row in rows))
                self.assertTrue(any(row["is_anomaly"] is True for row in rows))
                self.assertTrue(all(row["score"] is None for row in rows))
            json.dumps(payload, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
