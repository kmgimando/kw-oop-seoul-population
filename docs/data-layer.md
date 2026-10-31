# 생활인구 데이터 계층 사용 설명

김민규 담당 `PopulationRecord`와 `CsvPopulationRepository`의 구현 및 팀원 연동 규격이다.
탐지기 코드는 기존 인터페이스를 유지하고, `compare_detectors.load_records()`를 저장소에 연결했다.
새로운 서비스 클래스나 Flask 서버를 추가하지 않는다.

## 빠른 실행

저장소 최상위 폴더에서 실행한다. Python 3.10 이상과 표준 라이브러리만 필요하다.

```console
python demo_data.py
python demo_data.py --district 11680 --method moving_average --start 2026-01-29 --end 2026-02-09
python demo_data.py --district 11680 --method z_score --window 28 --threshold 3
python demo_data.py --method seasonal --window 28 --threshold 0.1 --min-samples 4
python -m unittest discover -v
```

가상 예제는 종로구·강남구의 2026-01-01~2026-02-09 자료 80개 행이다.
주중·주말 차이와 임의의 급증을 넣은 실행 예제로 실제 관측값이나 성능 평가 자료가 아니다.

실제 원본은 다음처럼 사용한다.

```console
python demo_data.py --csv data/population.csv --require-indicators
python demo_data.py --csv data/population.csv --district 11680 --start 2026-09-01 --end 2026-09-13 --method seasonal --output data/preview.json
python compare_detectors.py --csv data/population.csv
```

`demo_data.py`는 화면과 동일한 HTTP API가 아니라 로컬 점검용 명령줄 프로그램이다.
콘솔에는 기록 5개와 요약만 표시하고, `--output`을 지정하면 선택 기간의 모든 기록과 결과를 UTF-8 JSON으로 저장한다.
출력 경로로 원본 CSV와 같은 파일을 지정하면 오류로 알리고 원본을 보존한다.
JSON의 `analysis.summary.detection_rate`는 이상 건수/판정 가능 건수이며 정답 대비 정확도가 아니다.
판정 가능한 기록이 없으면 비율은 `null`이다. 과거 이력은 결과·통계에서 제외한다.

## PopulationRecord

한 날짜·한 지역의 원자료를 보관하는 동결 dataclass다.
날짜는 `datetime.date`, 코드는 CSV의 5자리 ASCII 숫자 문자열, 이름은 공백을 제거한 문자열로 저장한다.
시간이 포함된 `datetime.datetime`, 빈 지역명, 잘못된 코드, 음수·NaN·무한대·bool 인구값은 거절한다.
추정 인구의 소수점은 유지하고 값을 float로 통일한다.

속성은 `date`, `district_code`, `district_name`, `total_population`,
`external_inflow`, `interdistrict_movement`, 선택적인 `indicators` 객체다.
두 지표의 미제공 값은 `None`이고 실제 관측값 0과 구분한다.
기존 네 인자만 전달하는 생성 방식도 사용할 수 있다.

`validate()`는 값의 조건을 확인한다. `to_dict()`는 날짜를 문자열로 바꾸며 다음 형식으로 반환한다.
`indicators` 키에는 계산된 원인이나 변화율을 섞지 않고 CSV의 원래 지표값만 넣는다.

```json
{
  "date": "2026-01-01",
  "district_code": "11680",
  "district_name": "강남구",
  "total_population": 800000.25,
  "indicators": {
    "external_inflow": 0.0,
    "interdistrict_movement": null
  }
}
```

초기 버전의 `to_dict()`에 `indicators` 키가 추가되었다.
탐지 입력의 네 속성과 `DetectionResult`의 14개 필드에는 변경이 없다.
기존 제안서의 `population` 표기는 실제 탐지기에 맞춰 `total_population`으로 사용한다.

## CSV 로딩과 오류 정책

```python
from csv_population_repository import CsvPopulationRepository

repository = CsvPopulationRepository("data/population.csv", require_indicators=True)
record_count = repository.load()
districts = repository.list_districts(include_seoul_total=False)
first_day, last_day = repository.get_date_range()
quality = repository.get_data_quality()
```

필수 열은 `기준일ID`, `시구코드`, `시구명`, `총생활인구수`다.
기준일은 `YYYYMMDD` 형식과 실제 달력 날짜를 모두 검사한다.
`서울외유입인구수`는 `external_inflow`, `자치구간이동인구수`는 `interdistrict_movement`로 읽는다.
나머지 원본 열은 변경하지 않고 이 저장소의 분석 대상에서만 제외한다.

기본 `encoding="auto"`는 파일 전체를 UTF-8로 읽을 수 있는지 확인하고 실패하면 CP949를 시도한다.
UTF-8 BOM은 제거하며 `encoding="cp949"`나 `encoding="utf-8-sig"`로 명시할 수도 있다.
약 6.5MB인 현재 정적 CSV를 메모리에 읽고 객체를 구성하는 방식이다. 대용량 스트리밍 저장소나 DB는 구현하지 않았다.

`require_indicators=False`가 기본이므로 핵심 네 열만 가진 파일도 읽는다.
선택 열이 없거나 값이 비어 있으면 `None`으로 보관하고 품질 요약에 누락 수를 기록한다.
원본 기반 설명이 꼭 필요한 실행에서는 `require_indicators=True`로 열·값의 누락을 거절한다.
값이 들어 있는데 숫자가 아니거나 음수·NaN·무한대이면 옵션과 관계없이 거절한다.

