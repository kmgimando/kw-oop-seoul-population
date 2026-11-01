"""데이터 저장소와 실제 세 탐지기·명령줄 실행 사이의 연결을 검증한다."""

import csv
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from compare_detectors import load_records
from csv_population_repository import CsvPopulationRepository
from demo_data import main
from detectors import MovingAverageDetector, ZScoreDetector
from population_record import PopulationRecord
from seasonal_analyzer import SeasonalAnalyzer


class DataIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "population.csv"
        rows = []
        for index in range(80):
            if index == 20:
                continue  # 누락된 날짜를 0으로 채우면 탐지 결과가 바뀐다.
            day = date(2024, 1, 1) + timedelta(days=index)
            base = 1000 if day.weekday() < 5 else 800
            value = (base + (index % 4 - 1) * 10) * (1.5 if index == 72 else 1)
            for code, name, scale in (("11110", "종로구", 1), ("11680", "강남구", 2)):
                rows.append([day.strftime("%Y%m%d"), code, name, value * scale, 0, 30])
        with self.path.open("w", encoding="cp949", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(list(CsvPopulationRepository.REQUIRED_COLUMNS)
                            + list(CsvPopulationRepository.INDICATOR_COLUMNS.values()))
            writer.writerows(reversed(rows))
        self.repository = CsvPopulationRepository(self.path, require_indicators=True)
        self.repository.load()

    def test_three_detectors_match_the_previous_plain_record_contract(self):
        # 저장소 구현과 독립된 기존 4필드 로딩 방식으로 비교 입력을 만든다.
        with self.path.open(encoding="cp949", newline="") as source:
            previous = [SimpleNamespace(
                date=datetime.strptime(row["기준일ID"], "%Y%m%d").date(),
                district_code=row["시구코드"], district_name=row["시구명"],
                total_population=float(row["총생활인구수"]),
            ) for row in csv.DictReader(source)]
        records = self.repository.get_all_records()
        self.assertTrue(all(isinstance(record, PopulationRecord) for record in records))
        for detector in (MovingAverageDetector(), ZScoreDetector(), SeasonalAnalyzer()):
            with self.subTest(method=detector.method):
                self.assertEqual(detector.detect(records), detector.detect(previous))

    def test_history_query_matches_full_detection_for_each_method(self):
        start, end = date(2024, 3, 1), date(2024, 3, 5)
        for detector in (MovingAverageDetector(), ZScoreDetector(), SeasonalAnalyzer()):
            with self.subTest(method=detector.method):
                full = detector.detect(self.repository.get_records("11680"))
                expected = [row for row in full if start <= row.date <= end]
                inputs = self.repository.get_records("11680", start, end, history_days=detector.window)
                actual = [row for row in detector.detect(inputs) if start <= row.date <= end]
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 5)
                self.assertTrue(all(row.is_anomaly is not None for row in actual))

    def test_missing_date_has_no_fake_record_or_detection_result(self):
        missing_day = date(2024, 1, 21)
        records = self.repository.get_records("11110", missing_day, missing_day, history_days=28)
        self.assertEqual(records, [])
        self.assertEqual(MovingAverageDetector().detect(records), [])
        self.assertEqual(self.repository.get_data_quality()["missing_dates_by_district"]["11110"],
                         ["2024-01-21"])

    def test_existing_compare_command_uses_validated_population_records(self):
        self.assertEqual(load_records(self.path), self.repository.get_all_records())
        with self.path.open("a", encoding="cp949", newline="") as output:
            csv.writer(output).writerow(["20240101", "11110", "종로구", "1000", "0", "30"])
        with self.assertRaisesRegex(ValueError, "중복"):
            load_records(self.path)

    def test_cli_exports_only_requested_dates_with_raw_indicators(self):
        output = Path(self.directory.name) / "preview.json"
        argv = ["demo_data.py", "--csv", str(self.path), "--district", "11680",
                "--start", "2024-03-01", "--end", "2024-03-05", "--method", "seasonal",
                "--output", str(output)]
        with patch("sys.argv", argv), redirect_stdout(StringIO()):
            main()
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["records"]), 5)
        self.assertEqual(len(payload["analysis"]["results"]), 5)
        self.assertEqual(payload["analysis"]["summary"]["evaluated_count"], 5)
        self.assertEqual(payload["records"][0]["indicators"]["external_inflow"], 0)
        self.assertEqual(payload["analysis"]["results"][0]["date"], "2024-03-01")

    def test_cli_reports_bad_district_without_traceback(self):
        error_stream = StringIO()
        with patch("sys.argv", ["demo_data.py", "--csv", str(self.path), "--district", "99999"]):
            with redirect_stdout(StringIO()), redirect_stderr(error_stream):
                with self.assertRaises(SystemExit) as failure:
                    main()
        self.assertEqual(failure.exception.code, 1)
        self.assertIn("없는 자치구", error_stream.getvalue())
        self.assertNotIn("Traceback", error_stream.getvalue())

    def test_cli_export_cannot_replace_its_input_csv(self):
        before = self.path.read_bytes()
        with patch("sys.argv", ["demo_data.py", "--csv", str(self.path), "--output", str(self.path)]):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as failure:
                main()
        self.assertEqual(failure.exception.code, 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_requires_method_for_settings_and_limits_seasonal_options(self):
        for arguments in (["--window", "7"], ["--method", "z_score", "--min-samples", "4"]):
            with self.subTest(arguments=arguments), patch("sys.argv", ["demo_data.py", *arguments]):
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as failure:
                    main()
                self.assertEqual(failure.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
