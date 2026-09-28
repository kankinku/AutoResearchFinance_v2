# MCP Phase 6.2 — Neutral payload codec extraction

## 목적

Phase 6.2는 canonical official-SDK transport가 legacy manual protocol 모듈의
payload serialization helper를 직접 사용하던 의존성을 제거한다.

변경 전:

```text
codex_mcp_sdk_server
  -> codex_mcp_protocol.text_content
```

변경 후:

```text
codex_mcp_sdk_server
  -> codex_mcp_payload

codex_mcp_protocol
  -> codex_mcp_payload
```

manual rollback transport와 canonical SDK가 동일한 payload wire semantics를 공유하지만,
SDK가 rollback protocol 구현에 의존하지 않도록 책임 경계를 분리했다.

## Neutral codec

신규 모듈:

```text
integrations/codex_mcp_payload.py
```

제공 함수:

```text
encode_tool_payload(payload)
text_content_payload(payload)
```

직렬화 계약은 기존과 동일하다.

```python
json.dumps(payload, ensure_ascii=True, sort_keys=True)
```

즉 다음 semantics를 보존한다.

- deterministic key ordering
- Korean/non-ASCII payload의 ASCII escape
- Windows stdio code page 차이에서 diagnostic text 안정성
- public/legacy Tool payload text의 기존 wire representation

## Canonical SDK dependency

현재 `integrations/codex_mcp_sdk_server.py`는:

```text
integrations.codex_mcp_payload
```

만 사용해 Tool JSON text를 생성한다.

다음 import는 더 이상 존재하지 않는다.

```text
codex_mcp_sdk_server -> codex_mcp_protocol
```

따라서 canonical SDK의 payload serialization은 legacy manual transport 구현과 분리됐다.

## Manual rollback compatibility

`integrations/codex_mcp_protocol.py`에는 기존 Python API 호환을 위해
`text_content(payload)` wrapper를 유지한다.

wrapper는 직접 JSON 직렬화를 구현하지 않고:

```text
text_content()
  -> text_content_payload()
  -> encode_tool_payload()
```

순서로 neutral codec을 재사용한다.

따라서 rollback protocol의 wire text도 Phase 6.2 이전과 동일하다.

## 아직 남은 의존성

Phase 6.2는 payload codec만 분리한다.

현재 shared core에는 아직:

```text
codex_mcp_core
  -> codex_mcp_protocol.error
  -> codex_mcp_protocol.success
  -> codex_mcp_protocol.text_content
```

의존성이 남아 있다.

원인은 `CodexMCPServer.handle()`과 `_tool_error()`가 manual JSON-RPC envelope 책임까지
보유하기 때문이다.

이 부분은 의도적으로 Phase 6.3에서 분리한다. Phase 6.2에서 동시에 옮기지 않아
변경 범위를 제한하고 rollback regression 원인을 분리한다.

## Test-first contract

신규 테스트:

```text
tests/integrations/test_codex_mcp_payload.py
```

검증 내용:

1. neutral codec output이 기존 `json.dumps(... ensure_ascii=True, sort_keys=True)`와 정확히 동일
2. manual `text_content()` wrapper의 결과 동일
3. canonical SDK source에 `codex_mcp_protocol` import 없음
4. SDK와 manual protocol 모두 neutral payload module 사용
5. manual protocol이 payload JSON 직렬화를 자체 중복 구현하지 않음

## 실제 subprocess acceptance

Canonical official SDK:

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

두 acceptance 모두 exit code 0, stderr empty로 확인했다.

## 안전 경계

Phase 6.2에서 변경하지 않은 항목:

- canonical entrypoint
- manual rollback availability
- public 13 Tool
- hidden legacy 5 direct dispatch
- public contract v1
- RuntimeSnapshot v2
- Application Services
- StrategyIR
- evaluation/finance logic
- KIS/live safety
- order permission

```text
orders_enabled=false
```

를 유지한다.

## Repository release gate

```text
ruff = PASS
mypy = PASS (164 source files)
pytest = PASS (775 tests)
```

## Phase 6.2 판정

```text
neutral payload codec = IMPLEMENTED
sdk -> legacy protocol payload dependency = REMOVED
manual payload wire compatibility = PRESERVED
canonical SDK acceptance = PASS
manual rollback acceptance = PASS
orders_enabled=false
```

Phase 6.3에서 raw JSON-RPC request/envelope 처리를 shared core에서 manual rollback layer로
이동했고 `codex_mcp_core.py`의 legacy protocol dependency를 제거했다.

현재 상태는 `docs/operations/mcp-phase6-3-manual-jsonrpc-isolation.md`를 따른다.
다음 작업은 **Phase 6.4 — post-cutover contract and documentation consolidation**이다.
