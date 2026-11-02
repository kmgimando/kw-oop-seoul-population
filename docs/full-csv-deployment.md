# 전체 CSV 연결·실행·배포 안내

2026-11-02. 기준 main은 `223d6ef`이며, 미반영 데이터 수정 `a28e9bc`의 변경 내용도 포함한다.
작업 브랜치는 기존 `feature/data-layer`다. 최초에는 별도 worktree에서 검증했고,
이후 사용자 요청에 따라 검증한 수정본을 원래 `kw-oop-seoul-population` 폴더에 반영했다.
최신 main의 팀원 이력은 로컬 브랜치에 반영했으며, 아직 커밋하기 전의 통합 상태다.
commit·push·GitHub merge·Render 배포는 수행하지 않았다.

## 내 컴퓨터에서 화면 실행

이 수정본의 프로젝트 폴더를 VS Code에서 열고 터미널에서 실행한다.

```powershell
python -m pip install -r requirements-dev.txt
python dashboard_app.py
```

브라우저에서 http://127.0.0.1:8767/ 을 연다. 종료는 Ctrl+C다.

- 전체 실제 자료: `python dashboard_app.py`
- 기존 합성 샘플: `python run_sample_dashboard.py`
- 기존 Mock 화면: 서버 실행 후 `/?source=mock`
- 서버 상태 확인: `/healthz`에서 자치구 25개·기록 35,126건 확인

실제 자료 화면은 처음에 최근 90일을 보여 준다. 기간을 바꾸면 원본 전체 범위에서 조회할 수 있다.
파일 경로는 다음처럼 직접 지정하거나 환경변수 `POPULATION_CSV_PATH`로 설정할 수 있다.
상대 경로는 프로젝트 루트 기준이며, 경로를 생략하면 포함된 `data/population.csv`를 사용한다.

```powershell
python dashboard_app.py --csv "D:\자료\생활인구.csv"
```

## 포함한 원본과 한계

출처는 서울 열린데이터광장의 자치구별 서울 생활인구(250m) 일별집계표다.
원본을 바꾸지 않고 `data/population.csv`에 복사했다.

- 원본 크기: 6,497,750바이트, CP949
- 기록 수: 35,126건, 서울시 합계를 포함한 26개 지역
- 화면과 분석 대상: 합계 코드 11000을 제외한 25개 자치구
- 기간: 2023-01-01~2026-09-13
- 서울 외 유입인구·자치구 간 이동인구: 두 열 모두 제공, 이 스냅샷에 누락값 없음
- 누락 날짜: 2024-02-29, 전체 지역에 기록이 없으며 0이나 추정값으로 채우지 않음
- SHA-256: `1e8622bc35db7303ee7864a90428909a18fa5cb0d14fe49097b43e78e2d9fd2a`

`.gitattributes`로 이 CSV의 줄바꿈 변환을 막아 Windows와 Linux에서 동일한 바이트를 유지한다.
Git/Docker 제외 규칙은 합의한 이 원본과 합성 샘플만 포함하도록 수정했다.
이 자료는 고정된 스냅샷이며 매일 자동 갱신되지 않는다. 교체할 때는 manifest와 검증 결과도 갱신한다.
탐지율은 정확도가 아니며, 평일·주말만 구분하고 공휴일은 별도 처리하지 않는다.
유입·이동 지표가 함께 변해도 원인이라고 단정하지 않는다.

## 연결 구조와 수정 범위

1. `dashboard_app.py`가 CSV 경로를 정하고 기존 `CsvPopulationRepository`를 로딩한다.
2. 저장소가 `PopulationRecord`와 `MigrationIndicators`를 생성·검증한다.
3. 기존 `create_app(repository)`에 저장소를 전달한다.
4. 실제 지원 지역·기간·출처를 화면에 전달한다.
5. 기존 `/api/analysis`가 세 탐지기, 설명기, `ReportGenerator`를 호출한다.
6. 기존 JSON 응답을 adapter와 차트로 전달한다.

API 요청·응답 형식, 탐지 공식, 임계값, 설명 규칙, 결과 생성기와 클래스 구조는 유지한다.
원본 파일이 없거나 잘못되면 시작을 중단하며, 합성 자료로 자동 대체하지 않는다.

이전 결합본에서는 자치구 목록을 튜플로 반환하는 새 코드와 딕셔너리로 읽는 샘플 실행부가 맞지 않아
파일 충돌 없이도 서버 시작이 실패했다. 공통 조립 함수가 두 형식을 읽도록 수정하고 샘플 실행에서도 재사용한다.
추가 검토에서는 API 날짜를 YYYY-MM-DD로 엄격히 확인하고, 시작일 이전 이력 계산이 날짜 최솟값을 넘지 않게 했다.
화면 프로필도 실제 달력 날짜와 누락 날짜 목록의 형식을 확인한다.

## 팀원 확인 사항

- 권민우: 탐지 코드 변경 없음. 실제 2025년 종로구 결과가 유지되는지 확인.
- 서윤도: 출처·기본 기간·누락 날짜 표시 변경과 기존 샘플/Mock 유지 확인. 레이아웃·차트 계산·API 요청은 유지.
- 손호진: `app.py`의 날짜 형식 검증과 이력 시작일 계산 보완 확인. API 계약은 유지.
- 이건희: 결과 생성 코드 변경 없음. Docker 실행 대상과 새 원본의 포함 여부 확인. 실제 자료로 시연하면 캡처·출처 설명을 맞춤.

