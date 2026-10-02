# MCP Phase 6.3 — Manual JSON-RPC ownership isolation

> **역사적 단계 문서:** 이 문서는 해당 Phase의 완료/설계 스냅샷이다. 현재 운영 정본은 `mcp-current-state.md`이며, 실행 방법과 현재 구조는 정본 문서를 우선한다.

## 목적

Phase 6.3은 Phase 6.2의 payload codec 분리에 이어, legacy 2024-11-05 JSON-RPC request/envelope
책임을 shared application core에서 완전히 분리한다.

변경 전:

```text
codex_mcp_core
  -> application dispatch
  -> raw JSON-RPC handle()
  -> tools/call envelope
  -> 2024-11-05 initialize
  -> codex_mcp_protocol
```

변경 후:

```text
codex_mcp_core
  -> application services
  -> tool schema
  -> tool dispatch
  -> public/legacy payload metadata

codex_mcp_sdk_server
  -> official SDK protocol envelope
  -> codex_mcp_core

codex_mcp_manual_adapter
  -> legacy handle()
  -> legacy tools/call envelope
  -> 2024-11-05 initialize
  -> codex_mcp_protocol
  -> codex_mcp_core

codex_mcp_manual_server
  -> stdio line framing
  -> codex_mcp_manual_adapter
```

## Shared core 책임

`integrations/codex_mcp_core.py`의 `CodexMCPServer`는 이제 application-facing dispatcher다.

남는 책임:

- Application Service 생성/소유
- Tool argument validation
- Tool-specific dispatch
- Tool schema definitions
- public Tool plane
- public `_contract`
- hidden legacy `_compatibility`
- system/evaluation argument parsing

제거한 책임:

- raw JSON-RPC Mapping validation
- `initialize`
- `ping`
- `notifications/initialized`
- `tools/list` response envelope
- `tools/call` response envelope
- JSON-RPC success/error object
- manual Tool error envelope
- provider status write triggered by manual protocol messages
- `2024-11-05` protocol version response

기계적 ownership check:

```text
codex_mcp_protocol import in codex_mcp_core = NONE
def handle(...) in codex_mcp_core = NONE
def _call(...) in codex_mcp_core = NONE
def _tool_error(...) in codex_mcp_core = NONE
```

## Manual adapter

신규 모듈:

```text
integrations/codex_mcp_manual_adapter.py
```

`ManualCodexMCPServer`는 core `CodexMCPServer`를 상속하고 다음 legacy transport 책임만 추가한다.

- `handle(request)`
- `_call(request_id, params)`
- 2024-11-05 initialize response
- JSON-RPC success/error envelope
- manual tool error envelope
- manual tools/list
- manual provider status connection signal

따라서 business/application dispatch는 복제하지 않고 `self._dispatch()`를 그대로 공유한다.

## Manual rollback entrypoint

`integrations.codex_mcp_manual_server.py`는 이제:

```text
create_manual_mcp_server()
  -> ManualCodexMCPServer
  -> serve_lines()
```

를 사용한다.

manual rollback의 외부 동작은 변경하지 않는다.

```text
protocol_version = 2024-11-05
public tools = 13
hidden legacy direct dispatch = 5
public contract = v1
orders_enabled=false
```

## Canonical Python import compatibility shim

역사적으로 테스트와 일부 내부 consumer는:

```python
from integrations.codex_mcp_server import CodexMCPServer, create_mcp_server
```

뒤에 직접 `server.handle(...)`을 호출했다.

Phase 6.3에서 이 API를 즉시 깨뜨리지 않기 위해 `integrations.codex_mcp_server` façade는
Python import compatibility에 한해:

```text
CodexMCPServer -> ManualCodexMCPServer
create_mcp_server -> create_manual_mcp_server
```

를 유지한다.

중요한 점은 **runtime entrypoint는 여전히 official SDK**라는 것이다.

```text
python -m integrations.codex_mcp_server
  -> official SDK
```

즉 compatibility import API와 process transport ownership을 구분한다.

이 shim은 기존 unit/security regression을 한 번에 대량 재작성하지 않고 transport ownership을
먼저 분리하기 위한 migration seam이다.

## Canonical SDK

SDK adapter는 `integrations.codex_mcp_core.CodexMCPServer`를 직접 사용한다.

따라서 canonical runtime path에는:

- manual adapter
- manual `handle()`
- legacy JSON-RPC success/error helper
- `serve_lines()`

가 들어가지 않는다.

Phase 6.2에서 payload codec dependency도 이미 분리했으므로 canonical SDK path는
legacy protocol 구현과 코드 의존성이 없다.

## Test-first contract

신규 테스트:

```text
tests/integrations/test_codex_mcp_manual_adapter.py
```

검증 항목:

1. shared core source에 `codex_mcp_protocol` 없음
2. core class에 `handle` 없음
3. core source에 `_call`, `_tool_error` 없음
4. manual adapter가 core를 상속
5. manual initialize = 2024-11-05
6. manual tools/list = 13
7. canonical façade의 기존 Python import API는 계속 `handle()` 제공

## 실제 subprocess acceptance

Canonical SDK:

```text
status = PASS
canonical_entrypoint = sdk
sdk_protocol_version = 2025-11-25
legacy_protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
orders_enabled=false
```

Manual rollback:

```text
status = PASS
transport = manual_rollback
protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
orders_enabled=false
```

두 acceptance 모두 exit code 0이고 stderr는 비어 있었다.

## 안전 경계

Phase 6.3은 transport ownership refactor다.

변경하지 않은 항목:

- canonical official SDK entrypoint
- manual rollback availability
- public Tool = 13
- hidden legacy direct dispatch = 5
- public contract = v1
- RuntimeSnapshot = v2
- Application Service semantics
- StrategyIR
- evaluation/finance logic
- KIS/live boundary
- order permission

```text
orders_enabled=false
```

를 유지한다.

## Repository release gate

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (778 tests)
```

## Phase 6.3 판정

```text
shared core manual JSON-RPC ownership = REMOVED
shared core legacy protocol dependency = REMOVED
manual adapter ownership = ESTABLISHED
canonical SDK acceptance = PASS
manual rollback acceptance = PASS
Python compatibility shim = PRESERVED
orders_enabled=false
```

Phase 6.4 consolidation까지 완료됐다.
현재 운영 정본은 `docs/operations/mcp-current-state.md`, 완료 판정은
`docs/operations/mcp-phase6-completion.md`를 따른다.
