import argparse
import csv
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from detectors import DetectionResult, MovingAverageDetector, ZScoreDetector


ROOT = Path(__file__).resolve().parent


def load_records(path, encoding="cp949"):
    records = []
    with path.open(encoding=encoding, newline="") as source:
        for row in csv.DictReader(source):
            records.append(SimpleNamespace(
                date=datetime.strptime(row["기준일ID"], "%Y%m%d").date(),
                district_code=row["시구코드"].strip(),
                district_name=row["시구명"].strip(),
                total_population=float(row["총생활인구수"]),
            ))
    if not records:
        raise ValueError("CSV에 데이터가 없습니다.")
    return records


def main():
    parser = argparse.ArgumentParser(description="이동평균과 Z-score 탐지 비교")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--encoding", default="cp949")
    parser.add_argument("--output", type=Path, default=ROOT / "analysis_results")
    parser.add_argument("--ma-window", type=int, default=7)
    parser.add_argument("--ma-threshold", type=float, default=0.10)
    parser.add_argument("--z-window", type=int, default=28)
    parser.add_argument("--z-threshold", type=float, default=3.0)
    args = parser.parse_args()
    if args.csv is None:
        candidates = list(ROOT.glob("*.csv"))
        if len(candidates) != 1:
            parser.error("--csv로 원본 CSV 경로를 지정하세요.")
        args.csv = candidates[0]

    try:
        detectors = [MovingAverageDetector(args.ma_window, args.ma_threshold),
                     ZScoreDetector(args.z_window, args.z_threshold)]
        records = load_records(args.csv, args.encoding)
        results = [r for detector in detectors for r in detector.detect(records)]
        anomalies = sorted((r for r in results if r.is_anomaly),
                           key=lambda r: (r.date, r.district_code, r.method))
        args.output.mkdir(parents=True, exist_ok=True)
        path = args.output / "anomalies.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=DetectionResult.__dataclass_fields__,
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(r.to_dict() for r in anomalies)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"분석 실패: {error}\n")

    for detector in detectors:
        evaluated = [r for r in results if r.method == detector.method
                     and r.district_code != "11000" and r.is_anomaly is not None]
        count = sum(r.is_anomaly for r in evaluated)
        rate = count / len(evaluated) if evaluated else 0
        print(f"{detector.method}: {len(evaluated):,}건 중 {count:,}건 이상 ({rate:.2%})")
    print(f"결과: {path}")


if __name__ == "__main__":
    main()
