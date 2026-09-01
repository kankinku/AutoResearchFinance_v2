# QUANT AUTORESEARCH HARNESS — FINAL ARCHITECTURE v1.0

## 0. 시스템 정의

목표:

> 여러 출처에서 확보한 실제 투자 전략을 구조화하여 저장하고, 전략 간 조합·조건 변경·매개변수 탐색을 자동 수행한 뒤, 대량 병렬 백테스트와 견고성 검증을 통해 더 우수한 전략을 지속적으로 탐색한다.

최상위 원칙:

```text
LLM      = 생각한다.
LOCAL    = 수정한다.
WORKER   = 실행한다.
EVALUATOR= 판정한다.
MEMORY   = 기억한다.
```

LLM이 매 후보의 Python 코드를 직접 수정하지 않는다.

LLM은 오직:

* 결과 해석
* 연구 가설 생성
* 탐색 방향 결정
* 전략군 조합 방향 결정
* 새로운 Primitive가 필요한지 판단

을 담당한다.

실제 전략 변경·후보 생성·파라미터 탐색·백테스트·통계 계산은 로컬 시스템이 수행한다.

이는 첨부한 autoresearch 적용안의 핵심인 `Agent = 연구 선택 / Local Runtime = 수정·실행 / Evaluator = 불변 판정 / Memory = 연구 축적` 구조를 최종 설계의 중심 원칙으로 채택한 것이다.

---

# 1. 최종 전체 아키텍처

```text
                        HUMAN
                          │
                          ▼
                research_program.md
                research_policy.yaml
                          │
                          ▼
               ┌────────────────────┐
               │  RESEARCH DIRECTOR │
               │        LLM         │
               └─────────┬──────────┘
                         │
                 Research Intent
                         │
                         ▼
               ┌────────────────────┐
               │ EXPERIMENT PLANNER │
               │       LOCAL        │
               └─────────┬──────────┘
                         │
                  Experiment Batch
                         │
                         ▼
             ┌─────────────────────────┐
             │ STRATEGY MUTATION ENGINE│
             │          LOCAL          │
             └────────────┬────────────┘
                          │
                    Candidate Pool
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
      Parameter Search          Structure Search
      Grid / Random /           Add / Remove /
      Bayesian(Optional)        Replace / Crossover
             │                         │
             └────────────┬────────────┘
                          ▼
                  Candidate Validator
                          │
              duplicate / invalid 제거
                          │
                          ▼
                    JOB SCHEDULER
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
         WORKER 01     WORKER 02    WORKER N
             │            │            │
         Lean Docker   Lean Docker  Lean Docker
             │            │            │
             └────────────┼────────────┘
                          ▼
                IMMUTABLE EVALUATOR
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
     Performance      Robustness       Integrity
                          │
                          ▼
                    RESULT STORE
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
        Champion       Frontier      Rescue Pool
            │             │             │
            └─────────────┼─────────────┘
                          ▼
                  KNOWLEDGE ENGINE
                          │
                 Compact Summary
                          │
                          ▼
                  RESEARCH DIRECTOR
                          │
                          └── Generation N+1
```

---

# 2. 기존 KIS에서 그대로 유지할 부분

기존 `open-trading-api/backtester`는 버리지 않는다.

다음 기능을 그대로 기반으로 사용한다.

### Strategy Definition / YAML

현재 `.kis.yaml`은 이미:

```text
parameters
indicators
entry
exit
risk
```

를 구조화하고 있다.

예를 들어 SMA 전략은 `fast_period`, `slow_period`, `cross_above`, `cross_below`, 손절·익절 등을 데이터 구조로 표현한다.

따라서 이것을 확장하여 `Strategy IR`의 기반으로 사용한다.

### Parameter Optimizer

기존에는 이미:

```text
ParameterGrid
Grid Search
Random Search
ResultAggregator
```

가 존재한다.

이를 폐기하지 않고 새 Research Harness의 `Parameter Search Engine`으로 편입한다.

현재 `ParallelExecutor`는 명칭과 달리 Docker 자원 제약 때문에 실제로는 순차 실행하고 있으므로, 이 부분만 Worker Pool 구조로 교체한다.

### Lean Executor

현재 각 백테스트는 Docker로 격리되고:

```text
Algorithm → read only
Data      → read only
Results   → worker output
```

