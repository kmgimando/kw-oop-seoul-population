# 프론트엔드 실행 및 연동 안내

현재 화면은 합성 데이터와 Mock JSON으로 동작한다. 실제 서울 생활인구 분석 결과나 Flask API가 아니다. 프론트엔드 프레임워크와 npm 설치는 필요하지 않다.

## 추가 파일과 역할

| 파일 | 역할 |
| --- | --- |
| templates/index.html | 조회 폼, 통계, 차트, 날짜 상세 및 결과표 |
| static/css/dashboard.css | PC/모바일 레이아웃과 상태별 스타일 |
| static/js/config.js | 방법 기본값, 자치구 25개, Mock/API 모드와 임시 URL |
| static/js/model.js | 입력 검증, 상태/수치/통계, 최신 요청 보호 |
| static/js/adapter.js | API 응답 검증과 화면 모델 변환 |
| static/js/api.js | Mock/HTTP 공급자 선택과 HTTP 오류 처리 |
| static/js/mock-provider.js | 합성 JSON 로딩 및 시연 시나리오 |
| static/js/charts.js | Chart.js 시계열·범위·비교 차트 |
| static/js/dashboard.js | 폼, 조회, 상세 선택, 표 및 화면 상태 연결 |
| static/js/package.json | 테스트용 ES module 선언, 의존성 없음 |
| static/mock/detection-fixtures.json | Python 탐지기로 생성한 합성 결과 |
| static/vendor/chart.umd.min.js | 로컬 Chart.js 4.5.1 |
| static/vendor/Chart.js.LICENSE.md | Chart.js MIT 라이선스 |
| tests/frontend/build_mock.py | 합성 fixture 재생성 도구 |
| tests/frontend/dashboard.test.mjs | 프론트엔드 자동 테스트 19개 |
| docs/frontend.md | 실행 및 임시 연동 계약 안내 |
| docs/frontend-verification.md | 실제 수행한 검증 및 미실행 항목 |

## 로컬 실행

저장소 루트에서 실행한다.

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

브라우저에서 http://127.0.0.1:8765/templates/index.html 을 연다. 종료는 Ctrl+C이다. 파일을 더블클릭하는 file:// 방식은 ES module과 JSON fetch 때문에 지원하지 않는다. 이 서버는 Python 표준 라이브러리의 정적 파일 미리보기이며 Flask 분석 API가 아니다.

Flask 담당자가 templates/index.html을 render_template으로 제공하면 기존 ../static 경로는 루트 또는 단일 단계 라우트에서 작동한다. 중첩 라우트·URL prefix·다른 static 경로를 사용하면 세 자산 경로를 url_for('static', filename=...)로 변경해야 한다. Flask 앱이나 라우트는 이번 작업에 포함하지 않았다.

Chart.js 4.5.1 UMD 파일과 MIT 라이선스는 static/vendor에 포함되어 있다. 화면 실행 중 CDN·외부 글꼴·지도 서비스 연결은 필요 없다. 그래프는 날짜 문자열의 category 축을 사용해 시간대 변환을 피한다.

## 화면과 설정

25개 자치구, 날짜 범위, 세 탐지 방법을 선택할 수 있다. 방법을 바꾸면 이전에 입력한 방법별 설정을 유지한다. 비교에는 각 방법의 마지막 설정값을 사용하며 표에 실제 적용 설정을 표시한다. 조건 변경 후 분석 실행을 눌러야 반영된다.

window는 Mock fixture가 제공하는 7·14·28·56일 프리셋이다. 이동평균·계절성 임계값은 화면에서 백분율로 입력하고 통신 모델에서 비율로 변환한다. 예: 10 → 0.10. Z-score는 3 → 3σ이다. min_samples는 계절성에서만 표시하고 1 이상 window 이하 정수로 검증한다.

탐지율은 이상/(이상+정상)이다. 판정 가능한 날짜가 없으면 0% 대신 —를 표시한다. 판정은 is_anomaly의 true/false/null로 구분한다. zero_baseline과 zero_variance는 상태 이름만으로 판정불가로 바꾸지 않는다. null 수치도 0으로 바꾸지 않는다. 정상 범위가 없는 구간은 차트에서 연결하지 않고 판정불가 배경·점으로 구분한다.

