"""CSV → 객체 생성 → 자치구·기간 조회를 확인하는 실행 예제."""

import argparse
import json
from datetime import date
from pathlib import Path

from csv_population_repository import CsvPopulationRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="생활인구 데이터 계층 초기 실행 예제")
    parser.add_argument("--csv", type=Path, help="실제 생활인구 CSV 경로")
    parser.add_argument("--encoding", help="실제 CSV 기본값: cp949")
    parser.add_argument("--district", default="11680", help="자치구 코드")
    parser.add_argument("--start", type=date.fromisoformat, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="종료일 YYYY-MM-DD")
    args = parser.parse_args()

    csv_path = args.csv or Path(__file__).parent / "data" / "sample_population.csv"
    encoding = args.encoding or ("cp949" if args.csv else "utf-8-sig")
    repository = CsvPopulationRepository(csv_path, encoding=encoding)
    count = repository.load()
    records = repository.get_records(args.district, args.start, args.end)

    print(f"로딩한 기록: {count}개 / 지역: {len(repository.list_districts())}개")
    print(f"조회한 기록: {len(records)}개")
    print(json.dumps([record.to_dict() for record in records[:5]], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
