"""서울 생활인구 CSV 로딩, 원자료 검증, 날짜별 조회를 담당한다."""

import csv
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from io import StringIO
from pathlib import Path

from population_record import PopulationRecord


class CsvPopulationRepository:
    """검증이 끝난 기록만 보관한다. 누락 날짜를 임의의 인구값으로 채우지 않는다."""

    REQUIRED_COLUMNS = ("기준일ID", "시구코드", "시구명", "총생활인구수")
    INDICATOR_COLUMNS = {
        "external_inflow": "서울외유입인구수",
        "interdistrict_movement": "자치구간이동인구수",
    }
    SEOUL_TOTAL_CODE = "11000"

    def __init__(
        self,
        file_path: str | Path,
        encoding: str = "auto",
        *,
        require_indicators: bool = False,
        indicators_factory: Callable[..., object] | None = None,
    ) -> None:
        if not isinstance(encoding, str) or not encoding.strip():
            raise ValueError("encoding을 입력해 주세요. 기본값은 auto입니다.")
        if type(require_indicators) is not bool:
            raise ValueError("require_indicators는 bool이어야 합니다.")
        if indicators_factory is not None and not callable(indicators_factory):
            raise ValueError("indicators_factory는 호출 가능한 클래스나 함수여야 합니다.")
        self.file_path = Path(file_path)
        self.encoding = encoding.strip()
        self.require_indicators = require_indicators
        self.indicators_factory = indicators_factory
        self._records_by_district: dict[str, tuple[PopulationRecord, ...]] = {}
        self._dates_by_district: dict[str, tuple[date, ...]] = {}
        self._quality: dict = {}
        self._loaded = False

    def load(self) -> int:
        """파일 전체를 검증한 뒤 교체한다. 실패 시 기존 정상 데이터는 유지한다."""
        text, encoding_used = self._read_text()
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        try:
            headers = self._validate_headers(reader.fieldnames)
            reader.fieldnames = headers
            grouped: dict[str, list[PopulationRecord]] = {}
            first_lines: dict[tuple[str, date], int] = {}
            for row in reader:
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("열 개수가 헤더와 다릅니다.")
                    record = self._parse_row(row)
                    key = (record.district_code, record.date)
                    if key in first_lines:
                        raise ValueError(
                            f"중복된 자치구·날짜: {key[0]}, {key[1]} "
                            f"(처음 등장: {first_lines[key]}행)"
                        )
                    group = grouped.setdefault(record.district_code, [])
                    if group and group[0].district_name != record.district_name:
                        raise ValueError(f"같은 자치구 코드의 이름이 다릅니다: {record.district_code}")
                    group.append(record)
                    first_lines[key] = reader.line_num
                except (ValueError, TypeError) as error:
                    raise ValueError(f"CSV {reader.line_num}행 데이터 오류: {error}") from error
        except csv.Error as error:
            raise ValueError(f"CSV {reader.line_num}행 형식 오류: {error}") from error

        if not grouped:
            raise ValueError("CSV에 생활인구 기록이 없습니다.")
        records_by_district = {
            code: tuple(sorted(records, key=lambda record: record.date))
            for code, records in sorted(grouped.items())
        }
        dates_by_district = {
            code: tuple(record.date for record in records)
            for code, records in records_by_district.items()
        }
        quality = self._build_quality(records_by_district, headers, encoding_used)
        self._records_by_district = records_by_district
        self._dates_by_district = dates_by_district
        self._quality = quality
        self._loaded = True
        return quality["record_count"]

    def _read_text(self) -> tuple[str, str]:
        encodings = ("utf-8-sig", "cp949") if self.encoding.lower() == "auto" else (self.encoding,)
        for encoding in encodings:
            try:
                return self.file_path.read_text(encoding=encoding), encoding
            except UnicodeDecodeError:
                continue
            except LookupError as error:
                raise ValueError(f"지원하지 않는 인코딩입니다: {encoding}") from error
        raise ValueError("CSV를 읽을 수 없습니다. UTF-8 또는 CP949 인코딩을 확인해 주세요.")

    def _validate_headers(self, headers: list[str] | None) -> list[str]:
        if not headers:
            raise ValueError("CSV 헤더가 없습니다.")
        cleaned = [header.strip().lstrip("\ufeff").strip() for header in headers]
        if any(not header for header in cleaned) or len(cleaned) != len(set(cleaned)):
            raise ValueError("CSV 헤더에 빈 이름 또는 중복된 열 이름이 있습니다.")
        required = set(self.REQUIRED_COLUMNS)
        if self.require_indicators:
            required.update(self.INDICATOR_COLUMNS.values())
        missing = required - set(cleaned)
        if missing:
            raise ValueError(f"CSV 필수 열이 없습니다: {', '.join(sorted(missing))}")
        return cleaned

    def _parse_row(self, row: dict[str, str]) -> PopulationRecord:
        date_text = row["기준일ID"].strip()
        if len(date_text) != 8 or not date_text.isascii() or not date_text.isdigit():
            raise ValueError("기준일ID는 YYYYMMDD 형식이어야 합니다.")
        values: dict[str, float | None] = {}
        for name, column in self.INDICATOR_COLUMNS.items():
            value = row.get(column, "").strip()
            if self.require_indicators and not value:
                raise ValueError(f"{column} 값이 비어 있습니다.")
            values[name] = float(value) if value else None
        record = PopulationRecord(
            date=datetime.strptime(date_text, "%Y%m%d").date(),
            district_code=row["시구코드"].strip(),
            district_name=row["시구명"].strip(),
            total_population=float(row["총생활인구수"]),
            **values,
        )
        # 외부 지표 클래스가 준비되면 생성자만 주입한다. 설명 규칙은 구현하지 않는다.
        if self.indicators_factory is not None and all(value is not None for value in values.values()):
            indicators = self.indicators_factory(**values)
            if indicators is None or any(
                getattr(indicators, name, None) != value for name, value in values.items()
            ):
                raise ValueError("지표 객체는 원자료와 동일한 external_inflow·interdistrict_movement가 필요합니다.")
            record = replace(record, indicators=indicators)
        return record

    def get_records(
        self,
        district_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        history_days: int = 0,
    ) -> list[PopulationRecord]:
        """양 끝 날짜를 포함한다. history_days는 시작일 전 달력 일수다."""
        self._require_loaded()
        code = self._get_code(district_code)
        for bound in (start_date, end_date):
            if bound is not None and (not isinstance(bound, date) or isinstance(bound, datetime)):
                raise ValueError("조회 날짜는 datetime.date여야 합니다.")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if type(history_days) is not int or history_days < 0:
            raise ValueError("history_days는 0 이상의 정수여야 합니다.")
        if history_days and start_date is None:
            raise ValueError("history_days를 사용하려면 시작일이 필요합니다.")

        dates = self._dates_by_district[code]
        start = 0 if start_date is None else bisect_left(dates, start_date)
        end = len(dates) if end_date is None else bisect_right(dates, end_date)
        # 조회 기간에 실제 기록이 없으면 과거 기록만 반환하지 않는다.
        if start >= end:
            return []
        if history_days:
            history_start = date.fromordinal(max(1, start_date.toordinal() - history_days))
            start = bisect_left(dates, history_start)
        return list(self._records_by_district[code][start:end])

    def get_all_records(self, *, include_seoul_total: bool = True) -> list[PopulationRecord]:
        """자치구 코드·날짜 순으로 전체 기록을 반환한다."""
        return [
            record
            for district in self.list_districts(include_seoul_total=include_seoul_total)
            for record in self._records_by_district[district["district_code"]]
        ]

    def list_districts(self, *, include_seoul_total: bool = True) -> list[dict[str, str]]:
        self._require_loaded()
        if type(include_seoul_total) is not bool:
            raise ValueError("include_seoul_total은 bool이어야 합니다.")
        return [
            {"district_code": code, "district_name": records[0].district_name}
            for code, records in self._records_by_district.items()
            if include_seoul_total or code != self.SEOUL_TOTAL_CODE
        ]

    def get_date_range(self, district_code: str | None = None) -> tuple[date, date]:
        """전체 또는 특정 지역에 실제 존재하는 첫 날짜·마지막 날짜를 반환한다."""
        self._require_loaded()
        if district_code is not None:
            dates = self._dates_by_district[self._get_code(district_code)]
            return dates[0], dates[-1]
        return (
            min(dates[0] for dates in self._dates_by_district.values()),
            max(dates[-1] for dates in self._dates_by_district.values()),
        )

    def get_data_quality(self) -> dict:
        """JSON으로 전달 가능한 품질 요약을 반환한다. 내부 상태는 노출하지 않는다."""
        self._require_loaded()
        return deepcopy(self._quality)

    def _build_quality(self, groups: dict, headers: list[str], encoding_used: str) -> dict:
        first = min(records[0].date for records in groups.values())
        last = max(records[-1].date for records in groups.values())
        calendar = [date.fromordinal(day) for day in range(first.toordinal(), last.toordinal() + 1)]
        gaps = {}
        ranges = {}
        missing_values = dict.fromkeys(self.INDICATOR_COLUMNS, 0)
        for code, records in groups.items():
            observed = {record.date for record in records}
            missing = [day.isoformat() for day in calendar if day not in observed]
            if missing:
                gaps[code] = missing
            ranges[code] = {"start_date": records[0].date.isoformat(), "end_date": records[-1].date.isoformat()}
            for name in missing_values:
                missing_values[name] += sum(getattr(record, name) is None for record in records)
        return {
            "record_count": sum(len(records) for records in groups.values()),
            "region_count": len(groups),
            "district_count": sum(code != self.SEOUL_TOTAL_CODE for code in groups),
            "has_seoul_total": self.SEOUL_TOTAL_CODE in groups,
            "start_date": first.isoformat(),
            "end_date": last.isoformat(),
            "encoding_used": encoding_used,
            "indicator_columns": {name: column in headers for name, column in self.INDICATOR_COLUMNS.items()},
            "missing_indicator_values": missing_values,
            "date_ranges_by_district": ranges,
            "missing_dates_by_district": gaps,
            "missing_day_count": sum(len(days) for days in gaps.values()),
        }

    def _get_code(self, district_code: str) -> str:
        if not isinstance(district_code, str) or not district_code.strip():
            raise ValueError("district_code를 문자열로 입력해 주세요.")
        code = district_code.strip()
        if code not in self._records_by_district:
            raise ValueError(f"CSV에 없는 자치구 코드입니다: {code}")
        return code

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("먼저 load()를 호출해 주세요.")
