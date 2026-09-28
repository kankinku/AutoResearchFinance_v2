# MCP Phase 3-7.8 — 최종 Windows Docker Host Acceptance

## 목적

이 문서는 Phase 3-7.1부터 3-7.7까지 분산된 Docker Host Acceptance 절차를 실제
Windows + Docker Desktop 환경에서 한 번에 순서대로 실행하기 위한 **정본 runbook**이다.

Phase 3-7 구현 자체와 deterministic/mock regression은 Project Moon 환경에서 검증한다.
하지만 Moon에는 Docker CLI/Engine이 노출되지 않으므로 실제 Docker container 실행 증거는
Windows Docker Desktop host에서 별도로 확보해야 한다.

이 문서의 최종 판정 원칙은 다음과 같다.

```text
implementation_status = COMPLETE
Moon Docker execution = ENVIRONMENT_BLOCKED
Windows host acceptance = PASS required for external host sign-off
orders_enabled=false
```

## 단계별 근거 문서

각 세부 단계의 설계·판정 근거는 다음 문서에 있다.

| 단계 | 목적 | 상세 문서 |
| --- | --- | --- |
| 3-7.1 | Windows Docker Host 실행 절차와 전제 | `mcp-phase3-7-1-docker-host-procedure.md` |
| 3-7.2 | worker image build/context 검증 | `mcp-phase3-7-2-docker-image-build-validation.md` |
| 3-7.3 | 단일 Docker evaluation Job | `mcp-phase3-7-3-single-docker-job.md` |
| 3-7.4 | immutable Evidence와 Job identity 연결 | `mcp-phase3-7-4-docker-evidence-validation.md` |
| 3-7.5 | timeout 및 강제 container cleanup | `mcp-phase3-7-5-docker-timeout-validation.md` |
| 3-7.6 | transient retry / exhaustion | `mcp-phase3-7-6-docker-retry-exhaustion.md` |
| 3-7.7 | Controller 재시작 후 운영 제어권 복구 | `mcp-phase3-7-7-controller-restart-recovery.md` |

이 문서가 실제 실행 순서와 최종 PASS/BLOCKED 판정의 정본이며, 위 문서는 각 단계의
세부 설계 근거로 사용한다.

## 0. Host 전제 확인

저장소 루트에서 PowerShell을 연다.

필수 조건:

- Windows에서 현재 저장소 checkout에 접근 가능
- Docker Desktop이 Linux container engine으로 실행 중
- `uv` 사용 가능
- repository lockfile과 현재 checkout을 임의로 변경하지 않음
- KIS credential이나 live-order 권한이 acceptance에 필요하지 않음

먼저 현재 checkout을 확인한다.

```powershell
git status --short
uv sync --locked --extra dev
uv run --locked --extra dev python -c "import sys; print(sys.version)"
docker version
docker info --format '{{.ServerVersion}}'
```

`git status --short`에 사용자가 의도하지 않은 변경이 있으면 acceptance 결과와 섞지 않는다.
Docker Engine 확인이 실패하면 실제 container acceptance로 진행하지 않는다.

## 1. Docker 없이 build contract 정적 확인

실제 build 전에 Dockerfile과 build context 계약을 확인한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --image quant-autoresearch-worker:local `
  --check-build-context
```

정상 판정:

```text
status = STATIC_READY
image_built = false
image_reference = PASS
worker_dockerfile = PASS
dockerignore = PASS
orders_enabled = false
```

`STATIC_READY`는 Docker image가 실제로 build됐다는 뜻이 아니다. 이 단계는
`runtime/Dockerfile.worker`와 `.dockerignore` 계약만 검증한다.

## 2. 실제 worker image build + inspect

다음 명령은 실제 Docker Engine을 사용한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --image quant-autoresearch-worker:local `
  --build-image `
  --check-only
```

필수 PASS 조건:

```text
status = READY
image_built = true
docker_cli = PASS
docker_engine = PASS
docker_build = PASS
docker_image = PASS
orders_enabled = false
```

이 단계가 READY가 아니면 이후 Docker Job probe를 실행하지 않는다.

## 3. 단일 Docker Job + Evidence 통합 검증

Phase 3-7.3과 3-7.4는 동일 명령 한 번으로 함께 검증한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-acceptance `
  --image quant-autoresearch-worker:local `
  --prepare-fixture
```

`--prepare-fixture`는 체크인된 normalized 전략 하나와 합성 development Parquet를 사용한다.
validation/sealed OOS 데이터로 승격하지 않으며 주문 기능을 사용하지 않는다.

필수 PASS 조건:

```text
status = PASS
evaluation_status = COMPLETED
durable_job_count = 1
queue_status = SUCCEEDED
queue_attempt = 1
evidence_verified = true
evidence.status = VERIFIED
evidence.execution_mode = docker_worker
evidence.isolated = true
evidence.timeout_enforced = true
orders_enabled = false
```

또한 queue의 `job_id` / `managed_run_id`와 Evidence의 worker identity가 동일해야 한다.

## 4. Timeout + 강제 cleanup 검증

실제 timeout을 의도적으로 발생시키고 container cleanup을 확인한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-timeout-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-timeout `
  --timeout-seconds 0.5
```

필수 PASS 조건:

```text
status = PASS
queue_status = TIMED_OUT
queue_attempt = 1
max_attempts = 1
error_class = TimeoutError
container_removed = true
timeout_enforced = true
orders_enabled = false
```

이 단계의 `TIMED_OUT`은 의도된 성공 조건이다. timeout 뒤
`docker rm -f <owned-container>`가 수행되고 container가 남지 않아야 한다.

