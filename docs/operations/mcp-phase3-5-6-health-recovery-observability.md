# MCP Phase 3-5.6 — 오류·복구 상태 집계 정밀화

## 목표

기존 RuntimeSnapshot에 이미 존재하는 research, evaluation, worker, LLM,
recovery, Evidence, Knowledge, champion 상태를 다시 구현하지 않고 하나의
읽기 전용 health summary로 집계한다.

새 필드는:

```text
runtime.health
```

이다.

기존 `recent_errors`는 그대로 유지한다.

## Health 상태

`runtime.health.status`는 다음 중 하나다.

- `HEALTHY`
- `DEGRADED`
- `STALE`
- `UNAVAILABLE`
- `INTERRUPTED`
- `FAILING`

Health는 실행 제어 신호가 아니다. 관측용 read model이며 어떠한 retry/recovery/
process 종료도 수행하지 않는다.

## 우선순위

동시에 여러 문제가 존재할 수 있으므로 overall status는 다음 severity 순서로 정한다.

```text
FAILING
  > INTERRUPTED
  > UNAVAILABLE
  > STALE
  > DEGRADED
  > HEALTHY
```

동일 severity에서는 source와 stable issue code로 정렬해 결과를 deterministic하게 유지한다.

예를 들어 research가 INTERRUPTED인데 Evidence checksum까지 손상된 경우:

```text
health.status = FAILING
primary_source = evidence
primary_code = EVIDENCE_INTEGRITY_ERROR
```

이고 `RESEARCH_INTERRUPTED`도 issues 목록에는 남는다.

## Typed health contract

`RuntimeHealthSummary`:

- `status`
- `primary_source`
- `primary_code`
- `issue_count`
- `issues`
- `recovery_action_count`
- `last_recovery_event`
- `interrupted_research_run_id`

각 issue는:

- `status`
- `source`
- `code`
- `error_class`

만 가진다.

raw exception body, provider 상세 메시지, process marker는 포함하지 않는다.

## Source별 판정

### Evidence

`integrity_status=INTEGRITY_ERROR`

→ `FAILING / EVIDENCE_INTEGRITY_ERROR`

Evidence는 immutable 정본이므로 가장 강한 실패 신호 중 하나다.

현재 research가 가리키는 run이 Evidence에 없으면:

→ `DEGRADED / EVIDENCE_RUN_MISSING`

### Research

- `status=FAILED` → `FAILING / RESEARCH_FAILED`
- `status=INTERRUPTED` → `INTERRUPTED / RESEARCH_INTERRUPTED`
- `is_stale=true` → `STALE / RESEARCH_STALE`
- `consistency_status=WARN` → `DEGRADED / RESEARCH_STATE_INCONSISTENT`

research error는 raw text 대신 sanitized `error_class`만 issue에 연결한다.

### Evaluation Queue

Queue 자체를 읽을 수 없으면:

→ `UNAVAILABLE / EVALUATION_QUEUE_UNAVAILABLE`

Queue issue mapping:

| Queue issue | Health |
|---|---|
| EXPIRED_RUNNING_LEASE | STALE |
| RUNNING_LEASE_MISSING | DEGRADED |
| RETRY_EXHAUSTED_PRESENT | DEGRADED |
| TERMINAL_FAILURE_PRESENT | DEGRADED |
| ATTEMPT_RANGE_INVALID | FAILING |
| QUEUED_WITHOUT_ATTEMPTS_REMAINING | FAILING |

Snapshot은 expired lease를 수정하지 않는다.

### Worker

- heartbeat `STALE` → `STALE / WORKER_HEARTBEAT_STALE`
- status는 RUNNING인데 heartbeat는 OFFLINE → `STALE / WORKER_OFFLINE_WHILE_RUNNING`
- worker `FAILED` → `DEGRADED / WORKER_FAILED`

worker error는 `error_class`만 사용한다.

