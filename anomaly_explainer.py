"""이상 날짜의 참고 설명 생성기 (담당: 손호진)

이상(is_anomaly=True)으로 판정된 날에 대해, 같은 날의 유입·이동 지표가
평소(직전 comparison_window일 평균)보다 얼마나 변했는지 비교해서 문장을 만든다.
⚠️ 원칙: "지표가 같이 변했다" ≠ "그래서 인구가 변했다". 원인을 단정하는 표현은 쓰지 않는다.
"""

from datetime import timedelta

from migration_indicators import MigrationIndicators


class AnomalyExplainer:
    LABELS = {
        "external_inflow": "서울 외 유입인구",
        "interdistrict_movement": "자치구 간 이동인구",
    }
    DISCLAIMER = "지표가 함께 변했다는 사실만으로 생활인구 변동의 원인을 단정할 수 없습니다."

    def __init__(self, comparison_window=28, change_threshold=0.10):
        if type(comparison_window) is not int or comparison_window < 1:
            raise ValueError("comparison_window는 1 이상의 정수여야 합니다.")
        if not 0 < change_threshold:
            raise ValueError("change_threshold는 양수여야 합니다.")
        self.comparison_window = comparison_window
        # 설명 규칙: 지표 변화율이 이 값보다 크면 '눈에 띄게 변함'으로 본다
        self.explanation_rules = {"change_threshold": change_threshold}

    def explain(self, result, records):
        """탐지 결과 1개 + 생활인구 기록 목록 → details에 넣을 딕셔너리 (또는 None)

        반환 예: {"explanation": "...", "indicators": {...}, "comparison": {...}}
        """
        if result.is_anomaly is not True:          # 정상·판정불가 날짜는 설명 안 함
            return None

        same_district = {r.date: r for r in records
                         if r.district_code == result.district_code}
        today = same_district.get(result.date)
        today_ind = getattr(today, "indicators", None) if today else None
        if today_ind is None:
            return {"explanation": "이 날짜의 유입·이동 지표가 제공되지 않아 비교할 수 없습니다. "
                                   + self.DISCLAIMER,
                    "indicators": {name: None for name in MigrationIndicators.FIELDS}}

        # 직전 comparison_window일의 지표 평균 = 기준값 (당일은 제외)
        past = [same_district[result.date - timedelta(days=k)].indicators
                for k in range(1, self.comparison_window + 1)
                if (result.date - timedelta(days=k)) in same_district]
        baseline = MigrationIndicators.average(past)
        comparison = today_ind.compare_to_baseline(baseline)

        direction = "증가" if result.actual > (result.expected or 0) else "감소"
        sentences = [f"생활인구가 기준값보다 {direction}했습니다."]
        for name, info in comparison.items():
            sentences.append(self._describe(self.LABELS[name], info["change_ratio"]))
        sentences.append(self.DISCLAIMER)
        return {"explanation": " ".join(sentences),
                "indicators": today_ind.to_dict(),
                "comparison": comparison}

    def _describe(self, label, ratio):
        limit = self.explanation_rules["change_threshold"]
        if ratio is None:
            return f"{label}는 비교할 기준값이 없습니다."
        percent = f"{abs(ratio) * 100:.1f}%"
        if ratio > limit:
            return f"같은 날 {label}도 평소보다 {percent} 많았습니다."
        if ratio < -limit:
            return f"같은 날 {label}는 평소보다 {percent} 적었습니다."
        return f"{label}는 평소와 큰 차이가 없었습니다({percent} 이내)."
