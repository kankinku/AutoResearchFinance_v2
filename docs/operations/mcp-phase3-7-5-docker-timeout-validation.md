# MCP Phase 3-7.5 — Docker timeout host acceptance

## 목적

실제 Docker host에서 timeout을 결정론적으로 강제하고, 소유 컨테이너가 `docker rm -f`로 제거된 뒤 durable queue가 `TIMED_OUT / TimeoutError`로 남는지 검증한다.

## Host 명령

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-timeout-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-timeout `
  --timeout-seconds 0.5
```

## Probe 방식

빠른 backtest에 의존하지 않는다. 동일 worker image를 사용하되 acceptance probe에서만 entrypoint를 Python sleep으로 바꿔 timeout을 강제로 만든다. 컨테이너는 network none, read-only filesystem, capability drop, no-new-privileges, CPU/memory/PID 제한과 tmpfs를 유지한다.

Host는 durable probe Job을 enqueue/claim한 뒤 timeout이 발생하면 `docker rm -f <owned-container>`를 실행하고 queue를 `TIMED_OUT`으로 전환한다. 이어 `docker container inspect`가 실패하는지 확인해 컨테이너가 남아 있지 않은지 검증한다.

## PASS 조건

- queue_status = TIMED_OUT
- queue_attempt = 1
- max_attempts = 1
- error_class = TimeoutError
- container_removed = true
- timeout_enforced = true
- orders_enabled = false

## Moon 환경

Moon에는 Docker CLI/Engine이 노출되지 않으므로 실제 timeout container 실행은 `ENVIRONMENT_BLOCKED`다. 자동 테스트는 동일 command, queue transition, cleanup verifier를 deterministic injection으로 검증한다. 실제 Windows Docker Desktop host PASS는 별도로 필요하다.

## 안전 경계

이 probe는 전략 평가, KIS 주문, live account, credential 전달, promotion을 수행하지 않는다.
