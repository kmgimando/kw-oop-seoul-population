# 생활인구 이상탐지 API 연동 계약 제안

작성일: 2026-10-30. 작성 범위: 서윤도 담당 SeasonalAnalyzer 및 프론트엔드와 손호진 담당 Flask API, 이건희 담당 ReportGenerator 사이의 연동 계약.

이 문서는 팀 협의용 제안서다. 실제 Flask API와 ReportGenerator가 구현되었다는 뜻이 아니며, 이번 작업에서는 해당 코드를 작성하거나 실제 서버에 연결하지 않았다. 프론트엔드는 계속 Mock 모드로 동작한다.

## 1. 확정된 기존 구현과 협의할 제안

| 구분 | 현재 확인된 내용 | 상태 |
| --- | --- | --- |
| 탐지 호출 | BaseDetector.detect(records), 하위 클래스의 _evaluate(record, history) | 기존 코드 인터페이스 |
| 입력 객체 속성 | date: datetime.date, district_code: str, district_name: str, total_population: 유한한 0 이상 숫자 | 기존 코드 인터페이스 |
| 결과 객체 | DetectionResult의 14개 필드 및 to_dict() | 기존 코드 인터페이스 |
| 탐지 식별자 | moving_average, z_score, seasonal | 현재 구현 값 |
| 계절성 설정 | window=28, threshold=0.10, min_samples=4 | 현재 초기 기본값, 실제 데이터 보정 전 |
| 결과 이력 | history_size는 전체 연속 이력 수 | 기존 코드 의미 유지 |
| HTTP 경로와 방식 | GET /api/analysis | 임시 제안 |
| 응답 envelope | schema_version + methods 배열 | 임시 제안, 현재 프론트 adapter가 기대하는 구조 |
| 설명·이동 지표 | 방법별 details의 날짜 키로 연결 | 임시 제안 |
| HTTP 오류 코드·오류 JSON | 아래 7절 | 임시 제안 |

보고서의 PopulationRecord 속성명 population과 실제 탐지기의 total_population은 차이가 있다. 데이터 담당자와 합의해 탐지기에 필요한 total_population 및 district_name을 제공해야 한다. 이 문서는 다른 팀원의 데이터 클래스를 변경하지 않는다.

## 2. 엔드포인트와 요청

제안: GET /api/analysis. 응답 Content-Type은 application/json이다. 하나의 자치구와 날짜 범위에 대해 세 방법을 한 번에 실행한다. 인증·배포 경로·CORS 정책은 팀 실행 환경 확정 후 결정한다.

| Query 파라미터 | 전송 형태 / 해석한 자료형 | 규칙 |
| --- | --- | --- |
| district_code | 문자열 | 서울시 25개 자치구 코드. 예: "11110". 숫자로 변환하지 않음. 서울시 합계 "11000"는 이번 화면 선택 대상이 아님 |
| start_date | YYYY-MM-DD 문자열 → date | 실제 달력 날짜, 조회 시작일 포함 |
| end_date | YYYY-MM-DD 문자열 → date | 실제 달력 날짜, 종료일 포함, start_date 이상 |
| methods | JSON을 URL 인코딩한 문자열 → object | 아래 세 방법의 설정을 모두 포함 |

현재 fetchHttp()는 위 네 파라미터만 전송한다. selected_method는 화면에서 강조할 방법이며 서버로 보내지 않는다. scenario도 Mock 전용이며 실제 API 파라미터가 아니다. request body는 사용하지 않는다. GET 대신 POST로 합의하면 api.js의 통신부를 변경해야 한다.

methods의 실제 요청 값:

```json
{
  "moving_average": {"window": 7, "threshold": 0.1},
  "z_score": {"window": 28, "threshold": 3.0},
  "seasonal": {"window": 28, "threshold": 0.1, "min_samples": 4}
}
```

