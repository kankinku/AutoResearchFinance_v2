# Quant AutoResearch P1-2 — 범용 유한 상태·이벤트 표현 기능

**기준 2026-10-19 KST · P1-2 범위 내 격리 구현 `ISOLATED_IMPLEMENTATION_PASS` · P1 전체 `PARTIAL` · 운영 `NOT_DEPLOYED`**

## 작업 계약

- **작업 ID:** P1-2 (기존 T4의 Q05/Q10/Q11/Q12/Q18 보조 기능); 기존 사용자 20문답·[확정 순서](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md) `V05 → T4 → V01~V04 → V06 → V07` 불변.
- **목표:** 고정된 Pine 전략을 이식하는 대신 LLM이 장차 임의의 지표 이벤트 이후 상태를 기억하고, 순서가 있는 조건 분기, 만료·초기화·재진입 규칙으로 알고리즘을 표현할 수 있는 범용 typed primitive 제작.
- **구현 경계:** 개발·합성 데이터만. 기존 StrategyIR v1, AlgorithmPlan/WeightedVote, QQQ 개발 연구 세대 및 백테스트·비용·무결성·봉인 OOS·MCP URL/OAuth·실거래 OFF 불변. 임의 Python/Pine 코드 실행/무제한 반복/원본 특정 전략 추천 없음.

## 실제 구현

1. [`research/indicator_engine/state_machine_ir.py`](../../research/indicator_engine/state_machine_ir.py):
   - `StateDefinition`, `StateTransition`, `StateMachinePlan`, `CompiledStateMachine`, `StateTrace` — 엄격한 데이터 계약. P1-1 `Expression`의 boolean guard 및 중첩 논리/수식 재사용. 새 중복 계산 엔진 만들지 않음.
   - **봉 t마다 최대 1회 전이**. 해당 봉 종가에 확정된 상태·이벤트·0/1/unknown 신호를 저장하고 주문은 생성하지 않음. State 기반 연속 신호 또는 지정된 Transition 기반 단일 이벤트 신호 중 하나만 선택.
   - 우선순위: `reset_when` → 현재 상태의 `timeout_bars/timeout_to` → 현재 상태에서 선언 순서 첫 번째 참 조건. Unknown active guard/reset은 false로 바꾸지 않고 신호를 `None` 처리하고 상태를 보존. 비활성 상태 guard의 값은 해당 봉의 결정을 바꾸지 않음.
   - 정적 graph type/ID/transition target/중복/발화 target 검증. **최대 12 상태·24 전이·합계 192 expression 노드**, P1-1의 64노드/8깊이/500 과거봉·20,000 데이터 봉 상한 계승. `timeout_bars` 최대 500; 해시 및 시점별 결정 기록으로 재현성을 확보.
   - `compile_state_machine`, `evaluate_state_machine`, `state_signal_vector`. 연구 전용 `development_state_signal_vector`는 검증 경계에서 **DEVELOPMENT / us_equities / 1d / 단일 종목 / 원시 OHLCV**만 허용; 외부·미검증·봉인 시계열 차단. 산출값은 테스트에서만 이전 `StrategyIR`의 제공된 feature 벡터로 연결.
2. [`research/indicator_engine/expression_ir.py`](../../research/indicator_engine/expression_ir.py): 선언된 source가 하나도 없는 순수 상수 표현식도 **명시한 `bar_count`가 있을 때만** 안전하게 유한 개 봉으로 평가하도록 작게 확장. 기존 호출 시그니처/동작 유지.
3. [`tests/research/test_state_machine_ir_p1.py`](../../tests/research/test_state_machine_ir_p1.py):
   - **ARM→CONFIRM→FIRE**, 상태 유지와 재무장, 만료 vs 확인 경합, reset 우선권, 다중 guard 우선순위, 결측 fail-closed, 조건의 미래값 변조 거부, prefix-by-prefix 동일성, graph 손상·잘못된 source type·해시 조작·과도한 비용·봉인 OOS 차단.
   - synthetic data에서 **상태 이벤트 signal → 기존 StrategyIR feature_values → 비용 반영 canonical `BacktestEngine`** 테스트. 해당 봉 신호가 다음 봉 시가에서만 체결됨을 모든 체결에 대해 확인. 새 operator를 실제 자동 GPT 연구 후보에서 사용할 수 있다고 선언하지 않음.

## 검증 결과

- 관련 P1/P0/AcademicPlan/IntentBridge/ScopeLock **104 Pytest PASS / 0 FAIL**.
- 전체 Ruff **PASS**. 전체 MyPy **283 Python source PASS**. `git diff --check` **PASS**.
- **전체 Pytest NOT RUN** (P1-2 범위). 실제 GPT 10/100세대 자동 연구 **NOT RUN**. 벤더 PIT/OOS, 자산별 실수익, TradingView 동등성, 브로커/주문, 신규 공식 정식 세대 **NOT RUN**.
- **기능 커밋:** `60e2e83`, `feat/quant-same-session-350-20261019`, GitHub origin **PUSH PASS**.
- 운영 배포 **0**, 원본 350세대 변경 **0**, 기존 MCP URL/OAuth 및 실주문 OFF 변경 **0**.

## 남은 작업 / 우선순위

- 격리 상태기계만 구현됨. LLM-facing typed proposal, mutation/승계와 Feature Registry/S3 연구 provider를 거쳐 **실제 연구 세대에 사용 가능해지는 통합은 아직 미완료**. 유한 상태 외 동적 Position/Order policy 표현·실제 intrabar 체결은 P3 보류.
- **다음 고정 제품 단계:** T4 실제 연결 GPT/동일 연구예산 random 기준 10→100세대 진화 및 운영·복구 게이트 확인. 이번 기능의 통합이 이 작업을 무기한 늦춰서는 안 된다.
- **다음 범용 기술 단계 후보:** P1-3 안전한 신규 AST·상태 계획 등록 및 GPT Plan/StrategyIR test-only 통합(기존 v1 replay·hash 불변 확인); 기존 기능과 충돌하거나 sealed OOS/라이선스 없는 feature로 연결될 경우 fail closed. Pine 런타임/전용 카탈로그 추가는 진행하지 않음.
