"""C 담당 부분 테스트: 가짜 Repository로 Flask API 전체 흐름을 확인한다."""

import json
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

from anomaly_explainer import AnomalyExplainer
from app import create_app
from migration_indicators import MigrationIndicators

METHODS = {"moving_average": {"window": 7, "threshold": 0.1},
           "z_score": {"window": 28, "threshold": 3.0},
           "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}}


class FakeRepository:
    """김민규님 CsvPopulationRepository가 완성되기 전까지 쓰는 가짜 저장소."""

    def __init__(self):
        self.records = []
        day = date(2024, 1, 1)
        for i in range(60):
            spike = day == date(2024, 2, 20)
            self.records.append(SimpleNamespace(
                date=day, district_code="11110", district_name="종로구",
                total_population=200.0 if spike else 100.0 + (i % 3),
                indicators=MigrationIndicators(50.0 if spike else 20.0, 30.0)))
            day += timedelta(days=1)

    def list_districts(self):
        return [("11110", "종로구")]

    def get_records(self, code, start, end):
        return [r for r in self.records if r.district_code == code and start <= r.date <= end]


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app(FakeRepository()).test_client()

    def get(self, **params):
        query = {"district_code": "11110", "start_date": "2024-02-15",
                 "end_date": "2024-02-25", "methods": json.dumps(METHODS)}
        query.update(params)
        return self.client.get("/api/analysis?" + urlencode(query))

    def test_success_shape(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["schema_version"], 1)
        self.assertEqual({b["method"] for b in body["methods"]}, set(METHODS))
        for block in body["methods"]:
            self.assertEqual(len(block["results"]), 11)            # 조회 기간만
            self.assertEqual(block["settings"], METHODS[block["method"]])

    def test_spike_gets_explanation(self):
        body = self.get().get_json()
        ma = next(b for b in body["methods"] if b["method"] == "moving_average")
        info = ma["details"]["2024-02-20"]
        self.assertIn("서울 외 유입인구도 평소보다", info["explanation"])
        self.assertIn("단정할 수 없습니다", info["explanation"])
        self.assertEqual(info["indicators"]["external_inflow"], 50.0)

    def test_bad_dates(self):
        response = self.get(start_date="2024-03-01")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_PARAMETER")
        self.assertEqual(self.get(start_date="2024-13-01").status_code, 400)

    def test_bad_methods(self):
        self.assertEqual(self.get(methods="{not json").status_code, 400)
        broken = dict(METHODS, z_score={"window": 1, "threshold": 3.0})
        self.assertEqual(self.get(methods=json.dumps(broken)).status_code, 400)

    def test_unknown_district_and_path(self):
        self.assertEqual(self.get(district_code="99999").status_code, 400)
        self.assertEqual(self.client.get("/api/nothing").status_code, 404)

    def test_missing_indicators(self):
        explainer = AnomalyExplainer()
        result = SimpleNamespace(is_anomaly=True, district_code="1", date=date(2024, 1, 1),
                                 actual=1, expected=2)
        record = SimpleNamespace(district_code="1", date=date(2024, 1, 1), indicators=None)
        info = explainer.explain(result, [record])
        self.assertIsNone(info["indicators"]["external_inflow"])   # 0으로 채우지 않음


if __name__ == "__main__":
    unittest.main()
