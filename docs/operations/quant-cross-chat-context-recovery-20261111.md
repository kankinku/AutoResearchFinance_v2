# Quant GPT 대화가 바뀌어도 연구 이어가기 — 운영 안내 (2026-11-11)

## 사용 방법
- 새 채팅, 컨텍스트 압축 이후 또는 다른 GPT 작업 공간에서 "Quant 연구 이어서. 서버 상태부터 확인해"라고 요청한다.
- GPT는 기존 Quant AutoResearch MCP의 **get_research_brief({})**를 먼저 호출한다. 이 도구는 이제 저장된 SQLite의 살아 있는 연구 세션 ID, G 진행률, 다음 체크포인트 단계, 최근 3세대 실측 결과, 최근 2개 S7 대조결과만 반환한다.
- 하나의 활성 세션이면 algorithm_research_handoff.next_read에 적힌 **get_algorithm_research({session_id, response_mode:"compact"})**를 실행한다. 이때 다음 작업의 최신 모델 입력 스키마/기술 근거와 **현재 체크포인트 토큰**을 읽는다.
- 이후 GPT가 Plan 또는 Diagnosis를 제출하면 서버가 원본 DB에 증거를 영구 보관한다. 다른 채팅은 같은 순서로 독립 재접속한다.
- 복수 세션일 경우 선택을 요구하며, RUNNING/INTERRUPTED는 과거 작업자 중단을 확인하기 전 자동 재개하지 않는다.
- **한계:** MCP 서버가 GPT의 새 대화가 생성된 순간을 감지해 저절로 도구를 호출할 수는 없다. 관련 요청을 받은 GPT가 이 조회를 해야 한다. 상세 내용을 모두 프롬프트에 넣거나 새 요약 DB에 복사할 필요는 없다.

## 보존 정책
- 유일한 정본: 기존 academic-gpt-checkpoints/gateway.sqlite, cycles.sqlite 및 S7 보고.
- 요약/핸드오프: 세션 ID, 진행률, 단계, 원본 증거 해시, 지표 3건, 실험 2건만 (8KiB 미만).
- 자세한 기술 조회: Plan/Diagnosis 작성 시점에만 원본 checkpoint 도구를 호출한다.
- 기존 승인된 32 MCP 도구, 서버 공개 URL, OAuth 토큰, 전략 원장, 실주문 OFF 및 PIT/OOS 차단은 수정하지 않는다.
- 기존 G150 기록은 새 G1/G10의 부모나 모델 메모리로 연결하지 않는다.

## 장애 시
- brief에 "NO_ACTIVE_RESEARCH": 새 연구가 없는지 DB가 실제로 없는지 점검한다. ID나 40세대 진행을 임의 추정하지 않는다.
- "SELECTION_REQUIRED": 반환된 활성 세션 ID 중 사용자가 선택한 세션만 참조한다.
- "OPERATOR_RECOVERY_REQUIRED": 이전 연구 작업자가 실제로 종료됐는지 확인하고 기존 reconcile 도구 절차를 따른다.
- 기존 OAuth MCP 서버가 HTTP 502이면 이 기능은 원격 ChatGPT에서 호출할 수 없으므로 **서버 운영/프로세스 자동 재시작**이 필요하다. 서버에 저장된 기록은 그대로 남아 있다.
- 기록 해시와 원장 간 불일치가 있으면 자동 계속 진행하지 않는다.

## 검증
- 최초 RED: 4개 복구 시나리오 실패 → 구현 후 전체 연관 회귀 테스트 통과.
- 합성 데이터만 사용하는 동작 검증, 실제 G10/40 원장 읽기 검증 별도 실시.
- 100% 무인 연속 모델 호출 또는 새 채팅이 아무 지시 없이 자동 부팅됨을 의미하지 않는다.
