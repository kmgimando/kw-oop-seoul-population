"""고정된 실제 CSV → Repository → Flask → ReportGenerator의 연동 검증."""

import hashlib
import json
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from csv_population_repository import CsvPopulationRepository
from dashboard_app import ROOT, create_dashboard_app
from detectors import MovingAverageDetector, ZScoreDetector
from run_sample_dashboard import create_sample_app
from seasonal_analyzer import SeasonalAnalyzer


SOURCE = ROOT / "data/population.csv"
SETTINGS = {"moving_average": {"window": 7, "threshold": 0.1},
            "z_score": {"window": 28, "threshold": 3.0},
            "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}}
DETECTORS = {"moving_average": MovingAverageDetector, "z_score": ZScoreDetector,
             "seasonal": SeasonalAnalyzer}


class FullCsvDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = create_dashboard_app(SOURCE)
        cls.client = cls.application.test_client()
        cls.repository = cls.application.config["POPULATION_REPOSITORY"]

    def analysis(self, code="11110", start="2026-09-01", end="2026-09-13"):
        return self.client.get("/api/analysis", query_string={
            "district_code": code, "start_date": start, "end_date": end,
            "methods": json.dumps(SETTINGS)})

    def test_snapshot_bytes_and_loaded_coverage_match_team_manifest(self):
        manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), manifest["sha256"])
        quality = self.repository.get_data_quality()
        self.assertEqual(quality["record_count"], manifest["record_count"])
        self.assertEqual(quality["district_count"], 25)
        self.assertEqual(quality["region_count"], 26)
        self.assertEqual(quality["encoding_used"], "cp949")
        self.assertEqual(quality["missing_indicator_values"],
                         {"external_inflow": 0, "interdistrict_movement": 0})

    def test_root_profile_advertises_loaded_real_data_and_recent_default_period(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        match = re.search(r'<script id="dashboard-profile" type="application/json">(.*?)</script>',
                          response.get_data(as_text=True), re.S)
        profile = json.loads(match.group(1))
        self.assertEqual(profile["source"]["kind"], "seoul_population")
        self.assertEqual(len(profile["districts"]), 25)
        self.assertNotIn("11000", {item[0] for item in profile["districts"]})
        self.assertEqual((profile["start_date"], profile["end_date"]),
                         ("2023-01-01", "2026-09-13"))
        self.assertEqual(profile["missing_dates"], ["2024-02-29"])
        first = date.fromisoformat(profile["default_start_date"])
        last = date.fromisoformat(profile["default_end_date"])
        self.assertEqual(last - first, timedelta(days=89))

    def test_all_25_districts_api_matches_direct_detection_on_full_history(self):
        for code, _name in self.repository.list_districts():
            with self.subTest(district=code):
                response = self.analysis(code)
                self.assertEqual(response.status_code, 200, response.get_json())
                payload = response.get_json()
                records = self.repository.get_records(code)
                for block in payload["methods"]:
                    expected = [r.to_dict() for r in DETECTORS[block["method"]]().detect(records)
                                if date(2026, 9, 1) <= r.date <= date(2026, 9, 13)]
                    self.assertEqual(block["results"], expected)
                    self.assertEqual(len(block["results"]), 13)
                    self.assertTrue(set(block["details"]) <= {r["date"] for r in expected})

    def test_known_annual_counts_and_weekend_explanation_are_preserved(self):
        response = self.analysis(start="2025-01-01", end="2025-12-31")
        self.assertEqual(response.status_code, 200, response.get_json())
        blocks = {b["method"]: b for b in response.get_json()["methods"]}
        self.assertEqual({name: sum(r["is_anomaly"] is True for r in b["results"])
                          for name, b in blocks.items()},
                         {"moving_average": 120, "z_score": 1, "seasonal": 46})
        info = blocks["seasonal"]["details"]["2025-09-13"]
        self.assertIn("평소 주말보다 19.8% 많았습니다", info["explanation"])
        self.assertIn("원인을 단정할 수 없습니다", info["explanation"])
        source = self.repository.get_records("11110", date(2025, 9, 13), date(2025, 9, 13))[0]
        self.assertEqual(info["indicators"], source.to_dict()["indicators"])

    def test_missing_leap_day_is_not_invented_and_history_resets(self):
        response = self.analysis(start="2024-02-28", end="2024-03-03")
        self.assertEqual(response.status_code, 200)
        for block in response.get_json()["methods"]:
            rows = {r["date"]: r for r in block["results"]}
            self.assertNotIn("2024-02-29", rows)
            self.assertEqual(rows["2024-03-01"]["history_size"], 0)
            self.assertIsNone(rows["2024-03-01"]["is_anomaly"])

    def test_health_reports_success_only_after_csv_loaded(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "district_count": 25,
                                              "record_count": 35126})

    def test_city_total_remains_unselectable_and_empty_period_is_empty(self):
        self.assertEqual(self.analysis("11000").status_code, 400)
        response = self.analysis(start="2030-01-01", end="2030-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(not b["results"] for b in response.get_json()["methods"]))

    def test_earliest_supported_date_returns_empty_data_without_overflow(self):
        response = self.analysis(start="0001-01-01", end="0001-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(not b["results"] for b in response.get_json()["methods"]))

    def test_api_dates_use_canonical_format(self):
        self.assertEqual(self.analysis(start="20260901").status_code, 400)
        self.assertEqual(self.analysis(end="20260913").status_code, 400)

    def test_environment_override_explicit_path_and_missing_file_behavior(self):
        with patch.dict(os.environ, {"POPULATION_CSV_PATH": "data/no-such-source.csv"}):
            with self.assertRaises(FileNotFoundError):
                create_dashboard_app()
            app = create_dashboard_app(SOURCE)
            self.assertEqual(app.test_client().get("/healthz").status_code, 200)
        with patch.dict(os.environ, {"POPULATION_CSV_PATH": "data/population.csv"}):
            app = create_dashboard_app()
            self.assertEqual(app.config["DASHBOARD_PROFILE"]["record_count"], 35126)

    def test_default_path_is_independent_of_current_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {"POPULATION_CSV_PATH": ""}):
                    app = create_dashboard_app()
                self.assertEqual(app.config["DASHBOARD_PROFILE"]["record_count"], 35126)
            finally:
                os.chdir(previous)

    def test_sample_launcher_keeps_synthetic_identity_and_accepts_legacy_dicts(self):
        original = CsvPopulationRepository.list_districts

        def legacy(repository, **options):
            return [{"district_code": code, "district_name": name}
                    for code, name in original(repository, **options)]

        with patch.object(CsvPopulationRepository, "list_districts", legacy):
            profile = create_sample_app().config["DASHBOARD_PROFILE"]
        self.assertEqual(profile["source"]["kind"], "synthetic_sample")
        self.assertEqual(profile["districts"], [["11110", "종로구"], ["11680", "강남구"]])


if __name__ == "__main__":
    unittest.main()
