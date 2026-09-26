# MCP 전체 시스템 기동

## 실행 구조

`start_system`은 Phase 3부터 연구와 평가를 서로 독립적으로 병렬 실행하지 않는다.
사전점검을 통과하면 다음 구조로 실행된다.

```text
MCP start_system
  -> dashboard
  -> research_worker
       -> run_autoresearch()
       -> ResearchIntent
       -> preflight / mutation / candidate planning
       -> QueuedEvaluationExecutor
            -> local_scheduler (기본)
            또는
            -> PersistentJobQueue -> Docker evaluation-job worker
       -> Evidence / Knowledge / Dashboard projection
```

따라서 이전의 상시 `backtest_worker` 컨테이너는 더 이상 시작하지 않는다. Docker 모드에서도
평가 Job이 실제로 발생할 때만 1 Job 단위의 격리 컨테이너가 생성되고, 완료되면 제거된다.

## 최초 준비

Codex Desktop의 신뢰된 MCP 설정에 `.codex/config.toml.example`의 서버 섹션을
등록한다. `cwd`는 저장소 루트로 지정한다.

연구 방향 생성에는 로컬 `codex` CLI가 필요하다.

```powershell
codex login status
```

`state`가 새 디렉터리라면 한 번 초기화한다.

```powershell
python cli.py init --state-dir state
python cli.py set-mode --state-dir state --mode paper
```

## 평가 backend

기본값은 `local_scheduler`다. 이 모드에서는 Docker가 없어도 전체 연구 시스템을 실행할 수 있다.

```powershell
$env:QUANT_EVALUATION_EXECUTION="local_scheduler"
```

Docker 격리 평가가 필요할 때만 다음을 설정한다.

```powershell
$env:QUANT_EVALUATION_EXECUTION="docker_worker"
docker build -t quant-autoresearch-worker:local -f runtime/Dockerfile.worker .
```

MCP의 기존 `docker_image` 인자는 그대로 유지되며 Docker 모드의 Job worker image를 지정한다.
공개 MCP tool schema는 변경하지 않는다.

## 사전점검

`check_system`과 `start_system`은 공통으로 다음을 검사한다.

- Python runtime과 paper-only 상태
- 전략 소스와 Parquet 입력의 프로젝트 루트 제한
- market / series 데이터의 `development` 영역
- Codex CLI와 연구용 `.env`
- 평가 backend 설정
- Dashboard port
- Docker 모드인 경우에만 Docker CLI, Engine, worker image

`local_scheduler`에서는 Docker 검사를 선택 사항으로 표시한다. 따라서 Docker 미설치가
연구 시스템 전체를 차단하지 않는다.

## 시작되는 구성요소

관리 대상은 다음과 같다.

- `dashboard`: 로컬 Dashboard 프로세스
- `research_worker`: Codex-directed `run_autoresearch()` 프로세스
- `evaluation_backend`: 프로세스가 아니라 현재 평가 backend 상태를 나타내는 논리 구성요소

`evaluation_backend` 상태에는 활성 PersistentJob 수가 함께 표시된다. Docker worker는
상시 구성요소가 아니라 이 backend가 필요할 때 생성하는 단기 Job worker다.

## 반복 연구

기존 `repeat_generations`, `interval_seconds`, `method`, `count`, `seed`,
`min_trades`, `min_annual_trades`, `min_qqq_cagr_delta`, `parameter_domains`는
그대로 `research_worker`의 `ResearchLoopConfig`로 전달된다.

즉 `start_system`으로 시작한 세대는 이제 실제로 다음 순서를 따른다.

```text
ResearchIntent
-> typed operation preflight
-> candidate/evaluation plan
-> selected evaluation backend
-> Evidence
-> Knowledge/state update
-> next generation
```

이전처럼 ResearchIntent만 기록하고 별도 backtest worker가 원래 전략을 독립 평가하는 구조가 아니다.

## Docker Job 격리

`docker_worker` 모드에서는 Phase 3-2의 공통 Job 계약을 사용한다.

- SQLite durable queue
- host-side lease
- `runtime.system_worker --role evaluation-job`
- network 없음
- read-only project mount
- state mount만 read-write
- capability drop
- no-new-privileges
- PID / CPU / memory 제한
- process/container timeout
- timeout 시 `docker rm -f`
- lease expiry recovery
- retry exhaustion

Evidence에는 실제 실행 경계에 따라 다음이 기록된다.

```text
local_scheduler:
  isolated=false
  timeout_enforced=false

docker_worker:
  isolated=true
  timeout_enforced=true
```

## 상태 확인

`get_system_status`는 Dashboard와 research worker 상태 외에
`evaluation_backend.active_jobs`를 표시한다.

research worker가 종료되면 `research_worker.json`의 `SUCCEEDED` 또는 `FAILED`
상태가 반영된다.

## 중지

`stop_system`은 먼저 관리 중인 Dashboard/research 프로세스를 종료한다.

Docker evaluation Job이 실행 중이면 PersistentJobQueue에서 RUNNING Job을 조회하고,
해당 Job의 결정론적 container name을 계산하여 다음과 동일한 강제 cleanup을 수행한다.

