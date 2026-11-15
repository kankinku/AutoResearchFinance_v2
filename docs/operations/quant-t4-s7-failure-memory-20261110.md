# Quant T4 S7 실패 메모리·S8 연구 방향 검증 — [8/16]

**날짜:** 2026-11-10 · 승인된 [16단계 계획](../superpowers/plans/2026-11-10-quant-research-improvement.md) Task 7 · Q04/Q07/Q09/Q11/Q13/Q20.

## 기존 기능과 실제 결함

기존 `build_experiment_learning(history, records, max_recent=12)`는 저장된 S7 원본의 `record_hash`, 세대 증거, 가설 ID, 예측 방향과 실제 관측 상태를 이미 구분·검사한다. `build_cross_generation_memory`와 `build_economic_feedback`는 서명된 S7에 기반한 경제적 효과/타입화된 규칙 변경의 설명을 생성하며, 자동 승인하지 않는다. **이 기능은 그대로 보존**한다.

그러나 별도의 `build_research_direction(history, controlled_reports)`는 생성한 모드/방향을 사용할 때 S7 `record_hash`를 재계산하여 확인하지 않았다. 조작된 `status`와 이벤트 변동 수가 정본 원장에 서명되지 않았어도 다음 연구를 `EVOLVE`로 추천할 수 있었다. 동일한 실제 체결 추적(`same_fill_trace=True`)과 의사결정 이벤트 수 차이가 공존할 경우에도 새 실행 성과로 혼동할 가능성이 있었다.

## 변경 사항: S7/S8 감사 경계

- **S8 증거 보호:** S7 보고서의 `record_hash`를 독립 재계산하여 확인, 원본 세대 `evidence_hash`와 연결, 원본 `hypothesis_ids`를 계측한 가설 ID와 대조. 연구 범위가 개발 데이터·비인과 범위인지 검사하고 `out_of_sample_approved=False`, `broker_executable=False`, `causal_status=NOT_ESTABLISHED`를 강제한다. 실패 시 `ResearchBudgetError`로 중단한다.
- **실제 체결 신호 우선:** `same_fill_trace=True`이면 의사결정 이벤트 변경 숫자가 양수더라도 S8 `execution_change=UNCHANGED_EXECUTIONS`으로 분류. 기존 기록을 수정하지 않고 **EVOLVE 근거에서 제외**. S7의 예측 방향 일치 및 측정된 관측을 없애지 않으며, 실거래 가능성이나 인과성 승격 없음.
- **S7 다음 연구 지침:** S7 학습 패킷에 서명된 원본 `status`, 가설 ID, 관측된 `delta`, 변동 이벤트 숫자 및 기존 증거 해시를 그대로 제공한다. 같은 체결 추적과 변경 이벤트 수가 공존하면 **`UNCHANGED_FILLS_DESPITE_REPORTED_DECISION_CHANGES`** 원인으로 안내하고 다음 단계에서 규칙/계측 확인을 권장. 실행 변화가 없이 예측된 방향만 맞은 경우도 **`UNCHANGED_OBSERVED_TRACE`** 취급하여 새 실행 성과로 해석하지 않는다.
- **관측된 연구 품질 수치:** `measured_outcome_metrics`에 (1) 실제 S7 보고서가 존재하는 시험 수, (2) 체결 동일성을 제외한 **보고된** 실행 이벤트 변화 시험 수, (3) 무변화 시험 수, (4) 실패 수와 동일 child 전략 해시의 반복 실패 수 및 반복 실패율, (5) 일치/불일치 결과가 관측된 시험 중 가설 방향 일치율을 추가한다. `recent_evidence`는 기존의 12개 이하로 제한하되 전체 수치와 과거 실패 원인 누적은 **모든 서명된 현재 세션 S7**에서 계산한다.
- 신규 DB·가중치 조정·파라미터 변경·LLM 학습/생성·성능 승격·추가 MCP 도구 없음. `build_experiment_learning`, `build_research_direction`의 시그니처 및 기존 반환 키 보존; 추가 키는 개발 단계 관측 지표임. 회귀 테스트의 복구된 가짜 서명은 검증용 픽스처만 수정했으며 사용자의 원본 역사 기록은 변경하지 않았다.

## 검증 결과와 한계

- **TDD RED:** S8에서 변조된 S7 상태가 성공 방향으로 추천됨, 원본 가설 ID 없는 결과 수용, 동일 실제 체결인데도 신호 변경으로 EVOLVE, S7 계량 지표 누락 등 **신규 5개 테스트가 수정 전 FAIL**. GREEN: S7/S8/세대 간 메모리 **42 PASS**, 실 세션 테스트를 포함한 D05·S8·경제 결과·F3·MCP 제출/복구·거버넌스 **98 PASS + 4 SKIPPED**. 건너뜀은 `tests/research/test_lineage_p0_3.py`가 현재 마운트에 과거 Moon 원장 증거 파일을 요구하기 때문.
- 감사 경계 재검증: S7 hash 조작, 원본 세대/가설 불일치, 스스로 OOS·브로커 허가를 주장한 재서명 보고서, 실 체결 동일/이벤트 변경 충돌, 실제 다음 계획 컨텍스트 생성/재조회, 최근 맥락에 보이지 않는 오래된 실패의 통계 보존.
- `ruff check .` **PASS**; `mypy research/llm/experiment_learning.py research/llm/adaptive_direction.py` **PASS**; `git diff --check` **PASS**.
- 측정된 변화 시험 수는 **서로 다른 전략 사이의 독립 신규 체결 증거 수가 아니다**. `same_fill_trace`는 부모 대비 같은 체결 증거일 뿐, 전체 세대 간 동일 체결 여부의 대체물이 아니다. 반복 실패율은 자식 전략 해시 기반 반복의 **관측 비율**이지 인과적 실패율이 아니다. 가설 방향 일치는 독립 성공률·수익성/alpha/OOS 증명이 아니다.
- **전체 수트:** `pytest -q -x -p no:cacheprovider`는 **448 PASS, 1 FAIL**, 첫 실패에서 중단. 기존 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`가 작업공간에 없는 `state/moon-http/fresh-20261021/session-id.txt`를 요구한다. [7/16]에서도 동일하게 관찰된 역사적 환경 의존성. 전체 pytest PASS **아님**.
- 외부 LLM의 독립적 10/100세대 진단·실제 시장 데이터/실원장·다른 사용자 세션·브로커 주문·운영 배포 **NOT RUN**. 현재 새 세대는 [사용자 초기화 승인](../decisions/2026-11-10-quant-fresh-research-reset.md)에 따라 **과거 G1~G150/기타 실험의 부모·학습 기억을 가져오지 않아야 한다**. 이 단계의 테스트용 가짜 S7 기록은 실제 신규 연구에 저장하지 않았다.

**다음:** [9/16] Task 8: 과거 G94 등의 결과는 오직 동일 조건 통제시험을 위한 synthetic 재현 참고로만 이용 가능하고 새 G1의 직접 부모/지식 계승은 금지. 부모 다양화 opt-in 경로를 같은 예산/후보로 비교하고 독립 우월성 주장 금지.
