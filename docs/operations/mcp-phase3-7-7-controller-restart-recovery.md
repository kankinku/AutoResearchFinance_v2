# MCP Phase 3-7.7 — Controller 재시작·복구 Host Acceptance

## 목적

Phase 3-7.7은 실제 Docker evaluation Job이 실행 중인 상태에서 MCP 서버나
`SystemController` 객체가 재생성돼도 persisted managed state와 durable queue를 다시 읽어
운영 제어권을 복구할 수 있는지 검증한다.

합격 기준은 다음 세 가지다.

1. 재생성된 Controller의 `status()`가 기존 `managed_run_id`, 관리 프로세스,
   실행 중 Docker Job을 `RUNNING` 상태로 복원해 보고한다.
2. 복구 직후 `stop()`을 호출할 수 있고, 현재 managed run 소유 프로세스와
   해당 Docker container를 종료한다.
3. queue Job은 `CANCELLED`로 닫히고 최종 system status는 `STOPPED`,
   `orders_enabled=false`를 유지한다.

## Host acceptance 명령

Windows + Docker Desktop host에서 worker image가 준비된 뒤 다음 명령을 실행한다.

```powershell
uv run --locked --extra dev python scripts/verify_docker_evaluation.py `
  --project-root . `
  --state-dir state/docker-controller-restart-acceptance `
  --image quant-autoresearch-worker:local `
  --verify-controller-restart
```

이 probe는 실제 전략 평가나 KIS 주문을 실행하지 않는다. 격리 옵션을 적용한
단기 Docker container와 두 개의 임시 managed process를 생성해 persisted 상태를 만든 뒤,
새 `SystemController` 인스턴스로 재접속한다.

## 검증 흐름

1. unique `managed_run_id`와 durable queue Job을 만든다.
2. Job을 `RUNNING`으로 claim하고 결정론적 Docker container name을 계산한다.
3. Dashboard/research worker 역할의 임시 managed process를 실행하고 PID/identity marker를
   `state/system/system.json`에 저장한다.
4. hardened Docker probe container를 실행한다.
5. 첫 Controller 객체와 무관한 새 Controller를 생성한다.
6. `status()`에서 다음을 확인한다.
   - system = `RUNNING`
   - 동일 `managed_run_id`
   - evaluation backend `active_jobs=1`
   - RuntimeSnapshot의 active Job에 동일 `job_id`
   - `orders_enabled=false`
7. 새 Controller의 `stop()`을 호출한다.
8. 다음을 확인한다.
   - managed process 종료
   - `docker rm -f <deterministic-container-name>` cleanup
   - durable queue Job = `CANCELLED`
   - Docker container 미존재
   - 최종 system = `STOPPED`
   - `orders_enabled=false`

## 자동 회귀 테스트

Docker가 없는 환경에서도 Controller 재생성 계약을 고정한다.

`tests/runtime/test_system_controller.py`는 별도 Controller 인스턴스가 persisted 상태와
managed-run-scoped Job을 복구한 뒤, `stop()`이 현재 run의 Job만 정리하고 다른 run Job을
건드리지 않는지 검증한다.

`tests/scripts/test_docker_evaluation_acceptance.py`는
`--verify-controller-restart` CLI routing과 Docker 미설치 시 `BLOCKED` 동작을 검증한다.

## Moon 환경 실제 판정

현재 Project Moon 개발 환경에는 Docker CLI/Engine이 노출되지 않는다.

실제 실행 결과:

```text
status = BLOCKED
message = Docker CLI is not available
orders_enabled = false
```

따라서 Moon 내부에서 실제 Docker container 재접속/정리를 PASS했다고 주장하지 않는다.
코드 경로와 deterministic Controller recovery는 자동 테스트로 검증됐으며,
실제 Windows Docker Desktop host에서는 위 명령의 `PASS` 결과가 필요하다.

## 안전 경계

- KIS credential을 사용하지 않는다.
- paper/live order permission을 활성화하지 않는다.
- sealed OOS promotion을 수행하지 않는다.
- `orders_enabled=false`를 시작·복구·중지 후 모두 유지한다.
- Controller cleanup은 persisted `managed_run_id` 소유 범위로 제한한다.

## Phase 3-7.7 판정

Controller restart/recovery acceptance 경로 구현 및 deterministic regression 검증은 완료다.

실제 Docker Desktop host acceptance는 환경 의존 검증으로 남아 있다.

다음 단계는 **Phase 3-7.8 — 최종 Host Acceptance 문서화**다.
사용자 실행 명령, 실행 순서, PASS/BLOCKED 정상 출력과 최종 체크리스트를 하나의
정본 문서로 확정한다.
