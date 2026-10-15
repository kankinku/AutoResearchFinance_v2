# Quant Autoresearch D07 / 2-1 — MCP 32개 계약 및 운영 연결성 검사

기준: 2026-10-16 KST (2026-10-15 UTC). 기능 브랜치 `feat/d07-mcp-public-contract-gates-20261016`, 코드 커밋 `18c1bbb` GitHub Push 완료. **운영 서버 미배포**.

## 직접 확인한 운영 상태

- 이 대화에 연결된 Quant Autoresearch 도구 정의 **32개** 직접 확인. 실제 연결의 읽기 전용 `get_research_brief` 결과 서버 툴 수 **32개**; `get_workspace_status` 는 `READY`; `orders_enabled=false`, 기본 GPT 연구방식 `authenticated_chatgpt_mcp_client`. 별도 OpenAI API 모델 자동 호출은 비활성.
- 고정 URL `https://project-moon.taild689f9.ts.net/quant/mcp` 미인증 요청 **401** 확인. 서비스 프로세스는 기존 `AutoResearchFinance_v2-phase3-5-1-inventory`에서 실행 중. OAuth 승인·등록·URL 변경, 서비스 재시작, 실제 외부 계정 실행 없음.
- 연결 및 메타데이터 조회는 실제 운영 서버에서 실행했으나, 32개 각 도구의 데이터 변경/연구 실행 전체 성공을 주장하지 않는다.

## D07 개발 코드

- `integrations/chatgpt_mcp_sdk.py`: 공표된 JSON Schema 32개를 각각 검증한 뒤 외부 MCP 진입점에서 **dispatch 전에** 필드명/필수 필드/타입/정수 범위/토큰 형식/날짜 형식/enum과 입력 크기(256KiB)를 검증. 오류 반환은 `INVALID_TOOL_ARGUMENTS`, `orders_enabled=false`; 비밀값·입력 페이로드를 결과나 감사 로그에 출력하지 않음.
- `pyproject.toml`의 `jsonschema>=4.18,<5` 명시. 현재 public 32개 tool 이름·입력 스키마·내부 legacy 13 tool ABI·MCP 인증 endpoint 불변.
- `test_mcp_public_contract_d07.py`: 32개 모든 유효 입력이 각 tool dispatcher에 단 1회 전달되고, 32개 모두 알 수 없는 필드 요청은 내부 실행 호출 0회로 차단됨. 필수값 누락, 잘못된 데이터 타입과 날짜, 범위 초과, 승인되지 않은 tool 명칭도 거부하는 격리된 SDK 테스트.

## 실제 테스트

- 신규 D07 관련 **5 PASS**. HTTP bearer/OAuth 보안, 기존 SDK, Academic Plan→Diagnosis·S7, D01/D02 중복 복구, D05 실패 증거, D06 다자산 등을 묶은 9개 테스트 파일 **69 PASS**. Ruff/Mypy 변경 모듈 PASS; diff 검사 PASS.
- T3 전체 저장소 Pytest/Ruff/Mypy, T4 실제 외부 GPT 10/100세대·장시간 중단, T5 원본 PIT/OOS/경제성, T6 paper 및 모든 32개 운영 상태 변경 tool 실호출 **미실행**.
- **연결성 누락**: D01/D02/D05는 개발판 Academic MCP 경로에 있음(미배포). D03/D04 및 D06은 로컬 CLI 개발 기능이며 현재 MCP 32개에 직접 노출되지 않았음. 추가 연결 방식과 기존 도구 32개 계약 유지 방안은 D08에서 결정.

## 다음: D08 / 5-1

D01~D07 기능 병합 후 실제 배포 종속성·소스 커밋·DB 스키마와 immutable evidence 보존을 검증. 기존 URL/OAuth 등록·클라이언트 자격 정보 유지, 프로세스 롤백 점검. D03/D04/D06 안전한 MCP 접근 경로의 필요성 검토. 그 뒤 V01~V07 독립 가격 빈티지, PIT, sealed OOS, 통계/비용 및 모의거래 최종 검증.

**D07 결론:** 개발판 스키마 사전 검증 및 관련 회귀 PASS. 운영 상태 연결 32/32, READY, 401 확인. 서버에 아직 새 기능 미배포·운영 mutation E2E 미실행.
