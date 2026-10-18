# Quant AutoResearch T4 — 기존 기능 통합·재발 방지 개발계획

기준: 2026-10-19 KST. 상위 요구: 20문답 Q02/Q05/Q06/Q07/Q08/Q09/Q10/Q15/Q17/Q20 및 `docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md`. 기존 V05 → T4 → V01~V04 → V06 → V07 순서는 변경하지 않는다.

## 1. 문제 및 이미 확보된 증거

- 기존 GPT MCP 100세대 세션 `c1eadd67bad94d7ea182dc274224dbce`는 **53/100**으로 저장되어 있다. G4~G53은 50개 S7 보고서/고유 전략 해시를 가지지만 `parent_selections`=0, `successor_lineages`=0이다. 비PIT 동일 QQQ 개발기간에서 QQQ 수익 초과 0/50. GPT의 자유 추론/자동 계승을 입증하지 못한다.
- 직전 50세대의 호출자는 의사결정 대신 세대 번호에 따른 제한된 전략군·임계값 및 손실 진단 템플릿을 생성했다. 포지션 사이즈 축소에 따른 기계적 MDD 개선 29건을 실제 신호 우월성으로 계수하지 않아야 한다.
- **이미 존재하는 코드:** `research/llm/loss_attribution.py`, `experiment_learning.py`, `cross_generation_memory.py`, `economic_feedback.py`, `lineage_selection.py`, `lineage_replay.py`, `fixed_budget_arms.py`, `checkpoint_autopilot.py`, `s2_execution_preflight.py`; `application/academic_checkpoint_service.py`의 `_selected_development_parent`, `continue_verified_child`, `advance_inherited` 진입점. 전체 재구현·새 백테스트 엔진 작성 금지.
- **기존 실제 증거:** `7153a94`/`c636802`에서 G134/G135 정식 계승 세대, `0c11238`에서 동예산 3개 arm, `b54e303`/`8d5543d` 손실·세대 기억, `dd8ccd2` MCP 요약 응답. `fdaccd9`에 계산 지표·정책 브리지 개발품이 있지만 현 운영 코드 SHA `54a515f`에는 미포함. 운영 런처 SHA `1967288`.
- 현 부모 선택기는 **동일 세션** `successor_lineages` 또는 **이미 계승된** 세대의 S7 자식을 입력으로 사용한다. 일반 AlgorithmPlan으로 시작한 새로운 세션은 후속 계보를 외부 호출로 재생하지 않는 한 계속 `NO_VERIFIED_PARENT`에 머문다. 세션 간 원장/부모 SHA의 보안 경계 역시 별도 통합이 필요하다.
- 이미 존재하는 `evaluate_algorithm_experiments`의 후속 `continuation_intent` 모드는 S7 자식→손자 StrategyIR을 해시·체결·비용으로 재생하고, 동일 세션 `successor_lineages`를 생성한다. `get_algorithm_research`에서 이 **사용 가능한 시작 경로를 충분히 안내하지 않았던 것**이 재발 원인 중 하나이다.

## 2. 중복 방지 소유권 매트릭스

| 작업 | 재사용 소스 / 상태 | 이번 단계 변경 | 별도 잔여 검증 |
|---|---|---|---|
| GPT 손실 원인과 세대 기억 | loss_attribution, experiment_learning, cross_generation_memory / 운영 구현 | 재작성하지 않음 | 실제 GPT 후속 제안이 입력 근거를 인용하는지 |
| S7 체결·리스크·경제성 | 기존 S7 + economic_feedback / 운영 구현 | 변경 없음 | 리스크 크기 조절과 신호 변경을 별도 집계 |
| 정식 부모 계승 | lineage_selection / continue_verified_child / advance_inherited / 운영 구현 | **동일 세션 S7 후보를 명시적으로 제공하는 읽기전용 부트스트랩 안내** | 실제 후속 계보 작성→선택→정식 다음 세대 체결 검증 |
| 중복방지·엄격 검증 | semantic/effective hash, require_signal_change, require_execution_change / 운영 구현 | 기본값 일괄 변경 금지 | 정확한 계승 경로에서 선택 적용, 수동 비교 |
| 무작위 동일예산 대조 | fixed_budget_arms / 운영 구현 | 변경 없음 | 같은 부모, 같은 seed, 동일 백테스트 예산 |
| 자유형 전략/새 지표 | 기존 `fdaccd9` 개발 브랜치 / 운영 미배포 | 병합·재구현 금지 | 종단간 신규 신호→체결→계승 golden 검증 |
| MCP 응답 압축 | mcp_context_budget / 운영 배포 | 현재 도구는 변경 없음 | get_algorithm_research 별도 paging/compact 후속 작업 |

## 3. 순서 및 GO 조건 (현재 작업은 P0-1/P0-2 첫 절편만)

