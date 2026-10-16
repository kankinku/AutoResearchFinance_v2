# T4 중복 후보 자동 재제안 및 안전 복구 연계 — 2026-10-16

## 작업 목적과 범위
- 고정된 원본 20문답(Q02/Q06/Q08/Q15/Q17/Q20), 같은 100세대 연구 세션, 기존 MCP/OAuth/32개 도구와 실거래 비활성 정책을 변경하지 않는다.
- 기존 `AcademicMCPCheckpointService.submit_plan`의 중복 사전 검사(기존 운영 릴리스 `2622f14`)는 그대로 유지. 새 작업은 **상위 연구 실행기가 구체적인 중복 원인을 받아 모델에 새 계획을 요구하도록 연결**한다.
- 운영 기본값은 여전히 `authenticated_chatgpt_mcp_client`. 명시적 유료 API opt-in 없이 `OPENAI_API_KEY`를 요구하거나 새로운 호출 주체를 만들지 않는다.

## 구현
1. `DuplicateAlgorithmPlanError`: 유효한 두 오류 코드(`DUPLICATE_SEMANTIC_PLAN`, `DUPLICATE_EFFECTIVE_SIGNALS`)와 기존 동일 전략 세대 번호를 가진 **타입이 명확한** 오류. 기존 `ValueError`를 상속하므로 종전 MCP·테스트 호환성을 유지. 이 오류는 DB 체크포인트를 소비하기 전에만 발생한다.
2. `AcademicCheckpointAutopilot`: 외부 공급자의 `AlgorithmPlan` 제안이 중복이라면 동일 `AWAITING_PLAN`에서 최대 **3번 추가 GPT 재제안**한다. 각 호출에 타입·기존 동일 세대·남은 재시도 횟수·실질 신호를 바꾸라는 지침을 추가한다. 원래 `model_context`는 복제하여 요청에만 힌트를 추가한다. signed diagnostic context/원본 model_context/증거 원장은 변경하지 않는다.
3. **매번** 서버의 authoritative state를 다시 읽어 session/dataset/requested generations/orders OFF/OOS 미승인/status/phase/checkpoint token/완료 세대/immutable history를 검증하고, 일치하지 않으면 `AutonomousLoopError`로 안전 중단. 일반 `ValueError`/통신/권한/해시 오류는 중복이라고 추측해 자동 재제출하지 않는다.
4. 최대 시도 후 `DuplicateProposalRetryExceeded` → `SafeCheckpointRecoveryController`가 `HOLD_DUPLICATE_BUDGET`을 감사 로그에 기록하고 한 세대도 새로 커밋하지 않고 검토 대기. 상위 복구 제어기가 재시도 한도를 초기화해 무한 반복하는 일을 방지.
5. 실행 결과에 실제 재제안이 거절된 횟수 `rejected_duplicate_proposals_this_call` 반환. 이 횟수 자체가 연구 완료 세대나 백테스트 성과로 카운트되지 않음.

## 검증
- 초기에 신규 독립 오류 주입 테스트 5 PASS. 기존 MCP·S7·autopilot·복구·원본 20문답 범위 잠금 등 통합 **61 PASS**. 새 감사 로그 검증을 추가했으며 최신 정적 Ruff, Mypy 검사를 통과.
- 신규 시나리오: 세대 1 완료 후 2세대 중복 후보 입력→타입 에러 및 모델 재제안→세대 2 정상 커밋·각 S7 SHA 일치. 4회 연속 중복은 최초 제안+추가 3회 뒤 검토 대기하고 원장/토큰 보존. 일반 서버 오류는 다시 전송하지 않음. typed 오류 코드는 임의 문자열로 조작할 수 없음.
- 이 테스트의 제안 주체는 **테스트용 scripted provider**, 실제 GPT가 100세대 연구를 완료했다는 증빙이 아니다.

## 현재 운용 상태 및 미완료
- 기존 실제 연구는 가장 최근 확증으로 **32/100, 다음 `AWAITING_PLAN`**, S7 미측정 0, 실주문 OFF. 이번 작업은 실제 33세대 연구를 요청하지 않음.
- **신규 모델 실행기·복구 연동 코드는 개발 브랜치에 구현된 상태**. MCP 운영 기본 provider는 채팅 밖에서 지속 GPT 호출을 지원하지 않는다. 대화 종료 후 무인 실행은 여전히 `PROVIDER_REQUIRED`/BLOCKED인 외부 의존.
- 기본 MCP를 외부 모델 API로 전환하는 것은 원본 범위 잠금에 의해 명시 승인 없이 금지. 상주 실행 주체, 키·비용 상한·모델 선택·동시 실행 제어 및 정책 승인 후 정상 배포 검증이 다음 작업. 운영 MCP URL·OAuth·과거 원장은 그대로 유지.

## 다음 고정 작업
- 연결 가능한 승인된 GPT 호출 주체 여부 확정 및 기존 MCP 실행기 연계.
- 단일 실행 소유권, 중지·재개·heartbeat/통계·비용 상한 검증, 실제 연결된 GPT 33~100세대 완료 증거 검증.
- 이후 V01~V04 PIT/기준선/OOS 검증, V06 paper-only, V07 GO/NO-GO 순서 유지.
