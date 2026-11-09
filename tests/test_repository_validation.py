"""실제 CSV에서 발생할 수 있는 형식 오류와 조회 경계를 확인한다."""

import csv
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from csv_population_repository import CsvPopulationRepository
from population_record import PopulationRecord


class RecordValueTests(unittest.TestCase):
    def test_zero_and_missing_indicators_remain_distinct_in_json(self):
        record = PopulationRecord(date(2026, 1, 1), "11110", "종로구", 100, 0, None)
        values = json.loads(json.dumps(record.to_dict(), allow_nan=False))
        self.assertEqual(values["indicators"], {"external_inflow": 0.0, "interdistrict_movement": None})
        with self.assertRaises(FrozenInstanceError):
            record.total_population = 0

    def test_bad_indicator_values_and_codes_are_rejected(self):
        for value in (-1, float("nan"), float("inf"), True, "100", 10 ** 400):
            with self.subTest(value=repr(value)[:20]), self.assertRaises(ValueError):
                PopulationRecord(date(2026, 1, 1), "11110", "종로구", 100, value)
        for code in ("1111", "abcde", "１１１１０", " 11110", 11110):
            with self.subTest(code=code), self.assertRaises(ValueError):
                PopulationRecord(date(2026, 1, 1), code, "종로구", 100)

    def test_indicator_object_alone_populates_original_values_and_json(self):
        indicators = SimpleNamespace(external_inflow=0, interdistrict_movement=30)
        record = PopulationRecord(date(2026, 1, 1), "11110", "종로구", 100, indicators=indicators)
        self.assertEqual((record.external_inflow, record.interdistrict_movement), (0, 30))
        self.assertEqual(record.to_dict()["indicators"], {"external_inflow": 0.0, "interdistrict_movement": 30.0})
        with self.assertRaisesRegex(ValueError, "값이 다릅니다"):
            PopulationRecord(date(2026, 1, 1), "11110", "종로구", 100, 1, 30, indicators)
        with self.assertRaisesRegex(ValueError, "속성이 필요"):
            PopulationRecord(date(2026, 1, 1), "11110", "종로구", 100, indicators=object())


class RepositoryValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "population.csv"
        self.headers = list(CsvPopulationRepository.REQUIRED_COLUMNS)

    def write(self, rows, *, headers=None, encoding="utf-8-sig"):
        with self.path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(self.headers if headers is None else headers)
            writer.writerows(rows)

    def repository(self, rows, **kwargs):
        self.write(rows)
        repository = CsvPopulationRepository(self.path, **kwargs)
        repository.load()
        return repository

    def test_auto_encoding_and_trimmed_headers(self):
        for encoding in ("cp949", "utf-8", "utf-8-sig"):
            self.write([["20260101", " 11110 ", " 종로구 ", "100.25"]],
                       headers=[f" {name} " for name in self.headers], encoding=encoding)
            repository = CsvPopulationRepository(self.path)
            self.assertEqual(repository.load(), 1)
            record = repository.get_records("11110")[0]
            self.assertEqual((record.district_name, record.total_population), ("종로구", 100.25))
            self.assertEqual(repository.get_data_quality()["encoding_used"],
                             "cp949" if encoding == "cp949" else "utf-8-sig")

    def test_optional_and_required_indicator_columns(self):
        repository = self.repository([["20260101", "11110", "종로구", "100"]])
        self.assertIsNone(repository.get_records("11110")[0].external_inflow)
        self.assertEqual(repository.get_data_quality()["missing_indicator_values"]["external_inflow"], 1)
        with self.assertRaisesRegex(ValueError, "필수 열"):
            CsvPopulationRepository(self.path, require_indicators=True).load()

        headers = self.headers + list(CsvPopulationRepository.INDICATOR_COLUMNS.values())
        self.write([["20260101", "11110", "종로구", "100", "0", ""]], headers=headers)
        repository = CsvPopulationRepository(self.path)
        repository.load()
        record = repository.get_records("11110")[0]
        self.assertEqual(record.external_inflow, 0)
        self.assertIsNone(record.interdistrict_movement)
        with self.assertRaisesRegex(ValueError, "자치구간이동인구수"):
            CsvPopulationRepository(self.path, require_indicators=True).load()

    def test_all_population_columns_reject_non_finite_and_negative(self):
        headers = self.headers + list(CsvPopulationRepository.INDICATOR_COLUMNS.values())
        for index in (3, 4, 5):
            for value in ("-1", "NaN", "Infinity", "잘못된 값"):
                row = ["20260101", "11110", "종로구", "100", "20", "30"]
                row[index] = value
                self.write([row], headers=headers)
                with self.subTest(index=index, value=value), self.assertRaisesRegex(ValueError, "2행"):
                    CsvPopulationRepository(self.path).load()

    def test_duplicate_dates_and_inconsistent_names_are_not_silently_merged(self):
        for row, message in (
            (["20260101", "11110", "종로구", "100"], "중복된 자치구·날짜"),
            (["20260102", "11110", "중구", "100"], "이름이 다릅니다"),
        ):
            self.write([["20260101", "11110", "종로구", "100"], row])
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, message):
                CsvPopulationRepository(self.path).load()

    def test_bad_headers_and_wrong_column_counts(self):
        for headers in (self.headers + ["시구코드"], self.headers + [""]):
            self.write([], headers=headers)
            with self.assertRaisesRegex(ValueError, "헤더"):
                CsvPopulationRepository(self.path).load()
        for row in (["20260101", "11110", "종로구"],
                    ["20260101", "11110", "종로구", "100", "추가 값"]):
            self.write([row])
            with self.assertRaisesRegex(ValueError, "열 개수"):
                CsvPopulationRepository(self.path).load()
        self.path.write_text('기준일ID,시구코드,시구명,총생활인구수\n"20260101,11110,종로구,100', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "형식 오류"):
            CsvPopulationRepository(self.path).load()

    def test_extra_columns_and_quoted_names_are_read_correctly(self):
        self.write([["20260101", "11110", "종로,구", "100", "사용하지 않는 값"]],
                   headers=self.headers + ["추가열"])
        repository = CsvPopulationRepository(self.path)
        repository.load()
        self.assertEqual(repository.get_records("11110")[0].district_name, "종로,구")

    def test_quality_reports_internal_and_boundary_gaps_without_filling(self):
        repository = self.repository([
            ["20260101", "11110", "종로구", "100"],
            ["20260103", "11110", "종로구", "103"],
            ["20260102", "11680", "강남구", "200"],
            ["20260104", "11680", "강남구", "204"],
        ])
        quality = repository.get_data_quality()
        self.assertEqual(quality["missing_dates_by_district"], {
            "11110": ["2026-01-02", "2026-01-04"],
            "11680": ["2026-01-01", "2026-01-03"],
        })
        self.assertEqual(quality["missing_day_count"], 4)
        self.assertEqual(len(repository.get_records("11110")), 2)
        self.assertEqual(repository.get_date_range(), (date(2026, 1, 1), date(2026, 1, 4)))
        self.assertEqual(repository.get_date_range("11110"), (date(2026, 1, 1), date(2026, 1, 3)))
        quality["missing_dates_by_district"]["11110"].clear()
        self.assertEqual(len(repository.get_data_quality()["missing_dates_by_district"]["11110"]), 2)

    def test_api_district_contract_excludes_seoul_total_by_default(self):
        repository = self.repository([
            ["20260101", "11000", "서울시", "1000"],
            ["20260101", "11110", "종로구", "100"],
        ])
        self.assertEqual(len(repository.list_districts()), 1)
        self.assertEqual(repository.list_districts(), [("11110", "종로구")])
        self.assertEqual(len(repository.list_districts(include_seoul_total=True)), 2)
        self.assertEqual(repository.get_data_quality()["district_count"], 1)
        self.assertEqual(repository.list_districts(include_seoul_total=False),
                         [("11110", "종로구")])
        self.assertEqual(len(repository.get_all_records(include_seoul_total=False)), 1)
        self.assertEqual(len(repository.get_all_records()), 2)

    def test_history_uses_calendar_days_and_empty_queries_stay_empty(self):
        repository = self.repository([
            ["20260101", "11110", "종로구", "1"],
            ["20260105", "11110", "종로구", "5"],
            ["20260106", "11110", "종로구", "6"],
        ])
        rows = repository.get_records("11110", date(2026, 1, 6), date(2026, 1, 6), history_days=2)
        self.assertEqual([row.total_population for row in rows], [5, 6])
        self.assertEqual(repository.get_records("11110", date(2026, 1, 3), date(2026, 1, 3), history_days=2), [])
        self.assertEqual(repository.get_records("11110", date(2027, 1, 1), history_days=1000), [])
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repository.get_records("11110", date(2026, 1, 1), history_days=value)
        with self.assertRaisesRegex(ValueError, "시작일"):
            repository.get_records("11110", history_days=7)
        with self.assertRaises(ValueError):
            repository.get_records("11110", datetime(2026, 1, 1))

    def test_history_date_min_does_not_overflow(self):
        repository = self.repository([["20260101", "11110", "종로구", "100"]])
        self.assertEqual(len(repository.get_records("11110", date.min, history_days=28)), 1)

    def test_external_indicator_object_can_be_injected_without_importing_team_module(self):
        headers = self.headers + list(CsvPopulationRepository.INDICATOR_COLUMNS.values())
        self.write([["20260101", "11110", "종로구", "100", "0", "30"]], headers=headers)
        repository = CsvPopulationRepository(self.path, indicators_factory=SimpleNamespace)
        repository.load()
        record = repository.get_records("11110")[0]
        self.assertEqual(record.indicators.external_inflow, 0)
        self.assertEqual(record.indicators.interdistrict_movement, 30)
        with self.assertRaisesRegex(ValueError, "지표 객체"):
            CsvPopulationRepository(self.path, indicators_factory=lambda **kwargs: object()).load()
        self.write([["20260101", "11110", "종로구", "100", "", "30"]], headers=headers)
        repository = CsvPopulationRepository(self.path, indicators_factory=SimpleNamespace)
        repository.load()
        partial = repository.get_records("11110")[0].indicators
        self.assertIsNone(partial.external_inflow)
        self.assertEqual(partial.interdistrict_movement, 30)

    def test_failed_reload_keeps_records_date_index_and_quality_consistent(self):
        repository = self.repository([["20260101", "11110", "종로구", "100"]])
        previous = repository.get_data_quality()
        self.write([["20260102", "11110", "종로구", "200"]] * 2)
        with self.assertRaises(ValueError):
            repository.load()
        self.assertEqual(repository.get_data_quality(), previous)
        self.assertEqual(repository.get_date_range(), (date(2026, 1, 1), date(2026, 1, 1)))
        self.assertEqual(repository.get_records("11110")[0].total_population, 100)
        self.assertEqual(repository.get_data_quality()["record_count"], 1)

    def test_configuration_and_unloaded_state_are_explicit(self):
        for options in ({"require_indicators": 1}, {"encoding": ""}, {"indicators_factory": 7}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                CsvPopulationRepository(self.path, **options)
        self.write([["20260101", "11110", "종로구", "100"]])
        with self.assertRaisesRegex(ValueError, "인코딩"):
            CsvPopulationRepository(self.path, encoding="no-such-encoding").load()
        repository = CsvPopulationRepository(self.path)
        for action in (repository.get_data_quality, repository.get_date_range, repository.get_all_records):
            with self.assertRaises(RuntimeError):
                action()


if __name__ == "__main__":
    unittest.main()
