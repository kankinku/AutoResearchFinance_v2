# T4 / T3 historic G33 fixtures and self-contained model tests

Date: 2026-10-18 KST. Branch `fix/t4-immutable-g33-fixtures-20261018`, based on consolidated P2/P3 and T4 shadow G180 branch. Scope: Q02/Q06/Q07/Q08/Q09/Q14/Q17/Q20. This is a **test-only** T3 release blocker fix, not a live GPT research iteration, OOS examination, code release, real-money order, OAuth/URL change, or modification of the 20-question roadmap.

## Background: original full-suite regression

Before this fix, 1,719 tests passed and 7 failed. Five P0-3B tests were coupled to the live second session's formerly 33 completed generations; that session now holds 79 completed (179/300 overall). Those assertions expected generation 34/35, and some descendant strategies were now rejected by the **correct** real duplicate-signal gate. One crossover input test pointed at live ignored vendor QQQ Parquet files unavailable inside feature worktrees. The remaining STDIO MCP launcher integration failed because an isolated worktree lacks the ignored `.venv` path; rerunning with a local non-Git virtualenv link had already passed.

## What changed

- New test-only `tests/research/historical_g33_fixture.py` reconstructs the **actual historical session local G33** in a newly created temporary directory via SQLite backup handles opened **read only** from the prior SHA-audited frozen snapshot `state/moon-http/research/audits/phase1-20261017-1950/`. The generator requires exact original evidence hashes for G29 and G33, and preserves their complete unmodified original generation rows and the pinned selection for G34. **Only the destination copies** delete later generations, later S7 reports, later timing records and future parent selections. It separately clears stale transient plan/diagnosis/recovery receipts and resets only the copied session to a G33 `AWAITING_PLAN` test checkpoint. The original live SQLite and archived snapshot are never written to or truncated. The real S6-v2 catalog is copied from the audit snapshot.
- `tests/research/test_p0_3b_inherited_audit.py`, `tests/research/test_p0_3b_reinherit.py`: historical G34/G35 inherit/selection assertions now use that versioned temporary G33 environment, not ever-changing operating gateway/session rows. The original behavior, threshold assertions, costs, hash-chain checks, refusal on forged S7 and duplicate signal enforcement are not relaxed.
- `tests/application/test_adaptive_crossover.py`: creates a small ephemeral DEVELOPMENT Parquet fixture from the existing test market while copying only the Git-tracked normalized StrategyIR parents into a temporary project. No live ignored vendor dataset prerequisite; malformed partners must still fail closed.
- `tests/research/test_immutable_g33_snapshot_fixture.py`: verifies the original G33 evidence hash, clone's 33-row count, original 79-row snapshot count, exactly one pinned next-generation selection, isolated 33 S7 reports and removed stale submission receipts. If the original frozen checkpoint hash differs, fail closed rather than fabricate the prior generation.
- Test worktree `.venv` symlink to an existing authenticated development venv is **ignored/untracked**, purely local to run the existing stdio launcher integration. Does not change any official runner or user path.

## Verified checks / boundaries

- Previous direct failure group + adjacent functional regression: **15 PASSED**.
- New code whole repo Ruff: **PASSED**; whole repo Mypy: **PASSED, 274 source files**.
- Guarded release preflight `RELEASE_PRECHECK_PASSED_NOT_DEPLOYED`, `protected_modules_unchanged=true`, `runtime_untouched=true`, still requiring full-suite pass and separate HTTP/OAuth smoke and controlled rollback before any deploy.
- Full T3 Pytest: **1,729 PASSED / 0 FAILED** in 613.59 seconds, process exit code 0, 2026-10-18 KST. This includes the previously failing seven paths and the added G33 pinned-snapshot integrity test. Entire suite re-ran from one invocation, not a count assembled from targeted suites.
- Historical issue resolution: legacy G33 dependent cases now pass without lowering the effective-signal duplicate protection; independent copied input strategy+Parquet resolves the missing vendor file; worktree-only ignored `.venv` link resolves MCP STDIO startup, which was included in the green full-suite run.

## Remaining gates

The full T3 **test** gate is satisfied, but isolated HTTP/OAuth startup smoke and rollback/cutover have **not** been performed. A green full T3 test suite does NOT by itself deploy to existing `/quant` ChatGPT MCP. T4 must still verify isolated HTTP/OAuth startup, stable 32-tool registration, original credential/URL and rollback path, then authorized code pin/cutover and actual GPT-authored plan/diagnosis/S7 in the running session. The history remains 179/300, real trading disabled, and independently valid PIT/OOS evidence unavailable until the later V01–V04 stages.
