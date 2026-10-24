# T4-P0/P1: ChatGPT MCP 연속 연구 체크포인트 제어기 — 2026-10-24

**단계:** 확정된 T4 (S4/S5) 필수 종속성, 원래 Q02/Q06/Q07/Q08/Q09/Q15/Q17/Q18/Q20. **P1 제어기 개발/격리 검증 PASS, P0 실제 자동 모델 호출 BLOCKED, P5 20/100 변화 없음.**

## 문제와 원본 목표

기존 연구는 모델이 설계·진단을 작성하면 `AcademicMCPCheckpointService.submit_plan/submit_diagnosis`를 거쳐 실제 StrategyIR/체결/비용/S7/증거 원장으로 검증한다. P5 최초 20세대에서 이 과정은 정상 작동했으나 `research/llm/provider.py`의 `GPTIntentProvider`는 외부에서 전달받은 객체를 반환할 뿐 실제 GPT 호출을 수행하지 않는다. `ConfiguredJSONProvider`는 기존 승인된 ChatGPT↔MCP 기본 연결에 맞춰 명시적으로 폐기되었다. 서버 환경에 OpenAI 호출 자격증명·실제 모델 실행자/CLI 미제공. **따라서 실제 GPT 호출 없이 20→100을 연속 실행할 수는 없다.**

T4 요구사항은 모델이 매 세대 후보/진단을 작성하고, canonical 백테스트와 S7 검증 및 다음 계획을 확인한 후만 세대 계수가 진전하는 것. **10세대마다 멈추는 하드코딩은 없어야 한다.** 기존 OAuth·MCP URL·기본 모델 제공자·보호된 코어·봉인 OOS·실거래 OFF·기존 원장은 변경하지 않는다.

## 실제 구현

- 신규 `application/t4_checkpoint_orchestrator.py`: 명시적으로 **외부 모델 콜백을 주입받는** 체크포인트 상태기반 동기 제어기 `run_checkpoint_loop`; 루프는 별도 단계 수 제한 없이 목표 `requested_generations`까지 운행하도록 설계. 단기 목표 혹은 모델 호출 예산/중지 요청은 **명시적 정책으로만** 반영.
- `AWAITING_PLAN`에서 실제 모델이 작성한 `AlgorithmPlan`/선정 부모 `InheritedResearchIntent`를 제출하고 부모가 있는 경우 `require_execution_change=True`로 실체결 변화 사전검증. `AWAITING_DIAGNOSIS`에서 트레이드 관측 기반 진단 제출, 비용/S7/부모 선정/immutable evidence는 **기존** `AcademicMCPCheckpointService`가 실행.
- `get()`에서 완결 세대 수·모델 컨텍스트·원래 체크포인트 토큰을 재조회하여 검증. 세대 계산에 내부 카운터 사용 금지. 동일 토큰과 동일 단계로 거절된 `UNCHANGED_CANONICAL_FILLS`/S7 품질 거절시 모델에게 **거절 설명과 같은 원본 토큰**을 제공해 제한된 횟수 재작성. 제한 초과시 `RETRY_EXHAUSTED`로 종료.
- **응답 유실 시** 원장 상태를 재조회하며 이미 변경된 경우에도 **동일 payload+토큰 재제출**을 통해 기존 MCP가 보유한 recent-submission 영수증을 검증해 정상 replay일 때만 진행. 불일치/동시성 불명 상태는 `CheckpointUncertain`으로 중단, 추가 카운팅하지 않는다.
- 모델 콜백 호출 실패 및 provider 부재는 `ModelUnavailable`으로 종료. 모의 실행은 명시적 `TEST_ONLY`, 외부 모델 주입 경로는 `EXTERNAL_MCP_UNVERIFIED`로 구분. 반환값 `real_provider_verified`는 TEST_ONLY에서 무조건 false, 일반 경로에서도 기존 `model_capture_audit.independent_model_invocation_verified` 근거만 사용하며 콜백 자체가 모델 출처 증명이 되지 않는다. **실제 ChatGPT 모델을 호출하는 SDK·네트워크 로직이나 자동 백그라운드 프로세스는 아직 없음.**
- `max_model_calls`, `max_retries_per_checkpoint`, `should_stop` 명시적 중지·예산 경계. 주문 가능 혹은 독립 OOS가 활성화된 상태 또는 상태/세대 수가 불일치할 경우 FAIL-CLOSED.

