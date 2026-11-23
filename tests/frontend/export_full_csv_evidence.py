"""고정된 전체 원본의 실제 Flask 응답을 JS 검증에 사용할 수 있도록 저장한다."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dashboard_app import create_dashboard_app


def export(output):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Keep generated evidence outside the source repository")
    application = create_dashboard_app(ROOT / "data/population.csv")
    client = application.test_client()
    profile = application.config["DASHBOARD_PROFILE"]
    source = ROOT / "data/population.csv"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    settings = {"moving_average": {"window": 7, "threshold": 0.1},
                "z_score": {"window": 28, "threshold": 3.0},
                "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}}
    queries = [("all_districts", code, "2026-09-01", "2026-09-13")
               for code, _name in profile["districts"]]
    queries += [("annual", "11110", "2025-01-01", "2025-12-31"),
                ("gap", "11110", "2024-02-28", "2024-03-03"),
                ("empty", "11110", "2030-01-01", "2030-01-02"),
                ("full_history", "11110", profile["start_date"], profile["end_date"])]
    cases = []
    for label, code, start, end in queries:
        query = {"district_code": code, "start_date": start, "end_date": end,
                 "selected_method": "seasonal", "methods": settings}
        params = {key: query[key] for key in ("district_code", "start_date", "end_date")}
        params["methods"] = json.dumps(settings)
        response = client.get("/api/analysis", query_string=params)
        if response.status_code != 200:
            raise AssertionError(response.get_data(as_text=True))
        cases.append({"label": label, "query": query, "payload": response.get_json()})
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise AssertionError("Source CSV was modified")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"district_count": len(profile["districts"]), "profile": profile,
                                 "source_sha256": before, "cases": cases},
                                ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "district_count": len(profile["districts"]),
                      "source_unchanged": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