형태로 실행된다.

병렬 처리에 적합하다.

### LeanProjectManager

실행마다 UUID가 포함된 고유 `run_id`와 별도의 프로젝트 디렉터리를 생성하므로 서로 다른 실험의 결과 충돌을 방지할 수 있다.

---

# 3. Strategy IR을 Single Source of Truth로 확정

Python 코드가 전략의 원본이 되어서는 안 된다.

Canonical Strategy는 다음과 같은 구조화 데이터다.

```yaml
strategy:
  id: S001923
  family: momentum
  generation: 28

  parents:
    - momentum_014
    - volatility_009

indicators:

  fast:
    type: EMA
    period: 12

  slow:
    type: EMA
    period: 40

  rsi:
    type: RSI
    period: 14

entry:

  logic: AND

  conditions:

    - op: cross_above
      left: fast
      right: slow

    - op: less_than
      left: rsi
      value: 38

exit:

  logic: OR

  conditions:

    - op: cross_below
      left: fast
      right: slow

    - op: greater_than
      left: rsi
      value: 72

risk:

  stop_loss_pct: 4.0
  take_profit_pct: 12.0
  trailing_stop_pct: null

research:

  mutation:
    - M193
    - M228

  parent_score: 0.712
```

흐름은:

```text
Strategy IR
    ↓
Validator
    ↓
Compiler
    ↓
Lean Python
    ↓
Backtest
```

이다.

생성된 Python은 artifact일 뿐 전략 원본이 아니다.

---

# 4. Mutation Engine

LLM이 코드를 고치는 대신 미리 정의된 연산으로 전략을 변경한다.

핵심 Operation:

```text
SET_PARAMETER

ADD_RULE
REMOVE_RULE
REPLACE_RULE

ENABLE_RULE
DISABLE_RULE

CHANGE_AND_OR

ADD_INDICATOR
REMOVE_INDICATOR
SWAP_INDICATOR

CHANGE_ENTRY
CHANGE_EXIT

CHANGE_STOP
CHANGE_TAKE_PROFIT
CHANGE_TRAILING_STOP
CHANGE_POSITION_SIZE

ADD_REGIME_FILTER
REMOVE_REGIME_FILTER

CROSSOVER
COMBINE_STRATEGY
```

예:

```json
{
  "parent": "S001923",
  "operations": [
    {
      "op": "SEARCH_PARAMETER",
      "path": "entry.rsi.value",
      "min": 30,
      "max": 42,
      "step": 2
    },
    {
      "op": "ADD_REGIME_FILTER",
      "template": "adx_trend"
    }
  ]
}
```

LLM은 이 정도만 출력한다.

로컬 시스템은 자동으로:

```text
RSI 30
RSI 32
RSI 34
RSI 36
RSI 38
RSI 40
RSI 42

× ADX 15
× ADX 20
× ADX 25
× ADX 30
```

후보를 생성한다.

LLM 호출 1회로 수십~수천 번의 실험을 만들 수 있다.

---

# 5. Strategy Library

모든 수집 전략을 바로 연구 대상으로 넣지 않는다.

```text
strategies/
├─ primitives/
├─ templates/
├─ imported/
├─ normalized/
├─ generated/
└─ champions/
```

### imported

외부에서 확보한 원본 전략.

예:

```text
PineScript
Backtrader
Python
논문
블로그 전략
GitHub 전략
```

### normalized

분석 후 Strategy IR로 변환된 전략.

### primitives

재사용 가능한 최소 전략 구성 요소.

예:

```text
SMA cross
EMA cross
RSI
MACD
ATR
ADX
Bollinger
Volume breakout
52-week high
Volatility filter
Regime filter
Stop logic
Position sizing
```

새 Primitive 생성만 LLM 코딩을 허용한다.

한 번 등록한 Primitive는 이후 로컬 Mutation Engine이 무제한 재사용한다.

---

# 6. 병렬 실행 구조

기존 순차 Optimizer를 다음 구조로 변경한다.

```text
Candidate Generator

        ↓

     Job Queue

        ↓

 Resource Manager

        ↓

┌────────┬────────┬────────┬────────┐
│Worker 1│Worker 2│Worker 3│Worker 4│
└───┬────┴───┬────┴───┬────┴───┬────┘
    │        │        │        │
   Lean     Lean     Lean     Lean
 Docker   Docker   Docker   Docker
    │        │        │        │
    └────────┴────┬───┴────────┘
                 ↓
             Result Queue
```

