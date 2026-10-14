# Quant Autoresearch S4 — 기존 MCP URL 유지형 ChatGPT 연구 체크포인트

기준: 2026-10-14. 원 요구: **기존 Quant Autoresearch 앱을 재등록하지 않고 MCP URL을 그대로 유지**하며 S4의 GPT 기반 알고리즘 생성·백테스트·원인 분석을 연결한다.

## 절대 변경하지 않는 계약

- 기존 공개 리소스: `https://project-moon.taild689f9.ts.net/quant/mcp`.
- Moon nginx: `/quant/mcp` → 기존 loopback port 8787 `/mcp/`.
- OAuth 공개 기준 주소: `https://project-moon.taild689f9.ts.net/quant` (기존 pinned file 보존).
- 기존 OAuth 키·승인 sqlite·리프레시 토큰 저장 위치 변경/회전/초기화 금지.
- 기존 MCP 이름 24개 유지, 새 도구만 **additive**로 추가. 연결 해제, plugin 삭제·재등록, 리다이렉트/엔드포인트 변경 금지.
- 기존 운영 브랜치/원본 개발용 복구 커밋을 수정하지 않음; 소스 변경은 `feat/p0-indicator-research-engine-v1`에 커밋.

## 현재 신규 MCP 도구 (같은 URL의 tools/list)

- `start_algorithm_research(data_path, generations)` — 개발 데이터와 지표 카탈로그 고정, 세션·새 Plan 컨텍스트 생성.
- `get_algorithm_research(session_id)` — 세션 상태, 이전 결과와 다음에 GPT가 작성할 구조화 응답의 컨텍스트 조회.
- `submit_algorithm_plan(session_id,checkpoint_token,plan)` — *GPT가 직접 작성한* 구조화 AlgorithmPlan을 검증하고 실제 백테스트/판단 기록을 계산, 원인 분석용 증거 컨텍스트 반환.
- `submit_algorithm_diagnosis(session_id,checkpoint_token,diagnosis)` — GPT 원인 가설·반대 설명·실험 설계를 정확한 거래/평가 원장 해시와 대조하고 **한 세대를 커밋**, 다음 세대 입력 반환.
- `resume_algorithm_research(session_id)` — 중단된 세대에 대해 운영자의 명시적 재시도; 기존 완료 세대 보존.

**원리:** 서버는 LLM API를 내장하거나 모델 키를 보관하지 않는다. 인증된 ChatGPT MCP 클라이언트 자체가 Research Director이고, 두 시점마다 서버 증거를 확인해 모델이 Plan/Diagnosis를 제안한다. 사용자 인증은 기존 MCP OAuth가 담당한다. 이 호출 방식은 한 대화/워크플로 안에서 사용자의 세대별 수동 메시지 없이 여러 세대 진행 가능하나, ChatGPT 앱이 독립적으로 요청을 시작하는 무제한 백그라운드 연구 기능은 아니다.

**완료된 세대의 의미:** 생성된 Plan → 검증된 인디케이터와 비용 모델을 이용한 canonical backtest → 의사결정·체결 감사 → GPT의 **검증 전 원인 가설** + typed follow-up experiment → 이전 세대 해시와 링크된 체크포인트 저장. 의미상 같은 알고리즘 또는 **해당 개발 데이터에서 매매신호가 완전히 동일한 알고리즘**은 새로운 유효 세대로 세지 않는다.

## 상태 및 보안 경계

- 신규 연구 체크포인트는 기존 state dir 아래 별도의 `academic-gpt-checkpoints` 영역에만 저장. 기존 OAuth, 배치 워커/증거, 거래 데이터 파일을 수정하지 않음.
- 모든 입력 파일은 기존 `resolve_project_input` 로 project root 내부 `.parquet`만 허용하고, `DEVELOPMENT`만 평가 가능. Sealed OOS 및 실행·주문 권한 없음.
- 세대의 plan/diagnosis 단계를 분리한 32바이트 임의 checkpoint 토큰으로 중복 제출 차단. 주어진 토큰·단계·데이터/카탈로그 해시와 당시의 audit/diagnosis context를 다시 확인한다.
- 전송값의 오류는 기존 세대 원장을 수정하지 않는다. 상태가 비정상 종료 상태라면 자동으로 새 세대를 커밋하지 않는다.
- Plan은 인디케이터 **투표 비중**만 제어한다. 실제 투자금 배분이나 주문 실행이 아니다. 학술/개발 데이터의 결과는 independent OOS/PIT/live alpha가 아니다.

## 운영 적용 원칙

현재 공개 Quant HTTP 서버는 별도 복구용 Git 작업 디렉터리에서 시작한다. 실제 서버 코드를 새 기능이 있는 개발 작업 디렉터리로 바꾸더라도 `--project-root`는 **기존 운영 원본**을, `--state-dir`, `--public-url`, `--approval-key-file`은 **기존 절대 경로**를 사용한다. 새로운 server URL, OAuth issuer, approval DB를 만들지 않는다. 서비스 갱신 전후에는 주소 pin·OAuth 파일·비인증 401·OAuth metadata·기존 연결에서 `get_research_brief`를 확인한다. 실패 시 동일 URL과 기존 기동 스크립트로 롤백한다.

본 기능은 MCP 서버에서 모델을 호출하는 것이 아니라 기존 연결 클라이언트가 제출하는 진짜 GPT의 두 응답을 받아 처리하도록 **서버 능력을 추가**한 것이다. 새 5개 이름이 이미 열려 있는 오래된 채팅의 캐시 목록에 바로 나타나지 않을 수 있다. 이 경우 새 채팅에서 현재 연결 앱을 호출해 최신 tools/list를 확인하면 되며, 등록/URL 변경은 불필요하다. 새 채팅에서도 툴 목록이 갱신되지 않는다면 캐시의 문제로 구분해 보고하고, 도구가 이미 노출됐다고 가정하지 않는다.

## 개발 브랜치 최종 검증

- 단일/다세대 GPT 체크포인트 API, 잘못된 단계/nonce, 기존 도구 호환성, OAuth·HTTP 경로와 도구 추가 검증: **집중 테스트 61건 통과**.
- 저장소 전체 `pytest -q -p no:cacheprovider`: **1,337 passed / 0 failed / 415.62초**.
- `ruff check .` PASS; `mypy .` PASS (223 source files).
- OAuth·nginx route·public URL pin 구현 파일과 저장된 OAuth 데이터 형식을 변경하지 않았음. 인증 리소스 URL과 기존 도구 24개를 그대로 유지하고 MCP tools/list에 5개만 추가.
- 위 결과는 외부 GPT 도구 호출을 수용하는 서버 계약 및 mock-directed 2세대 백테스트 평가의 테스트. 실제 앱의 신규 도구 캐시 노출과 실제 GPT 대화의 후속 연구 능력은 운영 점검에서 별도 확인해야 함.
