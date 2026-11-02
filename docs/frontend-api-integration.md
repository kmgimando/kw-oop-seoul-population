# 최신 main 기반 합성 샘플 Flask 대시보드 통합

검증일: 2026-11-01. 작업 브랜치: feature/frontend-api-integration. 시작 커밋: origin/main de266398c739ab606db85ed9aa2e2c2ab56aa61f.

기존 create_app(repository), CsvPopulationRepository, 세 탐지기, AnomalyExplainer, ReportGenerator를 연결해 합성 샘플 CSV의 실제 HTTP 응답을 화면에 표시했다. 종로구·강남구의 2026-01-01~2026-02-09 자료만 API 지원 범위로 표시한다. 샘플 자체가 합성 자료이므로 실제 서울시 분석 결과나 정확도 검증으로 해석하지 않는다.

## 작업 분리와 보존

- 최신 원격 브랜치와 PR #1~#7 병합 상태를 재확인했다. main은 de26639이며 feature/data-layer의 a28e9bc는 미병합이었다.
- 별도 작업 폴더 kw-oop-frontend-api-integration에 새 브랜치를 만들었다. 기존 kw-oop-seoul-population 작업 폴더의 미커밋 변경을 가져오거나 덮어쓰지 않았다.
- 이번 작업은 origin/main 코드만 기준으로 하며 미병합 팀원 변경을 가져오지 않았다. 이전 작업의 격리 후보 서버나 실제 CSV 증거를 이번 성공 근거로 재사용하지 않았다.
- main과 팀원 브랜치를 수정하거나 새 commit·push·PR을 생성하지 않았다.

## 실행 방법

