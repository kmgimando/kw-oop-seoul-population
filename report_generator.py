"""
생활인구 기록·탐지 결과·참고 설명을 화면 응답 데이터로 구성

응답 형식: docs/api-contract-proposal.md (schema_version + methods 3개)
검증 기준: 프론트엔드 static/js/adapter.js가 거부하는 응답은 서버에서 먼저 막는다.
records: 사전 이력 포함 생활인구 기록
results: 방법별 DetectionResult 목록
explanations: 방법별 {"YYYY-MM-DD": 설명}
settings: 요청에서 검증된 방법별 설정
"""

import json
from datetime import date
from math import isfinite
from numbers import Real


class PayloadValidationError(ValueError):
    """
    응답이 API 계약과 맞지 않을 때 발생하는 예외로, 사용자 입력 오류가 아니므로 서버에서 500으로 처리
    ReportGenerator의 검증에서 문제가 발견되면 이유를 메시지로 담은 객체를 만들고 raise
    응답 검증 실패라는 사실을 알려주기 위해 ValueError 바로 사용하지 않고, ValueError를 상속한 새 클래스를 정의
    """


class ReportGenerator:
    SCHEMA_VERSION = 1
    DETAIL_KEYS = ("explanation", "indicators")
    INDICATOR_KEYS = ("external_inflow", "interdistrict_movement")
    NULLABLE_NUMBER_KEYS = ("expected", "lower_bound", "upper_bound", "score", "deviation_ratio")
    RESULT_KEYS = ("date", "district_code", "district_name", "method", "actual", "threshold",
                   "is_anomaly", "status", "history_size") + NULLABLE_NUMBER_KEYS

    def __init__(self, records, results, explanations, settings, start, end):
        self.records = records
        self.results = results
        self.explanations = explanations
        self.settings = settings
        self.start = start
        self.end = end
        self._records_by_key = {(r.district_code, r.date.isoformat()): r for r in records}

    def build_payload(self):
        payload = {"schema_version": self.SCHEMA_VERSION,
                   "methods": [self._build_block(name) for name in self.settings]}
        self.validate_payload(payload)
        return payload

    def _in_period(self, day) -> bool:
        return self.start <= day <= self.end

    def _build_block(self, method) -> dict:
        rows = [r.to_dict() for r in self.results[method] if self._in_period(r.date)]
        dates = {row["date"] for row in rows}
        return {"method": method, "settings": self.settings[method],
                "results": rows, "details": self._build_details(method, dates)}

    def _build_details(self, method, dates) -> dict:
        return {day: {key: info.get(key) for key in self.DETAIL_KEYS}
                for day, info in self.explanations.get(method, {}).items()
                if day in dates}

    def validate_payload(self, payload) -> None:
        if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
            raise PayloadValidationError("schema_version이 올바르지 않습니다.")
        blocks = payload.get("methods")
        if not isinstance(blocks, list):
            raise PayloadValidationError("methods는 목록이어야 합니다.")
        names = [block.get("method") if isinstance(block, dict) else None for block in blocks]
        if len(names) != len(set(names)) or set(names) != set(self.settings):
            raise PayloadValidationError(f"methods에는 {sorted(self.settings)}가 하나씩 있어야 합니다.")
        for block in blocks:
            self._validate_block(block)
        try:
            json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise PayloadValidationError(f"JSON으로 변환할 수 없는 값이 있습니다: {error}") from error

    def _validate_block(self, block) -> None:
        method = block["method"]
        if block.get("settings") != self.settings[method]:
            raise PayloadValidationError(f"{method}: 응답 settings가 요청 설정과 다릅니다.")
        rows = block.get("results")
        if not isinstance(rows, list):
            raise PayloadValidationError(f"{method}: results는 목록이어야 합니다.")
        dates = set()
        for row in rows:
            self._validate_row(row, method)
            if row["date"] in dates:
                raise PayloadValidationError(f"{method}: 중복된 날짜 {row['date']}")
            dates.add(row["date"])
        self._validate_details(block.get("details", {}), dates)

    def _validate_row(self, row, method) -> None:
        settings = self.settings[method]
        where = f"{method} {row.get('date') if isinstance(row, dict) else row}"

        def fail(message):
            raise PayloadValidationError(f"{where}: {message}")

        if not isinstance(row, dict) or set(self.RESULT_KEYS) - set(row):
            fail("결과 필드가 빠져 있습니다.")
        try:
            day = date.fromisoformat(row["date"])
        except (TypeError, ValueError):
            fail("date는 YYYY-MM-DD 문자열이어야 합니다.")
        if day.isoformat() != row["date"] or not self._in_period(day):
            fail("조회 기간 밖이거나 형식이 다른 날짜입니다.")
        if row["method"] != method:
            fail("결과의 method가 블록과 다릅니다.")
        if not isinstance(row["district_name"], str):
            fail("district_name은 문자열이어야 합니다.")

        record = self._records_by_key.get((row["district_code"], row["date"]))
        if record is None:
            fail("원자료에 없는 자치구·날짜입니다.")
        if not self._is_number(row["actual"]) or row["actual"] < 0 \
                or row["actual"] != float(record.total_population):
            fail("actual이 원자료의 생활인구와 다릅니다.")

        if row["threshold"] != settings["threshold"]:
            fail("threshold가 요청 설정과 다릅니다.")
        size = row["history_size"]
        if type(size) is not int or not 0 <= size <= settings["window"]:
            fail("history_size는 0 이상 window 이하의 정수여야 합니다.")
        if not isinstance(row["status"], str):
            fail("status는 문자열이어야 합니다.")

        # is_anomaly: true 이상, false 정상, null 판정불가 (1·0 같은 숫자는 허용하지 않음)
        if row["is_anomaly"] is not None and not isinstance(row["is_anomaly"], bool):
            fail("is_anomaly는 true, false, null 중 하나여야 합니다.")
        for key in self.NULLABLE_NUMBER_KEYS:
            if row[key] is not None and not self._is_number(row[key]):
                fail(f"{key}는 유한한 숫자이거나 null이어야 합니다.")
        if row["is_anomaly"] is not None and None in (row["expected"], row["lower_bound"], row["upper_bound"]):
            fail("판정된 결과에는 기준값과 정상 범위가 있어야 합니다.")

    def _validate_details(self, details, dates) -> None:
        if not isinstance(details, dict):
            raise PayloadValidationError("details는 객체여야 합니다.")
        for day, info in details.items():
            if day not in dates:
                raise PayloadValidationError(f"details의 {day}는 results에 없는 날짜입니다.")
            if not isinstance(info, dict):
                raise PayloadValidationError(f"details {day}: 설명은 객체여야 합니다.")
            if info.get("explanation") is not None and not isinstance(info["explanation"], str):
                raise PayloadValidationError(f"details {day}: explanation은 문자열이거나 null이어야 합니다.")
            indicators = info.get("indicators") or {}
            if not isinstance(indicators, dict):
                raise PayloadValidationError(f"details {day}: indicators는 객체여야 합니다.")
            for key in self.INDICATOR_KEYS:
                value = indicators.get(key)
                if value is not None and not self._is_number(value):
                    raise PayloadValidationError(f"details {day}: {key}는 숫자이거나 null이어야 합니다.")

    @staticmethod
    def _is_number(value) -> bool:
        """bool을 제외한 유한한 실수인지 확인한다. (True도 파이썬에서는 int라서 따로 막는다)"""
        return isinstance(value, Real) and not isinstance(value, bool) and isfinite(value)
