# MCP Phase 3-5 — Runtime observability completion

완료 기준 커밋: Phase 3-5.7 작업 기준 `b6d491f` 이후
검증 범위: SystemController → Application SystemService → MCP `get_system_status`

## 1. 완료 범위

Phase 3-5는 다음 세부 단계로 완료되었다.

- 3-5.1 runtime 상태 데이터 전수조사
- 3-5.2 typed RuntimeSnapshot schema consolidation
- 3-5.3 research observability 정밀화
- 3-5.4 evaluation observability 정밀화
- 3-5.5 Evidence / Knowledge / champion provenance 정밀화
- 3-5.6 runtime health / recovery 집계
- 3-5.7 end-to-end MCP integration validation

## 2. RuntimeSnapshot 최종 구조

`runtime.schema_version = 2`

항상 다음 read model을 제공한다.

- `system`
- `research`
- `evaluation`
- `evidence`
- `workers`
- `llm`
- `recovery`
- `knowledge`
- `strategy_state`
- `health`
- `recent_errors`
- `orders_enabled=false`

MCP tool 이름과 입력 schema는 변경하지 않았다.

## 3. End-to-end 상태 검증

`get_system_status` 경로에서 다음 대표 상태를 실제 application/MCP serialization까지
검증한다.

### STOPPED

초기화되지 않은 workspace:

- top-level `status=STOPPED`
- `runtime.system.status=STOPPED`
- typed schema v2 validation 통과
- `runtime.health=HEALTHY`
- orders disabled

여기서 HEALTHY는 프로세스 실행 중이라는 뜻이 아니라 active fault가 관측되지 않았다는
뜻이다.

### RUNNING

dashboard와 research worker process identity가 모두 유효한 managed run:

- top-level RUNNING
- nested `runtime.system.status=RUNNING`
- managed_run_id 일치
- typed RuntimeSnapshot validation 통과

### DEGRADED

research worker는 살아 있으나 dashboard process가 사라진 상태:

- top-level DEGRADED
- nested system DEGRADED
- runtime health DEGRADED

### INTERRUPTED

RUNNING research projection이 존재하지만 research owner process가 종료되고
active evaluation job도 없는 상태:

- SystemController lifecycle recovery가 research를 INTERRUPTED로 전환
- immutable Evidence end event를 INTERRUPTED로 닫음
- top-level INTERRUPTED
- runtime research/evidence/health 모두 interruption을 일관되게 반영

이는 read-only RuntimeSnapshot 자체의 mutation이 아니라 기존 SystemController
lifecycle reconciliation 책임이다.

### FAILED

현재 managed run의 research worker terminal state가 FAILED인 경우:

- top-level FAILED
- runtime system FAILED
- runtime health FAILING
- raw worker 오류 원문은 MCP output에 노출하지 않음

## 4. Source precedence 검증

동시에:

- RUNNING research가 stale
- durable Evaluation Queue가 unreadable

인 fixture에서:

```text
research.is_stale = true
evaluation.queue_health = UNAVAILABLE
health.status = UNAVAILABLE
health.primary_source = evaluation
health.primary_code = EVALUATION_QUEUE_UNAVAILABLE
```

을 검증했다.

즉 stronger health condition이 낮은 severity의 stale signal에 의해 가려지지 않는다.

개별 source signal은 health issues 안에 함께 보존된다.

## 5. MCP application boundary sanitization

SystemController 내부 state는 프로세스 복구를 위해 다음 정보를 저장할 수 있다.

- local project_root
- process identity_markers
- internal container name

이 정보는 내부 lifecycle 관리에는 필요하지만 MCP 소비자에게 필요하지 않다.

Phase 3-5.7부터 `SystemService`가 application boundary에서 다음을 제거한다.

- `project_root`
- `container_name`
- component `identity_markers`
- component internal `command/cwd/env_file`

SystemController의 persisted state는 변경하지 않으므로 controller recreation과 process
identity 검증 기능은 유지된다.

