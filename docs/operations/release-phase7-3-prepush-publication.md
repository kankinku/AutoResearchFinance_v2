# Release Phase 7.3 — Pre-push publication gate

## 목적

Phase 7.3은 원격 publication 직전의 마지막 비파괴 gate다.

이번 단계에서는:

- remote fetch
- divergence 확인
- remote default branch 확인
- push refspec dry-run
- lock 검증
- canonical SDK acceptance
- manual rollback acceptance

까지 수행한다.

**실제 push는 하지 않는다.**
**PR을 생성하지 않는다.**
**merge하지 않는다.**

## 현재 Git 상태

현재 로컬 브랜치:

```text
docs/mcp-phase3-5-1-state-inventory
```

이 이름은 현재 작업 범위에 비해 stale하지만 Phase 7.3에서는 rename하지 않았다.

Phase 7.3 gate 시작 시:

```text
HEAD = 4d4a88b
behind origin/master = 0
ahead origin/master = 45
working tree = clean
remote contains HEAD = no
```

원격 기본 브랜치:

```text
origin/master
HEAD = 5875af8
```

## 권장 publication target

PR 가독성을 위해 원격 publication branch는 다음을 권장한다.

```text
feat/autoresearch-runtime-mcp-sdk
```

로컬 브랜치를 rename하지 않고도 다음 refspec으로 publication할 수 있다.

```text
git push origin HEAD:refs/heads/feat/autoresearch-runtime-mcp-sdk
```

실제 push는 아직 수행하지 않았다.

## Push dry-run

먼저 현재 로컬 브랜치명으로 dry-run:

```text
git push --dry-run origin HEAD:refs/heads/docs/mcp-phase3-5-1-state-inventory
```

결과:

```text
PASS
[new branch] HEAD -> docs/mcp-phase3-5-1-state-inventory
```

그다음 권장 publication target으로 dry-run:

```text
git push --dry-run origin HEAD:refs/heads/feat/autoresearch-runtime-mcp-sdk
```

결과:

```text
PASS
[new branch] HEAD -> feat/autoresearch-runtime-mcp-sdk
```

두 dry-run 전후 모두 해당 remote branch는 실제로 존재하지 않았다.

즉:

```text
authentication/write path = dry-run verified
remote mutation = none
```

이다.

## Dependency gate

```text
uv lock --check = PASS
mcp = 2.2.0
pyarrow = 25.0.1
```

## MCP acceptance

Canonical official SDK:

```text
status = PASS
canonical_entrypoint = sdk
sdk_protocol_version = 2025-11-25
legacy_protocol_version = 2024-11-05
public tools = 13
hidden legacy compatibility = 5
public contract = v1
system_status = STOPPED
orders_enabled=false
```

Manual rollback:

```text
status = PASS
transport = manual_rollback
protocol_version = 2024-11-05
public tools = 13
hidden legacy compatibility = 5
public contract = v1
system_status = STOPPED
orders_enabled=false
```

## Security baseline

Phase 7.1에서 확인한 integration diff security baseline:

```text
secret pattern matches = 0
tracked runtime artifacts = 0
added binary files = 0
```

Phase 7.3에서는 이 baseline 이후 코드 변경이 없고 Phase 7.1~7.3은 문서/계약 package만 추가하고 있다.

## Phase 7.3 release gate

```text
ruff = PASS
mypy = PASS (165 source files)
pytest = PASS (794 tests)
fresh secret pattern matches = 0
tracked runtime artifacts = 0
added binary files = 0
```

## Docker Host Acceptance

실제 Windows + Docker Desktop의:

```text
Docker Host Acceptance = PENDING_EXTERNAL
```

상태는 변하지 않았다.

Moon 환경에서 실제 Docker Host PASS를 주장하지 않는다.

이 항목을 publication blocker로 볼지 merge blocker로 볼지는 PR/merge policy에서 명시적으로 판단해야 한다.
현재 merge-auditor package에서는 external pending으로 전달한다.

## 사용자 승인 경계

다음 remote mutation은 각각 사용자 승인 이후에만 수행한다.

```text
push = approval required
PR creation = approval required
merge = approval required
```

Phase 7.3의 "다음"은 이 gate를 수행하라는 승인이지 실제 push 승인으로 해석하지 않는다.

현재 상태는 명확하다. **push하지 않았다. PR을 생성하지 않았다. merge하지 않았다.**

```text
branch rename = NOT_PERFORMED
push = NOT_PERFORMED
PR creation = NOT_PERFORMED
merge = NOT_PERFORMED
```

## 다른 worktree 보호

다음 worktree에는 사용자 소유 미커밋 dependency 변경이 있다.

```text
/shared/moon-workspace/AutoResearchFinance_v2-analysis
M pyproject.toml
M uv.lock
```

publication 과정에서도 이 worktree를 수정/reset/clean하지 않는다.

## 실제 publication 명령

사용자가 별도로 push를 승인하면 권장 명령은:

```text
git fetch --prune origin
git rev-list --left-right --count origin/master...HEAD
git status --short
git push origin HEAD:refs/heads/feat/autoresearch-runtime-mcp-sdk
```

push 직전 필수 조건:

```text
behind origin/master = 0
working tree = clean
release gate = PASS
MCP acceptances = PASS
orders_enabled=false
```

## Phase 7.3 판정

```text
pre-push gate = READY
remote authentication/write path = DRY-RUN PASS
recommended publication branch = feat/autoresearch-runtime-mcp-sdk
remote mutation = NONE
Docker Host Acceptance = PENDING_EXTERNAL
user approval for push = REQUIRED
orders_enabled=false
```

다음 단계는 **Phase 7.4 — remote publication**이다.

Phase 7.4는 실제 remote mutation 단계이므로 자동 진행하지 않는다.
사용자 승인 후에만 push를 수행하고, push 후 remote ref와 commit SHA를 검증한다.
