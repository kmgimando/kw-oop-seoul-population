"""전체 생활인구 CSV와 기존 분석 객체를 조립하는 실행 진입점.

로컬: python dashboard_app.py
Docker/Render: gunicorn 'dashboard_app:create_dashboard_app()'
"""

import argparse
import os
from datetime import timedelta
from pathlib import Path

from app import create_app
from csv_population_repository import CsvPopulationRepository
from migration_indicators import MigrationIndicators


ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = ROOT / "data" / "population.csv"


def create_dashboard_app(csv_path=None):
    """인자 → 환경변수 → 포함된 원본 스냅샷 순서로 CSV 경로를 결정한다."""
    source = Path(csv_path or os.environ.get("POPULATION_CSV_PATH") or DEFAULT_CSV)
    if not source.is_absolute():
        source = ROOT / source
    return create_csv_app(source, source_kind="seoul_population", label="서울 생활인구 CSV")


def create_csv_app(source, *, source_kind, label):
    """출처·지원 범위를 실제로 로딩한 Repository에서 읽는다. 샘플 실행도 재사용한다."""
    repository = CsvPopulationRepository(source, require_indicators=True,
                                         indicators_factory=MigrationIndicators)
    repository.load()
    start, end = repository.get_date_range()
    districts = repository.list_districts(include_seoul_total=False)
    # 기존 main의 dict와 데이터 계층 수정본의 tuple을 모두 지원한다.
    options = [[item["district_code"], item["district_name"]]
               if isinstance(item, dict) else list(item) for item in districts]
    quality = repository.get_data_quality()
    profile = {
        "profile_version": 1, "default_mode": "api", "districts": options,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "default_start_date": max(start, end - timedelta(days=89)).isoformat(),
        "default_end_date": end.isoformat(),
        "source": {"kind": source_kind, "label": label, "filename": Path(source).name},
        "record_count": quality["record_count"],
        "missing_dates": sorted({day for days in quality["missing_dates_by_district"].values()
                                 for day in days}),
    }
    application = create_app(repository)
    application.config["POPULATION_REPOSITORY"] = repository
    application.config["DASHBOARD_PROFILE"] = profile

    @application.context_processor
    def dashboard_context():
        return {"dashboard_profile": profile}

    @application.get("/healthz")
    def health():
        return {"status": "ok", "district_count": len(options),
                "record_count": quality["record_count"]}

    return application


def main():
    parser = argparse.ArgumentParser(description="서울 생활인구 전체 CSV 대시보드 실행")
    parser.add_argument("--csv", help="CSV 경로. 생략 시 POPULATION_CSV_PATH 또는 포함된 원본 사용")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port는 1~65535여야 합니다.")
    try:
        application = create_dashboard_app(args.csv)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"CSV API: http://127.0.0.1:{args.port}/", flush=True)
    application.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