| 설정 | 자료형 | 기존 탐지기 조건 / 현재 화면 조건 |
| --- | --- | --- |
| window | integer, boolean 제외 | 부모는 1 이상, Z-score는 2 이상. 현재 화면·Mock은 7·14·28·56 프리셋만 지원. 실제 API가 더 넓게 허용할지는 협의 |
| threshold | 유한한 number, boolean 제외 | 0보다 큼. 이동평균·계절성은 비율, Z-score는 점수. 화면 10%는 요청 0.10으로 변환 |
| min_samples | integer, boolean 제외 | seasonal에서만 사용. 1 이상 window 이하 |

제안: 요청의 세 설정을 모두 필수로 받고, 서버가 임의로 누락값을 채우거나 값을 보정하지 않는다. 적용 불가능한 설정은 400으로 반환한다. 예를 들어 window=7, min_samples=7은 생성자상 유효하지만 주말 표본이 항상 부족할 수 있으며, 이를 정상으로 바꾸지 않고 판정불가로 처리한다. 데이터 검증 전에 임계값 기본값을 최종값으로 간주하지 않는다.

실제로 URL 인코딩한 요청 예시:

```http
GET /api/analysis?district_code=11110&start_date=2024-01-29&end_date=2024-01-29&methods=%7B%22moving_average%22%3A%7B%22window%22%3A7%2C%22threshold%22%3A0.1%7D%2C%22z_score%22%3A%7B%22window%22%3A28%2C%22threshold%22%3A3.0%7D%2C%22seasonal%22%3A%7B%22window%22%3A28%2C%22threshold%22%3A0.1%2C%22min_samples%22%3A4%7D%7D
Accept: application/json
```

## 3. 성공 응답 구조와 계산된 예시

최상위 schema_version은 숫자 1이다. methods는 세 block을 정확히 하나씩 포함하는 배열이다. 배열 순서는 자유이며 프론트엔드는 method 키로 구분한다. 각 block의 settings에는 실제 적용값을 반환한다. 현재 adapter는 요청 설정과 응답 설정이 다르면 오류로 처리한다.

| block 필드 | 자료형 | 규칙 |
| --- | --- | --- |
| method | string | moving_average / z_score / seasonal |
| settings | object | window, threshold 및 seasonal의 min_samples |
| results | array of DetectionResult.to_dict() | 요청 자치구·조회 기간의 모든 정상·이상·판정불가 결과 |
| details | object, 생략 가능 | 날짜별 설명과 이동 지표. 미제공이면 빈 객체 또는 생략 |

아래는 기존 Python 탐지기 세 개를 직접 실행해 만든 완전한 JSON 예시다. 입력은 2024-01-01~01-28의 평일 인구 100, 주말 인구 200, 01-29 실제값 150인 합성 자료다. 실제 서울 생활인구나 탐지 성능을 뜻하지 않는다. 요청 기간은 2024-01-29 하루이며 계산용 이전 이력은 응답에서 제외했다. 설명 문자열도 형식 설명을 위한 예시이고 실제 AnomalyExplainer의 출력이 아니다. 이동 지표는 원자료가 없으므로 null이다.

