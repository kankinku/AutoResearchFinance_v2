# Quant AutoResearch Phase 2-1 — observable trade-loss pattern packet

Date: 2026-10-17. Feature branch: `feat/quant-loss-attribution-p2-1-20261017` (descendant of Phase 1 frozen S7 risk-replay branch). Status: **implemented and fixture tested; not deployed to live MCP**.

## Scope

Implement a **bounded, evidence-linked, descriptive** trade-loss report for ChatGPT MCP's next `AlgorithmPlan` or `InheritedResearchIntent` planning context. The only LLM is the existing authenticated ChatGPT client. The server does not invoke any model API, alter a pending token, promote a strategy, mutate an immutable 179-generation record, change the existing MCP URL or enable real orders.

### Mechanism

`research/llm/loss_attribution.py`: fail-closed check of the canonical decision audit, dataset identity, signed audit checksum, equity hash and decision-to-market timestamp alignment. For up to eight worst closed losing trades, supply verified trade and decision IDs, actual next-open fills, pre-cost trade PnL, paid canonical fees, observed hold-period close peak-to-exit giveback, available entry/exit indicator values and evaluated regime gates. Selected top-eight positive-PnL trades are **illustrative, unmatched control samples**; never statistically independent.

Pattern codes are observational: absent prior-range breakout on entry; EMA or momentum switch by exit; materially higher Parkinson variance by exit; regime-gate switch; observed close-peak giveback; trading costs exceeding positive gross PnL. No observed supported indicator must be treated as an unknown value, not guessed. These codes are neither ground-truth causes nor financially predictive. Recompute a deterministic `evidence_hash`, append the latest origin generation evidence hash and audit hash, then provide up to four unexecuted, evidence-ID-bound single-change S7 test suggestions. Each includes a control, risk/cost tradeoffs and an explicit alternative explanation. More frequent loss markers must be juxtaposed with frequencies among selected winning examples; even higher loss frequency in eight examples is **not statistical significance**.

`application/academic_checkpoint_service.py` adds the packet as `model_context.loss_attribution` **only for the NEXT planning checkpoint**. `build_diagnostic_context()` and S2 historical `context_hash` are unchanged; old records can still be replayed. The packet explicitly identifies its source as the most recent counted strategy (not necessarily the highest-return promoted parent).

## Real frozen G179 replay: observed facts

Frozen canonical audit trace matches original G179 `audit_hash`. G179 counted strategy: 32 completed trades, 11 losses. Worst 8 loss examples:

| Observed condition | Losing cases / 8 | Positive-PnL controls / 8 |
|---|---:|---:|
| EMA turns off by exit | 8 | 8 |
| No prior range breakout at entry | 8 | 7 |
| Parkinson range variance grows by ≥1.5x | 1 | 0 |
| Regime gate turns off by exit | 1 | 0 |
| >3% observed close peak-to-exit giveback | 1 | 3 |

**Interpretation:** EMA turning off is not discriminative in these two selected samples. A breakout filter could discard winning entries (7/8 successful trade sample lacked breakout). The remaining 1/8 observations are very small samples, not diagnoses. Controlled counterfactual ablations and broader cohorts are required before changing the parent strategy. These observations come from repeatedly used 2020–2025 QQQ **development-only, non-PIT** prices, not OOS proof.

## Tests and next step

- New fixture tests cover hash/market tampering rejection, signed trade PnL and costs, bounded deterministic samples, explicit unverified hypotheses and stable S2 context when new planning advisory is added.
- Next planned Phase 2-2: verify differences against *all* closed wins/losses (not eight sampled extremes), match by regime and comparable holding period/exposure, combine with full-period child S7 attribution and test single-factor entry/exit counterfactuals with predeclared metrics. Only then promote a robust class of hypotheses to research memory. Finally compare GPT against budget-matched random search and embargo OOS.

All outputs are for research. `causal_status=NOT_ESTABLISHED`, `independent_oos_approved=false`, `broker_executable=false`.
