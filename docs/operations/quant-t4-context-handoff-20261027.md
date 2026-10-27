# Quant T4 대화 컨텍스트·세대 복구 운영 절차 (2026-10-27)

## 연구 계보와 세션을 혼동하지 말 것

`get_research_brief.generation` 또는 `get_workspace_status`의 Champion 상태는 독립 GPT 학술 연구 세션의 세대와 동일하지 않다. `get_research_batch_status`의 100/100 또한 고정 ResearchIntent 로컬 배치이며 매 세대 GPT가 진단한 세대 수가 아니다. **학술 세대 재개는 검증된 `session_id`의 `get_algorithm_research`가 권위자**이다.

## ChatGPT/MCP 컨텍스트 사용

1. 기존 Quant 연결과 `session_id`로 `get_algorithm_research`를 조회한다. 최신 서버에서는 `response_mode` 생략도 compact이며, 갱신된 클라이언트라면 명시적 `compact`를 사용할 수 있다. 진단/계획 **제출**에도 동일 기본 표현이 적용된다.
2. 응답 `checkpoint_phase`, `completed_generations`, `requested_generations`, `continuation.required_model_action`, `checkpoint_token`, `last_completed_evidence_hash`를 확인한다. 그 단계의 **현재** `model_context`로만 GPT가 전략/진단을 작성하고 기존 제출 도구로 보낸다. 모델 호출은 현 대화가 담당하며 서버 자체는 다음 GPT 턴을 생성하지 않는다.
3. 응답이 유실되거나 다른 대화로 전환하면 **이전 채팅 내용으로 제출을 추측하지 않고** 같은 `session_id`로 현재 체크포인트를 재조회한다. `AWAITING_DIAGNOSIS`면 이미 계획 제출됐으므로 진단부터 진행; `AWAITING_PLAN`이면 새 계획 제출. `INTERRUPTED`면 무결성/해당 세션 확인 후 명시 재개. 해시/토큰 충돌이면 진행 중단.
4. 전체 기록이 꼭 필요하면 `response_mode=full`을 명시한다. 도구 명세에 이 옵션이 없는 오래된 ChatGPT 연결에서는 기존 Quant 앱 연결을 **다시 로드/새 대화**해 도구 명세 갱신을 시도하되, 기존 MCP URL 및 OAuth 등록을 다시 생성하지 않는다. 전체 원장은 서버에 보존된다.

## 컨텍스트 비용 및 실패 관측

- 대시보드와 연구 요약은 기존 `summary` 모드로 기본 압축(실측 대략 18KB씩). 학술 GPT 체크포인트는 **타입드 의사결정 컨텍스트**가 커서 실제 68세대 압축 약 110KB; 사용자가 언급한 32KB는 목표이지 현재 달성 사실이 아니다. 128KiB 초과 시 읽기 요청은 `COMPACT_CHECKPOINT_UNAVAILABLE`을 표시하고 중요한 필드를 임의로 삭제하지 않는다.
- 성공한 제출 응답 압축 실패는 `FULL_FALLBACK_AFTER_SUCCESSFUL_WRITE`이므로 **동일 계획/진단을 무턱대고 재제출하면 안 된다.** 먼저 현재 체크포인트를 재조회한다.
- 10/25/50/100 history 전송 성능 테스트는 **합성/모의**로 표시한다. 진짜 GPT 모델 세대가 100까지 자동 진행된다고 해석하지 않는다. 서버에 의한 무인 채팅 턴 생성은 없고, 진짜 GPT가 매 세대 생성·진단해야만 세대가 성립한다.
- 유효한 판정 지표: 각 호출의 JSON bytes, 세대 수, Evidence head, phase, checkpoint token, 중복/누락 세대, 재조회 후 실제 복원 동작, 반환 오류 및 연구 원장 원상 보존. 문자 수와 모델 유료 토큰/컨텍스트 여유는 다르다.

## 변경 안전성

현재 URL/OAuth·원장/증거 해시·최고 전략·부모 선택/조합·독립 OOS 잠금·실주문 OFF를 그대로 둔다. 실제 운영 재기동은 기존 3DB 검증 가능한 백업과 32 tools, 인증된 무변경 세션 확인 후에만 수행한다. 이 문서는 재개 절차이고 연구 실행 요청 또는 실거래 허가가 아니다.
