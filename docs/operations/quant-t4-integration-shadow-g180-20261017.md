# Quant T4 integration gate: actual frozen-G179 to SHADOW-G180

Date: 2026-10-17 KST. Q02 Q06 Q07 Q08 Q09 Q14 Q15 Q17 Q20; approved T4 mechanism testing, not another goal or a changed stage order. The 20-question scope lock remains V05 → T4 → V01–V04 → V06 → V07. No broker permissions, token/URL/OAuth changes, no production cutover.

## Connected integration evidence (not synthetic 2-bar demonstration)

Uses the immutable Phase 1 frozen backed-up SQLite source `state/moon-http/research/audits/phase1-20261017-1950/`, second 100-generation session local G79/global G179. Original study uses non-PIT QQQ DEVELOPMENT prices for 2020–2025; this remains NOT independently OOS validated. `scripts/t4_shadow_checkpoint_smoke.py` makes independent SQLite backups with SQLite's backup API from read-only original handles into an automatically deleted temporary directory. It copies the vetted S6 catalog; price data is read only. Operational server and original study state never receive a write.

**End-to-end verified sequence:**

1. Open cloned `AcademicMCPCheckpointService.get` from exact saved G179 checkpoint; verify original 79/100 generations, awaiting GPT plan. The new planning context contains **trade-level loss attribution**, **full completed-trade cohort**, **verified S7 outcome link**, and **79 S7 trials in cross-generation learning memory**.
2. Parent inheritance selects existing counted StrategyIR successor from G75, contract `InheritedResearchIntent`, with replay-verifiable entry/exit rules.
3. Submit an explicitly labelled **fixed smoke plan**, reducing an existing entry gate threshold, entirely to the disposable clone. The real engine validates typed IR and reports next `AWAITING_DIAGNOSIS`.
4. Submit a bounded, evidence-ID-linked S2 diagnostic and one S7 exit-threshold ablation. The generator validates its own authenticated-from-existing-metrics context hash, hypothesis, canonical next-open execution, costs, and S7 paired experiment.
5. Confirm **80 completed local generations on the clone**, one new G180 S7 result and preserved equality of all 79 prior SHA256 generation evidence hashes. Confirm next planning context's memory contains **80** linked S7 trials, causal claims `NOT_ESTABLISHED` and orders disabled. Re-fetch `get` without creating another generation and compare exact historic/new evidence.

**Shadow result:** `SHADOW_G180_S2_S7_REPLAY_VERIFIED_NO_LIVE_MUTATION`. New cloned G180 evidence hash `5be179cfb561ac593e7c0734efe81e9fcb1a09f2a8f2a8b7febfafbbeea851f5`, cloned G180 S7 record hash `9324bc122b8da474dc6037a1332a4c2f248d510064729b861b63d0101155dead`, overall assertion receipt hash `a772649abe68c9ea59b5182416a06975c1337f9cefced862e3e9ba1d2f1177fe`. These are **test-only receipt hashes**, not new official generation hashes.

The script's proposal is deterministic and preselected for QA; **no actual external GPT MCP model** or commercial broker was invoked to create the shadow generation. Do not count this as autonomous LLM research progress or source it to a user-authored financial hypothesis. No alpha or statistical inference is made from its costed S7 result.

## Release readiness / boundaries

- The code includes previously pushed Phase 1, 2-1, 2-2, 2-3 and P3-1 improvements. A guarded **release preflight** against the actual launcher at the active development workspace returned `RELEASE_PRECHECK_PASSED_NOT_DEPLOYED`, `protected_modules_unchanged=true`, `requires_full_test_suite=true`; no process restart or runtime pin update was performed.
- Existing `.venv/bin/python` launcher smoke initially FAILED when invoked from the newly-created Git worktree, which had **no local virtualenv link**. Read-only test worktree's `.venv` was linked to the existing trusted research virtualenv; the isolated MCP STDIO launcher then PASSED **1/1** without product source changes. This is environment setup, not a regression in research code.
- New integration tests verify SQLite backup is independent of original and cannot overwrite a backup target, invalid source/path/session fails closed; associated MCP recovery and scope-lock tests are run with existing research tests.
- Running full Pytest, Ruff/Mypy, and operations ledger values are recorded in the authoritative progress file and must be checked before release. No isolated real HTTP/OAuth smoke or controlled rollback cutover was done at this point.

## Blocked before operations

- No live branch promoted or pinned; source feature tests alone are not the full deploy/runbook.
- The existing session's real 179/300 remains **AWAITING_PLAN**, not incremented by shadow test. Real GPT study begins only after the formal code release, full T3 check, OAuth/HTTP smoke, rollback snapshot and operator-reviewed cutover; then submit actual GPT-authored plan & diagnosis and independently verify new generation/S7 provenance.
- The previously fixed GOP/GPT vs random 10/10 comparison and offline fixed-budget 1×3 are separate evidence; neither proves GPT superior or OOS alpha.

## Full-regression result and release disposition

The first full-suite test run from this newly created Git worktree finished **1,719 PASS / 7 FAIL** (1,728 collected, 2 omitted/skipped); this is **NOT T3 release approval**. Failure groups: the STDIO MCP launcher lacked `worktree/.venv` (1, fixed as a local ignored symlink and separately **1 PASS**), a historical crossover batch fixture references a QQQ parquet present in the live original workspace but missing from the new feature worktree (1, not an algorithm bug), and **five** P0-3B historical-inheritance tests assume session counter **33** or a specific never-before-tested threshold, while the **actual mutable operating session already has local 79**. The inherited tests therefore assert 33/34 against real 79/80 and in some cases run into the correct duplicate effective-signal safety gate. These are stale mutable-fixture tests, **not** grounds to disable the duplication protection, reset/overwrite the live session, or fabricate older data. They must be revised to use immutable, versioned 33-generation historical fixtures before a full release.

The scope-targeted MCP/recovery/memory/cohort/loss/governance suite **51 PASS**; the QQQ G179→shadow-G180 full service smoke PASS; Ruff whole repository PASS; targeted script+test Mypy `--python-version 3.12 --follow-imports=skip` PASS. A first naive targeted Mypy invocation with the repository's default Python target tripped a NumPy 3.12 type-statement parse issue; the explicit Python version check passed. The full single-command suite did **not pass**; production cutover, HTTP/OAuth smoke, rollback and actual GPT G180 live run remain **NOT DONE**.

**Release decision: BLOCKED_FULL_T3_REGRESSION_PENDING_IMMUTABLE_TEST_FIXTURES.** Preserve existing branch, 32 MCP tools, URL/OAuth, live 179/300 count and disabled trading. Next authorized work: untie the five legacy tests from mutable live session (no production evidence mutation) and ensure QQQ test fixture availability; repeat one complete T3 pass, then isolated OAuth smoke/rollback and reviewed deployment before any real GPT generation.
