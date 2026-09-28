# MCP Phase 5.3 — Tool schema / dispatch parity

## 목적

Phase 5.3은 공식 Python MCP SDK shadow adapter에 현재 운영 MCP 계약을 그대로 연결하는 단계다.

이 단계의 목표는 기능 확장이 아니라 **transport parity**다.

현재 canonical production entrypoint는 여전히 다음 수동 서버다.

```text
python -m integrations.codex_mcp_server
```

공식 SDK shadow entrypoint:

```text
python -m integrations.codex_mcp_sdk_server
```

는 이제 Tool schema와 dispatch까지 연결됐지만, 실제 subprocess STDIO acceptance와 canonical
cutover는 아직 수행하지 않는다.

## 구현 구조

`integrations/codex_mcp_sdk_server.py`는 별도의 연구 로직을 구현하지 않는다.

```text
Official SDK Server
  -> SDKMCPServerAdapter
      -> existing _tools()
      -> existing CodexMCPServer._dispatch()
      -> existing _with_public_contract()
      -> existing _with_legacy_compatibility()
      -> existing Application Services
```

따라서 두 transport가 서로 다른 validation/business logic을 갖지 않는다.

현재 adapter 상태:

```text
SDK_ADAPTER_STATUS = SCHEMA_DISPATCH_PARITY
```

## Public Tool schema parity

SDK `tools/list` handler는 기존 `_tools()`의 13개 정의를 SDK `types.Tool`로 변환한다.

검증은 각 Tool을 다시 wire alias로 직렬화한 결과가 기존 dict와 동일한지 확인한다.

```text
SDK Tool.model_dump(by_alias=True, exclude_none=True)
==
manual _tools() definition
```

따라서 다음 항목이 그대로 유지된다.

- Tool name
- description
- inputSchema
- required
- enum
- defaults
- additionalProperties
- oneOf

광고되는 이름은 정확히 13개다.

## Hidden legacy direct dispatch

다음 5개 이름은 SDK `tools/list`에도 광고하지 않는다.

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

하지만 `tools/call` handler는 기존 `CodexMCPServer._dispatch()`를 공유하므로 direct call
호환성을 유지한다.

응답의 기존 migration metadata도 그대로 유지한다.

```text
set_research_mode       -> LEGACY_INTERNAL_TOOL
validate_research_cache -> LEGACY_INTERNAL_TOOL
plan_generation         -> LEGACY_INTERNAL_TOOL
get_research_context    -> LEGACY_INTERNAL_TOOL
submit_research_intent  -> DEPRECATED
```

hidden dispatch hard removal은 이번 단계 범위가 아니다.

## Public response contract parity

public Tool 실행 결과에는 기존 `_with_public_contract()`가 그대로 적용된다.

예:

```json
{
  "_contract": {
    "schema_version": 1,
    "tool": "initialize_research_state",
    "plane": "BOOTSTRAP_CONFIGURATION",
    "orders_enabled": false
  }
}
```

따라서 SDK 도입으로 public response contract version을 변경하지 않는다.

## Error sanitization parity

SDK handler에서 application validation/IO 오류를 그대로 SDK exception으로 흘리지 않는다.

다음 예외는 기존 수동 transport와 같은 경계에서 처리한다.

- OSError
- PermissionError
- TypeError
- ValueError

결과 payload:

```json
{
  "status": "ERROR",
  "message": "tool request failed"
}
```

SDK model 내부 Python 필드는 `is_error`지만 wire alias는 기존 MCP 규격대로 `isError`다.

거부된 filesystem path, repository URL, credential, provider detail, exception 원문을 반환하지 않는다.

unknown Tool 역시 같은 sanitized Tool error로 닫는다.

## Application Service 보존

SDK adapter는 자체 Workspace/Strategy/Evaluation/System service를 새로 구현하지 않는다.

기존 `CodexMCPServer` 인스턴스를 dispatch core로 사용하므로:

- WorkspaceService
- StrategyService
- PlanningService
- ResearchService
- EvaluationService
- SystemService

호출 경로가 수동 transport와 동일하다.

이 공유 방식은 Phase 5 migration 동안 parity를 가장 강하게 보장하기 위한 임시 seam이다.
canonical cutover 이후 수동 JSON-RPC envelope 제거 여부는 별도 단계에서 결정한다.

## Provider status

SDK `tools/list`에서도 기존 MCP 연결 의미와 동일하게 provider status를 다음 값으로 기록한다.

```text
provider = codex_desktop
status = ONLINE
reason = MCP_CONNECTED
```

initialize/ping까지 포함한 실제 protocol-level 동작은 Phase 5.4 subprocess acceptance에서 검증한다.

## 테스트

신규 parity test:

```text
tests/integrations/test_codex_mcp_sdk_parity.py
```

검증 항목:

1. public 13 Tool exact schema parity
2. SDK server capabilities에 tools 활성화
3. hidden legacy 5개가 list에 없음
4. hidden legacy 5개 direct dispatch 성공
5. public `_contract` v1 유지
6. `orders_enabled=false`
7. rejected path 비노출
8. unknown Tool argument 비노출
9. SDK wire serialization의 `isError` 의미 유지

## 안전 경계

Phase 5.3은 다음을 변경하지 않는다.

- canonical MCP entrypoint
- CLI
- Application Service behavior
- StrategyIR
- evaluation / finance logic
- Docker backend
- KIS credential
- paper/live permission
- sealed OOS policy
- public Tool 개수
- hidden legacy hard-removal policy

MCP order/live Tool은 추가하지 않았고 `orders_enabled=false`를 유지한다.

## Phase 5.3 판정

```text
public schema parity = VERIFIED
public tool count = 13
hidden legacy dispatch = 5
public contract = v1
sanitized tool errors = VERIFIED
canonical manual adapter = UNCHANGED
orders_enabled=false
```

다음 작업은 **Phase 5.4 — SDK STDIO shadow acceptance**다.

Phase 5.4에서는 실제 별도 subprocess로 공식 SDK shadow server를 띄워 initialize, tools/list,
public/legacy tools/call과 protocol negotiation을 검증한다. 그 전까지 production MCP 설정은
기존 수동 entrypoint를 유지한다.
