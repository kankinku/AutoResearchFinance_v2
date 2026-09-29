# Release Phase 7.1 — Pre-integration release inventory

## 목적

Phase 7.1은 Phase 6까지 완료된 로컬 변경을 원격 통합하기 전에 전체 범위를 다시 확인하는
**비파괴 release inventory**다.

이번 단계에서는 push하지 않는다.
merge하지 않는다.
브랜치도 rename하지 않는다.

현재 변경은 `origin/master` 기준:

```text
43 commits ahead
0 commits behind
0 merge commits
152 files changed
25700 insertions
935 deletions
```

이다.

## Git 상태

현재 브랜치:

```text
docs/mcp-phase3-5-1-state-inventory
```

이 이름은 실제 변경 범위보다 오래된 Phase명을 반영하고 있어 stale하다.

하지만 branch rename은 remote publication과 review context에 영향을 줄 수 있으므로 Phase 7.1에서는
수행하지 않았다.

현재 `origin/master`는 HEAD보다 앞서 있지 않다.

```text
behind = 0
ahead = 43
merge commits = 0
remote branch containing HEAD = none
```

따라서 현재 시점에는 rebase conflict 해결이 필요하지 않으며 commit stack은 선형이다.

## 변경 규모

전체 변경:

```text
files = 152
insertions = 25700
deletions = 935
commits = 43
```

이 정도 규모는 기능적으로 문제가 있다는 뜻은 아니지만 review surface가 크다.

따라서 Phase 7.2에서 PR-ready 설명과 merge-auditor 검토 단위를 명확히 만들어야 한다.

## Protected path 변경

보호 경로:

- core/data
- core/backtest
- core/evaluator
- core/validation
- core/costs
- core/integrity

중 실제 변경 파일은 5개다.

```text
core/backtest/engine.py
core/data/access.py
core/data/contracts.py
core/data/parquet.py
core/data/timebase.py
```

이 변경은 commit:

```text
8b421c9 fix: correct research evaluation semantics
```

에 집중돼 있다.

보호 경로 변경이 여러 Phase에 흩어지지 않고 하나의 finance correctness commit에 집중돼 있다는 점은
통합 검토 시 유리하다.

## Dependency 변경

직접 dependency 추가:

```text
pyarrow>=14.0
mcp>=2.2,<3
```

현재 lock/import smoke:

```text
uv lock --check = PASS
pyarrow = 25.0.1
mcp = 2.2.0
package imports = PASS
```

`uv.lock`은 신규 dependency와 transitive dependency 때문에 큰 diff를 가진다.

## 민감정보·runtime artifact 검사

추가된 diff line을 대상으로 다음 key/token 형태를 검사했다.

- private key
- GitHub PAT
- AWS access key
- OpenAI key-like token
- Bearer token

결과:

```text
secret pattern matches = 0
tracked state/runs/results/.moon artifacts = 0
added binary files = 0
```

cache와 `.moon/` 등의 로컬 산출물은 ignored 상태다.

## 다른 worktree 경계

다른 기존 worktree:

```text
/shared/moon-workspace/AutoResearchFinance_v2-analysis
branch = feat/mcp-phase3-execution-pipeline
```

에는 사용자 소유 미커밋 변경이 남아 있다.

```text
M pyproject.toml
M uv.lock
```

이 worktree는 현재 통합 작업에서 수정·reset·checkout·clean하지 않는다.

현재 source-of-truth worktree는 계속:

```text
/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory
```

다.

## 내부 검증 기준

Phase 6 최종 baseline:

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (782 tests)
canonical SDK acceptance = PASS
manual rollback acceptance = PASS
```

Phase 7.1은 release inventory 단계이므로 이 baseline을 integration prerequisite로 사용한다.

## Phase 7.1 release gate

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (786 tests)
```

## 외부 pending

실제 Windows + Docker Desktop Host Acceptance:

```text
PENDING_EXTERNAL
```

이다.

Moon 환경에서는 Docker CLI/Engine이 없어 실제 container host sign-off를 대신할 수 없다.

또한:

```text
git push = NOT PERFORMED
PR creation = NOT PERFORMED
merge = NOT PERFORMED
```

이다.

push와 merge는 사용자 승인 없이 수행하지 않는다.

## Integration assessment

현재 내부 코드 상태:

```text
internal release readiness = PASS
origin/master divergence = none
commit stack = linear
secret/runtime artifact scan = PASS
dependency lock = PASS
external Docker host sign-off = PENDING_EXTERNAL
remote publication = NOT PERFORMED
```

다만 43 commits / 152 files는 단일 review surface로는 크다.

따라서 다음 단계에서 commit을 다시 작성하거나 squash하는 것이 아니라, 이미 존재하는 atomic commit
구조를 활용해 reviewer와 merge-auditor가 이해할 수 있는 **PR-ready phase map**을 만든다.

## 다음 단계

다음은 **Phase 7.2 — PR-ready integration package**다.

Phase 7.2에서 다음을 준비한다.

- 43 commit을 논리적 Phase group으로 매핑
- PR summary
- 주요 architecture 변화
- protected-path review checklist
- dependency review checklist
- canonical SDK / rollback / Docker external pending 설명
- merge-auditor 검토 항목
- rollback 기준
- push 전 최종 command checklist

Phase 7.2도 push하지 않는다.
merge하지 않는다.

원격 publication은 그 이후 사용자의 명시적 승인 단계에서만 수행한다.
