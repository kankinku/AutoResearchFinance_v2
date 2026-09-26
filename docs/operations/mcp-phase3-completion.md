# MCP 전환 Phase 3 완료 보고서

## 완료 범위

Phase 3는 ResearchIntent 이후의 평가 실행을 실제 queue/worker 경계로 옮기고, MCP가 그 실행을 장시간 안전하게 관리·관측·복구할 수 있도록 만드는 단계다.

최종 실행 경로:

    MCP start_system
      -> managed research_worker
      -> run_autoresearch
      -> ResearchIntent / preflight / mutation
      -> QueuedEvaluationExecutor
           -> local_scheduler
           또는
           -> SQLite PersistentJobQueue
              -> isolated per-job Docker worker
      -> run_local_evaluation
      -> immutable Evidence / Knowledge
      -> sanitized get_system_status runtime snapshot

## 구현 결과

| 항목 | 결과 |
| --- | --- |
| 공통 evaluation executor | 완료 |
| typed cross-process job/result contract | 완료 |
| SQLite durable queue / lease | 완료 |
| local deterministic fallback | 완료 |
| Docker per-job worker / isolation | 완료 |
| timeout / forced cleanup / retry exhaustion | 완료 |
| heartbeat / attempt metadata | 완료 |
| SystemController canonical orchestration | 완료 |
| managed process ownership / restart recovery | 완료 |
| duplicate start / concurrent lifecycle guard | 완료 |
| managed-run scoped orphan recovery | 완료 |
| explicit INTERRUPTED + fresh-run restart | 완료 |
| integrated runtime snapshot | 완료 |
| real MCP STDIO subprocess acceptance | 완료 |
| locked runtime dependency reproducibility | 완료 |
| host Docker acceptance command | 완료 |

## 공개 계약 보존

Phase 2 기준으로 CLI, KIS 모듈, StrategyIR schema, Dashboard route에는 Phase 3 변경이 없다.
`integrations/codex_mcp_server.py`의 유일한 공개 diff는 start_system 설명을 실제 canonical orchestration에 맞게 수정한 것이며 tool name과 inputSchema는 변경하지 않았다.

Phase 0 public contract 및 MCP/security regression은 최종 점검에서 통과했다.

## 실제 acceptance

MCP STDIO subprocess acceptance:

    status=PASS
    protocol_version=2024-11-05
    server_name=quant-autoresearch
    tool_count=10
    system_status=STOPPED
    orders_enabled=false

Docker host acceptance in the Moon development container:

    status=BLOCKED
    reason=Docker CLI is not available
    orders_enabled=false

이는 Docker 실행 코드 실패가 아니라 현재 Moon 개발 컨테이너의 환경 제약이다. Docker 명령 구성, network/read-only/capability isolation, process timeout, docker rm -f cleanup, durable queue/lease/retry 동작은 자동 테스트로 검증돼 있다. 실제 Docker Desktop host에서는 `scripts/verify_docker_evaluation.py`로 acceptance를 수행한다.

## 재현 가능한 검증

    uv run --locked --extra dev ruff check .
    uv run --locked --extra dev mypy .
    uv run --locked --extra dev python -m pytest -q

Phase 3 이후 검증은 별도 pyarrow 주입 없이 `pyproject.toml`과 `uv.lock`만으로 필요한 runtime dependency를 재현한다.

## 안전 경계

- research와 acceptance 경로는 order permission을 활성화하지 않는다.
- KIS paper/live 분리 및 기존 live gate는 유지한다.
- Docker isolation이 실제 Docker worker에서 수행된 경우에만 isolated=true / timeout_enforced=true를 기록한다.
- local_scheduler는 isolated=false / timeout_enforced=false로 기록한다.
- raw ResearchIntent, credential/provider 정보, exception 본문은 통합 runtime snapshot에 노출하지 않는다.
- interrupted immutable Evidence run은 다시 열지 않고 새 run으로 재시작한다.

## 남은 외부 환경 확인

Phase 3 코드 범위에서 미완료 구현은 없다. 실제 Docker Engine acceptance만 Docker Desktop이 있는 host에서 실행해야 한다.
