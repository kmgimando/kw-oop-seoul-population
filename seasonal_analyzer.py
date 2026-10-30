"""Weekday/weekend detection compatible with the existing numeric history.

BaseDetector supplies oldest-first values for consecutive days immediately
before record.date, clearing history after gaps. Date reconstruction relies on
that contract. detect() is inherited, so a full window is required first.

DetectionResult.history_size always counts ALL retained days, including when
the matching group has too few samples. calculate_baseline() separately returns
the number of matching samples; no fields are added to DetectionResult.
Defaults are provisional, not calibrated against the original population CSV.
"""

from collections.abc import Sequence
from datetime import timedelta
from statistics import fmean
from typing import Any

from detectors import BaseDetector, DetectionResult


class SeasonalAnalyzer(BaseDetector):
    """Compare a day with prior weekdays or weekends; holidays are not special.

    Records use the same duck-typed attributes required by BaseDetector:
    date, district_code, district_name, and total_population.
    """

    method = "seasonal"

    def __init__(
        self, window: int = 28, threshold: float = 0.10, min_samples: int = 4
    ) -> None:
        super().__init__(window, threshold)
        if type(min_samples) is not int or not 1 <= min_samples <= window:
            raise ValueError("min_samples는 1 이상 window 이하의 정수여야 합니다.")
        self.min_samples = min_samples

    def calculate_baseline(
        self, record: Any, history: Sequence[float]
    ) -> tuple[float | None, int]:
        """Return (mean or None if insufficient, matching sample count).

        history follows BaseDetector's consecutive, oldest-first, past-only
        contract. At index i its date is record.date - (len(history) - i) days.
        This helper does not store state or inspect the current population.
        """
        is_weekend = record.date.weekday() >= 5
        samples = [
            value
            for i, value in enumerate(history)
            if ((record.date - timedelta(days=len(history) - i)).weekday() >= 5)
            == is_weekend
        ]
        count = len(samples)
        return (fmean(samples) if count >= self.min_samples else None, count)

    def _evaluate(self, record: Any, history: Sequence[float]) -> DetectionResult:
        baseline, _sample_count = self.calculate_baseline(record, history)
        if baseline is None:
            return self._result(record, len(history))
        # Reuse moving-average score, strict threshold, bounds and zero policy.
        return self._result(
            record, len(history), baseline, baseline,
            "evaluated" if baseline else "zero_baseline",
        )
