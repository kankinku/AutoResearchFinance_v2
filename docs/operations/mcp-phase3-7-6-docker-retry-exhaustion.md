# MCP Phase 3-7.6 — Docker retry / exhaustion host acceptance

## 목적

실제 Docker host에서 transient timeout이 설정된 횟수만큼만 재시도되고, 최대 시도 횟수에 도달하면 durable queue가 `RETRY_EXHAUSTED`로 종료되는지 검증한다. deterministic 오류는 재시도 대상이 아님을 같은 retry policy로 고정한다.

## Host 명령

```powershell
uv run --locked python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-retry-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-retry-exhaustion `
  --timeout-seconds 0.5 `
  --max-retries 2
```

`max_retries=2`이면 총 `max_attempts=3`이다. 각 시도는 Phase 3-7.5의 강제 timeout probe를 사용하며 매번 소유 컨테이너가 제거됐는지 확인한다.

## Retry policy

재시도 대상:
- TimeoutError
- ConnectionError
- BrokenPipeError
- WorkerProcessError

재시도하지 않는 deterministic 오류의 대표값은 `ValueError`다. 이 분류는 `runtime.evaluation_executor.is_retryable_error()`로 한 곳에서 사용한다.

## PASS 조건

- queue_status = RETRY_EXHAUSTED
- queue_attempt = max_attempts = max_retries + 1
- error_class = TimeoutError
- cleanup_count = max_attempts
- removed_container_count = max_attempts
- timeout_retryable = true
- worker_process_retryable = true
- deterministic_value_error_retryable = false
- timeout_enforced = true
- orders_enabled = false

## Moon 환경

Moon에는 Docker CLI/Engine이 없으므로 실제 다중 컨테이너 retry/exhaustion은 `ENVIRONMENT_BLOCKED`다. 자동 테스트는 동일 durable queue 전이와 retry policy를 deterministic injection으로 검증한다. 기존 executor 테스트도 Docker timeout 재시도, deterministic worker failure 비재시도, 최종 RETRY_EXHAUSTED를 검증한다.

## 안전 경계

이 probe는 전략 주문, KIS/live account, credential 전달, promotion을 수행하지 않는다. 다음 단계는 Phase 3-7.7 Controller 재시작 복구 검증이다.
