# PythonMCP G3 diagnosis corroboration and fail-closed resume gate

**Date:** 2026-10-26 KST
**Stage / Q IDs:** T4-PY-MCP-RECONCILE-RESUME-01 / Q02, Q06, Q08, Q09, Q11, Q15, Q16, Q17, Q20.
**User value:** recover defensible insight when an auxiliary model-audit acknowledgment was lost and prevent an already-completed study from consuming further model turns or duplicating evidence.
**Boundaries:** read-only, isolated PythonMCP `state/python-mcp/` only; no model invocation, login, market download, OAuth change, order, sealed OOS access, or change to original Moon/P5 and shared parallel development files. Existing frozen V05→T4→V01–V04→V06→V07 order remains in force.
**Acceptance:** demonstrate G3 canonical evidence corroboration from *independent DB tables within the same local checkpoint* while preserving the missing auxiliary log marker, and fail-closed no-op for completed or uncertain checkpoints. These same-host SQLite records are **not** independent provider proof.

## Implementation and actual check

- New `application/python_mcp_checkpoint_reconciliation.py` and `scripts/reconcile_python_mcp_cohort.py` wrap the existing read-only data/model evidence auditor and use `mode=ro` SQLite connections. The external JSONL log is never rewritten.
- A missing diagnosis `CANONICAL_ACCEPTED` log line is **corroborated** only when (a) canonical generation exists and its full hash chain was independently recomputed by the prior auditor, (b) a unique `generation_timings` row has a populated completion timestamp and the same generation evidence hash, and (c) a unique `p4_s7_approvals` row has matching counted evidence hash and valid locally recomputed review hash.
- If any additional record is missing or corrupted, mark `UNRESOLVED`, do not guess a success. A missing plan acknowledgment cannot be inferred merely from an eventual diagnosis. `original_auxiliary_log_restored` and `provider_attested` remain `false`.
- A matching fully completed session and gateway state returns **`resume_gate=NOOP_COMPLETED`** and `new_generations=0`. A truly pending `AWAITING_PROVIDER` session with `AWAITING_PLAN`/`AWAITING_DIAGNOSIS` returns **`REQUIRES_AUTHENTICATED_MODEL_DECISION`**, requiring a separate authorized model host. Any inconsistent, in-flight or uncertain checkpoint returns **`BLOCKED_CHECKPOINT_UNCERTAIN`**. None launches a model or advances the checkpoint.
- Prevent reading another workspace through a gateway-database symlink or resolved path escaping the isolated study directory.

**Observed on the existing real-price Codex SDK experimental cohort:** 20/20 already completed (not new progress), `linked_evidence_verified=true`, `missing_canonical_acceptance_markers=['G3:diagnosis']`, separate corroboration **`CORROBORATED_CANONICAL_SQLITE_ONLY`**, `original_auxiliary_log_restored=false`, `provider_attested=false`, `resume_gate=NOOP_COMPLETED`, `new_generations=0`. Original run had 53 SDK model output events but no independent model-provider invocation evidence. Source is 2020–2025 QQQ **non-PIT development only**; no 2026 OOS performance endorsement. Original G3 JSONL and SQLite evidence unchanged.

## Reproducible command in existing Moon Docker bash terminal

```bash
cd /shared/moon-workspace/AutoResearchFinance_PythonMCP
PYTHONPATH=. .venv/bin/python scripts/reconcile_python_mcp_cohort.py --work state/python-mcp/real-qqq-codex-20261025
```

## Tests and next requirements

- New tests first, implementation afterwards. Positive corroboration, tampered S7 hash, mismatched gateway phase, untrusted gateway symlink, incomplete and in-flight sessions are covered. Core tests also continue to reject changed source data, unverified source, or modified generation evidence.
- Scoped expanded pytest: **65/65 PASS** (81.59 seconds); Ruff changed sources/tests PASS, mypy new source/CLI PASS; `git diff --check` PASS. Full-repository pytest/mypy, true PIT/OOS economic acceptance NOT RUN.
- **Not implemented / not verified:** provider-signed proof and isolated trusted collector, model-provider billing or independently verified usage, V05 comprehensive realistic cost/statistics and PIT/OOS access, continued verified 10→100 new-generation research or deployment. Existing study remains `REAL_MODEL_NON_PIT_UNATTESTED_EXPERIMENT_ONLY`; formal independently attributed T4 acceptance remains blocked.
- Next approved order: V05 costs/statistical qualification, actual trusted provider attribution/isolated collection, then budgeted reproducible new GPT research with strict restart testing, then V01–V04 independent PIT/OOS gates. Original P5 and live order state remain unchanged.
