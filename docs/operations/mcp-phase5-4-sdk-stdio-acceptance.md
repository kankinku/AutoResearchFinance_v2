# MCP Phase 5.4 — 공식 SDK STDIO Shadow Acceptance

## 목적

Phase 5.4는 공식 Python MCP SDK shadow adapter를 **실제 별도 subprocess**로 실행해
프로토콜 협상과 Tool 계약을 STDIO 끝단에서 검증하는 단계다.

Phase 5.3의 in-process parity 검증만으로는 다음 문제를 잡을 수 없다.

- SDK subprocess bootstrap 실패
- STDIO framing/flush 문제
- initialize negotiation 문제
- SDK client와 server model alias 차이
- hidden legacy direct call의 실제 wire 동작
- subprocess error leakage

따라서 Phase 5.4에서는 실제 server process를 두 번 띄운다.

1. 현재 공식 SDK client의 정상 negotiation
2. 기존 2024-11-05 handshake client compatibility

canonical production entrypoint는 아직 변경하지 않는다.

## 정본 Acceptance 명령

저장소 루트에서 실행한다.

```powershell
uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py `
  --project-root . `
  --state-dir state/mcp-sdk-acceptance
```

Linux/bash에서는 줄바꿈 없이 같은 인자를 사용한다.

## Acceptance 구조

`scripts/verify_mcp_sdk_runtime.py`는 다음 순서로 검증한다.

### 1. Canonical entrypoint guard

먼저 기존 `integrations/codex_mcp_server.py`가 여전히
`integrations.codex_mcp_protocol.serve_lines`를 사용하는지 확인한다.

즉 Phase 5.4에서 production cutover가 우발적으로 일어났다면 acceptance를 실패시킨다.

정상 값:

```text
canonical_entrypoint = manual
```

### 2. 공식 SDK client negotiation

다음 조합으로 실제 subprocess를 띄운다.

```text
ClientSession
  -> stdio_client()
  -> python -m integrations.codex_mcp_sdk_server
```

현재 lock된 `mcp==2.2.0`에서 STDIO handshake가 협상한 버전은:

```text
2025-11-25
```

SDK v2는 2026 계열 protocol도 지원하지만, 현재 `ClientSession.initialize()`의 legacy
handshake 경로는 latest handshake revision인 2025-11-25를 사용한다. 따라서 이 acceptance는
실제 현재 SDK 동작을 기준으로 2025-11-25를 고정한다.

### 3. Public surface 검증

실제 `tools/list` 응답에서 정확히 13개 Tool만 광고되는지 확인한다.

```text
tool_count = 13
```

hidden legacy 5개는 목록에 없어야 한다.

### 4. Public Tool contract 검증

`get_system_status`를 실제 `tools/call`로 실행한다.

필수 contract:

```json
{
  "schema_version": 1,
  "tool": "get_system_status",
  "plane": "EVIDENCE_STATUS",
  "orders_enabled": false
}
```

acceptance 격리 state 기준 system status는 `STOPPED`여야 한다.

### 5. Hidden legacy direct dispatch

다음 5개 이름은 `tools/list`에 없지만 raw `tools/call` request로 직접 호출한다.

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

공식 `ClientSession.call_tool()` 고수준 helper는 목록에 없는 Tool을 호출할 때 진단 로그를
출력하므로, acceptance에서는 저수준 `send_request(CallToolRequest)`를 사용한다.

이 방식으로 실제 wire direct dispatch를 검증하면서 불필요한 stderr도 만들지 않는다.

기대 status:

```text
set_research_mode       = LEGACY_INTERNAL_TOOL
validate_research_cache = LEGACY_INTERNAL_TOOL
plan_generation         = LEGACY_INTERNAL_TOOL
get_research_context    = LEGACY_INTERNAL_TOOL
submit_research_intent  = DEPRECATED
```

legacy payload에는 public `_contract`가 붙지 않아야 하며 order capability도 노출하지 않는다.

