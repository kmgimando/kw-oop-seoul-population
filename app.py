"""Flask 서버 (담당: 손호진)

흐름: 요청 검증 → 기록 조회(Repository) → 탐지 3종(detect) → 설명(Explainer) → 응답 구성 → JSON
계약 문서: docs/api-contract-proposal.md (GET /api/analysis)
"""

import json
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request

from anomaly_explainer import AnomalyExplainer
from detectors import MovingAverageDetector, ZScoreDetector
from seasonal_analyzer import SeasonalAnalyzer

# 방법 이름 → 탐지기 클래스 (새 방법이 생기면 여기에 한 줄만 추가: OCP)
DETECTORS = {
    "moving_average": MovingAverageDetector,
    "z_score": ZScoreDetector,
    "seasonal": SeasonalAnalyzer,
}


class ApiError(Exception):
    """사용자에게 돌려줄 오류. 상태 코드와 오류 코드를 함께 가진다."""

    def __init__(self, status, code, message, fields=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields

    def to_dict(self):
        body = {"code": self.code, "message": self.message}
        if self.fields:
            body["fields"] = self.fields
        return {"error": body}


def parse_request(args, known_districts):
    """쿼리 파라미터를 검사해서 (자치구 코드, 시작일, 종료일, 방법별 설정)을 돌려준다."""
    def bad(field, message):
        raise ApiError(400, "INVALID_PARAMETER", message, {field: message})

    for field in ("district_code", "start_date", "end_date", "methods"):
        if not args.get(field):
            bad(field, f"{field} 값이 필요합니다.")

    code = args["district_code"]
    if code not in known_districts:
        bad("district_code", "지원하지 않는 자치구 코드입니다.")

    try:
        start = date.fromisoformat(args["start_date"])
        end = date.fromisoformat(args["end_date"])
    except ValueError:
        bad("start_date", "날짜는 YYYY-MM-DD 형식이어야 합니다.")
    if start > end:
        bad("start_date", "start_date는 end_date보다 늦을 수 없습니다.")

    try:
        settings = json.loads(args["methods"])
    except json.JSONDecodeError:
        bad("methods", "methods는 올바른 JSON이어야 합니다.")
    if not isinstance(settings, dict) or set(settings) != set(DETECTORS):
        bad("methods", "methods에는 moving_average, z_score, seasonal 설정이 모두 있어야 합니다.")

    detectors = {}
    for name, cls in DETECTORS.items():
        try:
            detectors[name] = cls(**settings[name])   # 생성자가 값 검증을 해 줌
        except (TypeError, ValueError) as error:
            bad("methods", f"{name} 설정 오류: {error}")
    return code, start, end, settings, detectors


def build_payload(records, results_by_method, details_by_method, settings, start, end):
    """[임시] 응답 구성. 이건희님의 ReportGenerator.build_payload()가 완성되면 교체한다."""
    blocks = []
    for name in DETECTORS:
        rows = [r.to_dict() for r in results_by_method[name] if start <= r.date <= end]
        blocks.append({"method": name, "settings": settings[name],
                       "results": rows, "details": details_by_method[name]})
    return {"schema_version": 1, "methods": blocks}


def create_app(repository, explainer=None):
    """repository: get_records(code, start, end), list_districts()를 가진 객체 (김민규님 담당)"""
    app = Flask(__name__)
    explainer = explainer or AnomalyExplainer()

    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return jsonify(error.to_dict()), error.status

    @app.errorhandler(404)
    def handle_not_found(_):
        return jsonify(ApiError(404, "NOT_FOUND", "존재하지 않는 경로입니다.").to_dict()), 404

    @app.errorhandler(Exception)
    def handle_unexpected(error):          # 스택 추적은 사용자에게 보내지 않는다
        app.logger.exception(error)
        return jsonify(ApiError(500, "INTERNAL_ERROR", "서버 오류가 발생했습니다.").to_dict()), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/analysis")
    def analysis():
        districts = {code for code, _name in repository.list_districts()}
        code, start, end, settings, detectors = parse_request(request.args, districts)

        # 기준 계산에 필요한 '조회 시작 전' 이력까지 넉넉히 가져온다
        longest = max(max(s["window"] for s in settings.values()),
                      explainer.comparison_window)
        records = repository.get_records(code, start - timedelta(days=longest), end)

        results_by_method, details_by_method = {}, {}
        for name, detector in detectors.items():
            try:
                results = detector.detect(records)        # 다형성: 같은 호출, 다른 판정
            except ValueError as error:                   # 원자료 결함 → 사용자 탓 아님
                raise ApiError(500, "DATA_INTEGRITY_ERROR", f"원자료 오류: {error}")
            results_by_method[name] = results
            details = {}
            for result in results:
                if start <= result.date <= end:
                    info = explainer.explain(result, records)
                    if info is not None:
                        details[result.date.isoformat()] = info
            details_by_method[name] = details

        payload = build_payload(records, results_by_method, details_by_method,
                                settings, start, end)
        return app.response_class(json.dumps(payload, ensure_ascii=False, allow_nan=False),
                                  mimetype="application/json")

    return app
