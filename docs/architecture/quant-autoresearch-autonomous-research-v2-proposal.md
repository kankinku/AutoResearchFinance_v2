# Quant Autoresearch — 자율 연구 엔진 v2 설계 추진안

상태: 2026-10-14 제품 요구 기준 설계안, **일부 기능 미구현**. [20문답 원본 결정](../decisions/2026-10-14-autoresearch-interview-20q.md)을 구현 가능한 요구사항으로 해석한다. 저장소 계약이 보존을 요구하는 기존 `quant-autoresearch-architecture-v1.0.md`를 덮어쓰지 않는다.

## 제품 목표

LLM이 검증된 라이브러리 인디케이터로 조건식·가중치·시장상태 전환을 결합한 매매 알고리즘을 생성하고, 고정된 개발 데이터로 테스트한 후 거래별 원인 분석·가설 수정·후속 세대 연구를 자동 반복한다. 초기에는 무작위 후보도 만들고, 이후 검증된 우수 후보 변이/인과 가설 검증/새 후보 탐색의 배분을 개선한다. 경제적 최종 목표는 실현 가능한 **예상 순수익**. 연구 엔진 완성과 경제적 성과 입증은 서로 다른 제품 단계이다.

```
 Operator: N세대 / 지속 실행, 간결한 완료 보고
        │
        ▼
 Autonomous Research Director (LLM) ← Research Memory / Evidence
  알고리즘 설계, 손실 원인 가설, 연구 우선순위, 후속 실험 설계
        │                                      ▲
        ▼                                      │
 Indicator Registry → Typed AlgorithmPlan     │
  (기존 라이브러리 + 출처 있는 논문 지표)       │
        │                                      │
        ▼                                      │
 Validator → Canonical StrategyIR             │
        │                                      │
        ▼                                      │
 Candidate Generator (random, elite, hypothesis, allocations)
        │                                      │
        ▼                                      │
 Deterministic Backtest + Decision/Fill Trace │
        │                                      │
        ▼                                      │
 Immutable Measurements / Evaluator ──→ LLM Analysis Packet
        │                                      │
        └──── Evidence/Plan Checkpoint ────────┘
                         (Generation N+1)
```

## 타입드 계약 (목표 상태)

### `IndicatorDefinition`
`indicator_id`, source (library/paper), source version/DOI/license, required fields/units, lookback, output shape, publication/availability timing, deterministic implementation hash, verification evidence, `PROPOSED|VERIFIED|QUARANTINED`. 오픈소스의 모든 이름을 검증 완료로 오인하지 않는다. 새 구현은 수치 독립 대조, prefix invariance, 결측·오류, 성능·자원 제한을 통과해야 후보에 사용 가능하다.

### `AlgorithmPlan` → `StrategyIR`
`algorithm_id`, parents, indicator_refs, regime classifier, `branch(condition → sub-strategy)`, rule expression tree, weights, entry/exit/hold, exposure cap, timeframes and execution-delay contracts. LLM은 데이터와 선언적 규칙을 만들며 임의 Python 코드를 신뢰된 엔진에서 바로 실행하지 않는다. 기존 `StrategyIR`에서 지원하지 않는 분기/전환/가중치 로직은 버전 있는 타입드 확장으로만 허용하고 레거시 전략을 깨지 않는다.

### `DecisionTrace` / `FillTrace` / `TradeLifecycle`
`run_id`, `candidate_id`, `decision_id`, `fill_id`, `trade_id`, `symbol`, `signal_asof`, `earliest_execution`, `indicators(name, value, version)`, rules(gate+boolean), selected regime/sub-strategy, decided action/target exposure, actual fill(price/qty/cost), exit reason and realized trade PnL. 무거래 또는 필터로 막힌 상황도 `NO_ACTION`/`BLOCKED`로 구분한다. 결정을 내린 완결봉과 다음 봉 체결을 같은 시각으로 기록하지 않는다. **인과 이유와 추정 원인을 구별**하고 모르는 값은 `UNKNOWN/UNATTRIBUTED`로 표시한다.

### `ResearchHypothesis`
`hypothesis_id`, observed evidence ids, LLM natural-language mechanism, intervention (add/remove indicator, threshold, branch, weight, etc.), control group, protected comparison scope, status `PROPOSED|TESTED|SUPPORTED|REJECTED|INCONCLUSIVE`. 경제적/인과적 주장과 데이터로 관측한 값은 분리한다.

