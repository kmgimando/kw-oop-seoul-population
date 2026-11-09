import csv
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from csv_population_repository import CsvPopulationRepository
from dashboard_app import create_dashboard_app
from population_refresh import KST, PopulationRefresh
from run_sample_dashboard import create_sample_app
from seoul_population_api import SeoulPopulationApi


SEED_END = date(2026, 9, 13)
NEXT_DAY = SEED_END + timedelta(days=1)
REGIONS = {"11000": "서울시", **{str(11000 + i): f"테스트구{i}" for i in range(1, 26)}}


def daily_rows(day):
    return [
        {"기준일ID": day.strftime("%Y%m%d"), "시구코드": code, "시구명": name,
         "총생활인구수": "120.5", "서울외유입인구수": "5", "자치구간이동인구수": "10"}
        for code, name in REGIONS.items()
    ]


class SeoulPopulationApiTests(unittest.TestCase):
    @patch("seoul_population_api.HTTPConnection")
    def test_date_filter_and_official_json_fields(self, connection):
        raw = {field: "0" for field in SeoulPopulationApi.COLUMNS}
        raw.update(STDR_DE_ID="20260914", SIGNGU_CODE_SE="11000", SIGNGU_NM="서울시",
                   TOT_LVPOP_CO="120.50", SU_ELSE_INFLOW_LVPOP_CO="5.25",
                   SIGNGU_MVMN_LVPOP_CO="10.75")
        result = {"SPOP_DAILYSUM_JACHI_250": {
            "RESULT": {"CODE": "INFO-000"}, "list_total_count": 1, "row": [raw]}}
        connection.return_value.getresponse.return_value = Mock(status=200, **{
            "read.return_value": json.dumps(result).encode()})
        row, = SeoulPopulationApi("test-key").fetch_day(NEXT_DAY)
        connection.assert_called_once_with("openapi.seoul.go.kr", 8088, timeout=10)
        connection.return_value.request.assert_called_once_with(
            "GET", "/test-key/json/SPOP_DAILYSUM_JACHI_250/1/26/20260914/")
        self.assertEqual(row["총생활인구수"], "120.50")
        self.assertEqual(row["서울외유입인구수"], "5.25")
        self.assertEqual(row["자치구간이동인구수"], "10.75")
        raw["STDR_DE_ID"] = "20260915"
        connection.return_value.getresponse.return_value.read.return_value = json.dumps(result).encode()
        with self.assertRaisesRegex(ValueError, "응답 형식"):
            SeoulPopulationApi("test-key").fetch_day(NEXT_DAY)

    @patch("seoul_population_api.HTTPConnection")
    def test_empty_response_and_errors_are_distinct_and_do_not_expose_key(self, connection):
        client = SeoulPopulationApi("test-key")
        response = Mock(status=200)
        connection.return_value.getresponse.return_value = response
        response.read.return_value = b'{"RESULT":{"CODE":"INFO-200"}}'
        self.assertEqual(client.fetch_day(NEXT_DAY), [])
        response.read.return_value = b'{"RESULT":{"CODE":"INFO-100","MESSAGE":"test-key"}}'
        with self.assertRaisesRegex(PermissionError, "인증키") as error:
            client.fetch_day(NEXT_DAY)
        self.assertNotIn("test-key", str(error.exception))
        response.status = 302
        with self.assertRaisesRegex(OSError, "302"):
            client.fetch_day(NEXT_DAY)
        connection.return_value.request.side_effect = TimeoutError("/test-key/json/")
        with self.assertRaisesRegex(OSError, "요청에 실패") as error:
            client.fetch_day(NEXT_DAY)
        self.assertNotIn("test-key", str(error.exception))


class PopulationRefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        source = directory / "seed.csv"
        rows = daily_rows(SEED_END)
        with source.open("w", encoding="cp949", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        self.original = source.read_bytes().rstrip(b"\r\n")
        source.write_bytes(self.original)
        self.seed = CsvPopulationRepository(source, require_indicators=True)
        self.seed.load()
        self.api = Mock(spec=SeoulPopulationApi, REGIONS=SeoulPopulationApi.REGIONS,
                        COLUMNS=SeoulPopulationApi.COLUMNS)
        self.api.fetch_day.side_effect = daily_rows
        self.cache_dir = directory / "cache"
        self.refresh = PopulationRefresh(self.seed, self.cache_dir, self.api)

    def test_backfill_then_repeat_preserves_original_and_cached_bytes(self):
        today = NEXT_DAY + timedelta(days=5)
        repository, added, skipped = self.refresh.refresh_once(today)
        self.assertEqual((added, skipped), (2, []))
        self.assertEqual(repository.get_data_quality()["record_count"], 78)
        self.assertEqual(repository.get_records("11001")[-1].date, NEXT_DAY + timedelta(days=1))
        self.assertEqual(self.seed.file_path.read_bytes(), self.original)
        before = self.refresh.cache.read_bytes()
        self.assertTrue(before.startswith(self.original))
        self.api.fetch_day.reset_mock()
        _, added, skipped = self.refresh.refresh_once(today)
        self.assertEqual((added, skipped), (0, []))
        self.api.fetch_day.assert_not_called()
        self.assertEqual(self.refresh.cache.read_bytes(), before)

    def test_incomplete_day_is_retried_even_if_later_day_is_available(self):
        today = NEXT_DAY + timedelta(days=5)
        self.api.fetch_day.side_effect = lambda day: daily_rows(day)[:25] if day == NEXT_DAY else daily_rows(day)
        repository, added, skipped = self.refresh.refresh_once(today)
        self.assertEqual((added, skipped), (1, [NEXT_DAY]))
        self.assertNotIn(NEXT_DAY, {record.date for record in repository.get_records("11001")})
        self.api.fetch_day.reset_mock(side_effect=True)
        self.api.fetch_day.side_effect = daily_rows
        repository, added, skipped = self.refresh.refresh_once(today)
        self.api.fetch_day.assert_called_once_with(NEXT_DAY)
        self.assertEqual((added, skipped), (1, []))
        self.assertEqual(repository.get_data_quality()["record_count"], 78)

    def test_invalid_batch_and_network_error_do_not_replace_cache(self):
        self.refresh.refresh_once(NEXT_DAY + timedelta(days=4))
        before = self.refresh.cache.read_bytes()
        later = NEXT_DAY + timedelta(days=1)
        bad = daily_rows(later)
        bad[0]["총생활인구수"] = "NaN"
        self.api.fetch_day.side_effect = [bad]
        with self.assertRaises(ValueError):
            self.refresh.refresh_once(later + timedelta(days=4))
        self.api.fetch_day.side_effect = [daily_rows(later), OSError("네트워크 실패")]
        with self.assertRaises(OSError):
            self.refresh.refresh_once(later + timedelta(days=5))
        self.assertEqual(self.refresh.cache.read_bytes(), before)
        self.assertEqual(self.seed.file_path.read_bytes(), self.original)
        self.assertEqual(list(self.cache_dir.glob("*.tmp")), [])

    @patch("dashboard_app.Thread")
    def test_dashboard_publishes_new_rows_and_dates_without_a_restart(self, thread):
        with patch.dict(os.environ, {"SEOUL_OPEN_API_KEY": "test-key",
                                     "SEOUL_POPULATION_CACHE_DIR": str(self.cache_dir)}):
            app = create_dashboard_app(self.seed.file_path)
            create_sample_app()
        self.assertEqual(thread.call_count, 1)
        client = app.test_client()
        self.assertEqual(client.get("/healthz").get_json()["record_count"], 26)
        self.assertEqual(app.config["DASHBOARD_PROFILE"]["end_date"], SEED_END.isoformat())
        kwargs = thread.call_args.kwargs
        with patch.object(SeoulPopulationApi, "fetch_day", side_effect=daily_rows), \
                patch("population_refresh.datetime", wraps=datetime) as clock, \
                patch("population_refresh.sleep", side_effect=KeyboardInterrupt):
            clock.now.return_value = datetime(2026, 9, 18, 13, tzinfo=KST)
            with self.assertRaises(KeyboardInterrupt):
                kwargs["target"](*kwargs["args"])
        self.assertEqual(client.get("/healthz").get_json()["record_count"], 52)
        page = client.get("/").get_data(as_text=True)
        self.assertIn('"end_date": "2026-09-14"', page)
        self.assertIn('"auto_refresh": true', page)
        response = client.get("/api/analysis", query_string={
            "district_code": "11001", "start_date": NEXT_DAY.isoformat(), "end_date": NEXT_DAY.isoformat(),
            "methods": json.dumps({"moving_average": {"window": 7, "threshold": 0.1},
                                   "z_score": {"window": 28, "threshold": 3},
                                   "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}})})
        self.assertEqual(response.status_code, 200)
        row, = response.get_json()["methods"][0]["results"]
        self.assertEqual((row["date"], row["actual"]), (NEXT_DAY.isoformat(), 120.5))
