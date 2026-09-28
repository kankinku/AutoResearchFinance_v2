# MCP Phase 3-7 — Docker Host Acceptance 완료 보고서

## 범위

Phase 3-7은 MCP 연구 실행의 `docker_worker` 경로를 실제 Windows Docker Desktop host에서
검증할 수 있도록 acceptance 절차와 자동 검증기를 완성하는 단계다.

완료된 세부 단계:

- 3-7.1 Windows Docker Host 실행 절차
- 3-7.2 worker image build/context 검증
- 3-7.3 단일 Docker evaluation Job
- 3-7.4 immutable Evidence 검증
- 3-7.5 timeout / `docker rm -f` cleanup
- 3-7.6 retry / exhaustion
- 3-7.7 Controller 재시작·복구
- 3-7.8 최종 Host Acceptance runbook

정본 실행 문서는
`docs/operations/mcp-phase3-7-8-final-host-acceptance.md`다.

## 구현 상태

```text
implementation_status = COMPLETE
host_acceptance_status = PENDING_EXTERNAL
Moon = ENVIRONMENT_BLOCKED
orders_enabled=false
```

`implementation_status = COMPLETE`는 acceptance 코드, deterministic regression,
문서 계약이 완료됐다는 뜻이다.

`host_acceptance_status = PENDING_EXTERNAL`은 실제 Windows + Docker Desktop Engine에서
container를 실행한 PASS 증거가 아직 Project Moon 환경에서 생성될 수 없음을 뜻한다.
이를 실제 Docker PASS로 바꾸어 기록하지 않는다.

## 구현된 Host 검증 범위

- canonical worker image build 및 image inspect
- isolated single evaluation Job
- durable queue `SUCCEEDED`
- immutable Evidence의 Docker execution provenance
- 강제 timeout 후 `TIMED_OUT`
- timeout container 강제 제거
- transient retry 후 `RETRY_EXHAUSTED`
- deterministic 오류 비재시도
- Controller 재생성 후 persisted managed runtime 복구
- recovered Controller의 managed-run-scoped process/container cleanup
- 최종 `STOPPED`
- 전 구간 `orders_enabled=false`

## Project Moon 판정

현재 Moon runtime에는 Docker executable/Engine이 노출되지 않는다.
따라서 실제 Docker 단계는 일관되게 다음 형태로 차단된다.

```text
status = BLOCKED
message = Docker CLI is not available
orders_enabled = false
```

이 상태는 `ENVIRONMENT_BLOCKED`이며 코드 실패나 Docker PASS로 해석하지 않는다.

Docker가 없어도 다음은 자동 테스트로 검증한다.

- Docker command/isolation 계약
- build context 계약
- queue 상태 전이
- timeout/retry 정책
- Evidence identity/integrity 연결
- managed-run 소유권
- Controller recreation/recovery
- public safety boundary

## 외부 Host sign-off 조건

Windows Docker Desktop host에서 정본 runbook의 Step 1~7을 순서대로 실행한다.

최종 sign-off에는 최소 다음 증거가 필요하다.

- build: `READY`
- single evaluation: `PASS / SUCCEEDED`
- Evidence: `VERIFIED`
- timeout: `PASS / TIMED_OUT / container_removed=true`
- retry: `PASS / RETRY_EXHAUSTED / removed_container_count=max_attempts`
- Controller restart: `PASS / recovered_status=RUNNING / final_status=STOPPED`
- repository regression: ruff / mypy / pytest PASS
- 모든 결과: `orders_enabled=false`

## 안전 경계

Phase 3-7 acceptance는 다음 권한을 추가하지 않는다.

- KIS order execution
- live account activation
- credential 전달
- sealed OOS promotion
- MCP order/live Tool

Docker worker는 network none, read-only filesystem, dropped capabilities,
no-new-privileges와 resource limits를 유지한다.

## 완료 판정

Phase 3-7의 **개발 및 acceptance harness 구축 범위는 완료**로 판정한다.

다만 실제 Windows Docker Desktop host PASS는 환경 외부 검증이므로
`host_acceptance_status = PENDING_EXTERNAL`을 유지한다.
외부 host에서 정본 runbook을 실행해 모든 조건이 PASS가 된 뒤에만 실제 Host Acceptance 완료
증거로 사용할 수 있다.
