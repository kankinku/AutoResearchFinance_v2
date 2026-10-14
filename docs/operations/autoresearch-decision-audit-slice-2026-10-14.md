# S1 + S2 일부 구현: 매매 판단 근거 추적 / 2026-10-14

참조: [20문답 요구사항](../decisions/2026-10-14-autoresearch-interview-20q.md) 9·11·18번, [자율 연구 로드맵](autoresearch-implementation-roadmap-2026-10-14.md).

## 이번 구현 (개발 브랜치, 연구 전용)

`research/indicator_engine/decision_audit.py`가 기존 `compile_research_hypothesis → evaluate_compiled_development → core.backtest.BacktestEngine` 흐름을 그대로 실행하고, **기존 코어를 수정하지 않은 채** 다음 구조화 데이터를 생성한다.

1. 매 완료봉의 `DecisionObservation`: `decision_id`, 시각, 다음 거래 가능 시각, 지표값, 진입/레짐 조건의 평가, 매매 의향, 필터링/워밍업/보유/무진입 상태.
2. 실제 체결과 연결한 `FillObservation`: `fill_id`, 왕복의 `trade_id`, 원래의 `decision_id`, 체결 시각/가격·수량·비용. 신호가 생긴 봉과 그다음 봉의 시가 체결 시점을 구별한다.
3. 청산된 포지션의 `ClosedResearchTrade`: 진입/청산 체결 연결, 수수료 포함 왕복 실현손익; 마지막에 열린 포지션은 실현손익을 임의로 생성하지 않는다.
4. LLM용 **객관 측정 패킷**: 자산곡선으로 계산한 수익률/CAGR/MDD/Sharpe/Sortino/승률/손익비 등, 한정된 체결 예시의 실제 신호값·조건 결과·체결 원장, 손실 사례의 진입·청산 결정 ID 및 지표값. `causal_claim=NOT_ESTABLISHED`, `hypotheses_tested=0`으로 표시한다.

### 격리·실패 방식

- `DEVELOPMENT`만 허용, Sealed OOS 차단, `candidate_promotable=false`, 실거래 권한 없음.
- **두 개의 검증된 이진 지표**를 조합하는 기존 연구용 StrategyIR 어댑터에만 적용. 복잡한 전략/손절/추가 인디케이터 등의 체결 사유를 지원하는 것처럼 보이게 하지 않는다.
- `StrategyIR`·계산 벡터의 무결성을 기존 평가기에 다시 확인한다. 모든 실제 체결은 바로 전 완결봉의 관측값과 다음 봉 시가 체결을 연결해야 한다. 연결 불가능한 체결·조건은 명시적 오류다.
- 지표 미준비, 레짐 필터, 조건 미충족, 보유, 실행된 요청을 분리하지만 **반사실 손익과 인과적 실패 원인은 산출하지 않는다**.
- 패킷은 안전하게 제한된 체결 예시만 포함한다. 전체 원장을 저장·조회하는 컨트롤러 API/LLM 자동 계획 기능은 미구현이며, 추후 S2·S4에서 연결한다.

## 실제 역사 데이터 읽기 전용 스모크 (후보 수익성 인증 아님)

- 사용 데이터: 기존 Tiingo의 QQQ 2020-01-02~2025-12-31 **1,508개 일봉**, latest-revision / **NON-PIT**.
- 관측 전략: 학술 연구용 time-series momentum + SMA direction 2지표 조합.
- 감사 결과: **1,508개 의사결정 레코드, 11건의 실제 체결, 청산된 왕복 거래 5건**.
- 실제 거래 ID와 직전 완결봉 지표값을 연결한 예: 2020-12-31 신호 (`time_series_momentum=1`, `sma_direction=1`) → 2021-01-04 시가 **315.11달러** 매수. 해당 값은 전략의 당시 판단 입력이지, 그것이 경제적 성과의 원인이라는 주장이 아니다.
- 결정론적 원장 해시: `4b2453ed45fcef79c701353f0075f0ab89246c72b72736a4b6ac6038a57d3563`.
- 전체 기간 개발용 평가액은 시장·지표 검증을 위한 재현 데이터일 뿐, OOS·독립 가격 소스·수익성 검증으로 취급하지 않는다.

## 다음 실제 작업

S2의 **실험·손실·환경별 분석에 충분한 구조화된 LLM 입력**과 S3의 **다중 분기·가중치 AlgorithmPlan 표현**을 결합해야 한다. 그 이후 S4에서 `application/gpt_guided_research_service`/배치 체크포인트를 재사용해 **매 세대 외부 LLM의 새로운 진단·계획을 자동 실행**하는 연구 컨트롤러를 완성한다. 그 전까지 이 작업을 '20문답의 자율 연구 엔진 완료'로 표시하지 않는다.

## 검증 및 배포 경계

- 단위 검증: 결정 기록·체결의 직전 봉 연결, 거래 식별자, 워밍업/필터링, 왕복 실현손익, future-candle prefix 불변성, Sealed OOS 차단, 전략·지표벡터 변조 거부.
- 실제 QQQ 1,508봉에서 백테스트 원본 체결 11건 모두 신호값·비용·결정 ID와 연결되고, 검증용 해시가 결정론적으로 생성됨.
- `pytest -q -p no:cacheprovider`: **1,289 passed, 0 failed**, 393.84초. 전체 `ruff check .` 및 `mypy .`도 통과.
- 기능 활성화는 `audit_compiled_academic_decisions(...)`를 명시적으로 호출할 때만 가능. 운영 서비스·기존 배치의 기본 동작, 데이터 원본, 복구 브랜치, 실거래/Sealed OOS 권한에 변경 없음.
- 실제 LLM 자율 연구 루프, 20문답 전체 제품 완성, 독립 OOS 검증, 수익 우위는 **완료되지 않음**.