### 6. Sanitized error 검증

프로젝트 밖의 의도적인 secret-like path로 `validate_strategy`를 호출한다.

필수 결과:

```json
{
  "status": "ERROR",
  "message": "tool request failed"
}
```

wire payload에 거부된 경로 문자열이 포함되면 실패한다.

### 7. 2024-11-05 compatibility

두 번째 SDK subprocess를 띄우고 `ClientSession.send_request()`로 initialize version을
명시적으로 `2024-11-05`로 요청한다.

server가 같은 버전을 반환한 뒤 session에 adopt하고 `notifications/initialized`를 전송한다.

그 이후 동일한 항목을 다시 검증한다.

- 13 public Tool
- public contract v1
- hidden legacy 5 direct dispatch
- sanitized error
- `orders_enabled=false`

따라서 단순 initialize 응답만 확인하는 것이 아니라 이전 client protocol에서도 실제 Tool
traffic이 동작하는지 확인한다.

## Project Moon 실제 결과

Phase 5.4에서 다음 명령을 실제 실행했다.

```text
uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py
  --project-root .
  --state-dir state/mcp-sdk-acceptance-phase5-4
```

결과:

```json
{
  "canonical_entrypoint": "manual",
  "legacy_compatibility_count": 5,
  "legacy_protocol_version": "2024-11-05",
  "orders_enabled": false,
  "public_contract_schema_version": 1,
  "sdk_protocol_version": "2025-11-25",
  "server_name": "quant-autoresearch",
  "status": "PASS",
  "system_status": "STOPPED",
  "tool_count": 13
}
```

process exit code는 0이며 stderr는 비어 있었다.

전체 repository release gate도 통과했다.

```text
ruff = PASS
mypy = PASS (161 source files)
pytest = PASS (766 tests)
```

## 자동 Regression

테스트:

```text
tests/scripts/test_mcp_sdk_runtime_acceptance.py
```

검증 항목:

- 실제 SDK subprocess 2개 실행
- current SDK negotiation = 2025-11-25
- legacy handshake = 2024-11-05
- public Tool = 13
- hidden legacy compatibility = 5
- public contract schema v1
- isolated system status = STOPPED
- canonical entrypoint = manual
- `orders_enabled=false`
- CLI safe summary
- failure detail 비노출

## 기존 manual acceptance와의 관계

기존 정본 수동 transport acceptance:

```text
scripts/verify_mcp_runtime.py
```

는 계속 유지한다.

Phase 5.4 SDK acceptance는 그 계약과 같은 13 public + 5 legacy + contract v1 +
`orders_enabled=false`를 검증하되, 추가로 SDK negotiation과 2024 compatibility를 확인한다.

Phase 5.5 cutover 전에는 두 acceptance 모두 PASS해야 한다.

## 안전 경계

Phase 5.4는 다음을 변경하지 않는다.

- canonical MCP entrypoint
- public Tool 개수
- hidden legacy removal policy
- Application Services
- StrategyIR
- evaluation / finance logic
- Docker backend
- KIS credential
- live account gate
- sealed OOS policy
- order permission

`orders_enabled=false`를 전 구간에서 유지한다.

## Phase 5.4 판정

```text
official SDK real stdio subprocess = PASS
SDK negotiated protocol = 2025-11-25
legacy protocol compatibility = 2024-11-05 PASS
public tools = 13
hidden legacy direct dispatch = 5
public contract = v1
sanitized errors = PASS
canonical manual adapter = UNCHANGED
orders_enabled=false
```

Phase 5.5에서 `python -m integrations.codex_mcp_server`의 production entrypoint를
공식 SDK adapter로 전환했고, 기존 수동 transport는
`integrations.codex_mcp_manual_server` rollback 경로로 격리했다.

최종 cutover 결과는 `docs/operations/mcp-phase5-5-canonical-sdk-cutover.md`를 따른다.
