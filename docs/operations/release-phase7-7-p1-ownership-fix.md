# Release Phase 7.7 — P1 ownership fix

## 배경

merge-auditor review run `20260929T044210Z-7acdadb6-ff01`에서 P1 ownership bug가 발견됐다.

문제:

```text
SystemController.stop()
  -> managed_run_id=None
  -> _terminate_docker_jobs(None)
  -> queue.running()
  -> 모든 RUNNING job 선택
```

이 때문에 system state에 `managed_run_id`가 없을 때 다른 managed run 소유의 Docker evaluation job까지
`docker rm -f` 후 `CANCELLED` 처리할 수 있었다.

## 수정

`runtime/system_controller.py`의 no-owner cleanup semantics를 변경했다.

현재 규칙:

```text
managed_run_id != None
  -> 해당 managed_run_id의 RUNNING job만 정리

managed_run_id == None
  -> payload에 managed_run_id 키가 없는 legacy-unowned RUNNING job만 정리
  -> managed_run_id 키가 있는 job은 건드리지 않음
```

즉 `None`을 "전체 job"으로 해석하지 않는다.

## Legacy compatibility

기존 legacy cleanup은 유지한다.

예전 queue job은 payload에 `managed_run_id` 자체가 없으므로 no-owner stop 시 계속 정리된다.

반면:

```json
{"managed_run_id": "other-run"}
```

처럼 ownership이 명시된 job은 현재 controller의 managed run이 없을 경우 절대 cleanup 대상으로 선택하지 않는다.

## Test-first regression

추가 테스트:

```text
test_stop_without_managed_run_cleans_only_legacy_unowned_docker_jobs
```

RED 결과:

- legacy-unowned container 제거
- foreign-owned container도 잘못 제거
- foreign-owned job이 CANCELLED

수정 후 GREEN:

- legacy-unowned container만 제거
- legacy-unowned job = CANCELLED
- foreign-owned container 제거 안 함
- foreign-owned job = RUNNING

직접 재현 결과:

```text
stop_status=STOPPED
commands=[docker rm -f quant-eval-legacy-unowned-1]
legacy_status=CANCELLED
foreign_status=RUNNING
```

## Runtime ownership regression

다음 runtime 묶음을 확인했다.

```text
tests/runtime/test_system_controller.py
tests/runtime/test_persistent_queue.py
tests/runtime/test_docker_evaluation.py
tests/runtime/test_process_lifecycle.py
tests/runtime/test_runtime_snapshot.py
```

결과:

```text
64 passed
```

## Repository release gate

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (795 tests)
```

## 안전 경계

변경하지 않은 항목:

- queue schema
- managed_run_id 생성 방식
- Docker container naming
- retry/lease semantics
- MCP Tool surface
- public contract
- manual rollback
- finance/data semantics
- KIS/live/order boundary

```text
orders_enabled=false
```

를 유지한다.

## Review 상태

기존 review run은 `7acdadb`에 고정돼 있으므로 이 수정 커밋이 생성되면 stale해진다.

P1은 코드상 수정되었지만, merge-auditor의 unresolved P1을 임의로 닫지 않는다.

다음 단계에서:

1. 수정 커밋을 원격 PR branch에 push
2. 새 head SHA 확인
3. 새 pinned review run 생성
4. P1 재검토
5. full QA 및 external Docker gate 상태 재확인

을 수행한다.

Phase 7.7 자체에서는 원격 push나 merge를 수행하지 않는다.
