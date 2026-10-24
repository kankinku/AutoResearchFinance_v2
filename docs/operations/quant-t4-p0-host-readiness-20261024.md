# T4-P0 모델 호스트 적격성 실측 — 2026-10-24

**원래 범위:** T4/S4/S5, Q02·Q06·Q07·Q09·Q15·Q17·Q20. **분류: 코드/읽기전용 진단 완료, 실제 모델 자동 호출 BLOCKED**.

## 왜 멈추는지 확인한 사항

- 기존 `research/llm/provider.py`의 `GPTIntentProvider`는 외부에서 작성된 객체를 전달하는 in-process adapter이고, 내부 GPT SDK/HTTP 호출이 없다. `ConfiguredJSONProvider`는 폐기됐으므로 원래 default MCP를 몰래 다른 모델로 교체하는 일이 없어야 한다.
- Moon 연구 실행 환경에서 `codex`, `claude`, `openai`, `ollama` 실행 파일 및 `OPENAI_API_KEY`·`ANTHROPIC_API_KEY`·`GOOGLE_API_KEY` 설정을 확인하지 못했다. 환경값은 읽지 않고 **존재 여부만** 확인했으며 Git에 자격증명을 저장하지 않았다.
- MCP 서버의 도구를 ChatGPT 클라이언트가 호출하는 것과 서버가 신규 GPT 응답을 독자적으로 생성하는 것은 다르다. 공식 API의 원격 MCP 통합도 별도 모델 실행 클라이언트를 전제로 함: https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- MCP `sampling/createMessage`는 서버→클라이언트 모델 요청이 가능한 구형 기능이지만 **MCP 2026-07-28 프로토콜에서 deprecated**. ChatGPT 클라이언트가 이 기능을 제공하는지 증명되지 않았다. 앞으로의 지속 연구 실행 기반으로 새로 도입하지 않는다. 근거: https://py.sdk.modelcontextprotocol.io/v2/handlers/sampling-and-roots/ 와 https://go.sdk.modelcontextprotocol.io/client/

## 실제 완료

- `application/t4_model_host_preflight.py`: 기존 `AcademicMCPCheckpointService.get`의 신뢰할 수 있는 상태를 사용하여 **READ_ONLY** 호스트 경계·계보/원장 수량·주문/OOS 차단·외부 모델 콜백 등록 여부·**제공자 독립 호출 증명**과 **단순 외부 수집기 서명**을 엄격히 분리한다. 콜백의 존재만으로 GPT 응답이 생성됐다고 인정하지 않는다. *과거* 제공자 증거가 있어도 *다음* 모델 호출의 보증이 되는 것은 아니므로 `can_advance_genuine_generations=false`를 유지한다.
- `scripts/quant_t4_host_readiness.py`: `--project-root --state-dir --session-file`을 명시하여 기존 격리 연구 원장을 조회하고 **컨텍스트/체크포인트 토큰/자격증명을 출력하지 않는** JSON을 반환. 인증된 실제 모델 호스트가 없으면 명시적 비영(2) 종료 코드. 거래나 모델 호출 없음.
- `tests/integrations/test_t4_model_host_preflight.py`: 호스트 미존재, 가짜 콜백, P4-2 수집기 서명과 공급자 서명 구별, 과거 모델 증거와 현재 호출 구별, 거래·OOS 경계 차단, 원장 상태/인증 유출 금지 등 **7건 테스트**.
- 실제 P5 조회 **20/100**, `AWAITING_PLAN` G21, 잔여 80; `status=BLOCKED_NO_AUTHENTICATED_MODEL_HOST`, `callback_present=false`, `model_invocation_verified=false`, `can_advance_genuine_generations=false`, `orders_enabled=false`, `independent_oos_approved=false`; CLI 종료 코드 2는 설계된 실패-차단. 사용자 원장 이력 추가 없음.
- scoped 테스트 `test_t4_model_host_preflight` + 기존 제어기 + 거버넌스 **20 PASS**. 전체 저장소 `ruff check .` PASS. 신규 `application/t4_model_host_preflight.py` mypy PASS. `mypy`를 스크립트 포함 두 파일에 적용 시 *기존 의존 파일* `application/academic_checkpoint_service.py`와 `research/llm/precommit_rejection_feedback.py`에서 **14건의 선행 타입 문제**가 노출됨: 현재 신규 module 자체의 오류는 없으며 이번 P0 범위의 기존 코어 수정은 하지 않는다. 전체 pytest/mypy NOT RUN.

## 다음 결정과 금지 사항

- **P0 비통과:** P5 100/100 실제 GPT는 미완료, 80세대 부풀리기 금지. 도구가 가진 Python 함수 객체가 곧 모델 공급자 증빙은 아니다.
- 기본 GPT↔MCP 모델 연결, 기존 OAuth·고정 URL, 실주문 비활성 및 봉인 OOS는 유지했다. 새로운 API 모델 호출을 사용자 승인 없이 구현·활성화하지 않았다.
- 승인 전환 옵션은 [모델 호스트 연결 제안 ADR](../decisions/2026-10-24-t4-model-host-options-proposed.md)에 **제안만** 기록. 실제 지속형 모델 호스트를 확인할 수 있으면 기존 연결 유지 방식으로 동작 검증하고, 그렇지 않으면 별도 API 세션 실행자·인증·비용에 대한 *사용자 명시 승인*을 받은 후에만 구현.
- 다음 수락 기준: 실제 공급자 응답의 독립 식별정보와 비용·모델 정보를 증거에 연동한 1세대 실연결 → 연속 3세대 및 중단/재개 → 기존 P5의 G21~100 재개. 기존 P4-2 사후 소급 enroll 금지, 원장 계보 수정 금지.
