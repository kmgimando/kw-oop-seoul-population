# 서울 생활인구 이상탐지

이동평균과 Z-score로 자치구별 생활인구의 급증·급감을 찾는다.
Python 3.10 이상에서 별도 설치 없이 실행할 수 있다.

## 파일

- `detectors.py`: 공통 추상 클래스, 이동평균·Z-score 탐지기, 결과 객체
- `compare_detectors.py`: CSV를 읽고 두 방법을 비교
- `test_detectors.py`: 탐지 동작 테스트
- `analysis_results/anomalies.csv`: 이상으로 판정된 날짜와 수치

## 실행

원본 생활인구 CSV를 프로젝트 폴더에 둔 뒤 실행한다.

```bash
python3 compare_detectors.py
python3 -m unittest test_detectors
```

기준을 바꾸려면 `--ma-window 14 --ma-threshold 0.15`처럼 옵션을 붙인다.
원본 파일은 `--csv "파일 경로"`로 지정하며 기본 인코딩은 CP949다.

## 사용

`records`는 `date`(datetime.date), `district_code`(str),
`district_name`(str), `total_population`(숫자) 속성을 가진 객체 목록이다.

```python
from detectors import MovingAverageDetector, ZScoreDetector

for detector in [MovingAverageDetector(), ZScoreDetector()]:
    results = detector.detect(records)
    anomalies = [r.to_dict() for r in results if r.is_anomaly]
```

`BaseDetector`가 지역별 정렬과 과거 이력 관리를 맡고, 하위 클래스가
`_evaluate()`에서 판정한다. 결과는 지역 코드·날짜 순으로 반환한다.
`to_dict()`는 API에 전달할 수 있도록 날짜를 문자열로 바꾼다.

- 이동평균: 직전 7일 평균 대비 변동률이 ±10%를 초과하면 이상
- Z-score: 직전 28일 평균·모표준편차 기준 점수의 절댓값이 3을 초과하면 이상
- 당일 값은 기준 계산에서 제외한다. 이력이 부족하면 `is_anomaly=None`이다.
- 날짜가 끊기면 이력을 다시 쌓는다. 평균·표준편차가 0이면 기준값과 다른 값을 이상으로 본다.

## 원본 CSV 결과

25개 자치구 기준이며 서울시 합계는 제외했다.

| 방법 | 평가 건수 | 이상 건수 | 탐지율 |
| --- | ---: | ---: | ---: |
| 이동평균 | 33,425 | 2,627 | 7.86% |
| Z-score | 32,375 | 418 | 1.29% |

원본은 2023-01-01~2026-09-13 자료이며 모든 지역의 2024-02-29가 누락돼 있다.
정답 라벨이 없으므로 탐지율은 정확도를 뜻하지 않는다.