history_size는 전체 연속 이력 수이다. 동일 그룹 표본 수가 아니며 공통 DetectionResult 필드는 바꾸지 않았다. 참고 설명과 이동 지표가 미제공이면 그 사실을 표시한다. 지표의 동반 변화만으로 인과를 단정하지 않는다.

## Mock 데이터

static/mock/detection-fixtures.json은 2024-01-01부터 2024-03-30까지 90일의 합성 데이터이다. 평일·주말 패턴과 변동을 인위적으로 만들고 기존 Python 탐지기와 SeasonalAnalyzer로 계산했다. 자치구별 차이는 시연용 배율이며 현실의 자치구 인구를 나타내지 않는다. 원본 CSV나 기존 analysis_results/anomalies.csv를 사용하거나 수정하지 않는다.

재생성 명령:

```powershell
python tests/frontend/build_mock.py
```

계절성 fixture는 min_samples=1로 가능한 기준값을 보관하고 matching_samples에 동일 그룹 표본 수를 별도로 보관한다. JS Mock provider는 요청한 min_samples에 따라 결과를 판정불가로 마스킹한다. 기준값과 점수는 Python에서 생성하며 threshold 변경 시 정상 범위와 판정만 시연용으로 갱신한다. 기준값 계산 알고리즘·Repository·ReportGenerator·분석 서버를 JS로 재구현하지 않는다.

시연 메뉴에는 혼합 결과, 기준값/표준편차 0, 빈 결과, 오류, 느린 응답이 있다. 전체 범위 밖은 빈 결과, 부분 겹침은 포함된 날짜만 반환한다. 표의 조회 일수는 실제 반환된 결과 수이다. 느린 요청은 2.5초, 일반 요청은 약 0.18초다. AbortController와 요청 세대 번호로 이전 응답과 이전 오류를 무시한다.

## 임시 API 계약

실제 API URL·HTTP 방식·JSON 최상위 구조는 미확정이다. 아래 내용은 프론트엔드 연동 제안이다.

- config.js: 기본 mode는 mock, 임시 apiUrl은 /api/analysis.
- api.js: 실제 HTTP 통신과 오류 해석. 기본 모드에서는 호출하지 않음.
- adapter.js: 임시 응답을 화면 모델로 변환·검증. 서버 응답 구조 확정 시 이 계층에서 매핑.
- mock-provider.js: 시연 데이터만 처리. API 전환 시 화면 코드를 바꿀 필요 없음.

GET /api/analysis 에 district_code, start_date, end_date, methods(JSON 문자열)를 전달하는 제안이다. methods는 세 방법 각각의 window, threshold, 계절성 min_samples를 포함한다. 응답 제안:

```json
{
  "schema_version": 1,
  "methods": [
    {
      "method": "seasonal",
      "settings": {"window": 28, "threshold": 0.1, "min_samples": 4},
      "results": ["실제로는 기존 DetectionResult.to_dict() 객체 목록"],
      "details": {
        "2024-02-01": {
          "explanation": null,
          "indicators": {"external_inflow": null, "interdistrict_movement": null}
        }
      }
    }
  ]
}
```

위 results 문자열은 설명용 자리표시자다. 실제로는 숫자·boolean·null·ISO 날짜를 유지하는 DetectionResult 객체들이 들어가며 세 방법의 block 모두 필요하다. results가 빈 배열인 것도 유효하다. 오류 제안은 {"error":{"message":"설명"}}와 HTTP 오류 코드다. 모든 설명은 textContent로 표시한다.

팀과 확정할 사항: 실제 라우트/HTTP 방식, 세 방법 동시 비교 지원 여부, 데이터/조회 가능 범위 메타데이터, 자치구 코드 체계, 기준 계산용 사전 이력 조회, 적용 설정 반환, 설명·이동 지표의 날짜 연결과 단위, 오류 구조, 배포 경로/CORS. API 모드 전환은 계약 확정 후 config.js와 adapter.js를 조정한다. 실제 서버 통합 검증은 미실행이다.

## 테스트

```powershell
python -m unittest discover -v
node --test tests/frontend/dashboard.test.mjs
```

Python 기존 36개 테스트는 유지한다. Node 표준 test runner로 모델 검증, Mock 시나리오, 응답 변환, null/단위/탐지율, 차트 데이터, HTTP 오류, 오래된 비동기 응답 및 오류 무시를 검증한다. Node는 테스트에만 필요하다.