```json
{
  "schema_version": 1,
  "methods": [
    {
      "method": "moving_average",
      "settings": {
        "window": 7,
        "threshold": 0.1
      },
      "results": [
        {
          "date": "2024-01-29",
          "district_code": "11110",
          "district_name": "종로구",
          "method": "moving_average",
          "actual": 150.0,
          "expected": 128.57142857142858,
          "lower_bound": 115.71428571428572,
          "upper_bound": 141.42857142857144,
          "score": 0.16666666666666655,
          "threshold": 0.1,
          "deviation_ratio": 0.16666666666666655,
          "is_anomaly": true,
          "status": "evaluated",
          "history_size": 7
        }
      ],
      "details": {
        "2024-01-29": {
          "explanation": "합성 예시에서 기준 범위를 벗어났습니다. 실제 사건의 원인으로 해석할 수 없습니다.",
          "indicators": {
            "external_inflow": null,
            "interdistrict_movement": null
          }
        }
      }
    },
    {
      "method": "z_score",
      "settings": {
        "window": 28,
        "threshold": 3.0
      },
      "results": [
        {
          "date": "2024-01-29",
          "district_code": "11110",
          "district_name": "종로구",
          "method": "z_score",
          "actual": 150.0,
          "expected": 128.57142857142858,
          "lower_bound": 0.0,
          "upper_bound": 264.0976140072163,
          "score": 0.4743416490252566,
          "threshold": 3.0,
          "deviation_ratio": 0.16666666666666655,
          "is_anomaly": false,
          "status": "evaluated",
          "history_size": 28
        }
      ],
      "details": {}
    },
    {
      "method": "seasonal",
      "settings": {
        "window": 28,
        "threshold": 0.1,
        "min_samples": 4
      },
      "results": [
        {
          "date": "2024-01-29",
          "district_code": "11110",
          "district_name": "종로구",
          "method": "seasonal",
          "actual": 150.0,
          "expected": 100.0,
          "lower_bound": 90.0,
          "upper_bound": 110.0,
          "score": 0.5,
          "threshold": 0.1,
          "deviation_ratio": 0.5,
          "is_anomaly": true,
          "status": "evaluated",
          "history_size": 28
        }
      ],
      "details": {
        "2024-01-29": {
          "explanation": "합성 예시에서 기준 범위를 벗어났습니다. 실제 사건의 원인으로 해석할 수 없습니다.",
          "indicators": {
            "external_inflow": null,
            "interdistrict_movement": null
          }
        }
      }
    }
  ]
}
```

results의 숫자는 문자열이나 퍼센트 기호가 붙은 값으로 변환하지 않는다. float의 JSON 표현 자릿수 차이는 허용하되 서버에서 화면용으로 반올림하지 않는다. NaN·Infinity·-Infinity는 허용하지 않으며 json.dumps(..., allow_nan=False)와 동등한 검증을 권한다.

## 4. 공통 탐지 결과와 세 방법의 의미

DetectionResult에 새 필드를 추가하지 않는다. 아래 필드를 모두 전달한다.

| 필드 | JSON 자료형 | 의미 |
| --- | --- | --- |
| date | string | YYYY-MM-DD, 시간·시간대 없는 분석 날짜 |
| district_code / district_name | string | 요청 자치구 코드와 이름 |
| method | string | 소속 block.method와 동일 |
| actual | number | 실제 생활인구, 유한한 0 이상 값 |
| expected | number 또는 null | 기준값, 판정불가면 null |
| lower_bound / upper_bound | number 또는 null | 정상 범위. 하한은 최소 0. 판정불가면 null |
| score | number 또는 null | 아래 방법별 점수. 기준값/표준편차 0이면 null |
| threshold | number | 소속 settings.threshold와 동일 |
| deviation_ratio | number 또는 null | (actual-expected)/expected. expected=0 또는 미제공이면 null |
| is_anomaly | boolean 또는 null | true 이상, false 정상, null 판정불가 |
| status | string | evaluated / insufficient_history / zero_baseline / zero_variance |
| history_size | integer | 사용 가능한 전체 연속 이력 수. 0 이상 window 이하 |

| 방법 | expected | score / 판정 |
| --- | --- | --- |
| moving_average | 직전 window일 인구 산술평균 | (actual-expected)/expected, 절댓값이 threshold 초과 |
| z_score | 직전 window일 인구 산술평균 | (actual-expected)/모표준편차, 절댓값이 threshold 초과 |
| seasonal | 직전 window일 중 현재 날짜와 같은 평일·주말 그룹 평균 | (actual-expected)/expected, 절댓값이 threshold 초과 |

