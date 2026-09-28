# MCP Phase 5 — 공식 SDK 전환 완료 보고서

## 완료 범위

Phase 5는 직접 구현한 MCP STDIO/JSON-RPC transport를 공식 Python MCP SDK로
안전하게 교체하는 작업이다.

완료된 단계:

- 5.1 SDK migration inventory / compatibility design
- 5.2 official SDK dependency + parallel adapter skeleton
- 5.3 Tool schema / dispatch parity
- 5.4 real SDK STDIO shadow acceptance
- 5.5 canonical SDK cutover + manual rollback isolation

## 최종 상태

```text
mcp dependency = mcp>=2.2,<3
locked sdk = 2.2.0
canonical entrypoint = integrations.codex_mcp_server
canonical transport = official_sdk
manual rollback = integrations.codex_mcp_manual_server
public tools = 13
hidden compatibility = 5
public contract = v1
runtime snapshot = v2
orders_enabled=false
```

## 보존된 기능

SDK 전환으로 다음은 변경되지 않았다.

- Application Service behavior
- workspace/bootstrap contract
- strategy validation/import
- feature catalog
- evidence/status planes
- deterministic evaluation
- managed system lifecycle
- durable evaluation queue
- Docker isolation
- research Evidence
- CLI
- KIS safety boundary

## Release acceptance

Canonical SDK:

```text
status = PASS
sdk_protocol_version = 2025-11-25
legacy_protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
canonical_entrypoint = sdk
orders_enabled=false
```

Manual rollback:

```text
status = PASS
protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
transport = manual_rollback
orders_enabled=false
```

## Repository release gate

```text
ruff = PASS
mypy = PASS (163 source files)
pytest = PASS (769 tests)
```

## 운영 원칙

정상 운영에서는 반드시 `integrations.codex_mcp_server`를 사용한다.

`integrations.codex_mcp_manual_server`는 emergency rollback 및 transport 비교용으로만
유지한다.

legacy protocol code 삭제는 별도 승인 전에는 수행하지 않는다.

## 완료 판정

```text
phase5_status = COMPLETE
canonical_sdk_cutover = COMPLETE
rollback_path = VERIFIED
orders_enabled=false
```

다음 개발 단계는 **Phase 6.1 — post-cutover stabilization inventory**다.
Phase 6은 rollback을 즉시 삭제하지 않고 canonical SDK와 legacy manual transport의
코드 소유권을 분리해 post-cutover 구조를 안정화한다.
