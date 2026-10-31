"""데이터 로딩·품질 점검·실제 탐지기 연결을 확인하는 명령줄 실행 예제."""

import argparse
import json
from datetime import date
from pathlib import Path

from csv_population_repository import CsvPopulationRepository
from detectors import MovingAverageDetector, ZScoreDetector
from seasonal_analyzer import SeasonalAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(description="서울 생활인구 데이터 조회 및 탐지 연결")
    parser.add_argument("--csv", type=Path, help="원본 CSV 경로. 생략하면 가상 예제 사용")
    parser.add_argument("--encoding", default="auto", help="auto / cp949 / utf-8-sig")
    parser.add_argument("--district", default="11680", help="자치구 코드")
    parser.add_argument("--start", type=date.fromisoformat, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="종료일 YYYY-MM-DD")
    parser.add_argument("--require-indicators", action="store_true", help="유입·이동 지표 누락 시 오류")
    parser.add_argument("--method", choices=("moving_average", "z_score", "seasonal"))
    parser.add_argument("--window", type=int, help="기준 계산 기간. 미지정 시 탐지기 기본값")
    parser.add_argument("--threshold", type=float, help="이동평균·계절성은 비율, Z-score는 점수")
    parser.add_argument("--min-samples", type=int, help="계절성 분석 최소 표본 수")
    parser.add_argument("--output", type=Path, help="조회 기간의 전체 기록·결과를 JSON 파일로 저장")
    args = parser.parse_args()
    if args.method is None and any(value is not None for value in (args.window, args.threshold, args.min_samples)):
        parser.error("탐지 설정을 입력하려면 --method를 선택해 주세요.")
    if args.min_samples is not None and args.method != "seasonal":
        parser.error("--min-samples는 seasonal에서만 사용합니다.")

    try:
        path = args.csv or Path(__file__).parent / "data" / "sample_population.csv"
        if args.output and args.output.resolve() == path.resolve():
            raise ValueError("JSON 출력 경로는 원본 CSV와 달라야 합니다.")
        repository = CsvPopulationRepository(
            path, encoding=args.encoding, require_indicators=args.require_indicators
        )
        repository.load()
        records = repository.get_records(args.district, args.start, args.end)
        quality = repository.get_data_quality()
        payload = {
            "data_quality": quality,
            "query": {
                "district_code": args.district.strip(),
                "start_date": args.start.isoformat() if args.start else None,
                "end_date": args.end.isoformat() if args.end else None,
            },
            "records": [record.to_dict() for record in records],
        }
        if args.method is not None:
            options = {name: value for name, value in (
                ("window", args.window), ("threshold", args.threshold),
                ("min_samples", args.min_samples),
            ) if value is not None}
            detector_class = {
                "moving_average": MovingAverageDetector,
                "z_score": ZScoreDetector,
                "seasonal": SeasonalAnalyzer,
            }[args.method]
            detector = detector_class(**options)
            inputs = repository.get_records(
                args.district, args.start, args.end,
                history_days=detector.window if args.start else 0,
            )
            requested_dates = {record.date for record in records}
            results = [result for result in detector.detect(inputs) if result.date in requested_dates]
            evaluated = sum(result.is_anomaly is not None for result in results)
            anomalies = sum(result.is_anomaly is True for result in results)
            settings = {"window": detector.window, "threshold": detector.threshold}
            if args.method == "seasonal":
                settings["min_samples"] = detector.min_samples
            payload["analysis"] = {
                "method": detector.method,
                "settings": settings,
                "summary": {
                    "evaluated_count": evaluated,
                    "anomaly_count": anomalies,
                    "normal_count": evaluated - anomalies,
                    "insufficient_history_count": len(results) - evaluated,
                    "detection_rate": anomalies / evaluated if evaluated else None,
                },
                "results": [result.to_dict() for result in results],
            }

        print(
            f"로딩: {quality['record_count']}개 기록 / {quality['district_count']}개 자치구 "
            f"/ 서울시 합계 포함: {quality['has_seoul_total']}"
        )
        print(f"데이터 범위: {quality['start_date']} ~ {quality['end_date']}")
        print(f"누락된 지역·날짜: {quality['missing_day_count']}건 (임의로 채우지 않음)")
        print(f"조회한 기록: {len(records)}개")
        print(json.dumps(payload["records"][:5], ensure_ascii=False, allow_nan=False, indent=2))
        if "analysis" in payload:
            print(json.dumps(payload["analysis"]["summary"], ensure_ascii=False, allow_nan=False))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2),
                encoding="utf-8",
            )
            print(f"JSON 저장: {args.output}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"데이터 처리 실패: {error}\n")


if __name__ == "__main__":
    main()