정확히 임계값과 같은 점수는 이상이 아니다. 평일은 월~금, 주말은 토~일이며 별도 공휴일 분류는 없다. 부모 detect()는 전체 window가 쌓이기 전에는 계절성의 min_samples가 충분해도 평가하지 않는다. 전체 이력이 충분해도 계절성 동일 그룹 표본이 min_samples보다 적으면 insufficient_history다. history_size를 동일 그룹 표본 수로 바꾸지 않는다. 필요한 동일 그룹 표본 정보는 향후 별도 details 확장으로 협의하며 현재 필수 응답에는 포함하지 않는다.

## 5. 세 방법 동시 비교

하나의 요청에서 같은 자치구·기간과 같은 원본 records를 세 탐지기에 전달한다. 방법별 window·threshold는 다를 수 있으며 seasonal에는 min_samples가 추가된다. 결과는 이상 날짜만 추출하지 말고 전체 날짜를 반환한다. 프론트엔드는 각 block.results에서 통계를 계산하므로 별도 summary는 현재 필수 계약이 아니다.

- 이상 건수: is_anomaly === true인 개수.
- 정상 건수: is_anomaly === false인 개수.
- 판정불가 건수: is_anomaly === null인 개수.
- 판정 가능 건수: 이상 + 정상.
- 탐지율: 이상 / 판정 가능. 분모가 0이면 null이며 화면은 —로 표시.

통계는 조회 기간만 대상으로 한다. warm-up 이력을 분모에 포함하지 않는다. 데이터가 없으면 세 block과 settings는 유지하고 results: [], details: {}로 200을 반환하는 방식을 제안한다. 일부 방법 실패 시 세 방법이 성공한 것처럼 정상 응답을 만들지 않는다. 현재 프론트엔드는 세 block을 요구하므로 부분 성공은 별도 계약 없이는 지원하지 않는다.

## 6. 설명과 이동 지표

방법별 details[date]를 해당 block.results의 date와 연결한다. 같은 날짜라도 방법별 판정이 다르므로 설명이 필요한 방법에 붙인다. 조회 기간 밖 또는 results에 없는 날짜를 details에 넣지 않는다. 정상·판정불가 날짜의 details는 생략하거나 설명을 null로 보낼 수 있다.

```json
{
  "2024-01-29": {
    "explanation": "형식 예시: 유입 지표가 함께 증가했으나 실제 원인으로 단정할 수 없습니다.",
    "indicators": {
      "external_inflow": null,
      "interdistrict_movement": null
    }
  }
}
```

explanation은 일반 텍스트 string 또는 null이며 HTML을 전달하지 않는다. indicators 값은 유한한 number 또는 null이다. 현재 키는 당일 지표의 원래 인구값을 담는 제안이며 변화율을 혼합하지 않는다. 인구 집계 단위·정의·서울 외 유입/자치구 간 이동의 집계 방식은 데이터 담당자와 확정해야 한다. 값이 미제공이면 null 또는 키 생략으로 표시하며 0으로 추정하지 않는다. 이 문서의 예시는 미제공 상태다.

기준 대비 변화율·비교 기간·기준값을 추가로 보여줄 경우 필드명·단위·비교 이력 기간을 별도 확정하고 adapter와 화면을 확장한다. 현재 UI는 두 지표의 값과 설명만 읽는다. 설명은 지표 동반 변화에 대한 참고 정보이며 인과관계나 실제 사건을 단정하지 않는다.

