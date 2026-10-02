# MCP Phase 3-5.2 — Existing RuntimeSnapshot schema consolidation

기준: Phase 3-5.1 state-source inventory 이후.

## 목표

기존 `runtime/runtime_snapshot.py`의 dict 기반 read model을 typed contract로 고정하고,
`SystemController.status()`의 lifecycle/process 상태와 operational runtime 상태를
하나의 일관된 `runtime` 구조로 제공한다.

공개 MCP tool 이름과 입력 schema는 변경하지 않는다. 기존 top-level
`status`, `components`, `managed_run_id` 등도 호환성을 위해 유지한다.

## Runtime schema v2

`runtime`은 다음 섹션을 항상 가진다.

- `system`: managed run, aggregate status, backend, process/component 상태
- `research`: current generation/phase, timing, sanitized error class, current intent summary
- `evaluation`: durable queue counts, active/queued jobs, latest execution record
- `evidence`: 현재 research run의 immutable Evidence 상태
- `workers`: heartbeat 기반 worker freshness
- `llm`: provider 상태와 마지막 operation/result
- `recovery`: 마지막 recovery event와 현재 reconcile 결과
- `knowledge`: Evidence-derived Knowledge projection count
- `strategy_state`: champion projection과 frontier/rescue 연결 상태
- `recent_errors`: raw message를 제외한 source + error class 요약
- `orders_enabled=false`

모델 정의는 `runtime/runtime_contracts.py`에 있으며 Pydantic
`extra="forbid"`를 사용해 accidental schema drift를 방지한다.

## Source precedence

Phase 3-5.1에서 정한 우선순위를 그대로 적용한다.

1. OS process validation
2. PersistentJobQueue SQLite
3. EvidenceStore SQLite
4. `system/autoresearch.json`
5. reconciled `system.json` / worker state
6. verified Knowledge projection
7. worker heartbeat / LLM provider projection
8. diagnostic JSONL
9. dashboard/legacy cache
10. initialized-only placeholder

### Evaluation

`queue.sqlite`가 Job 상태 정본이다. `evaluation-jobs.jsonl`은 latest execution의
isolation/timeout 등의 설명 정보만 제공한다.

RuntimeSnapshot 조회가 Queue DB를 생성하면 read가 state를 변경하게 되므로
`PersistentJobQueue.snapshot_jobs()`를 추가했다. 이 메서드는 DB가 없으면 빈 결과를
반환하고, DB가 있으면 SQLite read-only URI로 읽는다.

## ResearchIntent

현재 Intent는 `llm/intents.jsonl`에서 추측하지 않는다.

`llm/intents.jsonl`에는 research_run_id/generation 귀속 정보가 없기 때문에
RuntimeSnapshot은 `autoresearch.json.generations[]`에서
`current_generation`과 정확히 일치하는 generation record만 사용한다.

노출하는 정보도 제한한다.

- generation
- intent status
- mode
- parent IDs
- operation count
- repair attempt count

rationale, raw repair message, provider 내부 상세는 Snapshot에 포함하지 않는다.

## Managed process 통합

`SystemController`가 OS process identity를 검증하고 component 상태를 reconcile한 뒤,
그 결과를 RuntimeSnapshot의 `system` section에 전달한다.

따라서 응답은 호환성을 위해 다음 두 표현을 동시에 가진다.

```text
status/components        기존 public projection
runtime.system           typed consolidated projection
```

두 값은 같은 reconciled source에서 생성된다.

시스템이 아직 시작되지 않았을 때도:

```text
status = STOPPED
runtime.schema_version = 2
runtime.system.status = STOPPED
runtime.research.status = NOT_STARTED
```

형태로 동일 schema를 반환한다.

## Worker / LLM / Recovery

Worker는 `worker-heartbeats/*.json`에서 다음만 읽는다.

- worker/job id
- role/status
- last heartbeat
- ONLINE/STALE/OFFLINE/UNKNOWN
- attempt
- sanitized error class

LLM은 `llm/status.json`에서 provider/status/last_result/time/operation만 읽는다.

Recovery는 현재 reconcile 결과와 `recovery-events.jsonl`의 마지막 유효 이벤트를
합치되, durable queue/Evidence 상태를 덮어쓰지 않는다.

## Knowledge / Strategy state

Knowledge는 `knowledge.json`을 Evidence projection으로 명시하고
known_good/known_bad/unexplored/interactions 개수만 노출한다.

Champion은 `champion.json`의 sanitized summary를 읽는다.

`frontier.json`, `rescue_pool.json`은 현재 canonical loop에 durable production
writer가 연결되지 않았으므로 파일 내용이 존재해도:

```text
frontier_status = NOT_CONNECTED
rescue_status = NOT_CONNECTED
```

로 표시한다. 초기화된 빈 파일을 실제 연결된 runtime 상태로 오인하지 않는다.

## Side-effect-free read

`build_runtime_snapshot()` / `read_runtime_snapshot()`은 상태를 생성하거나 변경하지 않는다.

특히 state directory가 전혀 없는 경우 Snapshot 조회 후에도 directory가 생성되지 않는다.

Recovery mutation과 stale queue reconciliation은 계속 `SystemController`의 lifecycle
경계에서만 수행된다. Snapshot builder 자체는 pure read다.

## 호환성

변경하지 않은 항목:

- MCP tool name
- MCP input schema
- CLI command surface
- StrategyIR
- Dashboard route
- KIS permission/live gate
- paper-only order safety

기존 `runtime.research`, `runtime.evaluation`, `runtime.evidence`,
`runtime.orders_enabled` 필드도 유지되므로 기존 소비자는 그대로 동작한다.

## 검증 포인트

- typed RuntimeSnapshot validation
- current ResearchIntent sanitization
- worker raw error/identity marker 비노출
- managed run 기준 queue filtering
- no-state pure read
- frontier/rescue initialized-only 상태 비연결 처리
- STOPPED/RUNNING SystemController와 nested `runtime.system` 일치
- 기존 public MCP contract regression

다음 세부 단계는 Phase 3-5.3의 계획을 현재 구현 상태와 다시 대조한 뒤,
이미 Snapshot에 포함된 research generation 정보를 중복 구현하지 않고
남은 observability 세분화 작업만 수행해야 한다.
