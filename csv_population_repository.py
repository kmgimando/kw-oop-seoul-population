"""서울 생활인구 CSV를 읽고 기록 객체를 조회하는 저장소."""

import csv
from datetime import date, datetime
from pathlib import Path

from population_record import PopulationRecord


class CsvPopulationRepository:
    """CSV 파일 접근을 탐지 알고리즘과 분리한다."""

    REQUIRED_COLUMNS = ("기준일ID", "시구코드", "시구명", "총생활인구수")

    def __init__(self, file_path: str | Path, encoding: str = "cp949") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding
        self._records_by_district: dict[str, list[PopulationRecord]] = {}
        self._loaded = False

    def load(self) -> int:
        """CSV를 읽어 자치구별로 정렬하고 읽은 기록 수를 반환한다."""
        # 로딩 도중 오류가 나면 기존에 읽어 둔 정상 데이터는 유지한다.
        grouped: dict[str, list[PopulationRecord]] = {}
        count = 0

        with self.file_path.open(encoding=self.encoding, newline="") as source:
            reader = csv.DictReader(source)
            missing = set(self.REQUIRED_COLUMNS) - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV 필수 열이 없습니다: {', '.join(sorted(missing))}")

            for row in reader:
                try:
                    record = self._parse_row(row)
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValueError(
                        f"CSV {reader.line_num}행 데이터 오류: {error}"
                    ) from error
                grouped.setdefault(record.district_code, []).append(record)
                count += 1

        if count == 0:
            raise ValueError("CSV에 생활인구 기록이 없습니다.")

        for records in grouped.values():
            records.sort(key=lambda record: record.date)

        self._records_by_district = grouped
        self._loaded = True
        return count

    def _parse_row(self, row: dict) -> PopulationRecord:
        """원본 CSV의 열 이름과 파이썬 객체의 속성 이름을 연결한다."""
        date_text = row["기준일ID"].strip()
        if len(date_text) != 8 or not date_text.isascii() or not date_text.isdigit():
            raise ValueError("기준일ID는 YYYYMMDD 형식이어야 합니다.")

        return PopulationRecord(
            date=datetime.strptime(date_text, "%Y%m%d").date(),
            district_code=row["시구코드"].strip(),
            district_name=row["시구명"].strip(),
            total_population=float(row["총생활인구수"]),
        )

    def get_records(
        self,
        district_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PopulationRecord]:
        """자치구의 기록을 날짜 오름차순으로 반환한다. 시작·종료일을 포함한다."""
        self._require_loaded()
        if not isinstance(district_code, str) or not district_code.strip():
            raise ValueError("district_code를 문자열로 입력해 주세요.")
        for bound in (start_date, end_date):
            if bound is not None and (
                not isinstance(bound, date) or isinstance(bound, datetime)
            ):
                raise ValueError("조회 날짜는 datetime.date여야 합니다.")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")

        code = district_code.strip()
        if code not in self._records_by_district:
            raise ValueError(f"CSV에 없는 자치구 코드입니다: {code}")

        # 새 목록을 반환하므로 호출자가 목록을 수정해도 저장소는 바뀌지 않는다.
        return [
            record
            for record in self._records_by_district[code]
            if (start_date is None or record.date >= start_date)
            and (end_date is None or record.date <= end_date)
        ]

    def list_districts(self) -> list[dict[str, str]]:
        """자치구 선택 화면에 전달할 코드와 이름 목록을 반환한다."""
        self._require_loaded()
        return [
            {"district_code": code, "district_name": records[0].district_name}
            for code, records in sorted(self._records_by_district.items())
        ]

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("먼저 load()를 호출해 주세요.")

    # TODO: 자치구·날짜 중복, 동일 코드의 이름 불일치, 누락 날짜를 점검한다.
    # TODO: MigrationIndicators가 구현되면 유입·이동 지표 열도 객체로 변환한다.