## 실측 테스트 및 수락 기준

신규 `tests/integrations/test_t4_checkpoint_orchestrator.py` (9개 테스트):
- in-memory 가짜 체크포인트/가짜 연구 모델에서 **20→100 (80세대)** 연속 자동 전이; 160 가짜 응답(계획+진단) 및 P5가 아닌 TEST_ONLY 판정 (실제 GPT 80세대로 계산하지 않음).
- 계획 및 진단 제출 직후 응답 유실, 체크포인트 영수증 확인 후 재진행(중복 커밋 차단).
- 계획·S7 품질 거절시 같은 토큰으로 재작성; 지정한 재시도 상한 초과시 원장 count 미증가.
- 모델 콜백 실패 후 다음 호출에서 체크포인트 재개, 중간 모델 호출 예산 종료 후 진단 단계 재개.
- provider 없음/주문 게이트 위반시 실제 제출 시작 전 거절.
- **실제** `AcademicMCPCheckpointService`의 격리된 테스트시장·모의 응답을 사용해 Plan→Audit→진단→S7→1 counted 완결을 검증, **TEST_ONLY로 표시**.

실행 결과: 신규 9 PASS, 관련 포함 24 PASS (2026-10-24). 전체 `ruff check .` PASS, 신규 제어기 `mypy` PASS, `git diff --check` PASS. **전체 저장소 pytest/mypy NOT RUN**.

## 실제 P5 보호 재검증

원본 P5 `3b44e05e52b3497db6fa035681ed0a5d`, `/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024`. 현재 **20/100, AWAITING_PLAN(G21)**. `run_checkpoint_loop(..., model=None)`을 직접 실행해 **P0_ACTUAL_PROVIDER_BLOCKED** 에러가 발생함을 확인하고, 호출 전후 기존 `history` 동일·20/100 그대로·orders=false·OOS=false 확인. 라이브 GPT 신규 세대 **0개**, 이전 결과 보존. 대시보드 데이터 변경 없음.

## 후속 고정 T4 경로와 변경 승인 경계

1. **P0 BLOCKED**: 원래 승인된 ChatGPT↔MCP를 유지하면서 세대별 외부 GPT 콜백을 지속 호출하는 **실제 지원 호스트**의 능력/권한/실제 호출 영수증을 확보. 이것은 테스트 콜백만으로 입증 불가. 독립 `model_capture_audit`에서 provider invocation verified가 되도록 실제 도구 호출 감사 연결 필요.
2. 호스트가 지원되지 않으면 **기본 제공자 교체 없이** 별도 API 어댑터 도입의 옵션/인증·비용을 제시하고 **사용자 별도 명시 승인 및 ADR 전에는 구현/실제 호출 금지**. 사용자가 기존 OAuth 재발급을 승인한 것으로 간주 금지.
3. P0 해결 후 실제 외부 GPT로 격리된 1→소규모 연속 연구 확인(기존 R/P4 보존), 실제 MCP+QA 원장 동등성 및 영수증 확인한 뒤 기존 P5의 G21~G100 재개. 연구 중 세대 수/성과는 정식 원장만 인정.
4. 이후 원래 고정 순서 V05→T4→V01~V04 독립 PIT/OOS→V06 paper only→V07 GO/NO-GO. 실주문 비활성 유지.

**완료 판정:** P1 상태 제어기 및 테스트는 코드 완료, **P0 연속 실제 GPT 실행과 P5 100/100은 미달**. 모의 100/100 PASS와 실제 GPT 자율 완료를 혼동해서는 안 된다.
