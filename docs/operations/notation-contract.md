# 시스템 표기·지시문 계약

이 문서는 Strategy IR, Codex/Mimir 연구 루프, CLI, 대시보드가 공유하는 유일한 표기 기준이다.
새 기능은 이 문서의 용어와 형식을 사용해야 하며, 별도 별칭을 추가하지 않는다.

## 기준 용어

| 대상 | canonical 표기 | 의미 |
| --- | --- | --- |
| 전략 원본 | `Strategy IR` | 전략의 유일한 기준 표현. Python/Lean은 생성 산출물이다. |
| 지표 정의 | `FeatureSpec` | Registry에 등록되어 계산 가능한 지표·외부 시계열 특성 |
| 지표 선택 | `FeatureRef` | 전략이 실제로 사용할 지표와 시간봉·lag·lookback |
| 기존 지표 | `IndicatorSpec` | 전략 IR의 내장 인디케이터 정의 |
| 기준 자산 | `QQQ` | 동일 기간 전략 CAGR 비교의 주 벤치마크 |
| 보조 기준 | `NASDAQ` | 참고용 Nasdaq Composite 비교 |
| 모의 운용 | `Paper-only` / `모의투자` | 현재 주문 경계. 실전 주문은 연구 루프에서 금지 |

## 시간봉·지연 표기

허용 시간봉은 `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo`뿐이다. 화면에서는 각각
1분봉, 5분봉, 15분봉, 1시간봉, 일봉, 1주봉, 1개월봉으로 표시한다. 다른 종목이나 금리도
동일한 `FeatureRef(timeframe=..., lag_bars=..., lookback=...)` 형식으로 표현한다.
`lag_bars`는 미래값 방지를 위한 지연이고 `lookback`은 계산 창이다.

## ResearchIntent 출력 규칙

Codex는 반드시 하나의 `ResearchIntent` JSON만 반환한다.

- 연산자는 `cross_above`, `cross_below`, `less_than`, `less_equal`, `greater_than`,
  `greater_equal`, `equal` 중 하나만 사용한다.
- 경로는 Strategy IR 기준 점 표기만 사용한다. 예: `entry.conditions.0`,
  `exit.conditions.1`, `features.vix_rsi`, `indicators.sma_fast`, `risk.stop_loss_pct`.
- `ADD_RULE`·`ADD_REGIME_FILTER`는 `condition` 객체를 사용한다.
- `ADD_FEATURE`는 `features.<alias>`와 등록된 `FeatureRef`를 사용한다.
- `ADD_INDICATOR`·`SWAP_INDICATOR`는 `indicators.<alias>`와 `IndicatorSpec`을 사용한다.
- `SET_PARAMETER`는 scalar 값 하나만 사용한다.
- JSON Patch의 임의 `add`·`replace`·`remove`, 슬래시 경로(`/...`), 대괄호 경로(`...[0]`)는
  출력에서 금지한다. 과거 기록을 읽는 호환 경계에서만 canonical 점 표기로 변환한다.
- 파일 수정, Python 코드, evaluator 변경, credential 접근, 주문 제출을 지시하지 않는다.

## 평가 표기

`QQQ CAGR delta`는 `전략 CAGR - 동일 기간 QQQ CAGR`이며 단위는 퍼센트포인트다.
따라서 `0.10`은 `+10%p`로 표시한다. 절대 수익률, QQQ/NASDAQ 비교, 위험·강건성,
비용, 워크포워드, 완료 연도의 거래수·수익률은 서로 대체하지 않고 모두 기록한다.
완료 연도별 거래수 gate는 `31회 이상 통과`로 표기한다(`30회 이하는 탈락`).

## 상태 표기

내부 상태 코드는 대문자 enum을 유지하고 사용자 화면은 공통 한국어 라벨을 사용한다.
예: `ONLINE=온라인`, `OFFLINE=오프라인`, `STALE=응답 지연`, `CONNECTED=연결됨`,
`VALIDATED=검증 완료`, `FAILED=실패`, `NOT_AVAILABLE=미연결`.

이 계약을 변경할 때는 공통 상수, LLM 지시문, 입력 검증, 활성 대시보드, 테스트, 이 문서를
같은 변경으로 갱신한다.
