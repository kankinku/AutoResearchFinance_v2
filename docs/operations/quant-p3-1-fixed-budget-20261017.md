# P3-1: Fixed-budget three-arm canonical research comparison

2026-10-17 KST. Scope: Q02 Q04 Q06 Q07 Q08 Q09 Q14 Q17 Q20; part of already-approved T4 controlled-search evidence. Existing V05/T4/PIT/OOS/V06/V07 order unchanged. Feature branch `feat/quant-fixed-budget-arms-p3-1-20261017`; research-only, not deployed to running MCP. Original 179/300 generations remain untouched. No model invocation or live orders.

## New implementation

`research/llm/fixed_budget_arms.py` supports a three-arm comparison using one immutable parent, one QQQ DEVELOPMENT dataset and the same canonical fee model. Arms: saved GPT typed S7 intents, fixed-seed uniform parameter mutations, deterministic small local parameter mutations. K in 1..5 costed backtests per arm, plus one shared parent backtest. No adaptive retry or selective replacement, no new counted generation, no strategy promotion.

`scripts/compare_fixed_budget_arms.py` freezes all 3K candidate StrategyIR hashes and typed changes into an exclusive manifest *before candidate evaluation*. It independently checks frozen source DB/report/catalog hashes, GPT child hashes, parent replay audit and input market. Separate `score` command verifies the seed, original parent/market and frozen candidate generation identities before executing canonical runs. Scored report contains costed equity, total return, CAGR, Sharpe, full-period MDD, market exposure, closed trades, total costs, QQQ price-only buy/hold and parent deltas. Unchanged fill traces despite distinct StrategyIR hashes are explicitly measured. Both receipts have SHA-256 content hashes, and are stored only in ignored audit state.

## Actual frozen G179 demonstration

Source QQQ 2020-2025 non-PIT, second session local generation 79/global G179, saved GPT S7 proposal. Three arms receive exactly one candidate run each; PRNG seed `20261017`. Frozen manifest hash `197bfe93fc9452bf22c37aaca8a16943fb7211ebb29cc06976517565ddfba8cc`; verified result hash `0ea16cb21fbfec26533a0ade5a9e739cf8142e8c80250444a41922c8dda3b567`.

| Arm | Net return | Full MDD | Exposure | Closed trades | Fees USD |
|---|---:|---:|---:|---:|---:|
| Original parent | 51.888% | 8.435% | 32.825% | 32 | 658.27 |
| Historical GPT | 53.952% | 7.782% | 32.626% | 33 | 673.52 |
| Random | 29.502% | 24.424% | 56.499% | 5 | 97.04 |
| Local | 51.888% | 8.435% | 32.825% | 32 | 658.27 |

QQQ costed next-open buy/hold price-only return on same data: 187.772%. Local child's strategy hash differs but real fill trace and equity are identical to its parent: consumed search budget without behavioral improvement. The older GPT S7 child final wealth/cost replay was independently matched to the prior frozen record. Evidence files live under ignored `state/moon-http/research/audits/fixed-budget-p3-1-20261017-v2` with plan and scored receipt separated.

## Limitations and next task

GPT trial was historically chosen on these same reused development bars. Random/local are first-seed controls, not outcome-informed or posthoc cherry-picked. Equal backtest count is not equal total historical LLM inference time, model-token budget, computational cost or discovery effort; sample 1 per arm cannot show GPT superiority. This is neither independently pre-registered *prospective* research nor true PIT/OOS, multi-seed statistical inference or evidence of alpha. The random/local candidate bank is currently restricted to reviewed numeric rule thresholds and does not match full GPT StrategyIR expression space. Do not claim a successful fully autonomous tri-arm policy.

Next within T4: connected authenticated GPT prospective completed generations; multiple seeds and equal trial budgets on the same new parent pool, all intentions frozen before unseen results, unbiased walk-forward when independently available, and deployment gate/long-run recovery. Preserve the original project-scope acceptance stages and authorization boundaries.
