"""API 브랜치가 함께 있을 때 실제 저장소·지표 객체·서버의 계약을 검증한다."""

import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path

from csv_population_repository import CsvPopulationRepository
from population_record import PopulationRecord


ROOT = Path(__file__).resolve().parents[1]
HAS_API = (ROOT / "app.py").is_file() and (ROOT / "migration_indicators.py").is_file()
SETTINGS = {
    "moving_average": {"window": 7, "threshold": 0.1},
    "z_score": {"window": 28, "threshold": 3.0},
    "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4},
}


@unittest.skipUnless(HAS_API and find_spec("flask") is not None,
                     "feature/api-explainer와 Flask가 있는 통합 환경에서 실행")
class ApiCompatibilityTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        from migration_indicators import MigrationIndicators

        self.indicator_class = MigrationIndicators
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        source = Path(self.directory.name) / "population.csv"
        with source.open("w", encoding="cp949", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(list(CsvPopulationRepository.REQUIRED_COLUMNS)
                            + list(CsvPopulationRepository.INDICATOR_COLUMNS.values()))
            for index in range(80):
                day = date(2024, 1, 1) + timedelta(days=index)
                weekend = day.weekday() >= 5
                population = 100 if weekend else 200
                inflow = 50 if weekend else 100
                if day == date(2024, 3, 2):
                    population, inflow = 180, 60
                for code, name in (("11110", "종로구"), ("11000", "서울시")):
                    writer.writerow([day.strftime("%Y%m%d"), code, name, population, inflow, 30])
        # 서버 사용자는 factory를 별도로 지정하지 않아도 지표 객체를 받는다.
        self.repository = CsvPopulationRepository(source, require_indicators=True)
        self.repository.load()
        self.client = create_app(self.repository).test_client()

    def get_analysis(self, **params):
        query = {
            "district_code": "11110", "start_date": "2024-03-01",
            "end_date": "2024-03-05", "methods": json.dumps(SETTINGS),
        }
        query.update(params)
        return self.client.get("/api/analysis", query_string=query)

    def test_default_district_list_and_automatic_real_indicator_objects(self):
        self.assertEqual(self.repository.list_districts(), [("11110", "종로구")])
        record = self.repository.get_records("11110")[0]
        self.assertIsInstance(record.indicators, self.indicator_class)
        self.assertEqual(record.to_dict()["indicators"], record.indicators.to_dict())

    def test_real_repository_is_accepted_by_server_and_period_filter_is_preserved(self):
        response = self.get_analysis()
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["schema_version"], 1)
        self.assertEqual({block["method"] for block in body["methods"]}, set(SETTINGS))
        for block in body["methods"]:
            self.assertEqual(len(block["results"]), 5)
            dates = {row["date"] for row in block["results"]}
            self.assertTrue(all("2024-03-01" <= day <= "2024-03-05" for day in dates))
            self.assertTrue(set(block["details"]) <= dates)
            self.assertEqual(block["settings"], SETTINGS[block["method"]])

    def test_weekend_explanation_uses_available_real_objects_and_correct_direction(self):
        body = self.get_analysis().get_json()
        block = next(block for block in body["methods"] if block["method"] == "seasonal")
        info = block["details"]["2024-03-02"]
        self.assertIn("평소 주말보다 20.0% 많았습니다", info["explanation"])
        self.assertIn("원인을 단정할 수 없습니다", info["explanation"])
        self.assertEqual(info["indicators"]["external_inflow"], 60)

    def test_seoul_total_is_not_a_valid_analysis_district(self):
        self.assertEqual(self.get_analysis(district_code="11000").status_code, 400)

    def test_indicator_only_population_record_constructor_matches_teammate_usage(self):
        indicators = self.indicator_class(external_inflow=0, interdistrict_movement=None)
        record = PopulationRecord(date(2024, 1, 1), "11110", "종로구", 100, indicators=indicators)
        self.assertEqual(record.external_inflow, 0)
        self.assertIsNone(record.interdistrict_movement)
        self.assertEqual(record.to_dict()["indicators"], indicators.to_dict())

    def test_valid_empty_period_returns_empty_results(self):
        response = self.get_analysis(start_date="2030-01-01", end_date="2030-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(block["results"] == [] for block in response.get_json()["methods"]))


if __name__ == "__main__":
    unittest.main()
