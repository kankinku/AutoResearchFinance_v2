# Quant Autoresearch — 기본 LLM 연구 경로: 기존 ChatGPT MCP

상태: **개발 및 운영 적용 대상 정책**. 승인일 2026-10-15. 사용자가 **'기존의 mcp방식을 기본으로 설정'**하도록 명시한 결정을 구현한다.

## 실행 우선순위

1. **기본 `mcp`**: 이미 인증·연결된 ChatGPT가 LLM 연구 책임자가 되어 기존 MCP 리소스에서 전략을 설계한다. Quant 서버는 지표 카탈로그/타입드 StrategyIR/백테스트/거래 감사/진단 기록/세대별 S7·S8 증거 제공만 수행한다. 서버는 ChatGPT 모델을 내부적으로 호출하거나 유료 API를 자동 실행하지 않는다.
2. **예외 `openai-api`**: 운영자가 명시적으로 `--execution-mode openai-api --model <모델명>`을 지정하고 `OPENAI_API_KEY`를 제공한 *해당 CLI 실행에서만* 별도 OpenAI Responses API를 사용할 수 있다. `OPENAI_API_KEY`가 환경에 존재하는 것만으로는 전환하지 않으며, MCP URL·OAuth 키/DB도 변경하지 않는다. 별도 API 과금이 발생할 수 있으므로 기본 비활성.

## 기존 MCP 호출 순서

- `get_research_brief` / `list_market_data`: 가용 데이터와 기본 연구 경로 확인
- `start_algorithm_research(data_path,generations)`: 요청한 1~100세대의 연구 세션 생성; `checkpoint_token`과 `model_context`를 받음
- ChatGPT가 **실제 지표·시장 자료를 근거로** `AlgorithmPlan` 설계 후 `submit_algorithm_plan` 호출
- 반환된 실제 거래별 진단·원장 증거를 읽고 ChatGPT가 `DiagnosticResponse` 작성 후 `submit_algorithm_diagnosis` 호출
- `evaluate_algorithm_experiments`로 해당 세대의 가설에 대한 원본 대조 실험 완료 및 연구 기억 저장
- `get_algorithm_research`로 저장된 원장과 다음 세대 `research_direction` 확인; 완료 세대 수만큼 반복
- 통신 장애: `get_algorithm_research`로 실제 checkpoint 상태 확인, 필요 시 `resume_algorithm_research` / `reconcile_algorithm_research`, 작업 종료 시 `cancel_algorithm_research`.

**정확한 동작 한계:** MCP 자체가 서버 안에서 ChatGPT를 자율적으로 호출하는 것은 아니다. ChatGPT 쪽 클라이언트가 각 세대의 연구 도구를 반복 호출해야 한다. '기본을 MCP'로 설정했다고 서버 단독 10~100세대 모델 연구가 자동 실행되지는 않는다. 호출당 앱/모델 제한도 그대로 적용된다.

## 코드로 고정된 내용

- 중앙 정책 `research/llm/execution_policy.py`의 `DEFAULT_RESEARCH_EXECUTION_MODE='mcp'`; `research_execution_policy()` 메타데이터에는 MCP 기본·API 명시적 옵트인·실거래 비활성 포함.
- 기존 MCP의 `get_research_brief`와 `get_algorithm_research` 출력에 기본 모드를 광고. 기존 `llm_controller` 필드와 32개 MCP 도구는 **그대로 유지**하며 새 URL이나 인증 등록을 요구하지 않는다.
- 독립 CLI `scripts/run_academic_autopilot.py`는 `--execution-mode` 기본값도 `mcp`로 설정. 이 상태에서 실행하면 기존 MCP 도구 사용 안내를 반환하고 **세션/DB를 만들거나 유료 모델 요청을 하지 않는다**. API 모드를 원하면 `--execution-mode openai-api` 및 `--model`, `OPENAI_API_KEY`를 모두 명시해야 한다. `--model`만 제공하고 모드를 생략하는 실수는 거부한다.
- 기존 `checkpoint_autopilot.py` 자체와 `openai_response_transport.py`의 별도 API 수단은 삭제하지 않고 선택형으로 유지한다. MCP에서 실행되는 통상 연구 경로에는 API 키가 필요하지 않다.

## 운영상 보존 항목

- 등록된 MCP 주소: `https://project-moon.taild689f9.ts.net/quant/mcp`
- 기존 OAuth issuer/승인키/승인 DB, 지정 연구 원장, 버전별 catalog DB, 예전 핀 런타임과 롤백 브랜치 **보존**.
- 연구는 DEVELOPMENT·non-PIT 범위에서 실행하고 주문·실거래 권한은 계속 비활성. 별도 LLM API 키 주입, 앱 삭제·재등록, 모델 사용료 발생 작업을 자동으로 시작하지 않는다.

## 검증 기준

- 연결된 MCP `get_research_brief`의 `research_execution_policy.default_mode`가 `mcp`.
- 기존 연구 세션 `get_algorithm_research`의 `llm_controller`는 `authenticated_chatgpt_mcp_client`, `research_execution_policy.default_mode`는 `mcp`.
- 별도 CLI를 API 키가 있는 가짜 환경으로 실행해도 모드를 선택하지 않으면 모델/서비스 객체 생성이나 데이터 변경이 없고 MCP 지시문만 나오는 것.
- API 모드에서 모델 지정·키 누락 시 실패, API 모드가 아닌데 `--model`만 준 경우도 실패.
- 기존 MCP URL·32개 도구·OAuth 인증·연구 원장과 백테스트에 회귀 영향 없음.

- Full suite: 1,392 passed, 0 failed, 482.44 seconds.
- Ruff and mypy: 231 Python files passed.
