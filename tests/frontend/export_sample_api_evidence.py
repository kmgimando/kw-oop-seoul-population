"""Export synthetic Flask test-client responses for JS/live browser comparison."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from run_sample_dashboard import create_sample_app
from tests.test_sample_dashboard_integration import (
    SAMPLE, SETTINGS, api_response, direct_results, query, sample_repository, summarize,
)


def export(output):
    if output.resolve().is_relative_to(ROOT):
        raise ValueError("Keep generated evidence outside the source repository")
    before = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    repository = sample_repository()
    client = create_sample_app().test_client()
    cases = []
    for code in ("11110", "11680"):
        requests = [("default_full", query(code)), ("history", query(code, "2026-01-29")),
                    ("empty", query(code, "2027-01-01", "2027-01-10"))]
        for window in (7, 14, 56):
            settings = copy.deepcopy(SETTINGS)
            for value in settings.values():
                value["window"] = window
            requests.append((f"window_{window}", query(code, settings=settings)))
        settings = copy.deepcopy(SETTINGS)
        settings["seasonal"] = {"window": 7, "threshold": 0.2, "min_samples": 6}
        requests.append(("min_samples", query(code, settings=settings)))
        settings = copy.deepcopy(SETTINGS)
        settings["moving_average"]["threshold"] = 0.5
        settings["z_score"]["threshold"] = 6
        settings["seasonal"]["threshold"] = 0.5
        requests.append(("thresholds", query(code, settings=settings)))
        for label, q in requests:
            response = api_response(client, q)
            if response.status_code != 200:
                raise AssertionError((q, response.status_code, response.get_json()))
            payload = response.get_json()
            expected = direct_results(repository, q)
            for block in payload["methods"]:
                assert block["results"] == expected[block["method"]]
            cases.append({"label": label, "query": q, "payload": payload,
                          "stats": {name: summarize(rows) for name, rows in expected.items()}})
    assert before == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
    evidence = {"source_kind": "synthetic_sample", "sample_sha256": before,
                "source_unchanged": True, "cases": cases}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"cases": len(cases), "result_rows": sum(len(b["results"]) for c in cases for b in c["payload"]["methods"]),
                      "default_stats": {c["query"]["district_code"]: c["stats"] for c in cases if c["label"] == "default_full"},
                      "source_unchanged": True}, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
