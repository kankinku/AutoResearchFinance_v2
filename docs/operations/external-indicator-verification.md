# 외부 인디케이터 이식 검증 기록

검증 기준일: 2026-09-02

## 범위

다음 네 저장소를 고정된 커밋으로 감사하고, 제품 런타임에는 저장소를 의존성으로 설치하지 않은 채 순수 Python 계산기로 재구현했다.

| 저장소 | 감사 커밋 | 라이선스 | 적용 방식 |
| --- | --- | --- | --- |
| [marketcalls/pyindicators](https://github.com/marketcalls/pyindicators) | `93503d78db776b50a2777186202cb94c82ea5dc0` | MIT | 파생 구현 |
| [srlcarlg/srl-python-indicators](https://github.com/srlcarlg/srl-python-indicators) | `25e5dfaaa8fa0aba36dc7b24490fdfd5cdffaf29` | Apache-2.0 | 파생 구현 |
| [chironmind/CentaurTechnicalIndicators-Python](https://github.com/chironmind/CentaurTechnicalIndicators-Python) | `76ecbe515206206b0268d7ef0cebd9585bb09839` | MIT | 파생 구현 |
| [kshlgrg/pythonpine](https://github.com/kshlgrg/pythonpine) | `49dd6f9fad70b76848c1ca2ffedf3d10c4e66f98` | AGPL-3.0 | 원본 미복사 독립 재구현 |

주문·계좌·네트워크·다운로더·시각화 코드는 이식 대상에서 제외했다. 프로파일, 오더플로우, 세션 데이터가 필요한 기능은 해당 데이터 계약이 없으면 계산하지 않는다.

## 현재 카탈로그

`imported_feature_catalog()` 기준 결과는 다음과 같다.

| 항목 | 수량 |
| --- | ---: |
| canonical FeatureSpec | 159 |
| alias | 31 |
| 명시적 smoothing variant | 2 |
| scalar OHLCV | 147 |
| specialized 계약 | 12 |
| duplicate semantic group | 0 |
| QUARANTINED | 0 |
| 미실패 등록 항목 | 159 |

alias는 이름만 다른 동일 계산을 하나의 canonical 계산으로 연결한다. RSI의 기본·Wilder·EMA처럼 계산 방식이 실제로 다른 경우는 variant로 분리한다.

## 데이터와 시간축

- `US2Y`, `US10Y`, `US20Y`, `JP2Y`, `JP10Y`, `JP20Y`, `KR2Y`, `KR10Y`, `KR20Y`를 선택형 외부 시계열로 지원한다.
- 모든 시계열은 `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo` 변환 경로를 공유한다.
- 주봉·월봉은 완료된 봉만 사용하고, `available_at`이 신호 시각보다 늦은 관측은 as-of 정렬에서 제외한다.
- 금리·VIX·금·DXY·ETF·다른 종목의 값도 동일한 `SeriesRef → FeatureTransform → FeatureSpec` 경로로 조합한다.

## 검증 결과

다음 명령을 worktree에서 실행했으며 모두 통과했다.

```text
python -m pytest -q
340 passed

ruff check .
All checks passed!

python -m mypy .
Success: no issues found in 107 source files
```

추가로 카탈로그 전체 scalar 항목을 선언된 입력명으로 순회 계산했고, 전문화 항목은 `profile`, `order_flow`, `session` 계약별 테스트로 계산 경로를 확인했다.

## 운영 경계

이번 변경은 전략 연구·백테스트용 Feature Registry와 대시보드 카탈로그만 확장한다. 모의투자·실전투자 주문 게이트, 계좌 연동, LLM 연결, OOS 봉인 데이터 정책은 변경하지 않았다. 등록된 인디케이터가 자동으로 전략에 선택되거나 주문을 실행하지 않으며, 전략 IR에서 명시적으로 선택된 경우에만 백테스트 입력으로 사용된다.
