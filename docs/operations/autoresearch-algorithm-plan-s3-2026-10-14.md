# S3 1차 — LLM 가중 지표 조합·시장별 전략 전환 알고리즘

작성: 2026-10-14. [사용자 20문답 결정](../decisions/2026-10-14-autoresearch-interview-20q.md) 중 특히 5, 6, 10, 11, 13번과 [개발 로드맵](autoresearch-implementation-roadmap-2026-10-14.md)을 구현하는 **첫 번째 제한된 연구용 수직 슬라이스**이다.

## 기능 목적 및 이번에 실제로 구현된 범위

기존 `StrategyIR` / `BacktestEngine` / 검증된 논문 지표 라이브러리를 보존하면서, LLM이 선언형 `AlgorithmPlan`을 생성하고 그 계획이 검증된 지표를 읽어 복합 매매 신호를 생성한 뒤 표준 StrategyIR로 실행되도록 하였다.

- 신규 `research/indicator_engine/algorithm_plan.py`: `AlgorithmPlan` / `RegimeCase` / `IndicatorGate` / `WeightedVote` 및 결정론적 컴파일/감사/실행 어댑터.
- 각 케이스는 검증된 `regime` 또는 `risk` 지표에 대한 **완료봉 비교 조건**과 검증된 이진 `entry` 지표들의 양수 가중 합산, 진입 점수 임계값을 갖는다. 최대 8개 분기, 케이스당 최대 8개 지표. 첫 번째 성립하는 분기를 선택한다.
- 분기가 하나도 해당하지 않으면 현금 상태(`FLAT`), 소스 데이터가 준비되지 않았다면 진입 미허용(`None`). 지표값은 완료봉 t까지 계산되며 거래는 t+1 봉 시가부터 허용된다.
- `plan_entry`, `plan_regime`, `plan_vote_score`, `plan_branch_index`에 더해 **원본 모든 지표값**을 자료에 유지한다. `plan_branch_index=1`은 plan.cases[0], `2`는 plan.cases[1], `0`은 어느 케이스도 선택되지 않았음을 뜻한다. 구체적인 이름/가중치는 저장된 타입드 Plan이 정의한다.
- `ResearchSignalReplay` 및 `CompiledAcademicStrategy`에 통합해 기존 `evaluate_compiled_development()` / `audit_compiled_academic_decisions()`가 원본 지표값, 선택 분기, 점수, 신호, 체결·비용·손익을 연결할 수 있게 했다.
- `compile_provider_algorithm_plan(...)`은 LLM provider에게 **검증된** 지표 ID·역할·lookback·응답 JSON Schema와 시장 메타데이터만 주고 `AlgorithmPlan` 구조를 한 번 수신·검증한다. 실제 인증된 모델을 사용한 자율 실행 기능은 아니다.

## 조합 논리 예시

```json
{
  "plan_id": "qqq_weighted_regime_trial",
  "cases": [
    {
      "case_id": "calm",
      "when": {"indicator_id": "parkinson_variance", "op": "less_equal", "threshold": 0.0001},
      "votes": [
        {"indicator_id": "time_series_momentum", "weight": 0.7},
        {"indicator_id": "previous_range_breakout", "weight": 0.3}
      ],
      "min_score": 0.5
    },
    {
      "case_id": "volatile",
      "when": {"indicator_id": "parkinson_variance", "op": "greater_than", "threshold": 0.0001},
      "votes": [
        {"indicator_id": "previous_range_breakout", "weight": 0.7},
        {"indicator_id": "time_series_momentum", "weight": 0.3}
      ],
      "min_score": 0.5
    }
  ],
  "unmatched": "FLAT",
  "position_size_pct": 100
}
```

이것은 **테스트 예시**이며 투자 추천 또는 엔진이 자율로 발굴한 알고리즘이 아니다. 예를 들어 `calm` 구간에서 `momentum=1`, `breakout=0`이면 `plan_vote_score=0.7`, 진입 조건(`score >= 0.5`)은 참이다. 원본 지표값과 함께 매매 판단 기록에 남는다. 동일 단일종목 롱 포지션의 유지 중에 분기가 교체되는 것은 포지션 재배분/체결이 아니라 다음 매매 신호 계산기의 변경이다.

## 지원하지 않는 기능 / 권한 경계