```text
docker rm -f <evaluation-container>
```

성공적으로 종료된 Job은 queue에서 `CANCELLED / SystemStopped`로 기록된다.
컨테이너 cleanup에 실패하면 성공적으로 중지했다고 표시하지 않고 `STOP_FAILED`와
실패한 Job id를 반환한다.

## 안전 경계

- 실전투자 및 KIS order permission은 이 시스템 기동으로 활성화되지 않는다.
- research 입력은 development 데이터만 허용한다.
- validation / sealed OOS는 별도 promotion 경계를 유지한다.
- 공개 CLI command, MCP tool schema, StrategyIR, Dashboard route는 변경하지 않는다.
- Docker mode가 아니면 Docker가 없어도 연구 시스템을 실행할 수 있다.

## Phase 3-4: 재시작 복구와 lifecycle 소유권

관리 상태는 `state/system/system.json`에 `managed_run_id`, PID, 프로세스
identity marker와 함께 기록된다. 따라서 MCP 서버나 `SystemController` 객체가 재생성돼도
기존 Dashboard/research worker가 실제로 살아 있는지 다시 판별할 수 있다.

PID만으로 소유권을 판단하지 않는다. PID가 운영체제에서 재사용될 수 있기 때문에
프로세스 command line에 다음 marker가 모두 존재하는지 확인한다.

- dashboard: `cli.py dashboard`, state directory, dashboard port
- research worker: `runtime.system_worker --role research`, state directory,
  `--managed-run-id <id>`

marker가 일치하지 않는 프로세스는 현재 시스템의 소유 프로세스로 간주하지 않으며
`stop_system`도 종료하지 않는다.

### 중복 start 방지

`start_system`은 먼저 persisted 상태를 복구한다. 동일한 managed runtime의
Dashboard/research worker 또는 evaluation Job이 살아 있으면 새 시스템을 생성하지 않고
`ALREADY_RUNNING`을 반환한다.

동시에 여러 MCP 요청이 들어오는 경쟁 조건은
`state/system/lifecycle.lock`의 nonblocking OS file lock으로 직렬화한다.
다른 start/stop 변경이 진행 중이면 `BUSY`를 반환한다. 이 lock은 프로세스 종료 시
운영체제가 자동 해제하므로 별도의 영구 stale lock 파일 소유권에 의존하지 않는다.

### Job 소유권과 orphan 복구

managed research가 생성한 evaluation Job에는 `managed_run_id`가 저장된다.
상태 복구 및 중지는 다른 run의 Job을 건드리지 않고 해당 managed run에 속한 Job만 다룬다.

research worker가 사라진 뒤 lease가 만료된 Job은:

1. SQLite queue의 lease를 reconcile하고,
2. 해당 run의 재큐잉 Job을 orphan으로 판정하고,
3. `CANCELLED / OwnerExited`로 기록한다.

다른 managed run의 실행 중 Job은 그대로 유지한다.

### 집계 상태

`get_system_status`는 persisted process 상태와 evaluation queue를 합쳐 다음과 같이
집계한다.

- `RUNNING`: research 또는 evaluation Job이 정상 실행 중
- `COMPLETED`: research가 성공적으로 끝남
- `FAILED`: research worker가 실패함
- `DEGRADED`: 일부 필수 구성요소가 사라졌지만 다른 구성요소가 남음
- `STOPPED`: 관리 런타임이 없음
- `STOP_FAILED`: 소유 프로세스/컨테이너 cleanup 실패

### 실제 Docker host acceptance

Moon 개발 컨테이너처럼 Docker CLI가 노출되지 않는 환경에서는 정적/모의 검증만 가능하다.
Docker Desktop이 있는 실제 host에서는 다음 스크립트로 Engine/image와 실제
evaluation-job 컨테이너 경로를 확인한다.

```powershell
python scripts/verify_docker_evaluation.py `
  --project-root . `
  --image quant-autoresearch-worker:local `
  --check-only
```

실제 전략과 development Parquet가 준비돼 있다면:

```powershell
python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-acceptance `
  --image quant-autoresearch-worker:local `
  --source-path strategies/example.yaml `
  --data-path data/example.parquet
```

이 acceptance는 `docker_worker` backend를 사용해 후보 1개를 실제 Job으로 실행하며
주문 기능은 활성화하지 않는다.

## MCP 프로세스 자체 검증

Docker 검증과 별개로 MCP STDIO 서버 자체는 실제 별도 프로세스에서 확인할 수 있다.

    uv run --locked python scripts/verify_mcp_runtime.py --project-root . --state-dir state/mcp-acceptance

이 검사는 `initialize → tools/list → get_system_status`만 수행하며 연구 실행,
ResearchIntent 제출, KIS 주문은 수행하지 않는다. 정상 출력에는 protocol version,
server name, public tool count, 현재 system status와 `orders_enabled=false`만 포함한다.

Codex trusted MCP 설정도 `.codex/config.toml.example`처럼 `uv run --locked python`
경로를 사용한다. 따라서 MCP 서버와 평가 런타임이 동일한 lockfile 의존성을 사용한다.
