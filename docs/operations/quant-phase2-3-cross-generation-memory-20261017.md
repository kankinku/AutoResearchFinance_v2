# Quant AutoResearch P2-3 — typed cross-generation memory (2026-10-17)

Branch: `feat/quant-crossgen-memory-p2-3-20261017`, based on P2-2 commit `d82fae0`. The source remains in an isolated Git worktree. This does **not** deploy to the running Docker/MCP server, change the stable `/quant` URL, promote a child, execute an order, or increment the original research cycle.

## What was built

- `research/llm/cross_generation_memory.py`: creates evidence-linked, deterministic, bounded memory from already saved S7 records. Reuses existing `build_experiment_learning` and `build_economic_feedback` fail-closed evidence checks, then reconciles parent final equity, actual child equity, trade costs, intervention identity, trial hash and risk-window limitations.
- A canonical **exact fingerprint** of the typed intent operations (name, path, condition, thresholds, logic etc.) ignores unpredictable LLM prose, hypothesis IDs, and `parent_ids`. A separate **family fingerprint** groups the same operation/indicator/path with different parameter thresholds. When a `REMOVE_RULE` or `REMOVE_REGIME_FILTER` operation specifies only an array index, the family is explicitly **parent-strategy scoped** because the target indicator is otherwise unknown. These do not support false cross-parent aggregation.
- A child strategy hash duplicate is **not** the same claim as repeating exactly the same intervention on the same parent: both are counted and surfaced separately. Prior exact parent+intervention identities are supplied as a bounded list so future GPT planning can avoid redundant experiments or justify deliberate replication.
- Report how often families produced **costed** parent/child improvement, worse outcomes, unchanged final equity or inactive children, and note observed development-window MDD deterioration. This module explicitly does **not** verify whole-period S7-child MDD from the historic offline sidecar or estimate causal probabilities. The group classification keeps majority-positive-but-mixed families distinct from predominantly adverse families.
- A new `model_context.cross_generation_memory` field is assembled for each **NEXT GPT plan** from the saved DB state, not by modifying the historic S2 diagnostic context or creating a second source-of-truth database. The existing ChatGPT MCP remains the LLM interface. This is guidance, not a hard prohibition or strategy execution: formal duplicate-policy rejection/retest exemptions are not enabled by this change.

## Real saved S7 results on active second 100-generation campaign

This was replayed **read-only** against the immutable 2020–2025 QQQ research snapshot. There are 79 completed local generations (179/300 global). Of 79 S7 results: **42 child net final equity increased**, **31 decreased**, **6 unchanged**; **3 child strategy hashes repeat**, **0 exact parent+typed intervention pairs repeat**, and **0 unclassifiable structured intents**. The conservative parent-specific rule removal grouping produces **26 intervention families**; if unrelated array-index removal operations were incorrectly treated as the same rule, the family count would have been artificially lower.

| Family of typed interventions | Reused-development equity better | Worse | Same | Advisory interpretation |
|---|---:|---:|---:|---|
| Replace exit `plan_vote_score` threshold | 16 | 5 | 0 | Mixed but improvement-skewed, cannot infer causal mechanism |
| Add `previous_range_breakout` entry rule | 4 | 12 | 0 | Predominantly adverse; examine opportunity losses and conflicting evidence |
| Replace `parkinson_variance` entry threshold | 5 | 3 | 0 | Mixed, insufficient basis for a fixed optimum |
| Add `dual_sma_trend_50` entry rule | 1 | 4 | 1 | Predominantly adverse; review before retesting |
| Replace `time_series_momentum` entry threshold | 1 | 2 | 0 | Predominantly adverse; very small sample |

**Three** typed intervention families receive the advisory repeated-net-loss warning. All families are **post-selection**, tested on the same repeatedly reused development market. Family outcomes represent parameter sweeps and sometimes changing parents; they are not independent replications, a statistical p-value, or proof of expected net profit.

## Safety / validation boundaries

The source evidence records and report checksums remain unchanged. `full_period_child_mdd_verified=false`, `independent_oos_approved=false`, `broker_executable=false`, `automatic_strategy_execution=false`, `causal_status=NOT_ESTABLISHED`. The strategy's costed equity delta is allowed to disagree with a directional S7 metric match (e.g. the number of trades can improve while final wealth falls).

Test scope: synthetic 1–4 generation cohorts, numeric threshold change vs changed freeform prose, parent-scoped ambiguous removals, explicit repeated intervention and duplicated children, contradictory economic results, cost/parent/PnL tampering, missing S7, zero generations, and ChatGPT MCP next-context compatibility. Real-data replay and relevant regression tests are reported separately after running.

## Next steps

- P3-1: Split the research **engine modes** into budget-matched baseline random exploration, bounded local evolution and distinct data-derived GPT hypotheses. Keep a fixed, non-adaptive arm for comparison.
- P3-2: Verified indicator research registry and new academic mechanisms. All external references need provenance and data-available-before-test checks.
- P3-3: Structured novel rule compositions and risk/entry/exit regime interactions under execution semantics verified by canonical backtest.
- Follow-on: Programmatic duplicate preflight and explicit, justified retest exception (do not blindly prevent good independent repetitions). Include replay-verified whole-period MDD and exposure in every *future* S7, and then independent OOS/overfitting controls.
