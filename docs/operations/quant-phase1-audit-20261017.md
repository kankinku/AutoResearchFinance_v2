# Quant AutoResearch — Phase 1 independent audit foundation (2026-10-17)

Branch: `feat/quant-audit-phase1-20261017`. This implementation is **read-only**, does not alter the authenticated MCP URL, checkpoint phases, generation counters, orders or existing generation evidence. Working source stays in an isolated Git worktree; the active Moon service code and running process are untouched.

## 1-1: Freeze and provenance

- Source: active `academic-gpt-checkpoints/cycles.sqlite` and `gateway.sqlite`; online SQLite `backup()` snapshots for WAL-compatible non-destructive capture. Snapshots and reports are ignored operational state, not Git commits.
- Freeze: `state/moon-http/research/audits/phase1-20261017-1950/` under the active Moon project, including two frozen SQLite databases, `snapshot-manifest.json`, `quality-report.json` and `quality-report.md`.
- Each snapshot file has SHA256; checks fail closed if changed after capture, and SQLite integrity checks run on both backups.
- Two databases are backed up sequentially and are **not atomically synchronized**. The auditor detects mismatched or missing generation numbers, sessions, and dataset IDs before reporting. The stored evidence proof hashes are recorded but **not independently recomputed against the original backtest**; a snapshot hash is not a trading result verification.

## 1-2: Economic comparison

- Separate **hypothesis-direction match** from **economic success** (child final equity minus frozen-parent final equity) regardless of whether the experiment targets turnover, MDD or total return. Compare parent and child costs without aggregating independent backtests into claimed portfolio PnL.
- Recorded current session: 79 S7 experiments; better 42, worse 31, same 6; direction matched and economically worse **20**. Selected development parent: +63.48%, MDD 7.68%, exposure 31.37%, 34 closed trades; costed QQQ buy-and-hold reference +187.77%.
- Full-period child MDD/exposure replay summaries are currently available and matched to S7 identity for **40/79** experiments; remaining **39/79** cannot safely be inferred from development-window drawdowns. This is a telemetry gap, **not** 39 verified failures. Record absent measurements explicitly.
- The prior 100-generation session has 35 better, 64 worse, 1 same S7 child comparisons; the origin sessions are not independent market observations.

## 1-3: Diversity and overfit limits

- Current session S7: 76 unique child strategy hashes across 79 experiments, 3 repeated hashes, 6 cases with same-fill-trace true. Equal return+fill-count proxy yields **48 matching pairs** (not evidence of exactly equal fills). All 179 generations reuse the same 2020–2025 QQQ development dataset.
- Flags: selected-sample/multiple-testing risk, repeated dataset, no causal proof, no sealed independent OOS approval, no GPT-versus-random fixed-budget comparison. **No calibrated overfit probability or statistical alpha claims** are produced from the available records.
- Test fixtures exercise snapshot immutability/non-overwrite, integrity fail-closed, incomplete experiment joins and separation of predicted-direction accuracy from actual economic improvement.

## Run independently (using the existing project Python environment)

```bash
python -m scripts.audit_academic_campaign \
  --checkpoint-dir /path/to/active/state/moon-http/research/academic-gpt-checkpoints \
  --destination /path/to/active/state/moon-http/research/audits/unique-freeze-name \
  --origin-session a84a100b15a242269b554282b01d91c9 \
  --active-session 2ba41aaeacd547319cfbf7e6f266ad11
```

`--destination` must not exist. Reports are for offline inspection and do not promote strategy parents or submit additional generations.

## Remaining work / next stage

1. Extend S7 telemetry to persist replay-verified full-period child MDD, exposure and trade/cost summaries for **every** generation without changing past immutable evidence; on old generations offer a separately signed replay-derived sidecar, not a mutation of historic evidence.
2. Strengthen per-trade/indicator attribution, missing profitable trades, regime-specific hypotheses and counterfactual tests; log if a GPT hypothesis was derived from evidence versus a broad conceptual test.
3. Create GPT vs local/random evaluation groups with identical evaluation budgets and future embargoed test periods. No independent OOS promotion before data provenance and multiple-testing controls.
4. Resume later GPT generations only after explicit GPT input; preserve original `179/300` checkpoint. Do not claim unattended multi-generation AI inference.