Worker 수는 고정하지 않는다.

Resource Manager가:

```text
CPU 사용률
RAM 여유
Docker 사용량
평균 Backtest 비용
Queue 길이
```

를 기준으로 동시 실행 개수를 제한한다.

기본 구조:

```text
async Job Scheduler
+
Process Workers
+
Docker Lean
```

을 사용한다.

Ray/Celery 같은 무거운 분산 시스템은 초기 버전에는 사용하지 않는다.

---

# 7. 데이터 공유 방식

시장 데이터는 Worker마다 복사하지 않는다.

```text
shared DATA
      │
      ├── worker01 : read-only
      ├── worker02 : read-only
      ├── worker03 : read-only
      └── worker04 : read-only
```

결과만 독립시킨다.

```text
runs/

E000001/
E000002/
E000003/
E000004/
```

따라서 여러 Lean Docker 컨테이너가 동시에 동일한 역사 데이터를 읽으면서 별도 결과를 생성한다.

---

# 8. Candidate Cache

모든 실험에 Hash를 부여한다.

```text
experiment_hash = SHA256(

 strategy_ir
 + parameters
 + symbols
 + start_date
 + end_date
 + dataset_version
 + evaluator_version
 + cost_model_version

)
```

이미 존재하면:

```text
CACHE HIT
```

으로 처리한다.

백테스트하지 않는다.

이 기능은 장시간 연구에서 매우 중요하다.

---

# 9. 연구 탐색은 두 계층으로 분리

## Structure Search

무엇을 사용하는가를 탐색한다.

```text
SMA + RSI

SMA + ATR

RSI + Volume

Momentum + Regime

Strategy A Entry
+
Strategy B Exit
```

## Parameter Search

해당 구조 안에서 숫자를 최적화한다.

```text
SMA fast
SMA slow
RSI threshold
ATR
Stop Loss
Take Profit
```

따라서:

```text
Structure Search
       ↓
promising structure
       ↓
Parameter Search
```

순서가 기본이다.

---

# 10. Generation 단위 LLM 호출

LLM은 Experiment마다 호출하지 않는다.

실행 단위는 Generation이다.

```text
GENERATION N

Champion
+
Frontier
+
Knowledge
+
최근 실험 결과

        ↓

LLM

        ↓

Research Intent

        ↓

Local Planner

        ↓

256 Candidates

        ↓

Local Backtesting

        ↓

Local Evaluation

        ↓

Top 10

        ↓

Summary

        ↓

LLM
```

즉:

```text
256 Backtests
≈
LLM 1~2회
```

가 목표다.

---

# 11. Local Analyzer

백테스트 결과 전체를 LLM으로 보내지 않는다.

로컬에서:

```text
CAGR
Return
Sharpe
Sortino
MDD
Calmar
Win Rate
Profit Factor
Trade Count
Turnover

Parameter sensitivity
Correlation
Parameter importance
Regime breakdown
Cost sensitivity
```

등을 계산한다.

LLM에는 다음 정도만 전달한다.

```yaml
generation: 42

tested: 512
valid: 476

champion:
  id: S821
  robust_score: 0.784

observations:

  - RSI 32~36 구간 안정적
  - ATR > 28 거래 수 급감
  - stop loss < 3% 성능 악화
  - EMA 기반 전략이 SMA보다 MDD 개선

frontier:

  - S821
  - S924
  - S1031

unexplored:

  - volume regime exit
  - volatility adjusted sizing
```

---

# 12. Evaluator는 Agent 접근 금지

최상위 보안 경계다.

```text
MUTABLE

strategies/
experiments/specs/
research hypotheses


IMMUTABLE

core/data/
core/backtest/
core/evaluator/
core/validation/
core/costs/
core/integrity/
```

매 실험마다:

```text
strategy_hash
data_hash
engine_hash
evaluator_hash
cost_model_hash
```

를 기록한다.

Agent가 자신의 평가 기준을 변경해서 결과를 좋게 만드는 것을 구조적으로 차단한다.

---

# 13. 데이터는 세 영역으로 고정

```text
DATA

├─ DEVELOPMENT
├─ VALIDATION
└─ SEALED_OOS
```

### DEVELOPMENT

