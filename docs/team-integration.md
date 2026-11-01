# 데이터 객체와 팀 API 연동 기록

검증일은 2026년 11월 1일이다. 현재 데이터 코드와 손호진 담당 API 브랜치의 `4061c70`을
별도 로컬 폴더에 함께 구성해 검증했다. 실제 Git 병합이나 원격 push는 수행하지 않았다.

## 맞춘 인터페이스

- 탐지 입력은 date(datetime.date), district_code, district_name, total_population이다.
- get_records(code, start, end)는 시작일과 종료일을 포함하는 기록 목록을 반환한다.
- list_districts()는 서울시 합계를 제외한 (코드, 이름) 튜플 목록을 반환한다.
- 서울시 합계를 조회 목록에 넣으려면 include_seoul_total=True를 지정한다.
- API 모듈이 함께 있으면 CSV의 서울외유입인구수·자치구간이동인구수로 실제 MigrationIndicators를 생성한다.
- PopulationRecord 생성 시 indicators 객체만 제공하는 팀원 예제도 지원한다.

서버는 현재처럼 생성해 둔 Repository를 create_app(repository)에 전달하면 된다.
Repository는 먼저 load()를 호출한 상태여야 한다.

## CSV 스냅샷 확인

현재 원본은 2023-01-01~2026-09-13, 35,126개 행, 25개 자치구와 서울시 합계다.
지표 두 개의 누락값은 없고 모든 26개 지역에 2024-02-29 기록이 없다.

[source-manifest.json](../data/source-manifest.json)에 원본 파일의 SHA-256, 크기, 기간과 기록 수를 기록했다.
팀원들이 파일을 받은 뒤 해시를 비교하면 정확히 같은 파일인지 확인할 수 있다.
종료 날짜가 같다는 것만으로 원본 파일 전체가 동일하다고 단정하지 않는다.
원본 CSV는 로컬에서 보관하며 이 변경에 포함하지 않았다.

## 실제 CSV로 확인한 분석 결과

종로구(11110), 조회 기간 2025-01-01~2025-12-31에 대해 Flask test_client로 /api/analysis를 요청했다.
세 방법 모두 조회 기간의 365개 결과만 반환했고 계산용 이전 날짜는 응답에 포함되지 않았다.

- 이동평균: window=7, threshold=0.10, 이상 120일
- 평일·주말 계절성: window=28, threshold=0.10, min_samples=4, 이상 46일
- Z-score: window=28, threshold=3.0, 이상 1일

이는 정답 라벨에 대한 정확도 비교가 아니다. 기준과 임계값에 따라 이상으로 판정하는 날짜 수가 달라진 결과다.
공휴일은 별도로 구분하지 않으며, 평일·주말 구분만 반영한다.

## 보고서에 사용할 수 있는 통합 검증 사례

생활인구의 계절성 탐지 결과와 유입 지표 설명을 함께 확인하는 과정에서 비교 기준의 불일치를 발견했다.
2025년 9월 13일 토요일의 유입인구를 평일·주말을 섞은 직전 28일 평균과 비교하면
기존 설명은 32.3% 적다고 표시했다. 토요일을 같은 주말 그룹과 비교하도록 수정한 뒤에는
유입인구가 평소 주말보다 19.8% 많다는 설명으로 바뀌었다. 자치구 간 이동인구도
혼합 기준의 -29.2%에서 같은 주말 기준의 +17.4%로 비교 방향이 바뀌었다.

원인은 요일별 인구 수준 차이가 설명의 지표 기준값에 반영되지 않은 것이었다.
손호진 담당 커밋 4061c70에서 직전 28일 중 같은 평일·주말 그룹만 기준 계산에 사용하도록 수정했고,
현재 데이터 객체를 연결한 실제 CSV 요청에서도 수정 결과를 재현했다.
설명에는 지표의 동반 변화만으로 생활인구 변동의 원인을 단정할 수 없다는 문구를 유지했다.

검증 방법은 수정 전 a4afbe1의 설명 코드와 수정 후 4061c70의 설명 코드를 같은 원자료에 적용하는 것이었다.
이번에 직접 확인한 범위는 Python/Flask 응답과 프론트 adapter 변환까지이며,
브라우저 화면 캡처를 새로 수행했다는 뜻은 아니다.

## ReportGenerator 연동 시 합의할 부분

API의 임시 함수는 다음 여섯 인자를 사용한다.

```python
build_payload(records, results_by_method, details_by_method, settings, start, end)
```

권장 분담은 API가 기준 계산·설명에 필요한 과거 기록을 확보하고,
ReportGenerator가 최종 응답에 포함할 results와 details를 조회 기간으로 제한하는 것이다.
현재 임시 함수도 results를 조회 기간으로 제한한다. 최종 클래스가 그 책임을 이어받도록 하면 된다.
이 분담은 팀원과 확정할 권고이며 ReportGenerator를 대신 구현하거나 서버 코드를 바꾸지는 않았다.

최종 JSON은 schema_version=1과 세 methods 블록을 유지한다.
results에는 DetectionResult.to_dict()를 사용하고 details는 해당 결과 날짜에만 연결한다.
settings, boolean, null, 점수의 의미를 변경하지 않는다.

## 다음 실제 사용 순서

로컬 main 이력에는 탐지기 병합 aefce54와 계절성·프론트엔드 병합 9c684fd가 이미 있다.
같은 두 브랜치를 다시 병합할 필요가 있는지는 GitHub의 현재 PR 상태와 비교해 확인한다.
이후 데이터 계층 수정과 API 브랜치가 같은 실행 폴더에 있어야 한다.

API 브랜치의 app.py는 create_app()를 제공하므로 저장소를 생성해 전달하는 시작 코드가 필요하다.
다음은 두 브랜치를 함께 둔 뒤 실행할 수 있는 시작 코드 예제다.

```python
from app import create_app
from csv_population_repository import CsvPopulationRepository

repository = CsvPopulationRepository("data/population.csv", require_indicators=True)
repository.load()
app = create_app(repository)
app.run(host="127.0.0.1", port=5000, debug=False)
```

웹 화면에 실제 데이터를 표시하려면 Flask 환경에서 static/js/config.js의 mode를 mock에서 api로 전환한다.
apiUrl은 /api/analysis를 유지하고 Flask가 제공하는 루트 주소에서 화면을 연다.
정적 http.server만 실행해서는 Python 분석 API가 동작하지 않는다.
모드 전환·실제 서버의 브라우저 검증과 ReportGenerator 교체는 팀 통합 단계에서 진행한다.

## 자동 검증 범위

- 데이터 브랜치 단독: Python 67개 통과, API 모듈을 요구하는 6개는 건너뜀
- API 4061c70과 결합한 별도 폴더: Python 80개 모두 통과
- 실제 API JSON을 프론트 adapter에 전달해 세 방법의 이상 건수와 토요일 설명 보존 확인
- 실제 CSV의 알려진 누락 날짜와 숫자 지표, 25개 자치구 목록 확인

현재 API 응답 생성은 팀원 코드의 임시 build_payload()를 사용한 결과다.
향후 ReportGenerator로 교체한 뒤 같은 요청으로 다시 검증해야 한다.
