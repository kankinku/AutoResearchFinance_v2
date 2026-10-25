# PythonMCP read-only audit of existing 20-generation real-model development cohort

**Date** 2026-10-25 KST; **stage** T4-PY-MCP-REAL-QQQ-20-READONLY-AUDIT-01; **Q IDs** Q02/Q04/Q06/Q08/Q09/Q11/Q15/Q16/Q17/Q20.
**Value**: identify existing actual SDK-assisted QQQ study, verify what it really completed and report metrics instead of requesting a duplicate 10–20 generation run. **Boundaries**: audit existing isolated `state/python-mcp/` artifacts only; preserve original P5, uncommitted parallel changes, OAuth, MCP URLs, vendor credentials, sealed OOS and disabled orders. **Acceptance**: recompute chain hashes of all persisted 20 generations, verify exact dataset bytes/hash, evaluate SDK audit event coverage and transparently report missing markers without laundering SDK metadata into independent provider proof. **Next frozen stage**: finish V05 cost/statistical qualification and T4 externally trusted provider invocation capture and bounded repeatability before any 100-generation formal acceptance; thereafter V01–V04→V06→V07. No economic/OOS qualification claimed.

## Read-only discovery and measured outcome

The previously existing separate cohort `state/python-mcp/real-qqq-codex-20261025/` had already completed **20/20** (`COMPLETED`) before this audit; these generations were **not launched or added by this task**. The non-PIT research session is `a498e46f…`, dataset SHA-256 `94e1f5f118e6dc14d25dc95b654fcfd485f07bce251fb1c8a16d1843df638037`, canonical dataset hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`. Dataset holds **1,508 QQQ daily bars, 2020-01-02 through 2025-12-31** and is the same immutable source as the earlier source-import task.

- **Evidence**: 20 canonical generation records, generation indices sequential 1…20, all per-generation body hashes recalculated with `AcademicCycleService._row_evidence_hash` schema and all 19 predecessor links valid; completed=20/20. Original log and databases left unchanged.
- **Actual developer experiment:** source `run_real_dev.py` calls `CodexStructuredDecisionHost` with authenticated Codex SDK opt-in plan and diagnosis; P4 capture *disabled* (`p4_model_capture_v1=False`) and SDK metadata self-reported. **SDK audit recorded 53 distinct `MODEL_OUTPUT` events** (plan/diagnosis plus rejection retries), reporting **1,715,590 tokens** in total. This figure is SDK-reported accumulated tokens, not a provider bill or verified provider utilization. Some SDK output events were rejected before research acceptance. **No independently signed model-provider invocation receipts**, no independent attestation, no evidence of profitable real-time trading.
- **Audit completeness limitation:** local JSONL event `CANONICAL_ACCEPTED` for generation **G3 diagnosis is absent**, although SQLite contains its committed generation and canonical hash chain remains internally consistent. This is an audit-log coverage gap to repair or qualify, not grounds to fabricate an acknowledgment. This cohort must **not** be promoted to verified T4 independent-model acceptance without trusted evidence.
- **S7:** independent read-only SQLite count showed 20 approved quality-control entries, 0 rejected; S7 approvals are development-only and do not establish causality or independent OOS results.
- **20 generation results:** 19 positive and 1 negative. Largest development return **G16 +101.02%**, MDD **21.48%**, 25 trades (**below** 30-trade comparison filter). Best with at least 30 trades **G15 +82.69%**, MDD **29.64%**, 34 trades. Low-MDD candidate **G7 +51.42%**, MDD **8.01%**, 36 trades. Latest G20 **+48.71%**, MDD **31.10%**, 65 trades. These are alternative strategy variants tested on the **same development window**, not sequentially compounded portfolio returns. Same-window price-only QQQ buy-and-hold had been reported around +187.77% in previous dashboard reference; the strategies' development backtest numbers do not prove outperforming QQQ or 2026 transferability.
- **Canonical safety:** `broker_executable=false`, `independent_oos_approved=false` in generation records. No broker orders or OOS data opened by this audit. Source classification is explicitly `REAL_MODEL_NON_PIT_UNATTESTED_EXPERIMENT_ONLY`, not formal provider proof.

## Reproducible command in existing CMD → Docker terminal

```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
PYTHONPATH=. .venv/bin/python scripts/audit_python_mcp_cohort.py --work state/python-mcp/real-qqq-codex-20261025
```

Auditor added: `application/python_mcp_research_audit.py`, read-only CLI `scripts/audit_python_mcp_cohort.py`. It checks study boundary, source Parquet SHA-256, canonical dataset hash and development zone, recomputes each canonical evidence hash with session/sequence/prior link and validates no order/OOS flags; checks recorded model output event stage/generation/unique SDK turn IDs/positive tokens and flags missing accepted-event markers. **A valid local SDK identifier remains UNVERIFIED for model provider provenance.** Damaged price bytes, tampered evidence, missing model output, symlink escape and missing JSONL accepted-event are covered by tests.

## Verification / remaining items

- Tests: **57/57 PASS** across new audit tests, existing data import, Codex SDK, account probe, academic signed handoff, T4 orchestrator, and governance. Ruff PASS for new code/tests, mypy PASS for new source/CLI, `git diff --check` PASS. Full repository pytest/mypy, PIT/OOS/economic acceptance NOT RUN.
- **Still BLOCKED**: a collector independently isolated from the Codex model process, trusted attribution of actual provider invocations, V05 realistic net-cost/statistical acceptance and reproducible true new-generation autonomous T4 10→100 qualification. This historical **20/20 SDK-assisted development experiment** does not erase those acceptance criteria.
- Original P5 28/100, saved existing 20/20, account OAuth, Moon routes, other parallel worktree modifications and orders/OOS rights were not changed.
