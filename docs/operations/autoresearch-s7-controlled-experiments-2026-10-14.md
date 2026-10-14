# S7 첫 구현 — LLM 연구 가설의 통제 백테스트와 연구 기억

작성일: 2026-10-14. [20문답 결정](../decisions/2026-10-14-autoresearch-interview-20q.md)의 **원인 분석 → 대조 실험 → 객관적 결과 → 다음 세대 학습** 방향을 구현하는 초기 DEVELOPMENT-only 단계이다. S0~S10 전체 단계 완료나 독립적인 수익 검증을 의미하지 않는다.

## 구현 범위

- `research/indicator_engine/controlled_experiments.py`의 `compare_controlled_experiments(...)`가 이미 완료된 S3 `AlgorithmPlan`을 다시 컴파일하고, 동일 자료·동일 원장·동일 원본 지표 계산값에서 S2 `DiagnosticResponse`를 다시 승인한다. LLM이 원본·거래 ID·자료 해시 또는 child 수정안을 위조하면 비교 실험에 진입할 수 없다.
- 변경 후보는 기존 S2 `apply_intent()`가 생성한 **타입드 StrategyIR**만 허용한다. 신호 데이터, 기간, 실행 시가, 초기 자본과 기존 `CostModel`은 컨트롤과 동일하다. 바뀐 StrategyIR만 다시 canonical backtest한다. Arbitrary Python, 외부 주문, 시장 데이터 임의 취합, OOS 접근 없음.
- 테스트하는 지표: 누적수익률(`total_return`), 연환산수익률(`cagr`), 최대낙폭(`max_drawdown`), 샤프(`sharpe`), 소르티노(`sortino`). 이 단계에서 관측을 계산하지 못하는 승률, 이익계수, 거래횟수, 노출비율은 **가설 검증했다고 주장하지 않고 명시적으로 거부**한다.
- 각 실험 결과: 원본 전략/실험 후보의 결과값·차이, 동일 체결 기록 여부, 실제 체결 건수·최종 평가금, 예측 방향과 일치 여부. 신호·수익률이 하나도 바뀌지 않았으면 **`NO_OBSERVED_EFFECT`**, 예측한 방향과 맞으면 **`DIRECTION_MATCHED_DEVELOPMENT_ONLY`**, 아니면 **`DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY`**. 별도로 측정할 수 없는 지표는 `METRIC_UNAVAILABLE`.
- **일치 여부는 개발용 과거 구간에서의 관측**이며, 경제적 원인의 입증이 아니다. 모든 결과의 `causal_status=NOT_ESTABLISHED`, `out_of_sample_approved=false`, `broker_executable=false`.
- `application/academic_checkpoint_service.py`는 `evaluate_algorithm_experiments(session_id,generation)`로 이미 완료된 세대를 재구성한다. 원장 해시/diagnosis proposal hash/plan hash를 원본과 재검증하고 대조 실험 후 **원본 세대 테이블과 별개의** `experiment_reports`에 report와 checksum을 저장한다. 중복 호출은 저장된 동일 보고서를 그대로 돌려줘 완료 세대나 결과를 중복 집계하지 않는다. 저장된 보고서 무결성도 조회 때 검증한다.
- 다음 S4 알고리즘 계획 컨텍스트의 `prior_research.controlled_experiments`에 직전 세대의 통제 실험 결과를 연결한다. 이를 통해 LLM이 자신의 원인 가설이 **관측된 결과와 맞았는지** 확인하고 다음 실험을 제안할 수 있다. 개발용 검증 결과를 '입증된 인과'로 표시하지 않는다.
- 동일 `https://project-moon.taild689f9.ts.net/quant/mcp`에 **추가 공개 도구** `evaluate_algorithm_experiments` 1개를 추가. 기존 31개는 수정·제거하지 않고 합계 **32개**. URL·OAuth issuer/DB/토큰 저장 위치는 절대 변경하지 않는 설계다.

## 테스트 시나리오와 해석

- 검증된 전략에서 regime 필터를 제거하더라도 개발 구간의 매매가 바뀌지 않은 경우를 실제 백테스트로 발견, `NO_OBSERVED_EFFECT` 및 차이 0 기록. **구조를 바꿨다는 사실만으로 '연구 개선'이라고 하지 않음.**
- 고정 투자 비중을 100%에서 70%로 조정한 typed risk parameter 제안은 동일 시장/비용 조건에서 최대낙폭이 감소하는 것을 측정해 `DIRECTION_MATCHED_DEVELOPMENT_ONLY`로 기록. 이는 대체 설명을 기각한 인과관계 입증이나 실전 수익성 검증이 아니다.
- 원본 audit hash·관측 trade ID 위조, 자료 수정, 컴파일된 원본 Plan 변조, 미지원 메트릭을 모두 명시적으로 거부하는 테스트.
- MCP 통합 테스트: 1세대 완료 후 저장된 가설의 실제 대조 실험, 같은 요청의 멱등 반환, 다음 계획에 평가 결과 전달, 비완료 세대 및 잘못된 `generation`을 거부.

## 남은 작업

1. **S7 후속:** 각 실험 목적과 실제 수정된 StrategyIR/실행 결과의 귀속·대조가 1:1인지 강화. 시장 구간 분리, 변경 전후의 거래 차이 원인 구분, 복수 대안가설을 통제하는 반복 실험, 다중검정/효과크기와 불확실성 관리.
2. **S4/S5:** 실제 연결된 ChatGPT에서 새 도구를 직접 호출하는 수락 테스트. 서버 단독 GPT 프로바이더는 없는 구조이므로 실제 앱의 직접 호출 없이는 모델 자율 실행을 검증한 것이 아님. 세대 10~100, 지속형 작업 복구는 추가 과제.
3. **S6/S8/S9/S10:** 인디케이터 및 알고리즘 구성 요소의 확대, 자동 연구 예산 조절, 검증된 신규 지표 편입, 시장/기간/자산별 엄격한 독립 검증.

## 운영 및 복구 경계

변경은 개발 브랜치 `feat/p0-indicator-research-engine-v1`에서 테스트한다. 기존 운영 코드는 고정 커밋 `f63ec46`이며 OAuth 승인 sqlite·승인키·기존 라우트 및 복구 브랜치는 절대로 덮어쓰지 않는다. 운영 배포 시 기존 URL의 launcher가 참조하는 **고정 Worktree만 새로운 테스트 통과 커밋으로 교체**, 새 배포 브랜치에 변경 기록과 이전 runtime 보존.

## 최종 개발 브랜치 검증

- 저장소 전체 `pytest -q -p no:cacheprovider`: **1,351 passed / 0 failed / 511.43초**.
- `ruff check .`: 통과. `mypy .`: **224개 Python 소스 파일** 통과.
- S7 비교/저장 통합 테스트 6개 추가, 기존 S0~S5 전체 회귀 통과.
- 운영 앱에서 신규 도구가 기존 인증으로 직접 호출 가능한지와 실데이터 세대 비교 저장은 배포 후 별도 확인한다. 모델의 자동 가설 생성 능력은 이 비교 엔진 테스트로 입증하지 않는다.