1. **P0-1 문서·기준선:** 운영/개발/별도 브랜치 기능 차이를 현재 커밋과 53세대 실제 원장으로 기록. READ-ONLY, 신규 연구 0, 코드 재개발 0.
2. **P0-2A 동일 세션 계승 부트스트랩 안내(이번 구현):** S7 보고서의 원본 해시·실측 자식 해시·실제 체결 변동·양의 자본 변화가 일치하는 후보를 세대 컨텍스트의 짧은 `verified_lineage_bootstrap` 힌트로 제공. 포지션 축소만 한 자식은 제외. 보존된 S7 원본을 다시 쓰지 않으며 기존 `continue_verified_child` 계약/선택기를 재사용한다. *단, 힌트는 승격 증명이 아니다.* 전체 계승 검증(자식→손자 30개 이상 실제 완료거래, 정확한 체결·비용과 부모 대비 개선, MDD·노출 조건)은 기존 도구가 직접 시행한다. 후보가 없으면 `NO_SIGNAL_IMPROVING_CHILD_FOUND`를 정확히 보고한다.
3. **P0-2B 자동 계승 경로 검증:** 격리된 운영 원장 스냅샷에서 실제 S7 후보에 모델이 자유롭게 작성한 한 가지 `continuation_intent`로 기존 API를 호출해 hash-verified 계보→부모 선택→다음 세대 실제 `InheritedResearchIntent`/S2/S7 두 세대 연결 확인. 성공 전 운영 배포 금지. 세션 간 이전의 경우 별도 source-session hash 계약을 최소 확장하고 재사용한다.
4. **P0-3 모델 결정 증거:** GPT 제안/진단마다 모델-클라이언트 호출 출처, 사용한 prior experiment ID 및 선택 이유를 기록. 토큰·모델 identity는 서버가 모르면 `UNVERIFIED` 유지; 템플릿·오프라인 provider와 실제 GPT를 구분한다. 기존 외부 MCP 호출 정책 변경 금지.
5. **P0-4 품질 및 P0-5 대조:** S7 risk resize와 신호/체결 구조 변경 분리. 동일 예산 GPT vs random vs local 진화 재실행 후 독립적인 5~10세대 검증 통과 시만 47세대 재개 검토.
6. **P1 자유형 정책 연결:** 이미 개발된 `fdaccd9` 및 10/18 최종 검토의 G0~G5 소규모 vertical slice 검증을 우선 재사용. 새로운 AST/평가 코어의 별도 중복 구현 금지.

## 4. 현재 개발의 명시적 비목표

- 운영 서버/32도구/URL/OAuth/실거래 비활성/비PIT 원장/봉인 OOS/백테스트 코드 변경 없음.
- 자동 부모 승격, GPT 무인 호출, 임의 원격 LLM API 도입, 새 연구 세대 생성 없음.
- GPT가 장문의 모델 문맥을 자동으로 요약하고 독립적으로 의사결정한다고 주장하지 않는다.
- 선택된 이전 실험을 새로 "성공한 전략"이라고 명명하지 않는다. 모든 후보는 후속 검증이 요구된다.

## 5. 완료 기준과 다음 확정 작업

- 이 작업: S7 원본-제안-결과 hash 연결 검사, 자본 증가 및 실제 신호/체결 변화가 있는 후보만 안내, 크기 제한·결정성·과거원장 비변경/빈 세션/변조 실패 회귀 테스트 PASS. 코드 및 문서 commit/push. 운영 **미배포**.
- 다음 고정 작업: P0-2B 격리원장 계보 정식 연결 실증 → P0-3 실제 GPT 계획/진단 검증 → 같은 예산 대조군 → T4 남은 47세대 계속 여부 판정.

## 6. 첫 개발 절편(P0-2A) 구현·검증 결과

- 신규 파일: `research/llm/lineage_bootstrap_guidance.py`, `tests/research/test_lineage_bootstrap_guidance.py`.
- 수정 파일: `application/academic_checkpoint_service.py`에서 기존 `_context`의 `scored_reports`(저장 해시 검증을 거친 S7 기록)와 `selected_development_parent`만 **읽어서** `model_context.verified_lineage_bootstrap`을 추가. 기존 플랜/진단·S2/S7 원장·계승 알고리즘의 로직과 도구 수는 변경하지 않음.
- 필터: 동일 세션의 일반 AlgorithmPlan S7 원본 hash 연결, 감사·데이터셋·진단 hash 일치, S7 자식 StrategyIR hash/원본 제안 일치, 실측 costed equity 증가, 최소 60 *fill 이벤트* 및 시간/추가/제거 이벤트 변화. **60 fill 이벤트는 30개 완료 거래의 증거가 아니다**. 이 조건은 후속 재생 대상을 좁히는 스크리닝에 불과하며 기존 replay 함수가 완료 거래·수익·MDD·노출·비용·손자 변이 타당성을 최종 검증한다. 포지션 수량만 변경된 결과는 신호 개선 후보에서 제외함.
- 실제 비PIT G1~G53 읽기 전용 결과: 저장 S7 53개, 1차 부트스트랩 후보 **7개**, GPT에 반환한 후보 최대 **5개 / 3,330 JSON bytes**. 별도 SQLite Backup 생성 후 기존 서비스 `get`을 테스트하여 **53/100, AWAITING_PLAN, 후보 7, 선택 부모 없음, 계보 없음** 확인. 원본 운영 DB 쓰기 0.
- 테스트: 신규 5 PASS (원본 변경 없는 결정론적 우선순위, 빈 세션, 효과 없는 resize, S7 변조 거부, 기존 MCP 무승격); MCP 세션·P0 계승 및 재계승·OAuth SDK·20문답 범위잠금 등 관련 회귀 **43 PASS / 0 FAIL (113.51초)**; 저장소 전체 Ruff PASS; Mypy **277 source files PASS**. 전체 Pytest는 이 별도 개발 절편에서 실행하지 않음. 따라서 전체 스위트 합격이나 운영 적용을 주장하지 않는다.
- **남은 핵심 원인:** 선택할 최초 부모가 없는 세션에서 실제 후속 계보를 생성할 GPT 연구자가 없으면 기존 코드가 자동 계승되지 않는다. 이번 변경은 연결에 필요한 근거와 도구 입력을 알리는 것까지이며, **P0-2B의 실제 후속 재생→부모 선택→다음 counted 세대 연결 검증 없이는 47세대 재개 불가**. 완전 자율 GPT 호출 증거 역시 별도 P0-3 수락 조건 그대로 남음.