대량 탐색 허용.

### VALIDATION

상위 후보만 사용.

### SEALED OOS

Research Agent 접근 금지.

Champion Candidate가 됐을 때만 Promotion Gate를 통해 평가한다.

---

# 14. Funnel Evaluation

모든 후보에 비싼 평가를 수행하지 않는다.

```text
1,000 candidates

        ↓

FAST SCREEN

        ↓

200

        ↓

FULL BACKTEST

        ↓

50

        ↓

ROBUSTNESS

        ↓

10

        ↓

VALIDATION

        ↓

2~5

        ↓

Champion Candidate
```

Fast Screen에서는:

```text
수익성
MDD
trade count
명백한 실패
```

정도만 확인한다.

---

# 15. Robustness Layer

최종 평가 과정:

```text
Candidate
   ↓
Data Integrity
   ↓
Standard Backtest
   ↓
Transaction Cost
   ↓
Slippage Stress
   ↓
Parameter Perturbation
   ↓
Walk Forward
   ↓
Regime Breakdown
   ↓
CPCV / CSCV
   ↓
DSR
   ↓
PBO
   ↓
Complexity Penalty
   ↓
ROBUST SCORE
```

단순 Sharpe 최대화를 금지한다.

---

# 16. 전략 상태

기존 KEEP/DISCARD보다 세분화한다.

```text
CRASH

REJECT

NEAR_MISS

SURVIVOR

FRONTIER

CHAMPION_CANDIDATE

CHAMPION
```

`NEAR_MISS`는 매우 중요하다.

전략 전체는 탈락해도 유용했던 Mutation을 `Rescue Pool`에 저장한다.

---

# 17. Champion 하나만 유지하지 않는다

Greedy Hill Climbing을 방지하기 위해 Frontier를 둔다.

```text
Champion

Frontier
├─ Momentum
├─ Mean Reversion
├─ Breakout
├─ Trend
└─ Hybrid
```

각 Family가 독립적으로 진화할 수 있게 한다.

초기 탐색 정책은:

```text
Exploit
Explore
Crossover
Rescue
```

네 종류로 관리한다.

비율은 고정 상수가 아니라 연구 정책에서 수정 가능하게 한다.

---

# 18. Experiment Memory

저장은 3단계로 나눈다.

```text
RAW MEMORY
모든 실험

KNOWLEDGE MEMORY
통계적으로 반복 확인된 지식

LLM MEMORY
압축된 연구 상태
```

예:

```yaml
known_good:

  - momentum + volatility regime
  - RSI entry 31~36

known_bad:

  - RSI < 20
  - stop_loss < 2%
  - leverage > 1.8

interactions:

  - ATR filter helps momentum
  - ATR filter hurts mean_reversion

unexplored:

  - adaptive exit
  - volume normalized momentum
```

---

# 19. 저장 구조

초기 버전은:

```text
SQLite
+
Parquet
+
JSON
```

이면 충분하다.

```text
state/

experiments.sqlite

results/
  generation_001.parquet
  generation_002.parquet

frontier.json
champion.json
knowledge.json
rescue_pool.json
```

PostgreSQL은 멀티 머신으로 확장할 때 도입한다.

---

# 20. Git 사용 방식

모든 실험을 commit하지 않는다.

```text
일반 Candidate
→ DB만 저장

Frontier
→ snapshot 저장

Champion Candidate
→ Git commit

Champion
→ Git tag
```

예:

```text
champion-v001
champion-v002
champion-v003
```

이를 통해 의미 있는 전략 계보만 Git에 남긴다.

---

# 21. 연구와 실거래를 완전히 분리

Research Agent는 주문 권한을 가지지 않는다.

```text
AUTORESEARCH

      ↓

CHAMPION

      ↓

Deployment Gate

      ↓

Paper Trading

      ↓

Live Validation

      ↓

HUMAN APPROVAL

      ↓

KIS Trading Engine
```

KIS 계좌 주문 시스템은 별도 Trust Boundary에 둔다.

---

# 22. 최종 Repository

