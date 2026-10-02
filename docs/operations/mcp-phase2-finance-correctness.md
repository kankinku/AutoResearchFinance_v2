# MCP 전환 Phase 2 — 금융 평가 정확성

## 목적

Phase 2는 Phase 0/1의 CLI·MCP·Dashboard 계약을 유지하면서 자동 연구 결과의 금융적 신뢰성을 보강한다. MCP transport, KIS paper/live 경계, Application Service API는 변경하지 않는다.

## 데이터 구역

연구·mutation·candidate evaluation은 `development` 데이터만 사용할 수 있다.

- `development`: research
- `validation`: promotion validation 전용
- `sealed_oos`: promotion gate 전용

기존처럼 validation 데이터를 반복 탐색에 넣는 경로는 차단한다. `require_validation_zone()`과 `promotion_validation` capability를 별도 경계로 두어 후속 promotion pipeline이 명시적으로 사용하도록 한다.

## Timebase

`MarketDataSet`에 `timeframe`과 `calendar` 메타데이터를 추가했다. 기존 파일은 각각 `1d`, `us_equities`로 읽어 하위 호환을 유지한다.

연환산은 더 이상 고정 252를 사용하지 않는다.

- 미국주식 일봉: 252
- 미국주식 intraday: 실제 세션 내 관측 밀도 우선
- 24/7 시장 intraday: timeframe 기준 365일
- 주봉: 52
- 월봉: 12

기존 `1d/us_equities` 데이터의 dataset hash는 예전 방식과 동일하게 유지한다. 비기본 timebase만 hash에 timeframe/calendar를 포함한다.

## 일손실

후처리 risk validation은 intraday bar 하나를 하루로 보지 않는다. equity timestamp를 실제 날짜별로 묶고, 이전 종가에서 해당 일중 최저 equity까지의 손실을 일손실로 계산한다. timestamp가 없는 기존 직접 호출에는 기존 bar 기반 fallback을 유지한다.

## Robustness

이전 구현의 두 문제를 제거했다.

1. DSR observation 수에 `Metrics` 필드 개수를 넣지 않고 실제 equity return observation 수를 사용한다.
2. 계산한 robustness를 별도의 `robust_score()`로 다시 덮어쓰지 않는다.

CPCV는 후보의 실제 return path에서 held-out compounded return을 만들어 stability evidence로 사용한다.

PBO는 더 이상 fast/full/stress 세 숫자를 비교하지 않는다. 동일 세대의 후보군을 CSCV로 분할해 인샘플 최우수 후보가 아웃오브샘플 후보군의 하위 절반으로 내려가는 비율을 계산한다. 후보가 하나뿐이거나 관측치가 부족하면 PBO는 `None`으로 남겨 증거 부족을 명시한다.

DSR/PBO는 최종 robustness score에 반영되고 Evidence 및 dashboard ledger에도 선택적 필드로 기록된다.

## Temporal validation

기존 구현은 train 구간에서 candidate fitting/selection을 수행하지 않았으므로 엄밀한 walk-forward optimization이 아니었다. 동작은 유지하되 증거 명칭을 `temporal_holdout`으로 바로잡고 각 fold에 `selection_applied=false`를 기록한다.

실제 train→candidate selection→test 방식의 walk-forward optimization은 Phase 3/4의 통합 search pipeline에서 구현할 수 있도록 현재 의미를 과장하지 않는다.

## 호환성

다음 외부 계약은 유지한다.

- CLI 24개 서브커맨드
- 기존 MCP Tool 10개 및 schema
- Dashboard HTTP 경로
- Strategy IR 공개 구조
- Application Service 표면
- KIS paper/live 안전 경계
