# MCP Phase 6.4 — Post-cutover contract and documentation consolidation

> **역사적 단계 문서:** 이 문서는 Phase 6.4 완료 시점의 정리 기록이다.
> 현재 운영 정본은 `mcp-current-state.md`다.

## 목적

Phase 6.4는 Phase 6.2~6.3에서 분리한 transport ownership을 최종 계약으로 고정하고,
과거 단계 문서가 현재 운영 상태로 오해되지 않도록 문서 계층을 정리한다.

## 현재 운영 정본

신규 정본:

```text
docs/operations/mcp-current-state.md
```

다음 내용을 한 곳에서 정의한다.

- canonical official SDK entrypoint
- emergency manual rollback entrypoint
- 13 public Tool
- 5 hidden legacy compatibility calls
- public contract v1
- RuntimeSnapshot v2
- code ownership
- acceptance commands
- rollback/hidden legacy retention policy
- `orders_enabled=false`
- Docker Host Acceptance의 외부 pending 상태

## 역사 문서 보존 정책

과거 단계 문서는 삭제하거나 내용 자체를 현재 상태로 덮어쓰지 않는다.

다만 다음 종류의 문서에는 상단에 **역사적 단계 문서** 표식을 추가했다.

- 18 public Tool 시점
- public 13 Tool 전환 과정
- manual transport가 canonical이던 시점
- SDK shadow adapter 단계
- SDK canonical cutover 직후 단계
- Phase 6.1~6.3 stabilization 중간 상태

표식은 모두 `mcp-current-state.md`를 현재 정본으로 안내한다.

stale expression scan 결과:

```text
unmarked stale MCP documents = 0
```

## 운영 문서 링크

현재 실행·검증 문서도 정본을 직접 참조한다.

- `README.md`
- `docs/operations/verification.md`
- `docs/operations/system-orchestrator.md`

## Retention policy

manual rollback transport와 hidden legacy direct dispatch는 별개로 유지한다.

```text
manual rollback deletion = separate approval required
hidden legacy deletion = separate approval required
automatic cleanup = forbidden
```

Phase 6 완료 자체는 어떤 compatibility path의 삭제 승인도 의미하지 않는다.

## Acceptance

Canonical official SDK subprocess:

```text
status = PASS
canonical_entrypoint = sdk
sdk_protocol_version = 2025-11-25
legacy_protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
public_contract_schema_version = 1
system_status = STOPPED
orders_enabled=false
```

Manual rollback subprocess:

```text
status = PASS
transport = manual_rollback
protocol_version = 2024-11-05
tool_count = 13
legacy_compatibility_count = 5
public_contract_schema_version = 1
system_status = STOPPED
orders_enabled=false
```

Phase 6 관련 contract/security/acceptance regression:

```text
81 passed
```

## Repository release gate

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (782 tests)
```

## 외부 pending

Windows + Docker Desktop Host Acceptance는 여전히 별도 외부 검증이다.

Moon 환경의 Docker CLI/Engine 부재 때문에 Phase 6에서 실제 Docker Host PASS를 주장하지 않는다.

## Phase 6.4 판정

```text
current operational source of truth = ESTABLISHED
historical documents = MARKED
unmarked stale docs = 0
canonical SDK acceptance = PASS
manual rollback acceptance = PASS
retention policy = FROZEN
phase6 = COMPLETE
orders_enabled=false
```
