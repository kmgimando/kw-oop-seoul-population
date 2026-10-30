"""Build synthetic browser fixtures with existing Python detectors, not a server.

Run from the repository root: python tests/frontend/build_mock.py
This only writes static/mock/detection-fixtures.json, never original data/code.
"""

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import pstdev
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from detectors import MovingAverageDetector, ZScoreDetector
from seasonal_analyzer import SeasonalAnalyzer


def build_fixture():
    payload = {"description": "SYNTHETIC ONLY. Not real Seoul population or migration data.",
               "start_date": "2024-01-01", "end_date": "2024-03-30", "datasets": {}}
    for scenario in ("mixed", "zero"):
        records = []
        for i in range(90):
            day = date(2024, 1, 1) + timedelta(days=i)
            value = round((260000 if day.weekday() < 5 else 205000) + 6000 * math.sin(i / 3))
            if i in (30, 41, 62, 76):
                value = round(value * (1.42 if i in (30, 62) else 0.62))
            if scenario == "zero":
                value = 0 if i < 65 else 120000
            records.append(SimpleNamespace(date=day, district_code="11110", district_name="종로구", total_population=value))
        blocks = {}
        for cls in (MovingAverageDetector, ZScoreDetector, SeasonalAnalyzer):
            blocks[cls.method] = {}
            for window in (7, 14, 28, 56):
                detector = cls(window=window, **({"min_samples": 1} if cls is SeasonalAnalyzer else {}))
                results = detector.detect(records)
                scales, samples = [], []
                for i, result in enumerate(results):
                    history = tuple(float(r.total_population) for r in records[max(0, i - window):i])
                    scales.append(None if result.expected is None else pstdev(history) if cls is ZScoreDetector else result.expected)
                    samples.append(detector.calculate_baseline(records[i], history)[1] if cls is SeasonalAnalyzer else None)
                blocks[cls.method][window] = {"results": [r.to_dict() for r in results], "scales": scales, "matching_samples": samples}
        payload["datasets"][scenario] = blocks
    return payload


if __name__ == "__main__":
    target = ROOT / "static" / "mock" / "detection-fixtures.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_fixture(), ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    print(f"Synthetic fixture written: {target.name} ({target.stat().st_size:,} bytes)")
