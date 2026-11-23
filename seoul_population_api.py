"""서울 열린데이터광장 OA-23022의 날짜별 JSON을 CSV 열 형식으로 변환한다."""

import json
import re
from datetime import date
from http.client import HTTPConnection, HTTPException


class SeoulPopulationApi:
    SERVICE = "SPOP_DAILYSUM_JACHI_250"
    COLUMNS = {
        "STDR_DE_ID": "기준일ID",
        "SIGNGU_CODE_SE": "시구코드",
        "SIGNGU_NM": "시구명",
        "TOT_LVPOP_CO": "총생활인구수",
        "LVPOP_CO": "내국인생활인구수",
        "LNGTR_STAY_FRGNR_CO": "장기체류외국인인구수",
        "SRTPD_STAY_FRGNR_CO": "단기체류외국인인구수",
        "DAIL_MXMM_LVPOP_CO": "일최대인구수",
        "DAIL_MUMM_LVPOP_CO": "일최소인구수",
        "DAY_LVPOP_CO": "주간인구수(09~18)",
        "NIGHT_LVPOP_CO": "야간인구수(19~08)",
        "SU_ELSE_INFLOW_LVPOP_CO": "서울외유입인구수",
        "SIGNGU_MVMN_LVPOP_CO": "자치구간이동인구수",
        "LDADNG_DT": "적재일시",
    }
    REGIONS = 26

    def __init__(self, key: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ValueError("SEOUL_OPEN_API_KEY의 형식을 확인해 주세요.")
        self._key = key

    def fetch_day(self, day: date) -> list[dict[str, str]]:
        """하루치 기록을 가져온다. 서울시가 자료 없음으로 응답하면 빈 목록을 반환한다."""
        day_id = day.strftime("%Y%m%d")
        # 공식 API 주소는 HTTP를 사용한다. 리디렉션을 따라가거나 키가 든 요청 경로를 기록하지 않는다.
        connection = HTTPConnection("openapi.seoul.go.kr", 8088, timeout=10)
        try:
            connection.request("GET", f"/{self._key}/json/{self.SERVICE}/1/{self.REGIONS}/{day_id}/")
            response = connection.getresponse()
            status = response.status
            body = response.read(256 * 1024 + 1) if status == 200 else b""
        except (OSError, HTTPException):
            raise OSError(f"서울시 Open API 요청에 실패했습니다 ({day}).") from None
        finally:
            connection.close()
        if status != 200:
            raise OSError(f"서울시 Open API HTTP 응답 오류 ({status})")

        try:
            if len(body) > 256 * 1024:
                raise ValueError("응답 크기 초과")
            payload = json.loads(body, parse_float=str)
            result = payload.get(self.SERVICE, payload)
            code = result["RESULT"]["CODE"]
            if code == "INFO-200":
                return []
            if code == "INFO-100":
                raise PermissionError("서울시 Open API 인증키를 확인해 주세요.")
            if code != "INFO-000":
                raise OSError(f"서울시 Open API가 정상 처리되지 않았습니다 ({day}).")
            rows = result["row"]
            if not isinstance(rows, list) or not 0 < len(rows) == int(result["list_total_count"]) <= self.REGIONS:
                raise ValueError("응답 건수 불일치")
            converted = []
            for row in rows:
                if str(row["STDR_DE_ID"]) != day_id:
                    raise ValueError("요청 날짜와 응답 날짜 불일치")
                if any(type(row[field]) not in (str, int, type(None)) for field in self.COLUMNS):
                    raise ValueError("응답 필드 형식 오류")
                converted.append({column: "" if row[field] is None else str(row[field])
                                  for field, column in self.COLUMNS.items()})
            return converted
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
            raise ValueError(f"서울시 Open API 응답 형식이 올바르지 않습니다 ({day}).") from None
