from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import isfinite
from numbers import Real
from statistics import fmean, pstdev


@dataclass(frozen=True)
class DetectionResult:
    date: date
    district_code: str
    district_name: str
    method: str
    actual: float
    expected: float | None
    lower_bound: float | None
    upper_bound: float | None
    score: float | None
    threshold: float
    deviation_ratio: float | None
    is_anomaly: bool | None
    status: str
    history_size: int

    def to_dict(self):
        result = asdict(self)
        result["date"] = self.date.isoformat()
        return result


class BaseDetector(ABC):
    def __init__(self, window, threshold):
        if type(window) is not int or window < 1:
            raise ValueError("window는 1 이상의 정수여야 합니다.")
        if (isinstance(threshold, bool) or not isinstance(threshold, Real)
                or not isfinite(threshold) or threshold <= 0):
            raise ValueError("threshold는 유한한 양수여야 합니다.")
        self.window = window
        self.threshold = float(threshold)

    def detect(self, records):
        groups = defaultdict(list)
        for record in records:
            self._validate(record)
            group = groups[record.district_code]
            if group and group[0].district_name != record.district_name:
                raise ValueError("같은 지역 코드의 이름이 다릅니다.")
            group.append(record)

        results = []
        for code in sorted(groups):
            history = deque(maxlen=self.window)
            previous = None
            for record in sorted(groups[code], key=lambda r: r.date):
                if record.date == previous:
                    raise ValueError("중복된 지역·날짜입니다.")
                # 날짜가 끊기면 연속 이력을 다시 쌓는다.
                if previous is not None and (record.date - previous).days != 1:
                    history.clear()
                if len(history) < self.window:
                    result = self._result(record, len(history))
                else:
                    result = self._evaluate(record, tuple(history))
                results.append(result)
                # 당일 값은 판정이 끝난 뒤 추가한다.
                history.append(float(record.total_population))
                previous = record.date
        return results

    @staticmethod
    def _validate(record):
        if not isinstance(record.date, date) or isinstance(record.date, datetime):
            raise ValueError("date는 datetime.date여야 합니다.")
        for value in (record.district_code, record.district_name):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("지역 코드와 이름은 비어 있지 않은 문자열이어야 합니다.")
        value = record.total_population
        if (isinstance(value, bool) or not isinstance(value, Real)
                or not isfinite(value) or value < 0):
            raise ValueError("인구는 유한한 0 이상의 수여야 합니다.")

    def _result(self, record, history_size, expected=None, scale=None,
                status="insufficient_history"):
        actual = float(record.total_population)
        score = (actual - expected) / scale if scale else None
        lower = upper = anomaly = None
        if expected is not None:
            margin = self.threshold * scale
            lower = max(0.0, expected - margin)
            upper = expected + margin
            anomaly = abs(score) > self.threshold if scale else actual != expected
        return DetectionResult(
            date=record.date,
            district_code=record.district_code,
            district_name=record.district_name,
            method=self.method,
            actual=actual,
            expected=expected,
            lower_bound=lower,
            upper_bound=upper,
            score=score,
            threshold=self.threshold,
            deviation_ratio=(actual - expected) / expected if expected else None,
            is_anomaly=anomaly,
            status=status,
            history_size=history_size,
        )

    @abstractmethod
    def _evaluate(self, record, history):
        pass


class MovingAverageDetector(BaseDetector):
    """직전 window일 평균 대비 변동률로 판정한다."""

    method = "moving_average"

    def __init__(self, window=7, threshold=0.10):
        super().__init__(window, threshold)

    def _evaluate(self, record, history):
        mean = fmean(history)
        return self._result(record, len(history), mean, mean,
                            "evaluated" if mean else "zero_baseline")


class ZScoreDetector(BaseDetector):
    """직전 window일 평균과 모표준편차로 판정한다."""

    method = "z_score"

    def __init__(self, window=28, threshold=3.0):
        super().__init__(window, threshold)
        if window < 2:
            raise ValueError("Z-score의 window는 2 이상이어야 합니다.")

    def _evaluate(self, record, history):
        mean, std = fmean(history), pstdev(history)
        return self._result(record, len(history), mean, std,
                            "evaluated" if std else "zero_variance")
