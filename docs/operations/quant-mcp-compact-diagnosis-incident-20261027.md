# Quant MCP 압축 변경과 진단 제출 차단 — 사고 조사

- 기준일: 2026-10-27 KST
- 대상: 기존 Quant 운영 ChatGPT MCP, 학술 세션 (146/150, AWAITING_DIAGNOSIS)
- 범위: **읽기 전용 진단**. 운영 연구 원장·OAuth·기존 URL·실거래 설정 및 코드 변경 없음.

## 확인된 사실

1. 운영 소스 Git 커밋 `1d5ec9d`은 2026-10-27 20:22 KST에 `integrations/chatgpt_mcp_sdk.py`의 세 도구(`get_algorithm_research`, `submit_algorithm_plan`, `submit_algorithm_diagnosis`)의 생략형 `response_mode` 기본값을 `full`에서 `compact`로 바꾸었다. 서명·체결·진단 평가 코어의 인자는 변경하지 않았다.
2. 서버의 `ChatGPTMCPAdapter.call_tool`은 도구 입력 JSON/schema 검증 → canonical `super().call_tool` 호출 → 성공 응답 분석·압축 순으로 동작한다. 압축 실패한 **성공 쓰기**에는 `FULL_FALLBACK_AFTER_SUCCESSFUL_WRITE`로 원래 성공 결과를 반환하고, 읽기 전용 압축 실패에는 `COMPACT_CHECKPOINT_UNAVAILABLE`을 반환한다.
3. 운영 MCP 감사 원장 `state/moon-http/research/logs/mcp-events.jsonl` 기준 해당 시도 시간대(20:36~20:39 KST)에 `get_algorithm_research`는 정상 기록됐다. `submit_algorithm_diagnosis` 서버 수신 기록은 없었다. 직전 기록된 성공 진단은 18:56 KST였으며, 변경 배포 이전에 해당한다. 이 사실은 클라이언트/플랫폼에서 서버 도달 전에 거절했음을 지지하지만 **플랫폼 차단의 구체적인 내부 규칙/사유를 입증하지 않는다.**
4. 사용자의 Quant AutoResearch 앱별 권한은 `Allow all actions`으로 조회됐다. 앱 접근권한 부족은 현재 직접 근거가 없다. 앱별 권한과 ChatGPT 별도 안전 검사는 동일하지 않다.
5. 이 조사 시점에 연결된 ChatGPT의 `get_algorithm_research`/두 제출 도구는 모두 `response_mode?: full | compact`를 노출한다. 과거 구 도구 캐시는 당시 확인됐으나 **현재에도 명세 누락이 지속된다고 단정할 수 없다.**
6. 같은 운영 세션을 명시적 `full` 및 `compact`로 별도 조회했다. 양쪽 모두 **146/150, AWAITING_DIAGNOSIS**, checkpoint token, 최신 증거 hash, `model_context.context_hash`, `model_context.audit_hash`가 정확히 일치했다. `full` 출력 약 1,210,221(JSON 문자) 및 역사 146개, `compact` 약 41,026(JSON 문자) 및 역사 최신 1개. 연구 판단 원문 변경 증거 없음.
7. 개발 저장소는 운영 `chatgpt_mcp_sdk.py` SHA256이 동일하며 격리 체크포인트 GET/PLAN/DIAG/복구·합성 규모 테스트 12/12 PASS(2026-10-27). **실운영 GPT 재제출 1회 통과 증거는 아직 없음.** 12 PASS는 ChatGPT 클라이언트 안전 검사 자체를 포함하지 않는다.

## 결론 / 확신 범위

- **확정:** 서버 어댑터의 세 도구 응답 기본값이 수정됐고, 현재 체크포인트의 내용 해시/토큰은 full/compact 간 정확히 일치한다.
- **확정:** 문제가 된 진단 제출은 서버 감사 로그에 없다. 서버가 진단을 받아 평가한 뒤 압축하다 실패했다는 가설과 맞지 않는다.
- **미확정:** 클라이언트의 도구 명세 캐시 변동 또는 모델/금융-도구 쓰기 안전 게이트가 왜 해당 제출 요청을 사전 차단했는지. 이 거절 규칙은 Moon/Quant 서버 로그로 확인할 수 없다.
- **운영 위험:** 기본 쓰기 응답 포맷이 달라졌으므로 전체 `history`를 기대하는 레거시 소비자는 `response_mode=full`을 명시해야 한다. 이는 실제 호환성 영향이지만 해당 플랫폼 차단의 입증된 원인은 아니다.

## 권장 후속 검증

1. 연결된 ChatGPT 클라이언트에 현재 도구 명세가 반영된 상태에서 **안전 게이트를 우회하지 않고** 사용자가 요청하는 정상 진단 제출 1회를 시도해 감사 로그에서 실제 서버 도달 여부 확인. 현재 정상 조사에는 라이브 연구 쓰기를 포함하지 않았다.
2. 만약 동일한 “OpenAI safety check” 오류가 반복되고 서버 `tool_call`이 없다면, 플랫폼 측 도구 사전검사 문제로 분리. 시각, 앱 이름, 도구명, 오류 메시지, 사용자 승인 맥락만 포함해 제품 지원 경로에서 확인 요청. 체크포인트 토큰/실계좌 키는 보내지 않는다.
3. 서버에 요청이 도달한 후에만 `INVALID_TOOL_ARGUMENTS`·diagnostic hash/contract·성공 후 반환 압축 오류를 각각 분리해 로컬 수정. 코어 증거 규칙이나 금융/플랫폼 안전 검사를 완화하지 않는다.
4. 추후 호환성 회귀 테스트에서 쓰기 반환 `response_mode=full`과 `compact`의 단계·해시·토큰 동일성, 성공 후 압축 실패 시 거짓 오류 없음, 100세대 history 비중과 컨텍스트 누적량을 별도 측정한다.

## 비변경 범위

146/150 공식 세대 및 현재 진단 대기 체크포인트, 부모 계승/전략 점수, 원장·증거 SHA, 현재 MCP URL/OAuth, 명시적 paper-only/실주문 OFF, OOS 잠금, 32개 도구 유지. 별도 SDK 모델 호출/자동 연구 세대 진행 없음.