- 가중치는 **지표 투표 가중치**이며, 동적 자본 배분이나 레버리지·선물·숏포지션·리밸런싱 주문이 아니다. 포지션 크기는 고정 100% 현금 한도 내 연구용 매매로 유지한다. 더 일반적인 전략·복잡한 조건식·주문 제어는 이후 IR/체결 계약 검증이 필요하다.
- 이번 S3 1차는 **등록된 `time_series_momentum`, `previous_range_breakout` 이진 entry 신호 및 단일자산 VERIFIED regime/risk 신호**만 지원한다. 단순히 논문/오픈소스에 등장했다는 이유만으로 미검증 지표가 실행되는 것을 금지한다.
- 플랜/카탈로그/시장 데이터는 검증된 입력이어야 하며, 각 평가·감사 시 다시 카탈로그의 계산기를 실행해 원본과 derived vector를 검증한다. 과거 데이터가 갱신되거나 plan, 해시, 계산 벡터가 조작되면 실패한다.
- Sealed OOS에 대해서는 **LLM 제공자 호출 자체를 하지 않는다**. 코드/Python patch·임의 조건 연산자·무제한 분기·미검증 지표·모델 검증을 우회한 객체 복사는 거부한다.
- `candidate_promotable=false`, `point_in_time_verified=false`, `broker_executable=false`. 연구용 non-PIT 자료만 사용하고 운영 권한은 변화시키지 않는다.

## 실제 QQQ 데이터 개발용 검증

- 입력: 기존 Tiingo QQQ 2020-01-02~2025-12-31 1,508개 일봉. `parkinson_variance`, `time_series_momentum`, `previous_range_breakout` 모두 학술 기준 검증 후 등록.
- 동일 개발 데이터에서 위 플랜을 실행: **판단 1,508개, 총 체결 69건, 청산된 왕복 거래 34건**.
- 선택된 분기: `calm` 734봉, `volatile` 522봉, 워밍업/결측 252봉. 실제 매매 예시: 2020-12-31 완료봉의 Parkinson variance `0.00005235`, momentum `1.0`, breakout `0.0`으로 첫 분기 선택 및 점수 `0.7` 계산 → 2021-01-04 시가 **315.11달러** 체결.
- 시작 자본 1만 달러, 비용 포함 개발 구간 수익률 **+56.55%** (총 누적, 연환산 아님), MDD **12.98%**. 이는 사전 선택한 고정 연구 구간과 독립 비교/배당 기업행동/PIT 검증을 완료하지 않았으므로 **실제 순수익 우위·일반화 성능·매매 승인 근거가 아님**. 복수 후보를 연구하는 과정의 탐색 결과 중 하나일 뿐이다.
- 결정론적 원장 해시: `6f650e7734ee9d82603f068ad8fb24c360857cb83e8dbf9df8b84755ebd7fac5` (데이터·설계·검증된 계산기 고정 시).

## 후속 작업

1. **S3 남은 범위:** 일반화된 다중 지표/중첩 논리, 시장 상태별 연속 목표 비중과 복수 하위전략의 신호 전환의 의미를 설계해 기존 protected core의 비용·체결 모델과 충돌 없이 컴파일하는 기능. 계보·중복·사전검증 인터페이스를 S2와 통합.
2. **S4:** 실제 LLM이 각 세대 시작과 결과 분석 단계마다 `AlgorithmPlan` 및 `DiagnosticResponse`를 작성하고 후속 후보를 자동 실행하도록 **지속 가능하고 안전한 연구 제어기**를 연결. Mock provider 단일 호출은 자율 연구 완료 증거가 아니다.
3. 재현 가능한 통제실험·실제 평가 증거가 쌓인 뒤에야 인디케이터/계산기 자동 확장과 다자산 검증을 위한 연구 자원을 확대한다.

## 자동 검증 최종 결과

- S3와 기존 S1/S2 통합 집중 테스트: **40/40 통과**.
- 저장소 전체 회귀 테스트: `pytest -q -p no:cacheprovider` **1,325 passed, 0 failed (398.71s)**.
- `ruff check .` 전부 통과, `mypy .` **221 source files** 통과.
- 테스트 구조: 결과 재실행 결정론성, 완료봉→다음 시가 인과 시점, 미래 마지막 봉 변조 시 과거 신호 불변, 검증된 역할·지표만 사용, Sealed OOS 제공자 호출 차단, 알고리즘·데이터·사전 계산벡터 변조 거부, 무분별한 코드 필드와 잘못된 스키마·`model_copy` 우회 거부.
- 제공자 테스트는 **fake structured provider**이며, 외부 LLM API 사용/시장 탐색/세대 자동 진화는 이번 검증 범위가 아니다.