## 7. 오류 JSON과 HTTP 상태 코드 제안

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "start_date는 end_date보다 늦을 수 없습니다.",
    "fields": {"start_date": "종료일 이전 또는 같은 날짜를 입력하세요."}
  }
}
```

현재 프론트엔드는 error.message만 읽는다. code와 fields는 향후 상세 표시를 위한 선택 확장이다. 알 수 없는 응답이나 JSON이 아닌 HTTP 오류는 상태 코드 기반 일반 메시지로 처리한다. 스택 추적·서버 경로·비밀정보는 오류 메시지에 넣지 않는다.

| 상태 | 예시 code | 사용 상황 |
| --- | --- | --- |
| 200 | 해당 없음 | 정상 처리, 표본 부족 포함, 조회 데이터가 없는 유효 요청 |
| 400 | INVALID_PARAMETER | 누락 파라미터, 잘못된 날짜/기간/JSON, 미지원 방법/자치구/설정 |
| 404 | NOT_FOUND | 존재하지 않는 API 경로. 알려진 자치구의 빈 조회는 404가 아님 |
| 500 | INTERNAL_ERROR 또는 DATA_INTEGRITY_ERROR | 예기치 않은 서버 오류, 원자료의 중복 날짜·타입/값 오류 등 |
| 503 | DATA_UNAVAILABLE | Repository 데이터가 로딩되지 않았거나 소스에 접근할 수 없음 |

입력 검증과 원자료 검증을 구분한다. 탐지기 ValueError를 일괄 400으로 바꾸면 서버 데이터 결함이 사용자 입력 오류로 오인될 수 있다. 사용자 설정 오류는 요청 검증 단계에서 400으로 분리하고, 원자료 결함은 서버 오류로 보고한다. 표본 부족은 HTTP 오류가 아니며 200의 날짜별 null 결과다.

## 8. 조회 전 이력과 날짜 누락

손호진 담당 요청 처리 흐름의 제안:

1. 요청과 세 방법의 설정을 검증한다.
2. 가장 긴 window를 W라고 할 때 적어도 start_date-W일~end_date의 같은 자치구 records를 Repository에서 조회한다. 날짜 계산의 최솟값 경계를 처리한다.
3. AnomalyExplainer가 더 긴 comparison_window를 요구하면 해당 담당자와 합의해 조회 이력을 추가 확보한다.
4. 사전 이력을 포함해 각 탐지기의 detect(records)를 실행한다. 당일 값은 기존 부모가 판정 후 이력에 추가한다.
5. 설명 생성에 필요한 원래 records와 탐지 결과를 연결한다. 결과는 반드시 start_date~end_date만 응답한다. 모든 통계도 이 기간으로 제한한다.

현재 BaseDetector는 날짜가 끊기면 이력을 초기화한다. 사전 기간에 누락이 있거나 데이터 시작점이 가까우면 W일을 조회했더라도 초기 결과는 판정불가일 수 있다. 누락 날짜를 0이나 보간값으로 임의 생성하지 않는다. 원래 관측값 0은 누락과 다르며 보존한다. 데이터가 없는 날짜는 기존 detect()에서 결과 자체가 없으므로 응답에 임의의 DetectionResult를 만들지 않는다.

같은 자치구·날짜 중복은 데이터 결함이다. 서로 다른 자치구 이력을 섞지 않는다. 탐지 이후 이상 날짜를 과거 이력에서 제거하거나, 미래 데이터를 기준값에 넣거나, 방법별로 다른 원자료를 사용하는 정책도 추가하지 않는다. SeasonalAnalyzer의 날짜 역산은 현재 부모의 연속·과거·오래된 순 이력 계약을 전제로 한다.

## 9. 정상·이상·판정불가와 null

| 상황 | is_anomaly | status | 수치 처리 |
| --- | --- | --- | --- |
| 일반 정상 | false | evaluated | expected·범위·score 제공 |
| 일반 이상 | true | evaluated | expected·범위·score 제공 |
| 전체 이력 또는 계절성 표본 부족 | null | insufficient_history | expected·범위·score·deviation_ratio 모두 null |
| 기준값 0 | actual이 0이면 false, 다르면 true | zero_baseline | expected=0, 범위=0~0, score·deviation_ratio=null |
| 표준편차 0 | actual=expected이면 false, 다르면 true | zero_variance | 범위=expected~expected, score=null. expected>0이면 deviation_ratio 계산 가능 |

따라서 zero_baseline/zero_variance를 무조건 판정불가로 분류하지 않는다. JSON boolean과 null을 문자열 "true"/"false"/"null"로 바꾸지 않는다. null을 0·빈 문자열로 바꾸지 않는다. 실제 인구값 actual은 데이터가 존재하는 결과에서 항상 숫자다. 전체 데이터가 없으면 actual=null인 가짜 날짜를 만들지 않고 빈 results를 사용한다.

판정불가 예시도 기존 결과 객체로 직접 생성했다:

```json
{
  "date": "2024-01-01",
  "district_code": "11110",
  "district_name": "종로구",
  "method": "seasonal",
  "actual": 100.0,
  "expected": null,
  "lower_bound": null,
  "upper_bound": null,
  "score": null,
  "threshold": 0.1,
  "deviation_ratio": null,
  "is_anomaly": null,
  "status": "insufficient_history",
  "history_size": 0
}
```

## 10. 담당자별 구현 범위와 연동 전 확인

| 담당 | 구현·확인할 내용 |
| --- | --- |
| 손호진 API | 최종 경로/메서드 확정, 요청 파싱·검증, Repository와 세 탐지기 연결, 사전 이력 확보, AnomalyExplainer 호출, ReportGenerator 호출, HTTP 오류 변환, JSON 직렬화 |
| 손호진 설명·지표 | explain/compare 결과의 날짜·방법 연결, 지표 정의·단위·비교 기간, 미제공과 0 구분, 인과 단정 없는 설명 |
| 이건희 ReportGenerator | records/results/explanations 취합, to_dict() 재사용, 조회 기간 필터의 단일 책임 위치 합의, 세 method block·적용 settings·날짜별 details 구성, 빈 결과와 null 보존 |
| 서윤도 | 계약 확정 후 config.js·api.js·adapter.js의 필요한 매핑 수정, Mock→API 전환, 실제 Python 결과/JSON/화면 대조 및 UI 오류 검증 |
| 김민규와 협의 | 입력 속성명·코드 체계·날짜 범위·원본 데이터와 사전 이력 조회 계약 |
| 권민우와 협의 | 부모의 history·status·공통 결과 의미를 바꿔야 하는 요구 발생 시 사전 합의. 현재는 변경 없음 |

ReportGenerator.build_payload()는 보고서에 있는 설계 메서드이며 아직 실제 생성자나 인자 규격을 확정한 구현으로 가정하지 않는다. 본 문서는 담당자 코드를 대신 구현하지 않는다.

팀 확인 체크리스트:

- GET /api/analysis 및 methods JSON 파라미터를 사용할지, POST/다른 경로로 바꿀지.
- 세 방법 동시 응답과 schema_version=1 envelope, 적용 설정 echo를 지원할지.
- 결과 날짜 집합·요청 기간 필터·사전 이력 및 설명 비교 이력의 책임 위치.
- 실제 자치구 코드와 total_population 속성, 데이터 범위 메타데이터 제공 방식.
- window 프리셋 유지 여부, 기본값 보정 및 표본 부족 정책.
- details의 방법/날짜 연결, 이동 지표의 의미·단위와 미제공 처리.
- 오류 코드, 빈 조회 200, 데이터 결함/데이터 미준비 오류 구분.
- Flask 템플릿 라우트와 static 경로, 동일 origin 배포 또는 CORS.

계약 확정 뒤 실제 원본 CSV를 이용해 세 방법의 설정·기준값·점수·범위·상태·이상 건수·탐지율을 API 및 화면과 대조한다. 경계 날짜·누락·잘못된 요청·빈 조회·연속 요청도 실제 서버로 검증한다. 현재는 Python 36개와 JS 19개 테스트 및 Mock 브라우저 검증까지만 수행했으며 실제 Flask 연동은 미실행이다.
