# MCP Phase 3-7.4 — Docker Evidence 검증

## 목적

단일 Docker evaluation Job의 성공 판정을 durable queue 상태만으로 끝내지 않고,
동일 run/attempt/job의 immutable Evidence가 실제 Docker worker execution metadata를
기록했는지까지 검증한다.

## Host acceptance PASS 조건

Phase 3-7.3의 조건:

- 고유 managed_run_id
- 정확히 1개의 durable Job
- queue status = SUCCEEDED
- evaluation status = COMPLETED

에 더해 다음 Evidence 조건을 모두 만족해야 한다.

```text
attempt.research_run_id == evaluation result research_run_id
attempt.attempt_id == evaluation result attempt_id
execution.worker.job_id == durable queue job_id
execution.worker.managed_run_id == host acceptance managed_run_id
execution.worker.execution_mode == docker_worker
execution.worker.isolated == true
execution.worker.timeout_enforced == true
```

하나라도 다르면 host acceptance는 PASS하지 않는다.

## 검증 경로

`scripts/verify_docker_evaluation.py`의 `verify_docker_evidence()`는
`EvidenceStore.events()`를 read-only로 읽는다.

1. research_run_id + attempt_id에 해당하는 attempt event를 찾는다.
2. 정확히 하나인지 확인한다.
3. `execution.worker` object 존재 여부를 확인한다.
4. docker_worker / isolated / timeout_enforced를 확인한다.
5. durable queue의 job_id와 managed_run_id가 Evidence와 동일한지 확인한다.

Evidence checksum/integrity 오류가 있으면 안전하게 실패한다.

## 성공 출력

실제 Docker Desktop host에서 성공하면 single-job acceptance JSON에는 다음이 포함된다.

```text
status = PASS
queue_status = SUCCEEDED
durable_job_count = 1
evidence_verified = true

evidence.status = VERIFIED
evidence.execution_mode = docker_worker
evidence.isolated = true
evidence.timeout_enforced = true
evidence.job_id = <same queue job>
evidence.managed_run_id = <same managed run>
orders_enabled = false
```

## 검증한 실패 조건

자동 테스트는 다음을 거부한다.

- Evidence attempt 없음
- 동일 run/attempt가 유일하지 않음
- worker metadata 없음
- execution_mode가 docker_worker가 아님
- isolated=false
- timeout_enforced=false
- job_id 불일치
- managed_run_id 불일치
- Evidence store integrity/read 오류

## Canonical evaluator integration

단순 수동 Evidence fixture만 검사하지 않는다.

테스트에서 실제 `run_local_evaluation()`에 Docker execution context를 전달해
immutable Evidence를 생성한 뒤 `verify_docker_evidence()`가 같은
research_run_id / attempt_id / job_id / managed_run_id를 검증하는 경로도 실행한다.

이 테스트는 Evidence persistence 의미를 검증하지만 Docker container isolation 자체를
대체하지는 않는다.

## Moon 환경 판정

Moon에는 Docker CLI/Engine이 없으므로 실제 container가 생성한 Evidence를 여기서
관찰할 수는 없다.

따라서 현재 판정은:

```text
Evidence verification logic: COMPLETE
Canonical evaluator -> Evidence integration: VERIFIED
Actual Docker container Evidence on Moon: ENVIRONMENT_BLOCKED
Windows Docker Desktop host Evidence acceptance: 실행 필요
```

실제 host에서는 Phase 3-7.3과 같은 명령 하나가 Queue와 Evidence를 함께 검증한다.

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-acceptance `
  --image quant-autoresearch-worker:local `
  --prepare-fixture
```

PASS가 반환되면 3-7.3의 single Job과 3-7.4의 Evidence 조건이 동시에 충족된 것이다.

## 안전 경계

Evidence 검증은 읽기 전용이며 다음을 활성화하지 않는다.

- KIS 주문
- live account
- credential 전달
- validation/sealed OOS promotion

`orders_enabled=false`를 유지한다.

다음 단계는 Phase 3-7.5 — 실제 timeout 강제 및 `docker rm -f` host 검증이다.