RuntimeSnapshot에서도 기존 규칙대로 raw exception/provider text 대신
sanitized error class와 stable issue code만 노출한다.

## 6. Pure-read 통합 검증

Phase 3-5.2에서 RuntimeSnapshot builder는 이미 pure read였다.

3-5.7 E2E 검증에서 그 위 계층에 두 side effect가 추가로 발견되었다.

### 6.1 WorkerHeartbeatStore eager mkdir

기존:

```text
create_application_services()
→ EvaluationService()
→ QueuedEvaluationExecutor()
→ WorkerHeartbeatStore()
→ state/worker-heartbeats mkdir
```

따라서 실제 evaluation을 실행하지 않아도 MCP server 생성만으로 state가 생겼다.

수정 후:

- WorkerHeartbeatStore 생성자는 path만 보관
- 최초 `record()` 때만 directory 생성

heartbeat 기록 기능 자체는 그대로다.

### 6.2 모든 tools/call의 provider-status write

기존 CodexMCPServer는 `tools/call` 자체를 MCP connection activity로 간주해
`llm/status.json`을 기록했다.

따라서 read-only `get_system_status`도 state mutation을 일으킬 수 있었다.

수정 후 connection-state write는 다음 protocol-level handshake/activity에만 남긴다.

- `initialize`
- `ping`
- `tools/list`

일반 `tools/call`은 자동 provider-status write를 하지 않는다.

Codex proposal/repair를 실제 실행하는 provider는 기존처럼 자신의 상태를 별도로 기록한다.

### 6.3 Pure-read 보장 범위

초기화되지 않은 workspace에서:

```text
create_mcp_server()
get_system_status
```

만 수행하면 state directory 자체가 생성되지 않는 것을 E2E test로 고정했다.

단, 기존 SystemController `status()`는 active managed runtime이 있을 때 process liveness,
orphan queue, interruption을 reconcile하고 그 결과를 persist할 수 있다.

이 동작은 lifecycle recovery semantics이며 제거하지 않는다.

따라서 보장은 다음과 같다.

```text
RuntimeSnapshot read          = pure
MCP transport status query    = no incidental write
service construction          = no incidental heartbeat mkdir
managed lifecycle reconcile   = intentional mutation allowed
```

## 7. 보안/정보 노출 regression

E2E MCP payload에서 다음 값이 나오지 않는 것을 검증한다.

- raw research exception detail
- raw worker exception detail
- process identity markers
- local project root
- internal container name

대신 필요한 진단은:

- `error_class`
- stable health issue code
- source identifier

로 유지된다.

## 8. 공개 계약

Phase 3-5.7에서도 다음은 유지한다.

- MCP tool name set
- MCP input schemas
- CLI command surface
- StrategyIR contract
- Dashboard routes
- KIS/live permission boundary
- `orders_enabled=false` safety

`get_system_status`의 application-facing output은 내부 process identity metadata를 제거하지만
runtime/status/components의 기능적 정보는 유지한다.

## 9. Phase 3-5 완료 판정

Phase 3-5의 목적이었던 “MCP에서 현재 연구 시스템이 무엇을 하고 있고,
어디에서 문제가 생겼는지를 안전하고 일관되게 읽는 관측성 계층”은 완료로 판정한다.

완료된 기능:

- typed schema
- research progress/stale/consistency
- durable evaluation queue/retry/timeout health
- immutable Evidence integrity
- Knowledge projection sync
- champion provenance
- worker/LLM/recovery state
- consolidated health
- MCP end-to-end sanitization
- pure-read inactive status path
- lifecycle recovery 상태 일관성

다음 단계는 **Phase 3-6 — MCP 운영 명령 최종 정리**다.

Phase 3-6에서는 RuntimeSnapshot을 다시 확장하지 않고 현재 관측성 계약을 사용해
MCP tool surface를 공개/내부/중복/폐기 후보로 분류하고 실제 운영 UX를 정리한다.
