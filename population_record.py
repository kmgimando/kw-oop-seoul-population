"""하루의 자치구 생활인구를 표현하는 데이터 객체."""

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from numbers import Real


@dataclass(frozen=True)
class PopulationRecord:
    """한 날짜·한 지역의 원자료. 없는 지표와 실제 관측값 0을 구분한다."""

    date: date
    district_code: str
    district_name: str
    total_population: float
    external_inflow: float | None = None
    interdistrict_movement: float | None = None
    # 지표의 해석·비교는 별도 담당 객체에 맡기고 원래 수치는 위 필드에 보존한다.
    indicators: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # 팀원 코드처럼 indicators 객체만 전달해도 원자료 필드와 직렬화가 일치한다.
        if self.indicators is not None:
            for name in ("external_inflow", "interdistrict_movement"):
                if not hasattr(self.indicators, name):
                    raise ValueError(f"indicators 객체에 {name} 속성이 필요합니다.")
                indicator_value = getattr(self.indicators, name)
                original = getattr(self, name)
                if original is not None and original != indicator_value:
                    raise ValueError(f"{name} 원자료와 indicators 객체의 값이 다릅니다.")
                object.__setattr__(self, name, indicator_value)
        # 잘못된 값이 담긴 객체를 다른 팀원의 탐지기로 넘기지 않는다.
        self.validate()
        for name in ("total_population", "external_inflow", "interdistrict_movement"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, float(value))

    def validate(self) -> None:
        """날짜, 자치구 식별 정보, 인구값의 기본 조건을 확인한다."""
        if not isinstance(self.date, date) or isinstance(self.date, datetime):
            raise ValueError("date는 시간이 없는 datetime.date여야 합니다.")

        for name in ("district_code", "district_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}는 비어 있지 않은 문자열이어야 합니다.")
            if value != value.strip():
                raise ValueError(f"{name}의 앞뒤 공백을 제거해 주세요.")

        if (len(self.district_code) != 5 or not self.district_code.isascii()
                or not self.district_code.isdigit()):
            raise ValueError("district_code는 서울시 CSV의 5자리 숫자 문자열이어야 합니다.")

        for name in ("total_population", "external_inflow", "interdistrict_movement"):
            value = getattr(self, name)
            if value is None and name != "total_population":
                continue
            message = f"{name}은 0 이상의 유한한 숫자여야 합니다."
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(message)
            try:
                valid = isfinite(float(value)) and value >= 0
            except (OverflowError, ValueError):
                valid = False
            if not valid:
                raise ValueError(message)

    def to_dict(self) -> dict:
        """화면 응답에서 사용할 수 있도록 날짜를 문자열로 바꾼다."""
        return {
            "date": self.date.isoformat(),
            "district_code": self.district_code,
            "district_name": self.district_name,
            "total_population": self.total_population,
            "indicators": {
                "external_inflow": self.external_inflow,
                "interdistrict_movement": self.interdistrict_movement,
            },
        }
