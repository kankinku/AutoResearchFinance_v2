# MCP Current Operational State

> **CURRENT_OPERATIONAL_SOURCE_OF_TRUTH**
>
> 이 문서는 MCP 관련 **현재 운영 정본**이다. Phase별 문서는 설계·전환 이력을 보존하기 위한
> 역사 문서이며, 현재 실행 방법·Tool surface·transport 책임은 이 문서를 우선한다.

Phase 6 post-cutover stabilization까지 완료된 상태다.

## 현재 실행 정본

정상 운영 entrypoint:

```text
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

현재 transport:

```text
canonical transport = official_sdk
canonical entrypoint = integrations.codex_mcp_server
locked SDK = mcp 2.2.0
current handshake acceptance = 2025-11-25
legacy client compatibility = 2024-11-05
```

비상 rollback entrypoint:

```text
python -m integrations.codex_mcp_manual_server --state-dir state --project-root .
```

manual rollback은 production default가 아니다.

## Tool surface

현재 공개 surface:

```text
13 public
5 hidden legacy
public contract = v1
RuntimeSnapshot = v2
orders_enabled=false
```

public Tool:

- initialize_research_state
- get_workspace_status
- validate_strategy
- import_strategies
- list_strategies
- list_features
- get_research_evidence
- get_dashboard_status
- run_evaluation
- check_system
- start_system
- get_system_status
- stop_system

hidden legacy compatibility:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

hidden legacy 이름은 `tools/list`에 광고하지 않지만 direct compatibility dispatch는 유지한다.

## 코드 소유권

현재 책임 구조:

```text
integrations.codex_mcp_server
  -> canonical CLI façade
  -> official SDK runtime

integrations.codex_mcp_sdk_server
  -> mcp.server.Server
  -> official stdio transport
  -> codex_mcp_core dispatch
  -> codex_mcp_payload

integrations.codex_mcp_core
  -> Application Service ownership
  -> Tool schema
  -> Tool argument validation
  -> Tool dispatch
  -> public/legacy metadata
  -> NO manual JSON-RPC ownership
  -> NO codex_mcp_protocol dependency

integrations.codex_mcp_manual_adapter
  -> legacy 2024-11-05 handle()
  -> manual JSON-RPC envelope
  -> shared codex_mcp_core dispatch

integrations.codex_mcp_manual_server
  -> emergency rollback CLI
  -> serve_lines()

integrations.codex_mcp_protocol
  -> legacy line framing and JSON-RPC response helpers

integrations.codex_mcp_payload
  -> transport-neutral JSON Tool payload encoding
```

## Python compatibility façade

`integrations.codex_mcp_server`는 runtime에서는 official SDK를 실행한다.

다만 기존 테스트/내부 consumer가 사용하던:

```python
CodexMCPServer
create_mcp_server
```

import는 compatibility seam으로 manual adapter를 가리킨다.

이는 process transport가 manual이라는 의미가 아니다.

## Acceptance gates

Canonical SDK:

```text
uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py \
  --project-root . \
  --state-dir state/mcp-sdk-acceptance
```

Manual rollback:

```text
uv run --locked --extra dev python scripts/verify_mcp_runtime.py \
  --project-root . \
  --state-dir state/mcp-manual-rollback-acceptance
```

두 acceptance가 보장하는 공통 계약:

- 13 public Tool
- 5 hidden legacy direct compatibility calls
- public contract v1
- sanitized error boundary
- `orders_enabled=false`

## Retention policy

manual rollback transport와 hidden legacy dispatch는 서로 다른 compatibility 문제다.

현재 정책:

```text
manual rollback transport = RETAIN
hidden legacy dispatch = RETAIN
automatic deletion = FORBIDDEN
separate approval required = YES
```

둘 중 어느 것도 Phase 6 완료를 이유로 자동 삭제하지 않는다.

## Docker host acceptance

실제 Windows + Docker Desktop Host Acceptance는 MCP SDK stabilization과 별개다.

현재 Moon 환경에서는 Docker CLI/Engine 부재로 외부 host 검증이 필요하며,
그 상태를 MCP transport 완료와 혼동하지 않는다.

## 안전 경계

MCP는 다음 기능을 제공하지 않는다.

- order Tool
- credential Tool
- live account activation Tool
- sealed OOS bypass
- arbitrary shell/code execution Tool

항상:

```text
orders_enabled=false
```

다.
