"""유입·이동 인구 지표 객체 (담당: 손호진)

하루치 '서울 외 유입인구'와 '자치구 간 이동인구'를 저장하고,
기준값(과거 평균)과 비교해서 얼마나 변했는지 계산한다.
값이 없는 날은 None으로 둔다. (0으로 채우지 않는다: 0은 '실제로 0명'이라는 뜻이라서)
"""

from math import isfinite
from numbers import Real
from statistics import fmean


class MigrationIndicators:
    # 이 클래스가 다루는 지표 이름 목록 (프론트엔드 JSON 키와 똑같이 맞춤)
    FIELDS = ("external_inflow", "interdistrict_movement")

    def __init__(self, external_inflow=None, interdistrict_movement=None):
        self.external_inflow = self._check(external_inflow, "external_inflow")
        self.interdistrict_movement = self._check(
            interdistrict_movement, "interdistrict_movement")

    @staticmethod
    def _check(value, name):
        """None(미제공)이거나 0 이상의 유한한 숫자만 허용한다."""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Real) \
                or not isfinite(value) or value < 0:
            raise ValueError(f"{name}은(는) 0 이상의 숫자이거나 None이어야 합니다.")
        return float(value)

    @classmethod
    def average(cls, indicator_list):
        """여러 날의 지표 객체를 받아 '평균 지표 객체' 하나를 만든다 (기준값용).

        None인 날은 평균 계산에서 빼고, 남은 값이 하나도 없으면 None.
        """
        averages = {}
        for name in cls.FIELDS:
            values = [getattr(item, name) for item in indicator_list
                      if item is not None and getattr(item, name) is not None]
            averages[name] = fmean(values) if values else None
        return cls(**averages)

    def compare_to_baseline(self, baseline):
        """기준값(MigrationIndicators)과 비교한 결과를 지표별 딕셔너리로 돌려준다.

        예: {"external_inflow": {"actual": 120.0, "baseline": 100.0, "change_ratio": 0.2}, ...}
        비교할 수 없으면(값 미제공, 기준값 0) change_ratio는 None.
        """
        comparison = {}
        for name in self.FIELDS:
            actual = getattr(self, name)
            base = getattr(baseline, name) if baseline is not None else None
            ratio = (actual - base) / base if actual is not None and base else None
            comparison[name] = {"actual": actual, "baseline": base, "change_ratio": ratio}
        return comparison

    def to_dict(self):
        return {name: getattr(self, name) for name in self.FIELDS}

    def __repr__(self):
        return (f"MigrationIndicators(external_inflow={self.external_inflow}, "
                f"interdistrict_movement={self.interdistrict_movement})")