```text
quant-autoresearch/
│
├─ AGENTS.md
│
├─ README.md
│
├─ pyproject.toml
│
│
├─ research/
│  ├─ program.md
│  ├─ policy.yaml
│  ├─ objectives.yaml
│  └─ llm/
│     ├─ director.py
│     └─ context_builder.py
│
├─ strategies/
│  ├─ primitives/
│  ├─ templates/
│  ├─ imported/
│  ├─ normalized/
│  ├─ generated/
│  └─ champions/
│
├─ strategy_ir/
│  ├─ schema.py
│  ├─ parser.py
│  ├─ validator.py
│  └─ compiler.py
│
├─ mutation/
│  ├─ engine.py
│  ├─ operations.py
│  ├─ parameter.py
│  ├─ structural.py
│  ├─ crossover.py
│  └─ primitive_registry.py
│
├─ experiments/
│  ├─ planner.py
│  ├─ candidate_generator.py
│  ├─ deduplicator.py
│  └─ cache.py
│
├─ runtime/
│  ├─ scheduler.py
│  ├─ queue.py
│  ├─ worker_pool.py
│  ├─ lean_worker.py
│  └─ resource_manager.py
│
├─ core/                    # IMMUTABLE
│  ├─ data/
│  ├─ backtest/
│  ├─ evaluator/
│  ├─ validation/
│  ├─ costs/
│  └─ integrity/
│
├─ evaluation/
│  ├─ metrics.py
│  ├─ robustness.py
│  ├─ sensitivity.py
│  ├─ regimes.py
│  ├─ pareto.py
│  ├─ scoring.py
│  └─ selector.py
│
├─ memory/
│  ├─ experiment_store.py
│  ├─ knowledge.py
│  ├─ compressor.py
│  └─ rescue_pool.py
│
├─ state/
│  ├─ experiments.sqlite
│  ├─ champion.json
│  ├─ frontier.json
│  ├─ knowledge.json
│  └─ rescue_pool.json
│
├─ integrations/
│  └─ kis/
│
└─ deployment/
   ├─ paper/
   └─ live/
```

---

# 23. 최종 Generation 실행 규격

Canonical Loop는 이것으로 확정한다.

```text
01. Champion / Frontier Load

02. Knowledge Load

03. LLM Research Direction

04. Local Experiment Planning

05. Candidate Generation

06. Duplicate Cache Check

07. Strategy Mutation

08. Strategy Validation

09. Parallel Fast Backtest

10. Hard Gate

11. Parallel Full Backtest

12. Robustness Validation

13. Local Statistical Analysis

14. Robust Score

15. Champion / Frontier / Rescue Update

16. Experiment DB Save

17. Knowledge Extraction

18. LLM Context Compression

19. Plateau Detection

20. Next Generation
```

---

# 24. LLM 개입 규칙

LLM을 항상 호출하지 않는다.

```text
Generation 시작
→ 필요 시 호출

Local exploration 가능
→ LLM 호출하지 않음

개선 지속
→ LLM 호출하지 않음

Plateau 발생
→ LLM 호출

새 Strategy Family 필요
→ LLM 호출

새 Primitive 필요
→ LLM 코드 생성 허용
```

따라서 시스템이 성숙할수록 백테스트 횟수 대비 LLM 호출 비율은 계속 감소한다.

---

# 25. 최종 설계 원칙

이 프로젝트에서 절대 깨면 안 되는 것은 다음 다섯 가지다.

```text
1. Strategy는 코드가 아니라 IR이다.

2. LLM은 Candidate를 만들지 않는다.
   Candidate를 만드는 규칙을 결정한다.

3. 계산 가능한 것은 LLM에게 보내지 않는다.

4. Evaluator와 Data Contract는 Agent가 수정할 수 없다.

5. 백테스트 연구와 실제 주문 시스템은 완전히 분리한다.
```

최종적으로 이 시스템의 정체성은:

> `LLM-assisted Autonomous Quant Research Harness`

이다.

단순히 AI가 전략을 써주는 시스템도 아니고, 단순 파라미터 최적화기도 아니다.

```text
실제 전략 수집
     ↓
정규화
     ↓
전략 라이브러리
     ↓
LLM 연구 가설
     ↓
로컬 구조 변형
     ↓
대량 후보 생성
     ↓
병렬 Lean 백테스트
     ↓
불변 금융 Evaluator
     ↓
통계적 견고성 평가
     ↓
Champion / Frontier / Rescue
     ↓
연구 Memory 축적
     ↓
다음 Generation
```

이라는 지속적 전략 연구 플랫폼으로 확정한다.
