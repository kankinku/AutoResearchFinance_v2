# MCP Phase 3-6.4 — Public tools/list 전환

## 목표

Phase 3-6.2에서 확정한 장기 공개 MCP surface를 실제 `tools/list`에 적용한다.

기존 18개 공개 Tool 중 5개를 default public 목록에서 제거해 **13개**로 줄인다.

## 현재 공개 Tool 13개

### Bootstrap / configuration
- `initialize_research_state`
- `get_workspace_status`

### Catalog / validation
- `validate_strategy`
- `import_strategies`
- `list_strategies`
- `list_features`

### Evidence / status
- `get_research_evidence`
- `get_dashboard_status`
- `get_system_status`

### Execution / lifecycle
- `run_evaluation`
- `check_system`
- `start_system`
- `stop_system`

## tools/list에서 제외된 5개

- `set_research_mode`
- `validate_research_cache`
- `plan_generation`
- `get_research_context`
- `submit_research_intent`

## Legacy direct dispatch

Phase 3-6.7까지 기존 caller 호환을 위해 위 5개 이름의 direct `tools/call` dispatch는 유지한다.

즉:

```text
tools/list
  → 13개만 광고

tools/call(name=<legacy name>)
  → compatibility window 동안 여전히 실행
```

이는 보안 경계가 아니다. 이름을 아는 caller는 계속 호출할 수 있다.

## Legacy compatibility metadata

### INTERNALIZE 후보 4개

성공 응답에 다음 형태를 추가한다.

```json
{
  "_compatibility": {
    "status": "LEGACY_INTERNAL_TOOL",
    "replacement_tools": [],
    "note": "..."
  }
}
```

Tool별 replacement:

- `set_research_mode` → `get_workspace_status` + host/CLI configuration
- `validate_research_cache` → public MCP replacement 없음, CLI maintenance path
- `plan_generation` → `start_system`, `run_evaluation`
- `get_research_context` → `list_features`, `get_research_evidence`, `get_dashboard_status`, `get_system_status`

### submit_research_intent

Phase 3-6.3의:

```text
_compatibility.status = DEPRECATED
```

를 그대로 유지한다.

## Tool definition 구조

`_all_tools()`:
- 기존 18개 정의 전체
- phase0/phase4 schema regression 및 legacy compatibility용

`_tools()`:
- 현재 default public surface
- `_TARGET_PUBLIC_TOOL_NAMES`에 포함된 13개만 반환

이 구조로 historical schema와 현재 advertised surface를 분리한다.

## 안전 경계

변경하지 않은 항목:

- legacy Tool input schema
- dispatch validation
- Application Service 동작
- CLI 기능
- orders_enabled=false
- KIS/live permission
- strategy import static-only 경계
- RuntimeSnapshot

hidden legacy Tool은 호환성 shim일 뿐, 권한 은닉 수단으로 사용하지 않는다.

## 다음 단계

Phase 3-6.5에서는 `get_workspace_status`를 bootstrap/configuration-plane read로 명확히 고정한다.

목표:
- output contract 명시
- initialization/mode/audit/manifest 역할 분리
- runtime/dashboard status와 의미 충돌 방지