저장소 루트에서 Flask가 있는 Python 환경으로 실행한다. 일반적인 로컬 환경의 설치 예시는 다음과 같다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python run_sample_dashboard.py --port 8767
```

- API 화면: http://127.0.0.1:8767/
- 명시적 API 선택: http://127.0.0.1:8767/?source=api
- 기존 Mock 화면: http://127.0.0.1:8767/?source=mock

종료는 Ctrl+C다. 개발용 localhost 서버이며 운영 배포 설정은 포함하지 않는다. 정적 http.server는 Python 분석 API를 제공하지 않는다. 정적 미리보기에서는 기존 Mock 모드를 유지한다.

run_sample_dashboard.py는 기존 샘플 파일을 읽어 MigrationIndicators를 생성자 주입하고, load()한 Repository를 기존 create_app()에 전달한다. 새 분석 라우트·Repository·탐지기·ReportGenerator를 중복 구현하지 않는다.

지원 지역·기간·합성 출처는 로딩된 Repository에서 읽어 Flask 템플릿의 application/json 블록으로 전달한다. 운영 API 응답 envelope에는 새 필드를 추가하지 않았다. API 프로필이 없거나 잘못되면 지원되지 않는 25개 지역을 표시하는 대신 API 조회를 중단한다. 명시적 Mock 선택에서는 기존 25개 지역과 2024년 Mock 자료를 그대로 사용한다.

## 인터페이스와 계약 비교

| 대상 | 실제 인터페이스와 연결 |
| --- | --- |
| app.py | create_app(repository), GET /api/analysis. 요청 파싱 → 이력 조회 → 세 탐지기 → 설명 → ReportGenerator |
| CsvPopulationRepository | list_districts()는 dict 목록, get_records(code, start, end)는 date 경계 포함. 명시적 indicators_factory 지원 |
| PopulationRecord | date·district_code·district_name·total_population 및 원본 두 이동 지표, 선택적 indicators 객체 |
| MigrationIndicators | external_inflow·interdistrict_movement, to_dict(), compare_to_baseline() |
| AnomalyExplainer | explain(result, records), 같은 평일·주말 그룹의 과거 지표 비교, 인과 단정 없는 설명 |
| ReportGenerator | 여섯 인자로 결과·설명·설정·기간을 받아 build_payload(). 기존 to_dict() 사용, 조회 기간 필터 |
| config.js | 실행 프로필과 URL로 API/Mock 선택. 샘플 API 지원 지역은 Repository 메타데이터만 사용 |
| api.js | 기존 네 query 파라미터 전송, HTTP 오류 해석, Mock과 HTTP 공급자 분리 |
| adapter.js | schema_version=1, methods 세 block, settings·14개 결과 필드·details 검증. 형식이 맞아 변경하지 않음 |

docs/api-contract-proposal.md의 GET 경로, district_code/start_date/end_date/methods, 세 방법 동시 응답, schema_version, settings echo, boolean/null, 설명·이동 지표 구조는 실제 구현과 일치한다. 제안서의 누락 설정 400 조건은 이번 최소 수정으로 맞췄다. DATA_UNAVAILABLE 503 정책과 운영 메타데이터 API 등은 여전히 제안이며 구현 완료로 표시하지 않는다.

## 발견한 원인과 최소 수정

사전에 원인과 최소 변경 방향을 안내한 뒤 app.py 두 위치만 보완했다. 클래스 구조·탐지·설명·결과 계산은 바꾸지 않았다.

1. 자치구 목록: API는 tuple 목록을 가정했지만 실제 main Repository는 dict 목록을 반환했다. 실제 dict의 district_code와 기존 FakeRepository tuple을 모두 읽도록 목록 해석만 수정했다. Repository를 바꾸거나 미병합 수정본을 가져오지 않았다.
2. 누락 설정: 생성자가 기본값을 허용한 후 원래 settings의 window를 참조해 500이 날 수 있었다. 요청에서 각 방법의 window·threshold, 계절성 min_samples가 있는지 먼저 확인하여 400 INVALID_PARAMETER를 반환하도록 했다.

프론트엔드에서는 API 지원 지역·기간·출처를 적용했고, 실제 API의 빈 결과에 Mock 기간 안내가 나오지 않도록 수정했다. HTTP 실패를 Mock 데이터로 자동 대체하지 않는다. LatestRequest의 AbortController와 세대 번호 보호는 유지한다.

## 수정 및 추가 파일

| 파일 | 역할 |
| --- | --- |
| app.py | 자치구 목록 해석과 필수 설정 검증의 최소 보완 |
| run_sample_dashboard.py | 기존 factory와 합성 샘플을 조립하는 개발용 실행 진입점 |
| requirements-dev.txt | 검증한 Flask 3.1.2 개발 의존성 |
| templates/index.html | 서버 프로필 JSON, 동적 지원 범위 표시 위치 |
| static/js/config.js | 프로필 검증, API/Mock 모드와 지원 지역 선택 |
| static/js/model.js | 실제 지원 지역 목록을 통한 입력 검증 |
| static/js/api.js | 모드별 지원 지역 검증, 기존 HTTP 요청·오류 처리 유지 |
| static/js/dashboard.js | 샘플 범위 초기화, 출처 표시, 빈 결과, API 정보 누락 시 중단 |
| tests/test_sample_dashboard_integration.py | 실제 CSV Repository를 사용한 Flask 테스트 클라이언트 11개 |
| tests/frontend/export_sample_api_evidence.py | 합성 샘플의 Python/Flask 결과 증거 생성 도구 |
| tests/frontend/sample-api.test.mjs | 프로필·Adapter·차트·실제 HTTP 검증 9개 |
| docs/frontend.md | 현재 실행 안내로 연결 |
| docs/frontend-api-integration.md | 본 실행·검증·제한 기록 |

데이터 객체·Repository·MigrationIndicators·AnomalyExplainer·ReportGenerator·기본/계절성 탐지기와 기존 테스트는 변경하지 않았다. adapter.js와 charts.js도 기존 구현을 그대로 사용한다.

## 실제 실행한 검증

테스트 환경: Python 3.13.15, Flask 3.1.2, Node 24.22.1. 이번 도구 환경에서는 작업의 work/flask-packages를 PYTHONPATH에 지정해 격리된 의존성을 사용했고, TEMP/TMP도 쓰기 가능한 작업 폴더로 지정했다. 전역 설치는 수행하지 않았다.

```powershell
python -m unittest discover -v
python tests/frontend/export_sample_api_evidence.py --output '저장소 바깥의 절대 경로/sample-api-evidence.json'
$env:SAMPLE_API_EVIDENCE = '위에서 생성한 JSON의 절대 경로'
$env:SAMPLE_API_BASE_URL = 'http://127.0.0.1:8767'
node --test tests/frontend/dashboard.test.mjs tests/frontend/sample-api.test.mjs
```

| 검증 | 실제 결과 |
| --- | --- |
| 기존 Python 36개를 포함한 전체 회귀 | 94개 통과, 실패·expected failure·skip 0 |
| 기존 JavaScript 19개 + 추가 9개 | 28개 통과, 실패·skip 0 |
| 샘플 API 질의 조합 | 16개 조합, 1,512개 결과 행이 직접 Python 탐지와 일치 |
| 실제 HTTP | 위 16개 요청의 전체 JSON이 Flask 테스트 클라이언트 증거와 일치 |
| 직접 입력 검증·HTTP 오류 | 미지원 지역·잘못된 기간·누락 설정·없는 경로 처리 확인 |
| 기준값 0·표준편차 0 | 별도의 합성 zero CSV를 실제 Repository·Flask로 처리. score=null, 정상/이상 유지 |
| 시작 이전 이력 | 1월 29일~2월 9일의 12개 결과가 전체 이력 계산과 일치, 계산용 과거 날짜는 응답에서 제외 |
| 실제 Chromium | 두 자치구 × 세 방법 × 40일 = 240행 수치·상태 및 요약 통계 대조 |
| 차트 | 실제 Chart.js 렌더링, 기준값·상하한·이상점·판정불가 구간과 툴팁/상세 연결 확인 |
| 설정 전달 | UI에서 계절성 window=7, threshold=20%(0.2), min_samples=6을 적용해 판정불가 40일·탐지율 — 확인 |
| API 빈 결과·입력 오류 | 샘플 범위 안내와 역전 기간 오류 확인 |
| 연속 요청 | 실제 HTTP와 UI에서 최신 강남구 결과 유지. 기존 테스트에서 중단 무시 transport도 검증 |
| Mock 회귀 | Mock 지역 25개·기본 46일·빈 결과·오류 시나리오 확인 |

API 모드의 사용자 오류 응답은 실제 HTTP 자동 테스트로 확인했고, 브라우저에서는 정상 조회·빈 결과·클라이언트 입력 오류를 확인했다. 브라우저 네트워크 단절 시뮬레이션은 별도로 수행하지 않았다. 차트 입력 수치 전체는 자동 테스트로 비교했으며 모든 픽셀을 자동 비교한 것은 아니다.

두 자치구의 기본 설정 결과는 각각 다음과 같다. 같은 건수가 나오는 것은 합성 자료의 설계 때문이며 현실의 지역별 탐지 특성이 아니다.

| 방법 | 전체 | 이상 | 정상 | 판정불가 | 탐지율 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 이동평균 7일·10% | 40 | 10 | 23 | 7 | 30.3% |
| Z-score 28일·3 | 40 | 0 | 12 | 28 | 0.0% |
| 계절성 28일·10%·최소 4 | 40 | 1 | 11 | 28 | 8.3% |

탐지율은 이상/(이상+정상)이며 분모가 0이면 null/—다. 예를 들어 종로구 2026-01-31의 계절성 결과는 실제값 333,200명, 기준값 240,375명, 범위 216,337.5~264,412.5명, 변동률 약 38.6%로 표시된다. 이동 지표는 23,000명·46,000명이며 설명은 인과관계를 단정하지 않는다.

## 남은 사항과 팀원 확인

- 손호진: app.py 두 최소 변경의 계약 검토. 현재 dict 목록과 기존 tuple 테스트 호환, 누락 설정의 400 정책을 확인하면 된다. 운영 오류/503, 최솟값 날짜 등 샘플 범위 밖 경계 정책은 추가 검토가 필요하다.
- 김민규: list_districts 반환 계약의 향후 변경 시 API와 실행 프로필 조립도 함께 확인한다. 이번에는 미병합 브랜치를 가져오지 않았고 원본 데이터 계층은 유지했다.
- 이건희: 현재 ReportGenerator JSON과 기간·null 처리는 검증 통과했다. 지표 비교 상세를 새 필드로 추가할 때만 프론트 계약 확장이 필요하다.
- 실제 원본 CSV: 이번 브랜치에서는 로딩·분석·HTTP·화면 검증을 수행하지 않았다. 합의한 파일 해시·기간·25개 지역·지표 정의로 별도 프로필과 통합 검증을 진행해야 한다. 샘플 성공을 실제 원자료 성공으로 표시하지 않는다.
- 운영 배포·다중 브라우저·이번 변경의 모바일 전용 재검증은 미실행이다.

증거 JSON과 화면 캡처는 저장소 밖 outputs에 보관하며 소스나 원본 CSV를 덮어쓰지 않는다. 검증용 서버는 종료했고 commit·push·PR은 만들지 않았다.
