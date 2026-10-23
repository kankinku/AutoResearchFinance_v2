# Quant V3 G452-origin real parent crossover: ledger-bound audit and economic dedup (2026-10-23 KST)

## State: PARTIAL development gate implemented; NOT counted generation promotion

This change is a **development-only trust-boundary and six experimental combinations**, not 100 autonomous GPT generations, independent out-of-sample alpha, or deployable live trading. Original G452/G552 checkpoints, fixed OAuth registration, dashboard and order OFF remain unchanged. The source research dataset is the *same reused* QQQ daily development window **1,508 bars (2020-01-02 to 2025-12-31)**; it has been repeatedly fitted, so these returns are not independent proof.

### Changes

- `research/llm/ledger_donors_v3.py` introduces `checkout_counted_donors(service,session_id,(...))`: rehash/replay the complete saved academic generation lineage through `AcademicMCPCheckpointService._state`, verify each source's bound S7 gateway report and source evidence SHA, reconstruct original `inherited_strategy_ir` and recompute exact costed S2 audit/return/MDD/trade count before returning `VerifiedDonor` and actual compiled replay. The caller must **construct the service on a temporary database clone**; examples demonstrate isolation. Not a general direct reader of production DB, and there is still no independent third-party external attestation.
- `scripts/verify_v3_real_counted_donors.py` makes SQLite-backup-based ephemeral copies of the G452 lineage and runs **all 3! = 6 C entry/exit/risk permutations** for actual counted parent sources **G68, G192, G248**. It records per-variant exact S2 trace hash, costed equity, MDD, closed trades, fixed P2 risk budget (MDD<=30%, parent MDD rise<=15 percentage points, >=30 closed trades) AND an exact economic-duplicate check against parents.
- `research/llm/composite_validation_v3.py` now **rejects a structurally new but economically identical crossover child** even if its P2 review passes: the complete (equity_curve_hash, actual costed fill list) must differ from every verified donor. This is stricter than comparing rounded total return and drawdown. Added a red/green regression test in `tests/research/test_v3_composite_development.py`. Reworked old small fixtures to ensure the expected passing child is genuinely distinct; earlier identical-child fixture was misleading.
- `scripts/verify_v3_real_s7.py` runs a single **SCRIPTED** S7 close-threshold ablation for the development candidate and checks that the post-dedup validation rightly rejects promotion. Its observed S7 result was **NO_OBSERVED_EFFECT** (same final equity and drawdown).
- `scripts/verify_v3_ledger_integrity_fail_closed.py`: changes a generation evidence JSON or S7 gateway report JSON **only in disposable database copies**; both fail closed, respectively `broken generation hash chain` and `controlled experiment record integrity mismatch`.

### Actual outcomes (reused development bars)

Counted original parent returns / MDD / closed trades:
- G68 **+60.68% / 15.95% / 35**;
- G192 **+168.37% / 26.04% / 36**;
- G248 **+170.20% / 33.48% / 36** (fails default MDD30).

The six roles permutations:

| Entry / Exit / Risk donors | Return | MDD | Closed trades | P2 risk | Economic finding |
|---|---:|---:|---:|---|---|
| G68 / G192 / G248 | +118.48% | 19.53% | 18 | **Fail** (closed-trades) | differs from each source parent |
| G68 / G248 / G192 | +118.48% | 19.53% | 18 | **Fail** (closed-trades) | same economic result as another permutation |
| G192 / G68 / G248 | +74.67% | 36.94% | 127 | **Fail** (MDD) | differs from each source parent |
| G192 / G248 / G68 | +168.37% | 26.04% | 36 | P2 passes | **Exactly duplicates G192 original** → no promotion |
| G248 / G68 / G192 | +42.38% | 39.74% | 150 | **Fail** (MDD) | differs from each source parent |
| G248 / G192 / G68 | +170.20% | 33.48% | 36 | **Fail** (MDD) | exactly duplicates G248 original |

**Totals:** 6 canonical audited combinations, 1/6 superficially passes risk, **0/6 passes both risk + economic novelty**. Therefore **zero new promoted strategies**, and no claim of performance improvement. Historical counted risk donors all use `position_size_pct=100`, so this six-way result mostly measures entry/exit permutations and DOES NOT demonstrate superior risk parameter donor genetics. This is *important negative evidence* about the research engine's false novelty risk.

### Verification and operational limits
- Original G452 rows=452, final SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`, integrity_check=ok; original isolated G552/552 final SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`, integrity_check=ok.
- S7 experiment on the apparently best child had `NO_OBSERVED_EFFECT`: unchanged equity and MDD; scripted, **0 GPT model calls**.
- No original checkpoint was updated, no OAuth/Moon/dashboard changes, no API charges, no trading.
- Guard only de-duplicates against checked donor sources; full archive/global prior candidate fill-fingerprint registry for each experiment family remains **future integration work**. It does not treat distinct source hashes as automatically different performance.
- **The official counted checkpoint service does NOT yet ingest V3 composite `parent_set`, multi-parent S2/S7 results, regime shared NAV nor promote them.** Implementation of this new, versioned append-only V3 sidecar and 10-gen actual model-provenance controlled trials is the next gate. Do not imply it is done.

### Repeatable scripts (no side effects to original)
```bash
PYTHONPATH=. .venv/bin/python scripts/verify_v3_real_counted_donors.py
PYTHONPATH=. .venv/bin/python scripts/verify_v3_real_s7.py
PYTHONPATH=. .venv/bin/python scripts/verify_v3_ledger_integrity_fail_closed.py
```
Each script writes only new, ignored analysis JSON (the first two scripts forbid overwriting an earlier result) or disposable SQLite databases. Research results are saved in `state/moon-http/quant-moon-bounded-100-20261023/` as provenance artifacts; no broker or sealed OOS.

### Next gate
1. Add data-versioned V3 multi-parent sidecar records (donor component lineage, S2/P2/S7 proof hash, economic dedup hash, child evaluation) with one-shot atomic transaction/idempotent resume — **without rewriting existing G452/G552 and without mislabeling it a counted GPT generation**.
2. Apply C+D combined route portfolio on same 1,508 bars with independent NAV/route attribution and carry the selected regime into the origin evidence; shared capital must be audited before attempted promotion.
3. Only then run risk-budgeted 10-generation side-by-side deterministic vs *independently evidenced actual GPT-authored* research with real model receipts, followed by separate approved PIT/OOS. Previous historical dataset is not virgin OOS.
