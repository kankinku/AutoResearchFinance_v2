# P2 realistic child precommit gate + signed failure feedback — 2026-10-21

## Decision

**P2 functional pilot PASS** on **five cloned counted generations**, with exactly **12 audited high-MDD child candidates rejected before counted generation registration**. It DOES NOT prove positive independent OOS returns, nor implement per-generation GPT calls. The objective was to verify the risk cap is enforceable while examining valid-trial scarcity and the cost of generating alternatives.

## Prespecified conditions
- Frozen original academic QQQ daily development session: G452/452, 2020-01-02..2025-12-31, non-PIT. Original G452 head `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`; original source count/integrity checked unchanged.
- All **parent promotions** and **new child precommit** gates active.
- **Child max MDD <=30%**, **child-parent MDD increase <=15 percentage points**, **>=30 round-trip completed trades**. No limits were loosened. No broker orders.
- Maximum **five new counted generations G453–G457**, retain any rejection as an audited retry against the same checkpoint token.
- Controller remains `DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM`. The failure-feedback adaptation uses `DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT`; it is NOT real GPT model inference.

## Implemented and tested
- Added immutable failed mutation operations inside `precommit_risk_rejections.review_json` (already signed via `content_hash`). Retains source, parent selection, dataset, token identity, S2 costed equity hash and risk metrics.
- `research/llm/precommit_rejection_feedback.py` verifies each rejection record against the current parent, selected generation, dataset, checkpoint token and risk budget; fails closed on mismatch or altered hash. It supplies **a hypothesis**, observed MDD failure type, attempted strategy domains, rejection count, signed evidence digest and risk-invariant recommendations.
- On P2 opt-in `get(AWAITING_PLAN)`, exposes `precommit_rejection_feedback` in the model planning context. A deterministic controller receives feedback **only from actual rejected strategies** and reprioritizes not-yet-tried candidate operations to test alternative entry/exit hypotheses. Every candidate still undergoes full costed fill replay and the SAME hard precommit gate. No scoring falsification, no synthetic success, no use of the spent 2026 holdout.
- Added focused tests for evidence tampering, wrong parent/token, no-failure conservative behavior and actual remaining-queue reprioritization. Old controller behavior is unchanged when `precommit_child_risk_budget=None`.

## One-shot pilot execution and storage issue
- `scripts/run_p2_precommit_realistic_pilot.py` cloned 3 databases to the shared workspace and declared 5 new generations; the first run completed G453 and G454, accumulating 12 risk rejections (all MDD>30%) and 12 evidence-based reprioritizations.
- Then `sqlite3.OperationalError: disk I/O error` occurred during gateway `PRAGMA journal_mode=WAL` at the transition to the next research checkpoint, despite ample free space. All 3 cloned databases were verified via `PRAGMA quick_check`, and the checkpoint remained `G454/457 AWAITING_PLAN`. The root cause of the intermittent shared-volume SQLite I/O issue has **not been proved**.
- `scripts/resume_p2_precommit_pilot_local.py` used SQLite online backup to move that existing clone to a host-local `/tmp` directory and continued ONLY G455–G457. The resumed process exited 0 and all five generations had S7 reports, continuous evidence hashes and costed audits. No completed generation was rerun. The original G452 research remained untouched.
- Final result JSON: `state/moon-http/fresh-20261021/p2-precommit-realistic-5gen-20261021/result.json`, SHA256 content identity `cb0474d655aeb55413b3a2e4f6065eb15e6300e1c1f1583a47924508fcbd64a7`. Clone databases are kept only in ignored local operational runtime, not committed to GitHub.

## Measured 5-generation results (all development sample, not 2026 OOS)

| Generation | Measured return | MDD | Closed trades |
|---|---:|---:|---:|
| 453 | +73.034% | 27.909% | 103 |
| 454 | +38.439% | 23.077% | 78 |
| 455 | +168.370% | 26.045% | 36 |
| 456 | +1.664% | 27.782% | 422 |
| 457 | +22.228% | 22.195% | 83 |
| Average | +60.747% | 25.402% | — |

- **Precommit rejected children 12**; failure mode absolute MDD>30% in all twelve. **Adaptive reprioritization events 12**.
- **All attempted plan rejections 1,344**, predominantly historical duplicate signals, insufficient completed trades or invalid fixed mutation paths. This is evidence that finite static rule generators are still severely inefficient. These are *trial-level failures*, NOT 1,344 unsuccessful counted generations.
- Every committed child satisfied the actual precommit absolute MDD gate, the inherited-parent relative MDD limit, and closed trade minimum, according to the costed S2 audits. There was no backtest gain automatically guaranteed by this screen.

Historical P1 comparison on the *same first five generation slots* (different decisions/trials, not equal candidate budget):

| Same G453–457 slots | P1 mixed without parent risk | P1 parent selection risk-only | P2 parent + child precommit |
|---|---:|---:|---:|
| Average development return | +36.615% | +66.934% | +60.747% |
| Average development MDD | 33.403% | 30.130% | **25.402%** |
| Count of MDD>30% | 3/5 | 2/5 | **0/5** |

**Interpretation:** Mechanically effective, economically unproven. Results are selected on exactly the same historical sample and are subject to severe selection bias. Different numbers of candidate trials also invalidate claims of budget-normalized alpha or future risk suppression.

## Next engineering and scientific gates
1. **Data-driven algorithm proposals rather than simply reordering old enumerated rules.** P3 should connect actual separately logged GPT model inference to signed rejection evidence, with a constrained StrategyIR compiler and measured cost/quality, explicit policy approval and real post-generation proof. Do not conflate current deterministic feedback with model autonomy.
2. Enforce fixed **candidate evaluation budgets**, not just equal completed generations; report diversity and scarcity, and use multiple seeds and PIT-aware walk-forward splits.
3. Compare approved-but-unseen prospective OOS data, not the repeatedly reused 2020–2025 development nor already inspected 2026 holdout.
4. Improve SQLite storage reliability on shared filesystems (local scratch for temporary clone databases, WAL life-cycle discipline, integrity after resume).
5. Expand regime-specific exit, risk allocation and dynamic structure only with causal data/replay tests; do not overstate current fixed P2 policy.

## Durable final evidence snapshot

The /tmp recovery file is not the only surviving copy. To avoid loss of the actual research proof, `scripts/persist_p2_realistic_clone_snapshot.py` used SQLite online backup to copy all three **fully committed G457** clone databases and all candidate attempt logs into the ignored operational state directory `state/moon-http/fresh-20261021/p2-precommit-realistic-5gen-20261021/final-clone-snapshot/`. It validated `457` linked generations, the unchanged G452 source head, `457` stored S7 reports, all `12` signed precommit rejections, and SQLite full integrity checks.

Final clone manifest hash: `f716d567a49482823fd213444ede1d1eae18f9a288e468e385e0cd01b20f2267`. Original research remains `G452/452`. Neither cloned research database nor large data/log payload is committed to GitHub; only the verified scripts and result documentation are committed.
