# Release Phase 7.2 — PR-ready integration package

## 목적

Phase 7.2는 현재 로컬 변경을 원격에 올리기 전에 reviewer와 merge-auditor가
**44개 pre-package commit을 기능 단위로 이해할 수 있도록 정리한 handoff package**다.

이번 단계에서도 push하지 않는다.
PR을 생성하지 않는다.
merge하지 않는다.
commit history를 rewrite하지 않는다.

Phase 7.2 문서 커밋 자체가 추가되면 현재 브랜치의 ahead 수는 45가 되지만,
아래 리뷰 그룹은 이 패키지를 만들기 직전의 44개 변경 커밋을 대상으로 한다.

## PR 제목

권장 PR 제목:

```text
feat: harden autoresearch runtime and migrate MCP to official SDK
```

PR의 핵심 메시지는 단순 MCP transport 교체가 아니다.

```text
research/application boundary
+ finance/data correctness
+ durable evaluation runtime
+ runtime observability
+ safe MCP surface
+ Docker acceptance harness
+ official MCP SDK migration
+ post-cutover stabilization
```

을 하나의 검증된 integration stack으로 통합한 변경이다.

## PR 요약 초안

이 변경은 quant-autoresearch의 기존 기능을 유지하면서 연구 실행 경로와 MCP 운영면을
production-style boundary에 가깝게 재구성한다.

주요 변경:

- application service layer를 도입해 CLI/MCP와 domain/runtime 책임을 분리
- 데이터 zone, timeframe/calendar, annualization 및 evaluation semantics 수정
- evaluation을 durable queue/worker boundary로 이동
- managed runtime lifecycle, restart recovery, runtime snapshot/observability 강화
- 공개 MCP surface를 13개로 정리하고 5개 legacy compatibility dispatch는 숨김 상태로 유지
- Docker worker/image/job/Evidence/timeout/retry/controller-recovery acceptance harness 추가
- 공식 Python MCP SDK 2.2.0으로 canonical transport 전환
- legacy manual transport는 emergency rollback으로 격리
- runtime state/artifact/credential/order 안전 경계를 유지

