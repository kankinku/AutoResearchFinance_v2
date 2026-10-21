# Quant AutoResearch — standardized cohort operator (2026-10-21)

## Why this exists

The previous academic controller hard-coded `requested_generations == 152` and manually required backup, extension, candidate search, process start and research resume. That caused brittle restarts every 100-generation request.

## Canonical invocation

From the project worktree, with the existing `.venv` and no other academic writer running:

```bash
.venv/bin/python -u -m scripts.run_academic_cohort \
  --cohort-id G153-G252-20261021 --expected-start 152 --additional 100
```

Rerun **the same command with the same cohort ID** after a clean `AWAITING_PLAN` checkpoint interruption. It must never extend a second time on retry. If it is already completed, it verifies the evidence head and exits without adding generations.

## Actual work done

- Recovered the previous sealed academic session **G152/152**, including immutable G1–G152 Evidence chain and real S7 records.
- Backed up the canonical SQLite databases (`cycles.sqlite`, `gateway.sqlite`, catalog) using each SQLite backup API into the ignored persistent directory `state/moon-http/backups/academic-G153-G252-20261021/`; every copy passed `PRAGMA integrity_check` and SHA256 manifest. This is intentionally not Git.
- Extended the **same session** to **G252** using its existing audited `AcademicMCPCheckpointService.extend_completed_session` (100 additional). The original G152 evidence SHA remains unchanged.
- `scripts/run_academic_cohort.py`: file lock against overlapping research operators, stable idempotency key, expected previous completed generation, backup, evidence-chain validation, typed operator extension, detection of incompatible goals/IDs and impossible states, persisted operator JSON state and error type, gated resume only at `AWAITING_PLAN`, dynamic generation target and end checks.
- Existing deterministic typed-signal controller `scripts/fresh_development_cohort_controller_20261021.py` now reads the session requested target (must remain <=400), rather than the previous 152 literal. Existing >=30 actual closed trades, unique effective signals against all prior G1..., costed fills, evidence/S7 and no orders remain intact.
- Research dashboard `scripts/fresh_research_dashboard.py` recognizes the standardized `-m scripts.run_academic_cohort` process as a genuine local active controller. Normal performance chart auto-updates from canonical SQLite every 5 seconds.
- Preflight + targeted pytest unit tests check manifest atomicity, SQLite integrity-backed backups, invalid IDs/ranges, and no hard-coded G152; Ruff/mypy checks. No broker credentials or historical evidence in Git.

## G158 development candidate exhaustion

The original deterministic policy selected valid G153–G157 generations, then exhausted its static candidate list at G158. It correctly recorded `EXHAUSTED_TYPED_PLAN_POOL_G158`, marked the operator job `BLOCKED` and exited without fabricated progress. The stopped session remained `G157/252 AWAITING_PLAN`, all evidence intact.

Before resuming the **same cohort ID**, inspected the fixed feature set and confirmed `plan_entry`, dual-SMA, EMA, breakout, pullback, vote score, and branch index feature values actually exist across 1,508 development QQQ bars. Verified that an OR-entry with two changed rule conditions and one exit-rule change parses under `ResearchIntent` and `apply_intent`.

Extended the controller with deterministic bounded pairwise combinations of the **actual present** entry features (two conditions), AND/OR, distinct exit timing and directional inequality. New candidates still undergo full signal-vector deduplication, minimum >=30 closed trades, audited net-cost backtest, S7 and Evidence chain. This is **not proof of novelty or GPT-per-generation invention**; the same development sample and static indicator set remain a major overfitting risk.

The operator can be resumed from G157 without a new backup or extension:
```bash
.venv/bin/python -u -m scripts.run_academic_cohort \
  --cohort-id G153-G252-20261021 --expected-start 152 --additional 100
```

If it fails again, inspect the persisted cohort JSON `state/moon-http/fresh-20261021/cohorts/G153-G252-20261021.json`, gateway checkpoint phase, and read-only dashboard first. **Do not** delete/recreate the same session, weaken validation, invent research, or launch a second concurrent operator.

## Critical disclosure

This is a **deterministic GPT-designed strategy search and real backtest system**, not a proof of autonomous GPT agent actively reasoning each generation; per-generation independent GPT calls, data PIT validity, sealed OOS holdout, and live trading authorization remain **unverified or OFF**. Repeated development dataset performance and “best candidate” comparisons must not be represented as realized or OOS-validated excess return.
