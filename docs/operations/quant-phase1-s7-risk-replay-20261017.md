# Quant AutoResearch: Phase 1-2 historic S7 full-period risk restoration

**Recorded 2026-10-17 KST.** Work branch: `feat/quant-s7-full-risk-sidecar-20261017`; based on live P0-3B code pin `7153a94`, with prior read-only audit `6165ec9` cherry-picked. This branch is **not installed into running MCP** and does not alter existing session counters, original immutable generations, gateway rows, OAuth, fixed MCP URL or order control.

## Purpose and measured result

Previous Phase 1 offline snapshot `state/moon-http/research/audits/phase1-20261017-1950/` has active GPT session `2ba41aaeacd547319cfbf7e6f266ad11` local **79/100**, global **179/300**. All 79 S7 experiments had report metrics, but whole-period child MDD/exposure/closed-trades were available through verified parent selection for only 40. Window-level drawdowns were not sufficient to infer total drawdowns.

- Replayed **39 missing children** from the frozen algorithm plan/inherited StrategyIR and frozen catalog. Each child is validated against original source S7 identity, fully reconstructed canonical S7 output, StrategyIR hash, actual fills, transaction costs and final equity.
- **79/79 whole-period risk coverage** in new read-only `risk-replay-sidecar.json`: 40 previously replay-verified parent-selection candidates + 39 newly replayed children.
- Across 79 paired experiments, **MDD improved in 35**, worsened in **30**, approximately unchanged in **14**. Return improved with MDD no worse in **25**. Return improved but MDD worsened in **17**. Economic parent→child total return improved 42, worsened 31, tied 6; trade-count/metric direction matched but total return worsened 20.
- All numbers pertain to repeatedly selected **2020–2025 QQQ DEVELOPMENT** data. No independent out-of-sample claim, PIT guarantee, statistical causality or trading permission.

## Output location (ignored operational snapshot, never Git)

`state/moon-http/research/audits/phase1-20261017-1950/` contains:

- `cycles.sqlite`, `gateway.sqlite`, `snapshot-manifest.json` — prior frozen immutable capture.
- `catalog-for-risk-replay.sqlite` — separate catalog backup for read-only replay; **not the operational catalog**.
- `risk-replay-inputs.json` — SHA-256 of frozen catalog and input development Parquet.
- `risk-replay-sidecar.json` — per child source generation, source hashes, child hash, total return, whole-period MDD, exposure and closed trades; new replays have outcome equity hash, cost and record proof hash.
- `quality-report.json`, `quality-report.md` — refreshed joined risk diagnostics.

The new auditor checks all 79 source generation and report identities and validates replay proof links and original parent-selection records. The 40 legacy parent selections retain their prior replay-proof basis; they have not been re-executed in this pass. Existing immutable cycle evidence is not edited. Report generation fails closed on missing records or tampering.

## Reproduction

Use an **unmodified copy** of the input market parquet and the retained frozen SQLite snapshot. Do not run replay against live/catalog SQLite as writable input. From the new worktree:

```bash
python -m scripts.replay_academic_s7_risk \
  --snapshot /path/to/state/moon-http/research/audits/unique-frozen-capture \
  --catalog-source /path/to/academic-gpt-checkpoints/catalog-s6-v2.sqlite \
  --market-parquet /path/to/data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet \
  --session-id 2ba41aaeacd547319cfbf7e6f266ad11
```

The tool snapshots the catalog into the frozen audit directory, leaves live database files untouched, and only creates the final sidecar after all validations succeed. If catalog copying completes before an interrupted replay, restart is permitted **only if** the frozen copy and market-file SHA match their saved inputs. A successful sidecar will not be overwritten. The quality audit automatically includes sidecar metrics if present, otherwise reports the original partial coverage.

## Limits and follow-up

1. This closes the **historic missing 39/79 risk-stat coverage**, not live S7 on-write metrics for subsequent generations. Future S7 records still need a canonical sidecar/telemetry contract and fresh frozen snapshot to cover them.
2. The full source evidence chain's cryptographic regeneration, 2020–2025 repeated selection bias and random vs GPT controlled search remain separate checks. **No alpha proof** is asserted.
3. Next is Phase **2-1**: attribute entry/exit/risk failures to actual decision-state and trade histories; compare counterfactuals across market regimes and preserve the alternative explanation. Use this before adding new indicator search.