별도의 새 기능 구현을 팀원에게 요구하는 변경은 아니다. 같은 파일을 추가 수정 중이라면 이번 변경과 비교해 반영한다.

## Docker와 Render의 역할

Docker는 Python·라이브러리·코드·CSV를 같은 실행 환경인 이미지로 묶는다.
그 이미지를 실행한 것이 컨테이너다. Render는 컨테이너를 실행할 서버와 공개 접속 주소를 제공한다.

흐름은 GitHub의 코드·CSV → Render의 Docker 이미지 생성 → Gunicorn·Flask 실행 → 공개 주소 → 브라우저다.
화면 파일도 Flask가 제공하므로 프론트엔드 서버를 따로 배포할 필요는 없다.
Render가 저장소의 Dockerfile로 직접 이미지를 만들 수 있어 이 구성에서는 Docker Hub가 필수는 아니다.

Dockerfile은 Python 3.12에 Flask 3.1.2와 Gunicorn 23.0.0을 설치한다.
Gunicorn은 배포용 요청 처리 서버이고 `dashboard_app:create_dashboard_app()`을 실행한다.
CSV를 먼저 로딩한 뒤 worker를 시작하며, Render가 제공하는 PORT를 사용해 0.0.0.0에 바인딩한다.

Docker Desktop이 설치되고 실행 중인 컴퓨터에서 확인하는 명령이다.

```powershell
docker build -t seoul-population .
docker run --rm -p 8767:8767 seoul-population
```

http://localhost:8767/ 과 http://localhost:8767/healthz 를 확인한다.

## 나중에 Render에 배포할 때

1. 기존 `feature/data-layer`에서 변경 내용을 검토하고 commit·push하면 PR #10에 추가된다.
   새 브랜치나 새 PR을 만들 필요는 없다. 로컬의 통합 대기 상태도 해당 커밋으로 마무리된다.
2. Render에서 New → Web Service → GitHub 저장소를 선택한다.
3. 배포할 Branch를 지정한다. 팀에서 승인한 뒤 main을 사용하거나, 합치기 전 시험할 때는 이 변경이 올라간 브랜치를 선택한다.
4. Language는 Docker, Dockerfile Path는 `./Dockerfile`로 설정한다.
5. Docker Command는 비워 Dockerfile의 CMD를 사용한다. 샘플 실행 명령을 따로 넣지 않는다.
6. `POPULATION_CSV_PATH=/app/data/population.csv`, `WEB_CONCURRENCY=2`를 설정한다.
7. Health Check Path는 `/healthz`로 설정한다. 검토 중에는 자동 배포를 끈다.
8. 배포 후 상태·25개 구·자료 기간·알려진 탐지 사례를 실제 주소에서 확인한다.

같은 설정을 `render.yaml`에 준비했다. main 브랜치, 무료 web service 계획, 수동 배포 설정이며,
파일이 있다는 것만으로 서비스가 생성되거나 배포되지는 않는다.
공식 안내: [Docker](https://render.com/docs/docker), [Web Service](https://render.com/docs/web-services),
[환경변수](https://render.com/docs/configure-environment-variables), [Blueprint](https://render.com/docs/blueprint-spec).

## 검증을 재현하는 방법

Python 3.12·Flask 3.1.2에서 Python 테스트 113개 모두 통과했다. 실제 원본 요청 29개 조합과
합성 샘플 요청 16개 조합의 응답을 생성해, Node 테스트 33개가 통과했고 실제 HTTP 테스트 4개는 미완료다.
종로구 2025년의 이동평균 120일·계절성 46일·Z-score 1일과 토요일 유입 +19.8% 설명을 유지한다.

```powershell
python -m unittest discover -v
python tests/frontend/export_sample_api_evidence.py --output "$env:TEMP\seoul-sample-evidence.json"
python tests/frontend/export_full_csv_evidence.py --output "$env:TEMP\seoul-full-evidence.json"
$env:SAMPLE_API_EVIDENCE = "$env:TEMP\seoul-sample-evidence.json"
$env:FULL_CSV_EVIDENCE = "$env:TEMP\seoul-full-evidence.json"
node --test tests/frontend/dashboard.test.mjs tests/frontend/sample-api.test.mjs tests/frontend/full-csv.test.mjs
```

증거 JSON은 저장소 바깥 경로에 저장한다. 위 명령의 Node 테스트는 네트워크가 필요 없는 응답·차트 데이터 검증이다.
실제 서버 통신 테스트는 각각 샘플 서버와 전체 CSV 서버를 켠 뒤 SAMPLE_API_BASE_URL과 FULL_CSV_BASE_URL도 설정한다.
두 서버를 함께 실행하려면 별도 터미널에서 `python run_sample_dashboard.py --port 8768`과
`python dashboard_app.py --port 8767`을 실행하고, 테스트 터미널에 다음 주소를 지정한다.

```powershell
$env:SAMPLE_API_BASE_URL = "http://127.0.0.1:8768"
$env:FULL_CSV_BASE_URL = "http://127.0.0.1:8767"
node --test tests/frontend/dashboard.test.mjs tests/frontend/sample-api.test.mjs tests/frontend/full-csv.test.mjs
```

이번 도구 환경은 로컬 주소로의 HTTP 접속을 차단해 실제 HTTP 테스트 4개를 완료하지 못했다.
Docker 실행 파일도 없어 이미지 빌드·컨테이너 실행은 미검증이다. 실제 브라우저와 Render 배포도 남아 있다.
발표자는 발표에 쓸 컴퓨터에서 실행·조회·화면을 확인한 뒤 시연 버전을 정한다.
