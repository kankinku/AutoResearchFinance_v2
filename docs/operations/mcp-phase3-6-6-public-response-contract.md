# MCP Phase 3-6.6 — Public response contract

## 목적

장기 공개 MCP Tool 13개의 성공 응답에 공통 version marker를 추가해
클라이언트가 Tool별 payload를 기존 필드를 깨지 않고 안정적으로 식별할 수 있게 한다.

## 원칙

기존 응답을 새로운 envelope 안에 감싸지 않는다.

기존:

```json
{
  "status": "READY",
  "...": "..."
}
```

현재:

```json
{
  "status": "READY",
  "...": "...",
  "_contract": {
    "schema_version": 1,
    "tool": "get_workspace_status",
    "plane": "BOOTSTRAP_CONFIGURATION",
    "orders_enabled": false
  }
}
```

따라서 기존 필드의 이름, 위치, 의미는 유지되고 `_contract`만 additive하게 추가된다.

## Typed contract

`application/mcp_contracts.py`에 `PublicToolContractMetadata`를 둔다.

필드:

- `schema_version = 1`
- `tool`
- `plane`
- `orders_enabled = false`

Pydantic `extra=forbid`로 metadata drift를 막는다.

## Plane

### BOOTSTRAP_CONFIGURATION

- `initialize_research_state`
- `get_workspace_status`

### CATALOG_VALIDATION

- `validate_strategy`
- `import_strategies`
- `list_strategies`
- `list_features`

### EVIDENCE_STATUS

- `get_research_evidence`
- `get_dashboard_status`
- `get_system_status`

### EXECUTION_LIFECYCLE

- `run_evaluation`
- `check_system`
- `start_system`
- `stop_system`

총 13개이며 `_PUBLIC_TOOL_PLANES`는 공개 surface와 exact match해야 한다.

## orders_enabled

공통 contract의 `orders_enabled`는 항상 false다.

이는 해당 Tool 응답이 실제 주문 권한을 부여하지 않는다는 MCP boundary signal이다.

개별 payload 안에 기존 `orders_enabled=false` 필드가 이미 존재하는 경우에도
이를 제거하지 않는다.

## Legacy compatibility Tool

다음 5개 hidden legacy Tool에는 public `_contract` metadata를 붙이지 않는다.

- `set_research_mode`
- `validate_research_cache`
- `plan_generation`
- `get_research_context`
- `submit_research_intent`

이들은 Phase 3-6.7까지:

- `LEGACY_INTERNAL_TOOL`
- `DEPRECATED`

compatibility metadata만 유지한다.

즉 public contract와 legacy migration contract를 혼합하지 않는다.

## 호환성

변경하지 않은 것:

- Tool 이름
- inputSchema
- 기존 payload 필드
- Application Service return shape
- CLI return shape
- RuntimeSnapshot 자체 schema
- WorkspaceStatusSnapshot 자체 schema
- dashboard snapshot schema
- legacy direct dispatch
- order/live permission

공통 `_contract`는 MCP adapter에서만 추가된다.

## 검증

계약 테스트는 다음을 고정한다.

1. plane mapping이 정확히 13개 public Tool을 덮음
2. 네 plane 모두 존재
3. 기존 payload 필드는 그대로 유지
4. schema_version=1
5. orders_enabled=false
6. hidden legacy Tool에는 public contract가 붙지 않음
7. 실제 MCP 호출에서도 네 plane 대표 Tool이 metadata를 반환

## 다음 단계

Phase 3-6.7에서:

- exact 13 tools/list
- legacy direct dispatch compatibility
- CLI/Application Service 유지
- security boundary
- real stdio acceptance
- documentation alignment

를 최종 검증하고 Phase 3-6을 종료한다.
