# MCP Phase 3-7.3 — 단일 Docker Evaluation Job acceptance

## 목적

실제 Docker Desktop host에서 하나의 canonical evaluation을 다음 전체 경로로 실행했음을
검증할 수 있는 acceptance 경로를 고정한다.

```text
Host acceptance
-> QueuedEvaluationExecutor(docker_worker)
-> PersistentJobQueue enqueue/claim
-> docker run
-> runtime.system_worker --role evaluation-job
-> run_local_evaluation
-> PersistentJobQueue SUCCEEDED
-> host result read
```

## 결정론적 acceptance fixture

저장소에는 normalized 전략 JSON은 체크인되어 있지만 development Parquet fixture는 없다.
따라서 `--prepare-fixture` 옵션은 다음을 사용한다.

- `strategies/normalized/*.json` 중 정렬상 첫 전략
- state directory 아래에 생성한 `host-fixture/bars.parquet`
- dataset version: `docker-host-acceptance-v1`
- zone: `development`
- symbol: `QQQ`
- daily bars: 80개

fixture는 acceptance를 위한 합성 데이터이며 validation/sealed OOS로 승격하지 않는다.

state directory는 project root 내부에 있어야 한다. 그래야 컨테이너의 `/workspace/state`
overlay와 project-relative input contract가 동일한 파일을 가리킨다.

## Host 명령

Phase 3-7.2의 image build 검증이 READY인 Windows host에서:

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-acceptance `
  --image quant-autoresearch-worker:local `
  --prepare-fixture
```

사용자가 실제 development 전략/데이터를 지정하려면 기존 `--source-path`와 `--data-path`를
계속 사용할 수 있다.

## 성공 판정

단순히 evaluator가 dict를 반환하는 것만으로 PASS하지 않는다.
고유한 `managed_run_id`로 durable queue를 다시 읽어서 정확히 하나의 Job이 존재하고,
그 Job의 최종 상태가 `SUCCEEDED`인지 검증한다.

정상 결과에는 다음이 포함된다.

```text
status = PASS
evaluation_status = COMPLETED
durable_job_count = 1
queue_status = SUCCEEDED
queue_attempt = 1
job_id = <evaluation-...>
managed_run_id = <host-acceptance-...>
research_run_id = <run id>
attempt_id = <attempt id>
orders_enabled = false
```

## 자동 검증

Docker 없이도 다음을 검증한다.

- deterministic development Parquet fixture 생성
- fixture state가 project root 밖이면 거부
- docker_worker executor 사용
- managed_run_id가 executor와 queue 조회에 동일하게 전달됨
- durable Job이 없거나 하나가 아니면 PASS 거부
- queue final status가 SUCCEEDED가 아니면 PASS 거부
- 기존 worker subprocess/queue protocol 테스트

## Moon 실제 결과

Moon에서 fixture 생성은 성공했다.

```text
source = strategies/normalized/0a805e67c88e16da-4.json
zone = development
bars = 80
```

하지만 실제 Docker Job 실행은 환경 제한으로 다음에서 중단됐다.

```text
status = BLOCKED
message = Docker CLI is not available
orders_enabled = false
exit code = 2
```

따라서 Moon에서 단일 Docker Job이 실제 SUCCEEDED했다고 주장하지 않는다.
Windows Docker Desktop host에서 위 명령의 PASS 결과가 필요하다.

## 안전 경계

이 acceptance는:

- count=1
- min_trades=0
- min_annual_trades=0
- max_retries=0
- development data only
- no KIS order
- no live account
- orders_enabled=false

를 유지한다.

다음 Phase 3-7.4에서는 성공한 Job의 Evidence attempt를 같은 run/attempt/job과 연결해
`execution_mode=docker_worker`, `isolated=true`, `timeout_enforced=true`를 검증한다.
