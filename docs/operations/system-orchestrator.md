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
