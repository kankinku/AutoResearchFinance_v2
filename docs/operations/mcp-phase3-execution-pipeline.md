# MCP 전환 Phase 3-1 — Queue 기반 평가 실행 경계

## 목적

Phase 3-1은 기존에 테스트에서만 사용되던 `JobQueue`, `LocalScheduler`,
`ResourceManager`, `WorkerHeartbeatStore`를 실제 평가 실행 경로에 연결한다.

외부 CLI/MCP 스키마, StrategyIR, Dashboard HTTP 경로, KIS paper/live 경계는 변경하지 않는다.

## 실행 경로

기존:

```text
CLI / MCP / AutoResearch
  -> run_local_evaluation()
  -> GenerationPipeline
  -> BacktestEngine
```

Phase 3-1:

```text
CLI / MCP / AutoResearch
  -> QueuedEvaluationExecutor
  -> JobQueue
  -> LocalScheduler
  -> ResourceManager
  -> local backtest worker
  -> run_local_evaluation()
  -> GenerationPipeline
  -> Evidence / Knowledge / Dashboard projection
```

`run_local_evaluation()` 자체는 결정론적 내부 평가 함수로 유지한다. 따라서 직접 호출하면
`direct_local`, Application Service와 AutoResearch 기본 경로에서는
`local_scheduler`로 Evidence에 기록된다.

## 재시도

research policy의 `max_retries`, `job_timeout_seconds`, `max_concurrency`를
executor 기본 설정으로 사용한다.

현재 로컬 scheduler에서 자동 재시도하는 예외는 다음 worker/transport 계열로 제한한다.

- `TimeoutError`
- `ConnectionError`
- `BrokenPipeError`

전략 검증 실패, 입력 파일 오류 등 결정론적 오류는 재시도하지 않는다.

최대 시도를 모두 소진하면 job은 `RETRY_EXHAUSTED`가 된다. job log에는 오류 본문을
저장하지 않고 오류 클래스만 저장해 provider 또는 내부 상세정보가 상태 파일로 유출되지 않게 한다.

## 실행 Evidence

기존 `attempt.execution` 안에 worker metadata를 포함한다.

로컬 scheduler의 현재 의미는 다음과 같다.

```json
{
  "execution_mode": "local_scheduler",
  "isolated": false,
  "timeout_enforced": false
}
```

여기서 `lease_seconds`는 queue lease/recovery 정책 값이다. 현재 Thread 기반 local
scheduler는 실행 중인 Python 함수를 강제 종료하지 않으므로 이를 실제 timeout으로 표현하지 않는다.

## Heartbeat / 운영 상태

각 실행 job은 `state/worker-heartbeats/local-evaluation-*.json`에 worker heartbeat를 남긴다.
상태는 RUNNING 이후 SUCCEEDED 또는 FAILED로 갱신되고 queue attempt 번호가 함께 기록된다.

또한 `state/system/evaluation-jobs.jsonl`에는 민감한 오류 본문 없이 다음 운영 메타데이터를 남긴다.

- job id
- research run / attempt id
- generation
- queue attempt / max attempts
- terminal status
- error class
- execution mode
- isolation / timeout enforcement 상태
- lease seconds

## 아직 하지 않은 것

Phase 3-1은 Docker worker를 실제 job consumer로 전환하지 않는다.

현재 `SystemController`가 시작하는 Docker backtest worker는 기존 별도 실행 방식이다.
따라서 Phase 3-1의 실행 Evidence는 Docker 격리 또는 subprocess timeout을 주장하지 않는다.

다음 내부 단계에서 공통 job envelope/result contract를 파일 또는 IPC 경계로 직렬화한 뒤,
Docker worker가 같은 job을 소비하도록 연결해야 한다.


# Phase 3-2 — Cross-process / Docker evaluation worker

## Shared job contract

Phase 3-2 adds a versioned `EvaluationJobRequest` / `EvaluationJobResult` contract.
Only project-relative research input paths and validated evaluation options cross the
worker boundary. Typed parameter domains, mutation operations and StrategyIR overrides
are converted to JSON-safe payloads and reconstructed in the worker.

The queue of record for Docker execution is:

```text
state/system/evaluation-jobs/queue.sqlite
```

SQLite transactions make claim/update operations authoritative across processes. A host
claims a job and assigns its lease before launching the container. The container must
consume that already leased job; it cannot silently create or claim a different job.

## Docker worker path

Docker mode is opt-in. The default remains `local_scheduler`.

Process environment:

```text
QUANT_EVALUATION_EXECUTION=docker_worker
QUANT_EVALUATION_DOCKER_IMAGE=quant-autoresearch-worker:local
```

When enabled, the path is:

