"""Development launcher for the existing Flask factory and synthetic sample CSV.

No analysis routes, detectors or report generation are reimplemented here.
Run: python run_sample_dashboard.py --port 8767
"""

import argparse
from pathlib import Path

from app import create_app
from csv_population_repository import CsvPopulationRepository
from migration_indicators import MigrationIndicators


def create_sample_app():
    sample = Path(__file__).resolve().parent / "data" / "sample_population.csv"
    repository = CsvPopulationRepository(sample, indicators_factory=MigrationIndicators)
    repository.load()
    start, end = repository.get_date_range()
    districts = repository.list_districts(include_seoul_total=False)
    profile = {
        "profile_version": 1,
        "default_mode": "api",
        "districts": [[item["district_code"], item["district_name"]] for item in districts],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "source": {"kind": "synthetic_sample", "label": "합성 샘플 CSV",
                   "filename": "data/sample_population.csv"},
    }
    application = create_app(repository)

    @application.context_processor
    def dashboard_context():
        return {"dashboard_profile": profile}

    return application


def main():
    parser = argparse.ArgumentParser(description="합성 샘플 CSV Flask 대시보드 개발 실행")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port는 1~65535여야 합니다.")
    application = create_sample_app()
    print(f"SYNTHETIC SAMPLE API: http://127.0.0.1:{args.port}/", flush=True)
    print(f"MOCK: http://127.0.0.1:{args.port}/?source=mock", flush=True)
    application.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
