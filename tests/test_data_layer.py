"""데이터 계층의 입력 조건과 조회 동작을 확인한다."""

import csv
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from csv_population_repository import CsvPopulationRepository
from population_record import PopulationRecord


class PopulationRecordTests(unittest.TestCase):
    def test_serialization_uses_detector_field_names(self):
        record = PopulationRecord(date(2026, 1, 1), "11680", "강남구", 800000.25)
        self.assertEqual(record.to_dict(), {
            "date": "2026-01-01", "district_code": "11680",
            "district_name": "강남구", "total_population": 800000.25,
        })

    def test_invalid_values_are_rejected(self):
        for value in (-1, float("nan"), float("inf"), True, "100"):
            with self.subTest(population=value), self.assertRaises(ValueError):
                PopulationRecord(date(2026, 1, 1), "11680", "강남구", value)
        with self.assertRaises(ValueError):
            PopulationRecord(datetime(2026, 1, 1), "11680", "강남구", 100)
        with self.assertRaises(ValueError):
            PopulationRecord(date(2026, 1, 1), "", "강남구", 100)


class CsvPopulationRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "population.csv"

    def write_rows(self, rows, columns=None):
        with self.path.open("w", encoding="cp949", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(columns or CsvPopulationRepository.REQUIRED_COLUMNS)
            writer.writerows(rows)

    def test_cp949_loading_sorting_and_inclusive_filter(self):
        self.write_rows([
            ["20260103", "11680", "강남구", "103.5"],
            ["20260101", "11110", "종로구", "200"],
            ["20260101", "11680", "강남구", "100"],
            ["20260102", "11680", "강남구", "102"],
        ])
        repository = CsvPopulationRepository(self.path)
        self.assertEqual(repository.load(), 4)
        records = repository.get_records("11680", date(2026, 1, 2), date(2026, 1, 3))
        self.assertEqual([record.total_population for record in records], [102, 103.5])
        self.assertEqual(len(repository.list_districts()), 2)
        records.clear()
        self.assertEqual(len(repository.get_records("11680")), 3)

    def test_missing_columns_and_empty_data_are_rejected(self):
        self.write_rows([], ["기준일ID"])
        with self.assertRaisesRegex(ValueError, "필수 열"):
            CsvPopulationRepository(self.path).load()
        self.write_rows([])
        with self.assertRaisesRegex(ValueError, "기록이 없습니다"):
            CsvPopulationRepository(self.path).load()

    def test_bad_row_reports_line_number(self):
        for invalid_date, population in [("20260230", "100"), ("2026011", "100"), ("20260101", "-1")]:
            self.write_rows([[invalid_date, "11680", "강남구", population]])
            with self.subTest(date=invalid_date, population=population):
                with self.assertRaisesRegex(ValueError, "2행 데이터 오류"):
                    CsvPopulationRepository(self.path).load()

    def test_failed_reload_preserves_previous_records(self):
        self.write_rows([["20260101", "11680", "강남구", "100"]])
        repository = CsvPopulationRepository(self.path)
        repository.load()
        self.write_rows([["20260102", "11680", "강남구", "잘못된 값"]])
        with self.assertRaises(ValueError):
            repository.load()
        self.assertEqual(repository.get_records("11680")[0].total_population, 100)

    def test_queries_require_loading_and_valid_conditions(self):
        self.write_rows([["20260101", "11680", "강남구", "100"]])
        repository = CsvPopulationRepository(self.path)
        with self.assertRaises(RuntimeError):
            repository.get_records("11680")
        repository.load()
        with self.assertRaisesRegex(ValueError, "없는 자치구"):
            repository.get_records("99999")
        with self.assertRaisesRegex(ValueError, "시작일"):
            repository.get_records("11680", date(2026, 1, 3), date(2026, 1, 1))
        self.assertEqual(repository.get_records("11680", date(2027, 1, 1)), [])


if __name__ == "__main__":
    unittest.main()
