"""하루의 자치구 생활인구를 표현하는 데이터 객체."""

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real


@dataclass(frozen=True)
class PopulationRecord:
    """CSV 한 행의 핵심 값. 탐지기가 읽는 속성 이름을 공통으로 사용한다."""

    date: date
    district_code: str
    district_name: str
    total_population: float

    def __post_init__(self) -> None:
        # 잘못된 값이 담긴 객체를 다른 팀원의 탐지기로 넘기지 않는다.
        self.validate()

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

        population = self.total_population
        if (
            isinstance(population, bool)
            or not isinstance(population, Real)
            or not isfinite(population)
            or population < 0
        ):
            raise ValueError("total_population은 0 이상의 유한한 숫자여야 합니다.")

    def to_dict(self) -> dict:
        """화면 응답에서 사용할 수 있도록 날짜를 문자열로 바꾼다."""
        return {
            "date": self.date.isoformat(),
            "district_code": self.district_code,
            "district_name": self.district_name,
            "total_population": float(self.total_population),
        }

    # TODO: 손호진 담당 MigrationIndicators 구현 후 indicators 속성을 연결한다.
