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
        self.assertIn("서울 외 유입인구도 평소 평일보다", info["explanation"])   # 2/20은 화요일
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

    def test_weekend_compared_with_weekends(self):
        """토요일 지표는 평일이 아니라 직전 주말들과 비교해야 한다."""
        explainer = AnomalyExplainer()
        target = date(2024, 3, 2)                                  # 토요일
        records = []
        for k in range(0, 29):
            day = target - timedelta(days=k)
            weekend = day.weekday() >= 5
            inflow = 60.0 if day == target else (50.0 if weekend else 100.0)
            records.append(SimpleNamespace(district_code="1", date=day,
                                           indicators=MigrationIndicators(inflow, None)))
        result = SimpleNamespace(is_anomaly=True, district_code="1", date=target,
                                 actual=120, expected=100)
        info = explainer.explain(result, records)
        # 주말 평균 50 대비 60 → 20% 많음 (평일까지 섞으면 '적었다'로 반대가 됨)
        self.assertAlmostEqual(info["comparison"]["external_inflow"]["change_ratio"], 0.2)
        self.assertIn("평소 주말보다 20.0% 많았습니다", info["explanation"])


if __name__ == "__main__":
    unittest.main()
