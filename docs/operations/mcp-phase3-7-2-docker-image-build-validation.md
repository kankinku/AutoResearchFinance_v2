# MCP Phase 3-7.2 — Docker worker image build 검증

## 목적

Docker evaluation worker image의 build 경로를 코드와 acceptance script 수준에서 고정하고,
Docker Desktop이 있는 host에서는 실제 `docker build → image inspect`를 한 명령으로 검증할 수 있게 한다.

## Canonical image

기본 image reference:

```text
quant-autoresearch-worker:local
```

Canonical Dockerfile:

```text
runtime/Dockerfile.worker
```

Canonical build context:

```text
repository root .
```

Canonical command:

```text
docker build --tag quant-autoresearch-worker:local --file runtime/Dockerfile.worker .
```

## Static build contract

`scripts/verify_docker_evaluation.py --check-build-context`는 Docker 없이 다음을 검증한다.

- image reference가 비어 있거나 공백을 포함하지 않음
- `runtime/Dockerfile.worker` 존재
- Python 3.11 worker base contract 존재
- `/workspace` workdir 존재
- `runtime.system_worker` entrypoint 존재
- `.dockerignore` 존재
- `.env`, `.env.*`, `.git`, `state`, `.venv`가 build context에서 제외됨

Moon에서 실제 실행 결과:

```text
status = STATIC_READY
image_built = false
image_reference = PASS
worker_dockerfile = PASS
dockerignore = PASS
orders_enabled = false
```

즉 build 입력 계약은 검증됐지만 image 자체가 생성됐다는 뜻은 아니다.

## Build context 정리

기존 `.dockerignore`에 다음을 추가했다.

- `.venv`
- `.moon`
- `*.egg-info`
- `build`
- `dist`

특히 `.venv`가 `COPY . /workspace` context에 들어가면 image context가 불필요하게 커지고
host-specific virtualenv 파일까지 복사될 수 있으므로 반드시 제외한다.

## 실제 build 검증

Docker Desktop host에서는 다음 명령을 사용한다.

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --image quant-autoresearch-worker:local `
  --build-image `
  --check-only
```

내부 순서:

1. static build contract
2. Docker CLI 검색
3. `docker info --format {{.ServerVersion}}`
4. canonical `docker build`
5. `docker image inspect <image>`

전부 성공하면:

```text
status = READY
image_built = true
docker_cli = PASS
docker_engine = PASS
docker_build = PASS
docker_image = PASS
orders_enabled = false
```

## Moon 환경 실제 판정

현재 Moon 환경에는 다음이 모두 없다.

- `docker` executable
- `/var/run/docker.sock`
- Docker Desktop proxy socket
- mount된 Windows `docker.exe`

따라서 실제 build 시도는 다음으로 종료된다.

```text
status = BLOCKED
error_class = RuntimeError
message = Docker CLI is not available
orders_enabled = false
exit code = 2
```

이 결과를 build 성공으로 해석하지 않는다.

## 자동 테스트

자동 테스트는 다음을 검증한다.

- static contract와 canonical build command
- Docker 없이 static contract 검증 가능
- mock Docker host에서 `info → build → image inspect` 순서
- Docker CLI가 없으면 build path가 BLOCKED
- 기존 Docker evaluation runtime isolation/timeout command 계약

## 안전 경계

Image build 검증은 evaluation Job을 실행하지 않는다.

- KIS 주문 없음
- live account 없음
- strategy evaluation 없음
- managed research 시작 없음
- orders_enabled=false

## Phase 3-7.2 판정

코드/build-context/build-command 검증: COMPLETE
Moon에서 실제 Docker image build: ENVIRONMENT_BLOCKED
Windows Docker Desktop host 실제 build: 아직 실행 필요

따라서 다음 Phase 3-7.3의 실제 single Job acceptance 전에 Windows host에서
`--build-image --check-only` 결과가 READY인지 확인해야 한다.