중복된 헤더, 행의 열 개수 불일치, 깨진 CSV 인용부호, 동일 코드의 이름 불일치,
같은 지역·날짜의 중복을 오류로 알린다. 중복을 삭제하거나 합산하지 않는다.
새 파일 전체가 검증된 뒤 데이터와 품질 정보를 교체하므로 재로딩 실패 시 이전 정상 자료가 유지된다.
서버에서는 시작 시 한 번 로딩하고 조회에 사용한다. 동시 재로딩을 위한 잠금은 구현 범위에 포함하지 않는다.

## 기간 조회와 분석용 과거 이력

```python
from datetime import date
from detectors import MovingAverageDetector

detector = MovingAverageDetector(window=7, threshold=0.1)
start, end = date(2026, 9, 1), date(2026, 9, 13)
records = repository.get_records("11680", start, end, history_days=detector.window)
results = [row for row in detector.detect(records) if start <= row.date <= end]
```

`get_records(code, start_date=None, end_date=None, history_days=0)`는 날짜순 새 목록을 반환한다.
양 끝 날짜를 포함하고 생략한 방향은 전체를 조회한다. 날짜 문자열은 API에서 date로 변환한 뒤 전달한다.
`history_days`는 시작일 전의 **달력 일수**이며 관측 행 수가 아니다.
이 옵션을 사용하려면 시작일을 지정해야 한다. 0 이상의 정수만 받으며 bool은 거절한다.

세 방법을 동시에 실행할 때는 가장 긴 window를 사용하고, 설명 객체가 더 긴 과거 기간을 요구하면 함께 확보한다.
그 후 결과와 지표를 조회 기간으로 제한해 응답을 구성하는 책임은 API/ReportGenerator에 있다.
기간에 실제 기록이 하나도 없으면 과거 이력이 있더라도 빈 목록을 반환한다.
누락 날짜 때문에 이력이 끊기면 기존 BaseDetector가 이력을 초기화하므로 초기 결과가 판정불가일 수 있다.

`list_districts()`와 `get_all_records()`는 기본적으로 서울시 합계 코드 `11000`도 포함한다.
자치구 선택 화면과 25개 자치구 비교에서는 `include_seoul_total=False`를 명시한다.
서울시 합계를 25개 자치구와 다시 더하지 않는다.
없는 지역 코드와 잘못된 기간은 ValueError, 로딩 전 조회는 RuntimeError다.
알려진 지역의 유효한 빈 기간 조회는 오류가 아닌 빈 목록이다.

## 품질 요약

`get_data_quality()`는 내부 저장소와 분리된 딕셔너리를 반환하며 다음 정보를 포함한다.

- 전체 기록 수, 지역 수, 서울시 합계를 제외한 자치구 수와 합계 포함 여부
- 전체 첫 날짜·마지막 날짜, 실제 사용한 인코딩
- 유입·이동 열의 존재 여부와 값이 없는 기록 수
- 지역별 실제 날짜 범위
- 지역별 누락 날짜 목록과 누락된 지역·날짜 조합 수

누락은 파일 전체의 최소~최대 날짜를 공통 기준으로 계산한다.
따라서 중간에 빠진 날과 특정 지역의 처음·마지막 구간에 빠진 날을 모두 표시한다.
예를 들어 26개 지역에서 같은 날짜 하루가 빠졌다면 `missing_day_count=26`이다.
이 값을 서로 다른 달력 날짜 수나 이상탐지 건수로 해석하지 않는다.

## MigrationIndicators 연결

지표 비교·참고 설명 규칙은 손호진 담당 범위다. 이 코드에서는 지표 객체 자체를 새로 구현하지 않았다.
두 숫자 원자료는 이미 모든 기록에 보관하며, 외부 클래스가 준비되면 생성자를 주입할 수 있다.
아래의 `MigrationIndicators`는 해당 모듈이 실제 구현된 뒤 사용하는 연결 예제다.

```python
# 손호진 담당 모듈이 준비된 뒤에만 실행한다.
from migration_indicators import MigrationIndicators

repository = CsvPopulationRepository(
    "data/population.csv",
    require_indicators=True,
    indicators_factory=MigrationIndicators,
)
repository.load()
record = repository.get_records("11680")[0]
indicator_object = record.indicators
```

생성자는 `external_inflow=숫자, interdistrict_movement=숫자` 키워드 인자를 받고 같은 이름의 속성을 보존해야 한다.
두 값 중 하나라도 없으면 객체를 만들지 않고 `record.indicators=None`을 유지한다.
객체가 주입되지 않았더라도 원래 두 지표값과 `to_dict()["indicators"]`는 사용할 수 있다.
유입·이동 값만으로 실제 사건이나 이상 변동의 인과관계를 단정하지 않는다.

## 검증 결과와 남은 연결 작업

Python 66개 테스트와 기존 JavaScript 19개 테스트가 통과했다.
실제 파일은 35,126개 기록, 25개 자치구와 서울시 합계, 2023-01-01~2026-09-13 범위다.
두 이동 지표에 빠진 값은 없고, 모든 지역에서 2024-02-29가 빠진 것을 확인했다.
세 탐지기의 결과는 기존 네 속성 기반 로더와 동일했고, 기간 앞 이력을 포함한 조회도 전체 계산과 일치했다.

실제 Flask 서버, MigrationIndicators의 비교 규칙, AnomalyExplainer, ReportGenerator와의 실행은
해당 코드가 구현된 뒤 담당자와 연결해야 한다. 프론트엔드는 현재 Mock 모드를 유지한다.