현재 내부 release gate:

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (790 tests)
canonical SDK subprocess acceptance = PASS
manual rollback subprocess acceptance = PASS
orders_enabled=false
```

실제 Windows + Docker Desktop Host Acceptance는 `PENDING_EXTERNAL`이다.

## 리뷰 그룹

### G1 — Baseline / Application / Finance correctness

커밋:

```text
e0304bf test: freeze MCP transition baseline
061ea14 refactor: add application service layer
8b421c9 fix: correct research evaluation semantics
```

검토 포인트:

- CLI/MCP가 Application Service를 통해 domain 기능을 호출하는지
- 기존 공개 동작이 service layer 도입으로 바뀌지 않았는지
- data-zone capability가 development/validation/sealed OOS를 정확히 구분하는지
- timeframe/calendar metadata와 annualization이 기존 daily US-equity contract를 깨지 않는지
- protected core 변경이 테스트로 커버되는지

### G2 — Durable execution runtime

커밋:

```text
2269cba
7d9d92d
27c380b
ef24713
429bf4f
77a2d62
684a354
a826922
```

검토 포인트:

- evaluation이 local durable scheduler/worker 경계로 이동했는지
- SQLite queue/lease/attempt semantics
- managed_run ownership
- duplicate lifecycle 방지
- interrupted run recovery
- locked runtime acceptance

### G3 — Safe MCP features / runtime observability

커밋:

```text
ad4efda
4168cb7
5aece21
31e3795
6063f40
c7e0ef5
b6d491f
3e6b790
```

검토 포인트:

- 상태 read model이 research/evaluation/evidence/worker/LLM/recovery를 일관되게 표현하는지
- pure read status 호출이 불필요한 state mutation을 만들지 않는지
- error/identity/internal path sanitization이 유지되는지

### G4 — Public MCP surface contracts

커밋:

```text
8e210b8
a28b69b
04bf69c
fe44dfd
76834e2
4423bb5
e49eddb
```

최종 공개 surface:

```text
13 public
5 hidden legacy
public contract = v1
RuntimeSnapshot = v2
orders_enabled=false
```

검토 포인트:

- hidden legacy Tool이 `tools/list`에 노출되지 않는지
- `submit_research_intent`가 deprecated compatibility behavior만 수행하는지
- public response의 `_contract`가 안정적인지

### G5 — Docker Host Acceptance harness

커밋:

```text
39933ba
6745801
5d20995
f6a4779
ea429df
f777bf9
a3ad90b
3ea5f98
```

검토 포인트:

- image/build contract
- single Docker evaluation
- immutable Evidence/Job identity
- timeout + `docker rm -f` cleanup
- bounded retry/exhaustion
- controller restart recovery
- 다른 managed run/container를 정리하지 않는 ownership guard

중요:

```text
Docker Host Acceptance = PENDING_EXTERNAL
```

Moon에서는 실제 Docker Engine이 없어 host sign-off를 주장하지 않는다.

### G6 — Official MCP SDK migration

커밋:

```text
d8ef64b
e9017ec
4573904
5c2a5bb
db4e2f1
```

검토 포인트:

- `mcp>=2.2,<3`, locked `mcp==2.2.0`
- official SDK low-level Server 사용
- public 13 schema parity
- hidden 5 direct compatibility call
- current SDK handshake `2025-11-25`
- 2024-11-05 client compatibility
- canonical entrypoint가 official SDK인지
- manual transport가 rollback으로만 남는지

### G7 — Post-cutover stabilization

커밋:

```text
9c2a27b
c63cff6
9e0b8ed
f782cbe
```

검토 포인트:

- neutral payload codec이 SDK/manual 양쪽에서 wire semantics를 공유하는지
- shared core가 manual JSON-RPC를 소유하지 않는지
- manual adapter가 legacy 2024 envelope만 소유하는지
- 현재 운영 정본이 `mcp-current-state.md`인지
- 역사 문서가 현재 설정으로 오해되지 않는지

### G8 — Pre-integration inventory

커밋:

```text
2cd7fca
```

검토 포인트:

- integration scope
- security scan
- user-owned other worktree boundary
- external blocker
- remote action 미수행 상태

## Protected path review

보호 경로를 바꾼 핵심 커밋은:

```text
8b421c9 fix: correct research evaluation semantics
```

이다.

변경 protected files:

```text
core/backtest/engine.py
core/data/access.py
core/data/contracts.py
core/data/parquet.py
core/data/timebase.py
```

merge-auditor는 이 부분을 별도 고위험 리뷰 대상으로 취급해야 한다.

필수 확인:

- research role은 DEVELOPMENT만 읽음
- VALIDATION은 promotion_validation/promotion_gate만 접근
- SEALED_OOS는 promotion_gate만 접근
- default `1d/us_equities` dataset hash는 과거와 호환
- non-default timeframe/calendar는 hash에 포함
- Parquet metadata round-trip
- multi-symbol backtest에서 timeframe/calendar 보존
- annualization이 calendar/timeframe을 반영

## Dependency review

직접 추가 dependency:

```text
pyarrow>=14.0
mcp>=2.2,<3
```

현재 lock:

```text
pyarrow = 25.0.1
mcp = 2.2.0
uv lock --check = PASS
```

검토 포인트:

- pyarrow는 Parquet fixture/metadata contract에 필요
- mcp는 canonical SDK transport에 필요
- Codex trusted config가 `uv run --locked`를 사용
- dependency addition이 KIS/live/order 권한을 추가하지 않음

## Security / artifact review

검사 결과:

```text
private key-like matches = 0
GitHub PAT-like matches = 0
AWS access key-like matches = 0
OpenAI key-like matches = 0
Bearer token-like matches = 0
tracked state/runs/results/.moon artifacts = 0
added binary files = 0
orders_enabled=false
```

다른 worktree:

```text
/shared/moon-workspace/AutoResearchFinance_v2-analysis
```

에는 사용자 소유 미커밋:

```text
pyproject.toml
uv.lock
```

이 남아 있다.

이 worktree를 reset/clean/checkout하지 않는다.

## merge-auditor handoff

merge-auditor는 다음 순서로 판단한다.

1. `origin/master...HEAD`가 0 behind인지 확인
2. full release gate 확인
3. G1 protected-path finance/data correctness 검토
4. G2 durable runtime ownership/recovery 검토
5. G4 public/hidden Tool contract 검토
6. G5 Docker harness가 실제 Docker PASS를 과장하지 않는지 확인
7. G6 SDK canonical + rollback path 검토
8. secret/runtime artifact scan 확인
9. user-owned 별도 worktree에 영향이 없는지 확인
10. 실제 Windows Docker Host Acceptance 상태를 확인
11. merge 가능 여부를 독립적으로 판정

현재 package의 merge 상태는:

```text
internal release gate = PASS
merge readiness = CONDITIONAL_EXTERNAL_PENDING
Docker Host Acceptance = PENDING_EXTERNAL
```

이다.

## Rollback

### 전체 integration rollback

원격 merge 후 중대한 회귀가 확인되면 history를 강제로 rewrite하지 않고
해당 integration PR/merge commit을 revert하는 것을 기본 rollback으로 한다.

### MCP transport만 문제인 경우

공식 SDK transport 문제를 domain/runtime regression과 분리하기 위해 trusted MCP module을
임시로:

```text
integrations.codex_mcp_server
  -> integrations.codex_mcp_manual_server
```

로 전환할 수 있다.

이것은 rollback diagnostic path이며 manual transport를 다시 canonical 설계로 되돌리는 의미가 아니다.

### 금지

`AutoResearchFinance_v2-analysis` worktree는 사용자 소유 미커밋 dependency 변경이 있으므로
rollback이나 cleanup 대상으로 사용하지 않는다.

## push 직전 체크리스트

원격 publication 승인이 내려진 뒤 push 직전에 다음을 다시 확인한다.

```text
git fetch --prune origin
git status --short
git rev-list --left-right --count origin/master...HEAD
uv lock --check
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy .
uv run --locked --extra dev python -m pytest -q
uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py --project-root . --state-dir state/mcp-sdk-prepush
uv run --locked --extra dev python scripts/verify_mcp_runtime.py --project-root . --state-dir state/mcp-manual-prepush
```

필수 조건:

```text
behind origin/master = 0
working tree = clean
all validation = PASS
orders_enabled=false
```

Docker Host Acceptance가 merge gate라면 Windows 결과도 함께 첨부해야 한다.

## Phase 7.2 판정

```text
PR-ready package = PREPARED
44 pre-package commits = GROUPED ONCE
protected-path review = EXPLICIT
dependency review = EXPLICIT
merge-auditor handoff = PREPARED
rollback = DOCUMENTED
remote publication = NOT PERFORMED
Docker Host Acceptance = PENDING_EXTERNAL
```

다음 단계는 **Phase 7.3 — pre-push publication gate**다.

Phase 7.3도 자동 push하지 않는다.
먼저 remote divergence와 release gate를 재검증하고, 실제 push가 필요한 시점에 사용자 명시 승인을 받는
경계로 사용한다.
