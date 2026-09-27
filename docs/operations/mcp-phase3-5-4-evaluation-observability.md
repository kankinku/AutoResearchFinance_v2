# MCP Phase 3-5.4 — Evaluation Job 상태 집계 정밀화

## 목표

Phase 3-5.2에서 이미 제공하던 `counts / active_jobs / queued_jobs / latest_job`을
유지하면서 Evaluation Job의 재시도·timeout·terminal 상태와 durable queue 건강 상태를
더 정확하게 보여준다.

실행·retry 정책 자체는 변경하지 않는다.

## Source authority

Evaluation 관측 정보는 두 소스를 명확히 분리한다.

### 현재 상태 정본

```text
state/system/evaluation-jobs/queue.sqlite
```

SQLite queue가 다음 정보의 정본이다.

- 현재 Job status
- 현재 attempt
- max attempts
- lease
- error class
- retry pending 여부
- retry exhausted 여부

### attempt 이력

```text
state/system/evaluation-jobs.jsonl
```

이 파일은 executor가 attempt 종료 시 append하는 diagnostic journal이다.

현재 상태를 덮어쓰는 정본으로 사용하지 않는다. 다음에만 사용한다.

- recent attempt history
- latest completed attempt
- execution mode
- isolated 여부
- timeout enforcement 여부
- research/generation/attempt 연결 정보

raw error body는 노출하지 않는다.

## 추가 RuntimeSnapshot 필드

`runtime.evaluation`에는 다음이 추가된다.

- `queue_health`
- `queue_issues`
- `total_jobs`
- `terminal_jobs`
- `retry_summary`
- `recent_terminal_jobs`
- `recent_attempts`

기존 `status / counts / active_jobs / queued_jobs / latest_job`은 그대로 유지한다.

### Job 단위

active/queued/terminal Job에는 다음이 추가된다.

- `retries_used`
- `attempts_remaining`
- `retry_pending`
- `lease_expired`

attempt는 claim될 때 증가하므로:

```text
retries_used = max(0, attempt - 1)
attempts_remaining = max(0, max_attempts - attempt)
```

QUEUED인데 이미 한 번 이상 실행된 Job은 `retry_pending=true`다.

## Retry summary

`retry_summary`:

- `jobs_with_retries`: 실제 두 번째 이상 attempt가 시작된 Job 수
- `retries_used`: 전체 추가 attempt 수
- `retry_pending_jobs`: 실패 후 다시 QUEUED 상태인 Job 수
- `retry_exhausted_jobs`: 현재 RETRY_EXHAUSTED 상태인 Job 수

아직 두 번째 claim이 시작되지 않은 retry-pending Job은
`jobs_with_retries`에는 포함하지 않고 `retry_pending_jobs`에 포함한다.

## Terminal Job

현재 queue의 terminal 상태:

- SUCCEEDED
- FAILED
- TIMED_OUT
- CANCELLED
- RETRY_EXHAUSTED

`recent_terminal_jobs`은 SQLite `updated_at` 순서를 이용해 가장 최근 terminal Job
최대 20개를 반환한다.

이는 현재 durable 상태 목록이며 attempt history와는 다르다.

## Recent attempt history

`recent_attempts`은 `evaluation-jobs.jsonl`에서 현재 managed run에 속한 최근
최대 20개 record를 newest-first로 제공한다.

포함 정보:

- job id
- terminal attempt status
- queue attempt/max attempts
- sanitized error class
- execution mode
- isolation/timeout enforcement
- research run / attempt id / generation

JSONL에는 timestamp가 현재 기록되지 않으므로 임의 timestamp를 생성하지 않는다.
파일 append 순서만 recent ordering으로 사용한다.

## Queue health

`queue_health`:

- `HEALTHY`
- `WARN`
- `UNAVAILABLE`

안정적인 issue code:

- `QUEUE_UNREADABLE`
- `EXPIRED_RUNNING_LEASE`
- `RUNNING_LEASE_MISSING`
- `ATTEMPT_RANGE_INVALID`
- `QUEUED_WITHOUT_ATTEMPTS_REMAINING`
- `RETRY_EXHAUSTED_PRESENT`
- `TERMINAL_FAILURE_PRESENT`

### 중요

Snapshot은 stale lease를 reconcile하지 않는다.

예를 들어 RUNNING Job의 lease가 이미 만료됐더라도 조회 과정에서는:

```text
status = RUNNING
lease_expired = true
queue_health = WARN
queue_issues += EXPIRED_RUNNING_LEASE
```

로만 표시한다.

실제 QUEUED/RETRY_EXHAUSTED 전환은 기존 lifecycle/recovery 경계에서만 수행된다.

## Queue read health

기존 `PersistentJobQueue.snapshot_jobs()`의 호환 동작은 유지한다.

추가된 `snapshot_jobs_with_status()`는 다음을 구분한다.

- `EMPTY`: DB 자체가 아직 없음
- `READY`: DB를 정상적으로 read-only 조회함
- `UNAVAILABLE`: SQLite/schema/payload를 안전하게 읽지 못함

DB가 없으면 만들지 않는다. 손상된 DB도 Snapshot 조회가 자동으로 복구하거나
덮어쓰지 않는다.

## local_scheduler와 docker_worker

durable SQLite queue는 Docker/process boundary에서 특히 중요하다.

`local_scheduler`는 실행 중 Job을 in-memory queue에서 관리하므로 실행 중 local Job이
SQLite에 나타나지 않을 수 있다. 대신 완료된 local attempt는 기존
`evaluation-jobs.jsonl`과 worker heartbeat를 통해 관측할 수 있다.

따라서:

- durable current Job lifecycle: SQLite가 정본
- cross-backend recent attempts: JSONL
- worker freshness: heartbeat

로 역할을 나눈다.

## 안전성

변경하지 않은 것:

- retry 조건
- max_retries
- timeout 값
- lease recovery
- Docker cleanup
- evaluator 실행
- Evidence
- MCP tool 이름/입력 schema
- KIS/live permission

관측 layer만 추가되었다.

## 다음 단계

Phase 3-5.5에서는 Evidence/Knowledge 상태를 중복 구현하지 않고 다음을 정밀화한다.

- Evidence journal과 Knowledge projection sync 상태
- 마지막 Evidence event/generation
- champion promotion 연결성
- Knowledge projection freshness
- frontier/rescue가 아직 NOT_CONNECTED인 이유를 명확하게 유지