```text
EvaluationService / AutoResearch
  -> QueuedEvaluationExecutor
  -> PersistentJobQueue (SQLite)
  -> lease job
  -> docker run --network none --read-only ...
  -> runtime.system_worker --role evaluation-job
  -> load leased EvaluationJobRequest
  -> run_local_evaluation
  -> Evidence / Knowledge / ledger
  -> EvaluationJobResult
  -> PersistentJobQueue SUCCEEDED
  -> host reads result
```

The project mount is read-only. Only the selected state directory is overlaid read-write.
The container runs with no network, all Linux capabilities dropped,
`no-new-privileges`, PID/memory/CPU limits and a noexec temporary filesystem.

## Timeout enforcement

Unlike the local Thread scheduler, Docker mode enforces the research policy
`job_timeout_seconds` at the process/container boundary.

If `docker run` exceeds the timeout:

1. the host executes `docker rm -f <container>`,
2. the local Docker CLI process is killed,
3. the leased job is marked `TIMED_OUT`,
4. retry policy is applied,
5. after the maximum attempt count the job becomes `RETRY_EXHAUSTED`.

A nonzero worker process that exits before updating the shared queue is marked
`WorkerProcessError` and may be retried. A worker that records a deterministic
error such as `ValueError` is not automatically retried.

## Crash / lease recovery

Because the lease is stored in SQLite rather than process memory, a new host process can
call `reconcile_stale()` after an expired lease. The job is then either requeued or
marked `RETRY_EXHAUSTED` according to its persisted attempt count.

This recovery behavior is covered by an actual separate Python-process integration test,
not only by two queue objects in the same interpreter.

## Evidence semantics

A worker that actually executes inside the Docker job path records:

```json
{
  "execution_mode": "docker_worker",
  "isolated": true,
  "timeout_enforced": true
}
```

The local path continues to record:

```json
{
  "execution_mode": "local_scheduler",
  "isolated": false,
  "timeout_enforced": false
}
```

Operational job logs continue to omit exception message bodies and retain only error
classes.

## Environment verification limitation

The Moon development container used for Phase 3-2 does not expose a Docker CLI.
Therefore a real Docker Engine smoke run cannot be executed from this environment.

Validated here instead:

- Docker command isolation and mount contract
- forced `docker rm -f` cleanup on timeout
- timeout/retry state transitions
- persistent queue and lease recovery
- real separate-process worker consumption
- typed request/result round trip

A host-side Docker smoke remains an environment acceptance check rather than a missing
code path.


# Phase 3-3 — SystemController orchestration unification

Phase 3-3 removes the final legacy split in `SystemController.start()`.

Previously:

```text
start_system
  -> research_worker: propose one ResearchIntent and exit
  -> backtest_worker: independently run repeated evaluation of the original strategy
```

That meant the two workers ran in parallel but did not form a causal research loop.

Now:

```text
start_system
  -> research_worker
       -> run_autoresearch()
       -> ResearchIntent
       -> evaluation executor
       -> Evidence / Knowledge
       -> next generation
```

There is no permanently running `backtest_worker`. Docker evaluation uses the durable
job path introduced in Phase 3-2 and creates a container only for a leased evaluation Job.

The execution backend is selected internally through
`QUANT_EVALUATION_EXECUTION=local_scheduler|docker_worker`; the public MCP schema remains
unchanged. Local scheduler is the default. Docker prerequisites are mandatory only when
`docker_worker` is selected.

System status exposes a logical `evaluation_backend` component with the number of active
persistent jobs. System stop terminates managed processes, forcibly removes active Docker
evaluation containers, and marks successfully stopped persistent jobs as CANCELLED.

# Phase 3-4 — Durable managed lifecycle recovery

Phase 3-4 makes managed-system ownership survive MCP/Controller recreation.

- `managed_run_id` is propagated from `SystemController` to the research worker and
  evaluation executor.
- Persistent evaluation Jobs retain the same managed-run identity.
- Managed process PID plus command-line identity markers are persisted so PID reuse cannot
  cause an unrelated process to be treated as owned.
- `get_system_status` reconstructs process liveness and queue activity from persisted state.
- Duplicate `start_system` returns `ALREADY_RUNNING` when the existing managed runtime is
  still active.
- Concurrent start/stop transitions are serialized by a nonblocking cross-process lifecycle
  file lock and return `BUSY` instead of racing.
- Expired evaluation leases are reconciled only within their owning managed run. If the
  research owner is gone, requeued orphan Jobs are cancelled as `OwnerExited`.
- Recovered `stop_system` terminates only owned processes and owned Docker evaluation Jobs.
- System health is aggregated into RUNNING, COMPLETED, FAILED, DEGRADED, STOPPED or
  STOP_FAILED.

A separate `scripts/verify_docker_evaluation.py` host acceptance command verifies real
Docker Engine/image availability and can run one isolated evaluation Job without enabling
orders.
