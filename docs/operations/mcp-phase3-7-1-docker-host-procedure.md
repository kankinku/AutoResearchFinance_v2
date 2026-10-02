# MCP Phase 3-7.1 — Windows Docker Host 실행 절차

## 목적

실제 Docker Desktop이 설치된 Windows host에서 `docker_worker` acceptance를 실행하기 위한
절차를 현재 코드 계약과 일치하도록 고정한다.

이 단계에서는 evaluation Job을 실행하지 않는다. Docker 이미지 build와 단일 Job 실행은
후속 단계에서 검증한다.

## 전제

- 저장소 루트에서 PowerShell 실행
- Docker Desktop 설치 및 Linux container engine 실행
- `uv` 사용 가능
- 연구 state는 paper mode
- 실제 acceptance에 사용할 전략과 Parquet는 project root 아래에 위치
- KIS 주문 credential은 Docker image에 포함하지 않음

Docker runtime path는 Linux container를 전제로 한다.
`runtime/Dockerfile.worker`는 `python:3.11-slim` 기반이다.

## 1. 저장소와 Python lock 확인

```powershell
git status --short
uv sync --locked --extra dev
uv run --locked python -c "import sys; print(sys.version)"
```

Host-side acceptance script는 repository lockfile 환경에서 실행한다.

## 2. Docker Desktop 확인

```powershell
docker version
docker info --format '{{.ServerVersion}}'
```

둘 중 하나라도 실패하면 다음 단계로 진행하지 않는다.
Docker Desktop GUI가 실행 중이어도 Engine이 아직 준비되지 않은 경우 `docker info`가 실패할 수 있다.

## 3. 평가 backend 선택

현재 우선순위:

```text
process environment
> .env QUANT_EVALUATION_EXECUTION
> local_scheduler default
```

Host acceptance에서는 현재 PowerShell process에 명시한다.

```powershell
$env:QUANT_EVALUATION_EXECUTION="docker_worker"
```

이 환경변수는 평가 backend만 선택하며 주문 권한이나 live account 권한을 활성화하지 않는다.

## 4. Worker image 이름

기본 image reference는 `quant-autoresearch-worker:local`이다.
MCP `check_system` / `start_system`의 `docker_image` 인자와 `QueuedEvaluationExecutor`의 기본값도 같은 이름을 사용한다.
다른 tag를 사용할 경우 build, check-only, MCP config에서 같은 값을 사용해야 한다.

## 5. Build command

Phase 3-7.2에서 검증할 canonical command:

```powershell
docker build `
  --tag quant-autoresearch-worker:local `
  --file runtime/Dockerfile.worker `
  .
```

Build context는 repository root `.`이다.
`.dockerignore`는 `.env`, Git metadata, state/runs/results/logs/cache/raw source와 Python/test cache를 제외한다.
따라서 host credential/state를 worker image에 복사하는 방식으로 build하지 않는다.

## 6. Image 존재 확인

Build 후:

```powershell
docker image inspect quant-autoresearch-worker:local
```

또는 repository acceptance:

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --image quant-autoresearch-worker:local `
  --check-only
```

READY 조건은 Docker CLI, Docker Engine, 지정 image inspect 성공이며 `orders_enabled=false`를 유지한다.

## 7. 실제 evaluation 전에 준비할 입력

Phase 3-7.3에서 사용할 전략과 development Parquet는 project root 아래에 둔다.
예: `strategies/normalized/<strategy>.json`, `data/<development-bars>.parquet`.
Series data가 필요하면 역시 project root 아래 development data를 사용한다.

## 8. Runtime mount 계약

```text
project root -> /workspace        read-only
state dir    -> /workspace/state read-write
/tmp         -> tmpfs
network      -> none
filesystem   -> read-only
capabilities -> ALL dropped
no-new-privileges -> true
pids         -> 256
memory       -> 2g
cpus         -> 1.0
```

Container는 `python -m runtime.system_worker --role evaluation-job` 경로로 실행되고,
평가 결과와 queue 상태만 state mount를 통해 host로 돌아온다.

## 9. Timeout cleanup

Host timeout을 초과하면 `docker rm -f <quant-eval-...>`로 컨테이너를 제거하고
queue 상태를 TIMED_OUT/retry policy로 전환한다. 실제 timeout은 Phase 3-7.5에서 검증한다.

## 10. 안전 경계

Docker Host Acceptance는 KIS 주문, live account 활성화, sealed OOS promotion,
credential 전달을 수행하지 않는다. Worker runtime network도 비활성화된다.
`orders_enabled=false`는 acceptance 결과에 유지한다.

## Moon 환경 한계

현재 Moon 실행 환경에는 Docker executable이 노출되지 않는다.
따라서 Moon 내부에서 실제 Docker Desktop Engine이나 Windows host image를 build했다고 판정하지 않는다.

Phase 3-7.2는 이 한계를 명시적으로 유지하면서 build command/Dockerfile/preflight 계약을 자동 테스트하고,
Docker가 노출된 host에서는 같은 명령으로 실제 build를 수행한다.