terminal worker의 OFFLINE 상태 자체는 정상 종료일 수 있으므로 별도 오류로 만들지 않는다.

### LLM

provider status가:

- OFFLINE
- FAILED
- ERROR

중 하나면:

→ `DEGRADED / LLM_PROVIDER_UNAVAILABLE`

LLM failure만으로 전체 시스템을 FAILING 처리하지 않는 이유는 기존 autoresearch가
repair/fallback 경로를 가질 수 있기 때문이다.

### Knowledge

- STALE → `DEGRADED / KNOWLEDGE_STALE`
- MISSING → `DEGRADED / KNOWLEDGE_MISSING`
- INVALID → `DEGRADED / KNOWLEDGE_INVALID`

Evidence integrity error는 Evidence source의 stronger signal로 이미 표현되므로
중복된 Knowledge issue는 생성하지 않는다.

### Champion provenance

실제 champion이 있는데 Evidence에서 찾을 수 없으면:

→ `DEGRADED / CHAMPION_EVIDENCE_NOT_FOUND`

champion이 있는데 promotion audit가 없거나 손상되었으면:

- `PROMOTION_AUDIT_MISSING`
- `PROMOTION_AUDIT_INVALID`

로 DEGRADED 상태를 추가한다.

frontier/rescue의 `NOT_CONNECTED`는 이미 알려진 미구현 persistence gap이므로
전체 health를 항상 DEGRADED로 만들지 않는다.

## System / component

- system `FAILED` → FAILING
- component `FAILED` → FAILING
- system `DEGRADED` → DEGRADED

STOPPED 상태 자체는 장애가 아니다.

따라서 runtime state가 하나도 없는 clean workspace는 health상 `HEALTHY`다.
이는 “프로세스가 실행 중”이라는 뜻이 아니라 “관측된 active fault가 없다”는 뜻이다.

## Recovery 결과

과거 recovery event가 존재한다는 이유만으로 시스템을 계속 DEGRADED로 유지하지 않는다.

대신 health summary에:

- `recovery_action_count`
- `last_recovery_event`
- `interrupted_research_run_id`

를 별도로 제공한다.

`recovery_action_count`는 현재 reconcile 결과의:

```text
reconciled_jobs ∪ cancelled_orphaned_jobs
```

고유 Job 수다.

현재 research/recovery 상태가 실제 INTERRUPTED일 때만 overall health가 INTERRUPTED가 된다.

## recent_errors와의 관계

`recent_errors`는 기존 호환 필드로 유지한다.

역할은 다르다.

```text
recent_errors
  = source + error_class 위주의 기존 오류 요약

health
  = 현재 전체 runtime 상태를 source authority와 severity에 따라 판정한 운영 요약
```

Health issue는 exception이 없는 stale/integrity/projection 문제도 표현할 수 있다.

## Side-effect-free

Health 계산은 이미 만들어진 typed snapshot들을 입력으로 사용한다.

따라서 health 계산 자체는:

- Queue reconcile
- recovery event append
- Knowledge sync
- Evidence mutation
- process stop/restart

를 수행하지 않는다.

## 호환성

변경하지 않은 항목:

- 기존 RuntimeSnapshot field
- `recent_errors`
- MCP tool 이름/입력 schema
- CLI
- Dashboard route
- StrategyIR
- retry/recovery semantics
- Evidence/Knowledge semantics
- KIS/live permission
- order enablement

## 다음 단계

Phase 3-5.7에서는 지금까지의 3-5.1~3-5.6 결과를 하나의 관측성 계약으로 검증한다.

권장 범위:

1. SystemController → RuntimeSnapshot → MCP 출력 end-to-end contract test
2. STOPPED/RUNNING/DEGRADED/INTERRUPTED/FAILED 대표 fixture 검증
3. raw secret/error leakage regression
4. pure-read filesystem mutation regression
5. state-source precedence regression
6. 3-5 단계 최종 문서/완료 판정
