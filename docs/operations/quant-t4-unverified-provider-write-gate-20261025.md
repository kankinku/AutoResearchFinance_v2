# T4-P0/P1 — 미검증 모델 콜백 운영 원장 차단 (2026-10-25 KST)

**진행 단계:** T4 / Q02·Q06·Q07·Q08·Q15·Q17·Q20
**상태:** 미검증 호출 운영 반영 차단 **PASS**, 격리된 연속 80세대 모의 전이 **PASS**, 실제 자동 GPT 호스트 **BLOCKED**.

## 왜 필요한가

기존 P1 `application/t4_checkpoint_orchestrator.py`는 `TEST_ONLY`와 `EXTERNAL_MCP_UNVERIFIED` 구분을 보고서에 표시했지만, 후자의 경로도 공급자 호출 출처를 검증하지 않은 `model.propose()`의 결과를 정식 `submit_plan/submit_diagnosis`로 보낼 수 있었다. 기존 `application/t4_model_host_preflight.py`의 별도 읽기전용 실패 판정을 P1의 실제 제출 시점에는 적용하지 않았던 허점이다. 이는 모의 콜백을 실제 GPT 연구세대로 계수할 수 있어 사용자 원래 Q02/Q17의 진짜 자율 연구 조건을 위반한다.

## 이번 패치 및 수락 조건

- `application/t4_checkpoint_orchestrator.py`: **`EXTERNAL_MCP_UNVERIFIED`는 제출·GPT 콜백 이전 `ModelUnavailable`로 fail closed**. 실제 모델 제공자 per-invocation 증명 및 사용자가 승인한 호스트 통합을 갖추기 전에는 운영 write 가능한 모드가 존재하지 않는다. 과거 `model_capture_audit`의 서명/기존 호출 결과나 `model.provider_signed_receipt_verified = True`와 같은 임의 속성만으로 우회되지 않는다.
- `TEST_ONLY`는 내부 격리된 테스트 서비스가 명시적으로 `_t4_fixture_only=True`로 표시된 경우에만 허용. 이는 운영 코드가 mock 테스트를 실수로 실행하는 것을 막는 개발 안전장치이지, 동일 머신 상에서 악의적인 Python 개발자를 막는 암호학적 권한 모델이라는 뜻이 아니다. 서비스 내부 P4-3/S7/StrategyIR/거래비용은 변경되지 않았다.
- `tests/integrations/test_t4_checkpoint_orchestrator.py`: 실제 GPT 출처가 없을 때 거부, 자기 주장 verified 속성 불인정, 과거 provider receipt 재사용 거부, unmarked test-only 거부, fixture marker로 production gate 우회 불가 등 **신규 5개** 회귀 시험. 기존 TEST_ONLY 20→100 모의 내구성 및 비용포함 격리된 단일 서비스 실험은 유지.
- 상태 변화 없는 진짜 P5 직접 검증: `AcademicMCPCheckpointService`의 운영 격리 state `3b44e05e52b3497db6fa035681ed0a5d`, **20/100 / G21 AWAITING_PLAN**, `model.propose()` 호출 횟수 **0**, 외부 미검증 모드와 TEST_ONLY 모두 **실행 전 BLOCK**, G20 마지막 evidence `f514f9c2d907d0fc27b9e0a906bd91e4ebf4f44fb16a866dbb826264edf48316` 불변·history 전체 동일. 실거래·OOS 승인 False 유지.

## 프로그램 검증 결과

- 관련 T4/P0·P1/P4-2 모델 capture/P4-3 S7·거버넌스 및 모델 출처 `pytest` **39 PASS**.
- 전체 저장소 `ruff check .` **PASS**.
- 변경된 핵심 모듈 `mypy application/t4_checkpoint_orchestrator.py` **PASS**.
- `git diff --check` **PASS**.
- 저장소 전체 pytest, 저장소 전체 mypy, 독립 PIT/OOS/실거래는 **NOT RUN**.
- **실제 신규 GPT 세대 0**, 원래 P5 세대 목표 **20/100**, 남은 **80 미실행**; 백그라운드 실행자 없음.

## 차단 해제 경계 및 다음 고정 작업

현재의 `EXTERNAL_MCP_UNVERIFIED` 구현은 향후 승인된 별도 통합으로 자동 우회되면 안 된다. 다음 핵심 **P0 차단 요인**은 *실제 GPT가 다음 세대 Plan/Diagnosis를 생성하는 지속 실행 호스트 및 호출별 출처 검증*이다. 현재 Moon 환경의 ChatGPT↔MCP는 서버가 ChatGPT를 역호출하는 방법을 제공하지 않으며, 모델 CLI/API 인증이 존재하지 않는다.

기본 GPT↔MCP, OAuth 및 고정 URL을 그대로 유지하면서 사용 가능한 ChatGPT 호스트가 나타나면 실제 실행을 증빙하고 연계할 수 있다. 별도 OpenAI API/Responses/Agents SDK 도입은 [사용자 승인 전 제안 ADR](../decisions/2026-10-24-t4-model-host-options-proposed.md)에서만 검토하며, 기존 모델 연결/과금/인증 변경은 **명시적 사용자 승인 이전에는 하지 않는다**. 이후 진짜 외부 모델 1세대 Plan→Audit→Diagnosis→S7→counted 및 연속 3세대·중단 재개를 통과해야 P5 G21~G100으로 확장한다.

기존 원래 V05→T4→V01~V04→V06→V07 순서를 유지하고 주문 OFF와 독립 OOS 보호 해제 금지. P1 실행 불안전 문제에 대한 실제 수정이며 **P0 완료 혹은 실제 무인 연구가 시작됐다는 주장은 금지**.
