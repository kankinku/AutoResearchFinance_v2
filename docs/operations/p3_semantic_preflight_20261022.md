# P3 Semantic Preflight — Development-only signal equivalence and scalar subsumption

**2026-10-22 · branch `feat/quant-parent-portfolio-20261021`**

## Goal and scope

Reject provably redundant or development-signal-identical inherited strategy
mutations before the expensive *new child* costed S2 backtest, P2 precommit
risk gate or counted-generation registration. In the prior model-authored G453
research attempt, S7 discovered an OR-exit subset (`vote<=0.25` inside
`vote<=0.5`) with **NO_OBSERVED_EFFECT** only *after* counted commitment.
This new preflight moves the semantic check to planning.

It is completely opt-in: `AcademicMCPCheckpointService(
p3_semantic_preflight=True, parent_portfolio_v2=True, ...)`. Explicit
`--p3-inherited` foreground API research configuration activates it;
**the default MCP, P1, P2, canonical StrategyIR, and the original research
evidence remain unchanged**. No OAuth/MCP re-registration, paid model call or
trade order.

## Two independently named checks

1. **`PROVABLE_CONDITION_SUBSUMPTION`**: conservative threshold
   implication for one *appended* scalar condition, unchanged other entry/
   exit/regime/features/risk, and AND/OR semantics. Examples:
   `EMA<=0.25` added to `EMA<=0.5 OR ...` is redundant;
   `EMA>0.75` AND an added `EMA>0.5` is redundant. Strict/non-strict
   bounds and equality are handled explicitly, never approximated.
   Unsupported aliases or cross-reference predicates are **not** asserted to
   be symbolically equivalent.
2. **`DEVELOPMENT_SIGNAL_EQUIVALENCE`**: derive evaluated parent and
   child entry, exit, regime gate booleans for **all 1,508 development bars**
   from the existing compiled, replay-verified feature values. If none
   differ and risk policy matches, reject as **sampled equality only**.
   This is NOT a universal or independent OOS conclusion. If risk/position
   size changed, equal gates alone do not justify rejection.
   Any observed signal change is allowed to continue into full costed audit
   and strict P2 child risk budget; the preflight does not predict profits.

Both checks record parent/child signal digests, first differing indices,
number of signal differences, compiled strategy hashes, dataset hash and
a structured reason. Rejected candidates are never registered in immutable
counted generations.

## Evidence and retry

Rejected semantic proposals append to opt-in `gateway.sqlite` sidecar table
`p3_semantic_rejections`, uniquely keyed by session/generation/request hash.
The JSON receipt is content-hashed and bound to the checkpoint token,
selected parent, original evidence, dataset and exact typed operations.
Repeated identical submissions are idempotent. Gateway `get` validates
stored receipts and emits `p3_semantic_rejection_feedback` with a digest and
recent rejected operations; invalid identity or hash fails closed.

Model runner treats `P3_SEMANTIC_PREFLIGHT_REJECTED` as a bounded,
retryable *planning* failure: no stage transition, planning token consumed or
generation committed, and the next model request includes the verifiable
failure reason. It never relaxes the P2 risk budget or silently falls back
to deterministic searches.

## Tests and clone E2E

- `tests/research/test_p3_semantic_preflight.py`: strict/non-strict
  implication boundaries, true and false subset cases, sampled equality on
  binary signal values, sampled non-equivalence on fractional values, and
  same-signals/different-risk nonrejection.
- `tests/research/test_p3_inherited_loop.py`: semantic-rejected proposal
  returns to the model with the rejection details and the model submits a
  distinct proposal within its unchanged attempt budget.
- `scripts/test_p3_semantic_clone_e2e.py`: isolate G452 by SQLite backup,
  select verified G68 parent with P1/P2 child MDD<=30%, delta<=15pp,
  trades>=30, and explicitly enable P3 semantic preflight.

Clone sequence, exactly as executed:

| Proposal | Result | Committed? |
|---|---|---|
| Add EMA<=0.25 to existing OR-exit EMA<=0.5 | `PROVABLE_CONDITION_SUBSUMPTION` | NO |
| Add EMA<=0.75 to OR-exit EMA<=0.5 (EMA direction sampled 0/1) | `DEVELOPMENT_SIGNAL_EQUIVALENCE` | NO |
| Add vote_score<=0.5 to existing EMA OR-exit | Different gate signal; passes P2 child risk | YES, G453 |

The clone verified two durable, hash-correct rejections; re-submitting
each does not duplicate receipts or change the planning checkpoint token.
The third proposal generated G453 on the copied dataset, full costed
backtest and S7. Child development return +9.6870%, MDD 23.9916%;
economics **worse** than parent G68 (+60.6753%, MDD 15.9543%). All three
clone DBs pass integrity checks; original academic evidence still **452/452**.
The E2E exercises predetermined fixture mutations, **not** independent GPT
model inference or new alpha research. Source 2020–2025 development was
previously reused; inspected 2026 holdout is not used for OOS claims.

## Limitations / next

- The symbolic simplifier handles simple scalar thresholds only; does not
  handle arbitrary indicator expressions, mixed feature sources, generalized
  Boolean equivalence, or regime-specific exits.
- Sampled gate equality can occur by coincidence and says nothing about
  unseen regimes; strategy families with different risk allocation aren't
  screened out on gate equality alone.
- No prospective PIT OOS validation. P3's full autonomous LLM generative
  discovery remains unproven; the current demonstration is functional.
- For future work: equivalence fingerprints across a new fixed validation
  regime and a restricted expression DSL with compiler-time proof obligations.