### `GenerationEvidence`
`generation_id`, algorithm/parent hashes, candidate hashes, dataset+cost+executor versions, RNG seed, measured outcomes, tested/rejected hypotheses, completed LLM analysis and validated next plan. 모든 시도(실패 포함)를 보존하고 동일한 의미의 후보와 실험 환경을 식별한다.

## 세대 상태 머신 (목표)

```
NEW → CANDIDATES_CREATED → VALIDATED → EVALUATED
    → TRACE_AND_METRICS_VERIFIED → LLM_DIAGNOSIS_PROPOSED
    → NEXT_EXPERIMENT_PLAN_VALIDATED → GENERATION_COMMITTED
```

*한 세대는 이 흐름 전체.* 중단·타임아웃·모델 응답 손실·원장 불일치는 미완료/실패/재시도 대기 상태이며 '성공 세대'로 집계하지 않는다. 체크포인트의 멱등성과 동일 자원 경쟁 제어가 필요하다.

## 현행 시스템 재사용 / 차이

| 기반 | 존재·재사용 | 미충족 요구 |
|---|---|---|
| `strategy_ir`, `mutation` | 기본 조건/인디케이터/파라미터, 안전한 구조변형 | 복수 하위전략 선택 및 일반 가중치 규칙 |
| `core/features`, `research/indicator_engine` | 폭넓은 지표 카탈로그, 수학 검증 및 일부 연구 전용 지표 | 하나로 연결된 검증된 지표 소비 경로와 연구 중 자동 확장 |
| `core/backtest`, `evaluation` | 체결 내역, 비용, 자산곡선, 위험 평가 | 실행 판단별 지표값/조건/거래ID/손익을 연결하는 완전한 원장 |
| `application/research_batch_service` | 초기 외부 GPT 의도 후 로컬 후보 생성·반복·평가·저장·재개 | **각 세대마다 LLM이 거래와 실패 원인 분석 후 재설계하지 않음** |
| `application/gpt_guided_research_service` | 외부 GPT가 세대별 typed intent를 제출할 수 있는 체크포인트 | **사용자가 자리를 비워도 이어지는 진짜 자율 LLM 루프**와 통합되지 않음 |
| `memory/evidence_*`, `evaluation/local_analyzer` | 불변 기록, 결과·실패 게이트 요약 | 원인 가설과 반증/지표 기여도를 메모리에 구조화해 재사용 |

**주의:** 보호 경계를 변경하지 않는 한 연구용 어댑터에서부터 판단 추적을 구현한다. 현재 핵심 BacktestResult에는 모든 내부 차단 사유가 없어 거래의 **실제** 사유가 불명확한 경우에는 추측해 저장하지 않는다. 전체 체결 원장 도입은 별도 core 변경 검토가 필요하다.

## 데이터·통계·실거래 격리

- 첫 연구는 *공통으로 고정된* 자산/기간을 사용하고, 유망 전략만 다양한 자산/기간으로 확대 검증한다. 고정 데이터에서 사후에 잘 맞는 구간을 찾아 통과시키지 않는다.
- 개발 자료의 반복 연구를 독립 OOS나 PIT 데이터로 간주하지 않는다. 데이터 수정 이력, 기업행동/배당·분할, 체결 비용·유동성, 투입한 가설 수를 기록한다.
- LLM은 연구 **제안자**, 불변 평가 엔진은 **판정자**. OOS 조회, 실거래 주문, 보안 정보 열람, 평가 기준 변경을 허용하지 않는다.
- LLM 연결 방법, 자원 한도, 고정 자산/기간, 평가 상한은 아직 사용자 미확정이며 정책 파일로 별도 관리할 설계 항목이다.

## 최종 3단계 검증

1. **자율 실행**: LLM 생성/분석이 포함된 N=10/100세대, 지속 연구 중단·재개가 실제 작동하고 정확한 증거/계보가 남는지 검증.
2. **진화 능력**: 동일 비용·고정 데이터·시드의 랜덤/기존 규칙 베이스라인 대비 중복 감소, 유망 가설 수, 원인 검증 성공률, 유효 후보 발견 효율의 재현 가능한 차이를 측정.
3. **수익 검증**: 독립 검증 데이터와 다자산/다국면, 수수료·슬리피지·거래량 제약·위험을 고려한 경제적 성과. 연구 성공과 실거래 허가는 구별.
