# Quant AutoResearch P2-2: Full-trade cohort and historical S7 experiment linkage

Branch: `feat/quant-cohort-s7-link-p2-2-20261017` (based on P2-1 `b54e303`). Research scope **REUSED_DEVELOPMENT_ONLY**, not PIT/OOS, trading/order approval, statistically independent causality, or deployed production MCP code.

## What changed

- `research/llm/trade_cohort_review.py` computes deterministic whole-cohort observations **from every audited closed trade**, rather than 8 largest losses and 8 largest winners. Trade ID, real net costed PnL, entry/exit indicator and gate observations come from the existing integrity-verified canonical execution audit. No new trading logic is invented.
- Ex-ante entry trend bucket uses only 20 prior-to-signal-close bars: `UP` if 20-bar close change ≥3%, `DOWN` if ≤−3%, otherwise `SIDEWAYS`. Volatility bucket is `ELEVATED` for ≥1.5% average absolute daily close movement over those same bars, otherwise `CALM`. Warm-up bars are `UNKNOWN`. These are **analysis** definitions, not parameter-optimized entry features.
- Split by realized hold duration `SHORT` ≤5 bars, `MEDIUM` ≤20, otherwise `LONG`, to compare descriptive cohorts. Matched examples require identical entry trend/volatility bucket and realized holding-duration bucket; each winning control is used at most once. Final matching **uses ex-post holding time/outcome**, so it is not an estimable causal effect. Sample display is capped to 8 pairs, while the total matched/unmatched population is accounted for separately.
- Count observed indicator markers among **all** wins and losses. Percentages are descriptive; no p-value/significance, conditional causal proof, or predictive model is asserted. Groups with fewer than five wins or five losses are flagged insufficient.
- `link_completed_s7_to_cohort` checks parent generation, original real decision/trade IDs, immutable stored S7 report hash, controlled dataset/strategy/audit identity, shared-costed parent and child final equity, direction labels and zero-order boundaries. Return-direction and the *expected metric's* direction remain distinct. Previous S7 reports are reused **read-only**, not rerun or fabricated; no additional official generations are added.
- `AcademicMCPCheckpointService._context()` adds `model_context.trade_cohort_review` and `model_context.paired_s7_evidence_link` to the NEXT GPT planning request when there is a previous generation. Historical S2 context hashes, counted cycle rows, MCP URL and costed fills remain unchanged.

## Reproduced G179 example (frozen QQQ 2020–2025 development data)

Frozen G179 audit hash equals its original stored content-addressed audit hash. Whole-trade cohort consists of **32 completed trades: 21 winners, 11 losers**. Six example pairs share pre-entry trend, volatility bucket and a realized holding-period band; five losing trades remain unmatched in these bands.

| Observed completed-trade signal | Losing trades | Winning trades |
|---|---:|---:|
| EMA signal turns off by exit | 11/11 | 21/21 |
| No previous-range breakout at entry | 11/11 | 18/21 |
| Parkinson range variance rises by >=1.5× while held | 1/11 | 1/21 |
| Regime gate turns off by exit | 1/11 | 3/21 |

All six populated trend/volatility/holding cohorts lack at least five observations from **both** win and loss groups. Thus **no differentiating predictor is established**; in particular, the EMA exit signal cannot distinguish gains from losses here.

The counted G179 `S7` predeclared exit-rule experiment was replayed in the earlier phase. Latest immutable report: parent final development equity `$15,188.84`, changed child `$15,395.20`, **+$206.37 equity** (same $10,000 initial capital, +2.06 percentage points of starting capital); canonical total paid costs `$658.27 → $673.52` (**+$15.25 costs**). The record is a **paired costed development comparison**, not independent validation, proof of profitability against QQQ, cause or an approved new parent. This phase only verified/linked the result.

## Tests, safety and next step

Test evidence includes fail-closed corrupt audit and controlled S7, future close perturbations cannot change previously observed entry regime, all closed trades counted including uncovered winning observations, deterministic non-reused matches, bounded samples, unchanged historical S2 `context_hash` and MCP ordering. Runtime deployment is a **separate guarded step** after regression testing; this branch does not modify the running Docker service.

**Remaining phase 2-3:** persist cross-generation hypotheses by a stable *mechanism/indicator/intervention fingerprint*, correlate only verified S7 economic outcomes, flag recurrent failures and duplicate child strategies, and incorporate confirmed repeated disconfirmations as next-GPT planning guidance. No true model training claim without independent controlled comparison. Later phases need randomized baseline, independent holdout/walk-forward, and predeclared cost/risk gates.
