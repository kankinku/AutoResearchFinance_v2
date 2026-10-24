# ADR 제안 — T4 GPT 장기 실행 모델 호스트 선택 (미승인)

- 날짜: 2026-10-24
- 상태: **PROPOSED — NOT USER APPROVED / NOT IMPLEMENTED**
- 대응: 원래 20문답 Q02,Q06,Q07,Q08,Q15,Q17,Q20 및 사용자 승인된 T4 단계.
- 변하지 않는 조건: 20/100 기존 P5 원장 보존, GPT↔MCP 기본/URL/OAuth 유지, 개발 데이터만 연구, 실거래 OFF, 봉인 OOS 및 검증 gate 유지.

## 발생 문제

기존 ChatGPT MCP 도구는 사용자 채팅 모델이 Plan과 진단을 제출할 때까지 기다린다. 리모트 Moon 워커에서 다른 모델을 호출할 권한/SDK/자격증명이나 ChatGPT 클라이언트의 무인 모델 반복 호출 capability가 발견되지 않았다. 80개 세대 checkpoint controller는 TEST_ONLY 장기 시뮬레이션만 통과했으며 실제 LLM 생성이 아니다.

## 허용 검토 옵션 (승인 전 구현 금지인 항목 명시)

**A: 기존 ChatGPT가 지원하는 영속 실행 호스트를 공급받는 방식 (우선 검토).** 모델 판단과 MCP 도구 호출을 호스트가 관리하며 모델/응답 ID를 세대별 연결한다. Moon은 원래 AcademicMCPCheckpointService만 호출한다. *이 환경에서 실제 제공자 콜백 기능이 입증되지 않아 현재 불가*. 호스트가 승인된 기능으로 제공되고 기존 인증을 재사용하면 변경 범위 최소. 호스트의 무인 실행·청구·중단/권한·대화 내 출처 영수증 증거 확인 전 GO 불가.

**B: 별도 OpenAI API/Agents SDK/Responses 모델 실행자 (명시 승인 필요).** 외부 서버가 모델을 직접 호출하고 ChatGPT↔MCP 전략 검증 서비스를 툴로 호출. `OpenAI API`의 원격 MCP 도구 연결은 공식 지원되지만 ChatGPT 구독 OAuth를 API 과금자격으로 자동 사용할 수 없음. 이 방식은 신규 비용/키/권한/모델·보안경계 및 원래 default model 교체 위험이 있으므로 **사용자 별도 승인과 보안 ADR 없이 키 설정/비용 발생/설치/기본 경로 전환 금지**. 기존 MCP는 병렬 검증 도구로 유지 가능하지만 원래 채팅 모델이 아닌 별도 API 모델의 판단이 되므로 연구 계보에 이를 명시할 것.

**C: MCP 클라이언트 sampling/createMessage (권장하지 않음).** 구형 버전에서만 이용 가능한 클라이언트→서버 반대방향 샘플링 인터페이스로 2026-07-28부터 deprecated, 클라이언트의 지원 여부 미검증. 새로운 자동 연구 호스트의 필수 의존성으로 설계하지 않음.

공식 문서:
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- https://developers.openai.com/api/docs/guides/agents-api/tools/mcp
- https://py.sdk.modelcontextprotocol.io/v2/handlers/sampling-and-roots/

## 승인 이후 성공 판정(사전 연구 우회 금지)

1. 운영 계정/키를 리포지토리에 노출하지 않고, 모델 호출 영수증(실제 provider ID, request/response, 비용·사용량)과 checkpoint payload hash 연결.
2. 실제 GPT 1세대 plan→canonical backtest→trade-ID analysis→S7→counted evidence 결속 검증; 모의 컨트롤과 독립 표시.
3. 3세대 연속 생성·같은 세션 재시작·중복 거절 재작성 검증; 모델 출처/인증/원장 일관.
4. P5 G21~100 진짜 모델 연구: 내부 수동 반복/단일 결정적 배치로 100을 채우지 않음. 외부 시장 PIT/봉인 OOS는 별도 V01~V04 보류.

**사용자 명시 승인 상태: 아직 없음.** 위는 기술 선택안을 명문화한 것이지 기존 OAuth·MCP를 교체하는 개발 승인 기록이 아니다.
