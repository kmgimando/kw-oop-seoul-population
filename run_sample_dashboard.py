"""Development launcher for the existing Flask factory and synthetic sample CSV.

No analysis routes, detectors or report generation are reimplemented here.
Run: python run_sample_dashboard.py --port 8767
"""

import argparse
from pathlib import Path

from dashboard_app import create_csv_app


def create_sample_app():
    sample = Path(__file__).resolve().parent / "data" / "sample_population.csv"
    return create_csv_app(sample, source_kind="synthetic_sample", label="합성 샘플 CSV")


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
