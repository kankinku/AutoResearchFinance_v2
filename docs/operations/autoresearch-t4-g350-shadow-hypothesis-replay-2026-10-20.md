# Quant AutoResearch — G350 기반 계승 수정안 실측 (격리 재생)

**2026-10-20 KST | T4 | Q02/Q06/Q07/Q08/Q09/Q17/Q18/Q20**

**판정: 두 GPT 설계 수정안 모두 기존 부모보다 손익과 위험 측면에서 개선되지 않았음. 정식 G351/G352 미생성. 운영 배포 및 실주문 없음.**

## 범위와 출처

기존 메인 Quant AutoResearch를 새로 만들지 않고, 2026-10-20 코드 SHA `c8e21b6`의 첫 S7 부모 연결 기능을 검증한 후 **실제 과거 350세대 데이터와 동일한 QQQ RAW 개발 데이터**를 이용해 두 개의 GPT 작성 `ResearchIntent`를 시험했다.

원본 DB: `/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory/state/moon-http/research/academic-gpt-checkpoints` (원본 읽기 전용).
실험용 격리 복제: `/shared/moon-state/t4-inheritance-shadow-uwpu4sxv/academic-gpt-checkpoints`. 원본 SQLite `backup` API로 `gateway.sqlite`, `cycles.sqlite`, `catalog-s6-v2.sqlite` 복제. 임시 **복제본에만** 세션 목표를 352로 열었으며, 운영 원본은 `COMPLETED 350/350` 그대로다.

출발 부모는 기존 G262의 S7에서 정밀 재생·선정된 StrategyIR:
- G262 원본 Evidence SHA `bc3fccb5a9f6805ec44c81cfdef6ed1a83c01bfb5dfec46d1f882745231d3cb0`
- 선택 부모 StrategyIR SHA `23f6365f34e8a34e5ff6884f05db0e2ef90e1f3b7367b5a192aaee1d1fc2070c`
- selection SHA `1b0e217d66858bf6f320168cf990e785caf65bdb504e756af4429b8b87d4eddf`
- QQQ 개발 데이터 SHA `328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6`
- 기존 부모: `entry = plan_entry > 0.5 AND dual_sma_trend_50 > 0.5`; `exit = plan_entry <= 0.5`. 단일 QQQ 현금 long/flat, 동일 canonical next-open 거래/비용.

원본 측정값 및 전략 해시의 기계 판독 기록: [격리 후보 2건 측정 JSON](evidence/quant-validation-20261020/t4-g350-shadow-two-hypothesis-measurements.json).

## 실제 GPT 가설 및 독립 백테스트

| 수치 | 원래 부모 | 수정안 A: 청산 유예 | 수정안 B: EMA 진입 확인 |
|---|---:|---:|---:|
| **비용 반영 누적수익률** | **+74.5916%** | +56.5717% | +54.3206% |
| **전체 구간 MDD** | **6.0014%** | 11.3773% | 6.4639% |
| Sharpe | 1.1481 | 0.7683 | 0.9568 |
| 체결 수 | 108 | 79 | 78 |
| 추산 청산 거래 | 54 | 39 (79 fills, 미청산 마지막 포지션 가능) | 39 |
| 실행 비용 | $1,173.57 | $775.31 | $792.55 |
| 새 StrategyIR SHA | 원본 위와 동일 | `e78023d3aa99c0f6ec46e55853affec0a29e67dc6044f6fc93bf84f24de5b6d4` | `24724b2b066673080728fd356338ff2bc0efe4105fd858ec413b2f4ca9fb9693` |
| 거래 시퀀스 실제 변경 | — | YES | YES |
| 부모 승격 검토 | 기존 부모 유지 | **개선 미충족** | **개선 미충족** |

**A (실패 가설):** 현재 청산은 `plan_entry <= 0.5`로 한 번의 분기 진입 신호 해제에 민감할 수 있다. 단일 구조 변경으로 `exit.conditions.0`을 `plan_vote_score <= 0.45`로 대체, 부분 신호 훼손에도 포지션을 유지하면 불필요한 청산을 줄일 수 있다는 가설을 시험했다. 실제로 비용과 체결은 감소했지만 수익률 **−18.02%p**, MDD **+5.38%p**로 악화. 큰 손실 하나는 exit 점수 0.267까지 하락한 뒤 청산. 비용 절약만으로 개선이라고 판단하지 않는다.

**B (A의 부정적 결과를 참고한 대체 가설):** 기존 G262 부모의 손실 거래 `23f6365f34e8-T-000088`은 단기 EMA 방향 0인데도 이중 SMA 및 모멘텀 신호가 양수인 진입이었다. 청산 정책은 원래대로 유지하고 `entry.conditions`에 `ema_direction_20 > 0.5`를 추가했다. 진입 확인을 늘리는 것이 조기 손실을 줄일 수 있다는 가설이었으나, 비용은 줄었지만 수익률 **−20.27%p**, MDD는 **+0.46%p**로 악화. 진입 기회를 지나치게 제한했을 가능성은 추가 가설일 뿐 확정 원인은 아님.

두 변경은 각각 **원래 선정된 G262 부모**와 같은 개발 바·가격·비용·고정 자본에서 비교했다. A가 부모로 확정되지 않았으므로 B를 A의 공식 계승 자식이라고 부르지 않는다.

## 검증된 경계 / 차단 항목

- **PASS**: 기존 운영 350/350/COMPLETED, G350 Evidence `26647e424913125cee1ec1dd6333538938237fb7205f7fc5147519b9c6cb725d` 불변. 복제본은 요청만 352/350, AWAITING_PLAN, 총 기록 350행. 선택된 G262 부모가 재생 가능하며 부모 StrategyIR/결정/체결/비용 실측 일치. Python 추론으로 고친 숫자 아닌 실제 `audit_inherited_decisions`·`evaluate_compiled_development` 비용 반영 결과 사용. 이전에 검증된 부모 계승 관련 회귀 Pytest 9 PASS.
- **BLOCKED**: 정식 `submit_algorithm_plan` 제출 시 실행 환경의 안전 게이트가 요청을 차단. 따라서 S2 제출/진단/S7의 **영구 원장 커밋은 실행되지 않았다**. 수정안 A/B는 실제 backtest를 거친 **shadow counterfactual 연구**일 뿐 `G351/G352` 정식 세대가 아니다. 안전 게이트 우회 시도 금지.
- **NOT RUN**: 실제 운영 코드 배포 및 OAuth/MCP 원래 URL 호환 점검, 정식 351→352 연속 GPT 세대, GPT 무인 자율성, 신규 지표/수학식의 운영 사용, PIT/OOS 및 경제적 수익성 검증. 주문·브로커 접근 **없음**.

## 다음 작업

실험 제출 경로가 정상적으로 허용되는 연구 전용 세션에서 안전한 테스트와 운영 MCP 배포·원장 백업·복구를 먼저 확인한다. 그런 다음 **G350 → G351(실제 GPT-authored inherited intent → costed S2 → GPT 진단 → S7) → G352(재선정 부모 기준 새 구조 가설)**을 실제 세대 증거·부모 선택 해시로 연속 검증한다. 현재 개발 데이터 상에서는 **G262 부모를 유지하고 A/B 모두 채택하지 않는다**. 원래 20문답/단계 V05→T4→V01~V04→V06→V07, 기존 MCP/OAuth, 보호 코어, 실거래 OFF 불변.
