# MCP Phase 6 — Post-cutover stabilization 완료

## 완료 범위

Phase 6은 official SDK cutover 이후 남아 있던 transport ownership 기술부채를 정리했다.

완료된 단계:

- Phase 6.1 — post-cutover stabilization inventory
- Phase 6.2 — neutral payload codec extraction
- Phase 6.3 — manual JSON-RPC ownership isolation
- Phase 6.4 — contract/documentation consolidation

현재 운영 정본:

```text
docs/operations/mcp-current-state.md
```

## 최종 구조

```text
canonical = official_sdk
entrypoint = integrations.codex_mcp_server
public tools = 13
hidden legacy = 5
public contract = v1
RuntimeSnapshot = v2
orders_enabled=false
```

공식 SDK runtime은 더 이상 legacy protocol module에 의존하지 않는다.

shared core도 manual JSON-RPC envelope를 소유하지 않는다.

## Rollback 및 compatibility 유지 정책

다음은 의도적으로 유지한다.

- `integrations.codex_mcp_manual_server`
- `integrations.codex_mcp_manual_adapter`
- `integrations.codex_mcp_protocol`
- hidden legacy direct dispatch 5개
- 기존 Python import compatibility seam

이들은 자동 삭제 대상이 아니다.

manual rollback 삭제와 hidden legacy dispatch 삭제는 각각 별도 승인 후에만 진행한다.

## Release gate

```text
canonical SDK acceptance = PASS
manual rollback acceptance = PASS
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (782 tests)
unmarked stale MCP documents = 0
```

## 외부 미완료 항목

Windows + Docker Desktop에서 수행해야 하는 Docker Host Acceptance는 계속 외부 검증 항목이다.

이는 Phase 6 MCP stabilization 완료를 막지 않는다.

## 완료 판정

```text
phase6_status = COMPLETE
canonical_transport = official_sdk
transport_ownership = STABILIZED
manual_rollback = RETAINED
hidden_legacy_dispatch = RETAINED
orders_enabled=false
```