## 5. Retry / exhaustion 검증

transient timeout이 정책상 허용된 횟수만 재시도되는지 확인한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-retry-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-retry-exhaustion `
  --timeout-seconds 0.5 `
  --max-retries 2
```

필수 PASS 조건:

```text
status = PASS
queue_status = RETRY_EXHAUSTED
queue_attempt = 3
max_attempts = 3
max_retries = 2
error_class = TimeoutError
cleanup_count = 3
removed_container_count = 3
timeout_retryable = true
worker_process_retryable = true
deterministic_value_error_retryable = false
timeout_enforced = true
orders_enabled = false
```

`RETRY_EXHAUSTED` 역시 이 probe에서는 의도된 성공 조건이다. 핵심은 무한 재시도가 아니라
정확히 `max_retries + 1`번 시도 후 종료되는 것이다.

## 6. Controller 재시작·복구 검증

실행 중 Job을 가진 managed runtime을 만든 뒤 Controller 객체를 새로 생성해도 기존
운영 상태를 복구하고 안전하게 중지할 수 있는지 확인한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-controller-restart-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-controller-restart
```

필수 PASS 조건:

```text
status = PASS
probe = controller_restart
recovered_status = RUNNING
active_jobs_after_reconnect = 1
stop_status = STOPPED
queue_status_after_stop = CANCELLED
container_removed = true
processes_stopped = true
final_status = STOPPED
orders_enabled = false
```

복구된 Controller는 persisted `managed_run_id`에 속한 프로세스와 Job만 정리한다.
다른 managed run의 Job을 cleanup 대상으로 취급하면 안 된다.

## 7. 최종 회귀검증

Host probe와 별개로 현재 checkout 전체 검증을 수행한다.

```powershell
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy .
uv run --locked --extra dev python -m pytest -q
```

Phase 3-7.8 작성 시 Project Moon 기준 검증 baseline은 다음과 같다.

```text
ruff = PASS
mypy = PASS
pytest = PASS
orders_enabled=false
```

테스트 개수는 이후 정상적인 테스트 추가로 증가할 수 있으므로 최종 sign-off는 특정 개수보다
exit code 0과 전체 PASS를 기준으로 한다.

## 8. MCP STDIO companion acceptance

Docker Host Acceptance 자체와 별개로 MCP public/legacy contract를 실제 subprocess에서
다시 확인하려면 다음을 실행한다.

```powershell
uv run --locked --extra dev python scripts/verify_mcp_runtime.py `
  --project-root . `
  --state-dir state/mcp-acceptance
```

정상 결과는 MCP public tool 13개, legacy compatibility 5개, public response contract v1,
유효한 system status와 `orders_enabled=false`를 보고해야 한다.

이 단계는 Docker 3-7 acceptance를 대체하지 않는다.

## BLOCKED 판정 해석

다음과 같은 출력은 PASS가 아니다.

```text
status = BLOCKED
error_class = RuntimeError
message = Docker CLI is not available
orders_enabled = false
```

Project Moon에서는 Docker CLI/Engine이 노출되지 않기 때문에 위 결과를
`ENVIRONMENT_BLOCKED`로 기록한다. 이는 deterministic regression 실패를 의미하지 않지만
실제 Windows Host Acceptance를 대신하지도 않는다.

Windows host에서는 다음처럼 분류한다.

- Docker CLI 없음: host prerequisite BLOCKED
- Docker Engine 응답 실패: host prerequisite BLOCKED
- image inspect 실패: build/image prerequisite BLOCKED
- Step 3~6에서 prerequisites는 통과했지만 `status != PASS`: acceptance failure로 조사
- `orders_enabled != false`: 안전 계약 위반으로 즉시 실패
- container/process cleanup 검증 실패: acceptance failure로 조사

## 최종 체크리스트

Phase 3-7 Windows Host sign-off는 아래가 모두 충족돼야 한다.

- [ ] Step 1 `STATIC_READY`
- [ ] Step 2 `READY` + image build/inspect PASS
- [ ] Step 3 single Job `SUCCEEDED` + Evidence `VERIFIED`
- [ ] Step 4 timeout `TIMED_OUT` + container removed
- [ ] Step 5 retry `RETRY_EXHAUSTED` + 모든 attempt container removed
- [ ] Step 6 Controller reconnect `RUNNING` 복구 후 `STOPPED` cleanup
- [ ] Step 7 ruff / mypy / pytest PASS
- [ ] 모든 acceptance payload에서 `orders_enabled=false`
- [ ] KIS 주문, live account 활성화, credential 전달, sealed OOS promotion 없음
- [ ] acceptance가 만든 `quant-eval-*` container가 종료 후 남아 있지 않음

다른 연구 작업이 의도적으로 실행 중이라면 그 작업의 container/process를 acceptance 잔여물로
오인해 종료하지 않는다.

## Phase 3-7.8 판정

Phase 3-7.1~3-7.7에서 구현한 Host Acceptance 경로의 실행 순서, 성공 조건,
환경 차단 조건, 안전 경계를 하나의 runbook으로 통합했다.

Project Moon에서 검증할 수 있는 코드·계약·회귀검증 범위는 완료다.
실제 Windows Docker Desktop 결과는 외부 환경 증거이므로 별도 실행 후 기록해야 한다.

Phase 3-7 개발 범위의 상태:

```text
implementation_status = COMPLETE
host_acceptance_status = PENDING_EXTERNAL
Moon = ENVIRONMENT_BLOCKED
orders_enabled=false
```
