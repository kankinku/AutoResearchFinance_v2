# Quant V3.0 — Release checkpoint · 2026-10-27 KST

**Release ID:** `quant-v3.0.0` · **Release branch:** `main` · **Frozen predecessor:** `cda8e7695ea9d941cb94addea71d4fd397d8978a`.

## Exactly what is frozen

- Working source from the original Quant operational branch `fix/quant-g100-to-g150-continuation-20261027`, including stable ChatGPT MCP academic checkpoint compression, chart-first research dashboard, existing StrategyIR, typed parent evolution/S7, governance and 150-generation analysis.
- Original academic GPT research session `14626d55fb2b461faa485df911920071`: **150/150 COMPLETED**, evidence chain from G1–G150, 150 S7 report records, final evidence hash `23925180a3664a669773f515d65cffa0607b6189cdfd59fcbff05b9864ab814d`. Data hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e`.
- Study results: G94 top reused-development +206.81% / MDD22.67% / 35 trades. QQQ price-only, transaction-costed comparator +187.77%; PIT/independent holdout profitability not demonstrated. `docs/operations/quant-150-generation-comprehensive-review-20261027.md` and `quant-150-generation-s7-audit-20261027.csv` are the audit summary and complete tabulation.
- This **product V3 checkpoint label is not a claim that all Q01–Q20 requirements or V01–V07 release gates have passed**. The Python package in `pyproject.toml` is not being re-versioned, and no operating service is auto-deployed by a Git tag.
- Existing fixed Quant MCP URL, OAuth issuer/client identity, live paper-only mode, sealed OOS, protected core and existing research/session history are unchanged.

## Private canonical research-state backup

Three SQLite files were copied using read-only source connections and SQLite online backup into the *existing production Quant workspace's* private operator backup folder:

`state/moon-http/operator-backups/quant-v3-checkpoint-20261027/` (**outside Git**, permissions directory 0700, SQLite files 0600).

| File | Bytes | SHA-256 |
|---|---:|---|
| `cycles.sqlite` | 1,736,704 | `786e45b6542f101cc9488f4a9a28af56199b2eb141112647bb636b53b2335e84` |
| `gateway.sqlite` | 2,334,720 | `1c4903e5e57167c490ace927cc443ce53ea39a55f44a6d4535e7dcf3f1965232` |
| `catalog-s6-v2.sqlite` | 53,248 | `478fe89ca8c3a9daf8f61f83a7b3118f52c716ef61527ed92abcd42e280e2de1` |

Backup integrity tests: **3/3 `PRAGMA integrity_check=ok`**, `cycles.sessions` 150/150 COMPLETED and G150 evidence head verified, `gateway.experiment_reports` 150. Source databases, OAuth database/key and trading settings were not modified. Do not add SQLite backups, source market data, credentials or logs to Git. Code tag alone does not restore mutable academic research state.

## Branch topology

The GitHub repository **had no `main` branch** when this checkpoint was requested. Its existing default branch was `master` and the released Quant research history was divergent from that older branch (no common merge base in the inspected local repository). Rather than silently merge unrelated histories or force-update `master`, create **new `main` from the V3 frozen predecessor**, then tag V3 and branch three independent research lanes from that exact checkpoint.

- `main`: versioned V3 baseline; no experimental code or independent validation results.
- `research/v3-strategy-evolution`: Track 1, continue typed genetic/LLM strategy discovery after G150 without deleting parent memory.
- `research/v3-event-detection`: Track 2, separately identify drawdown/crash, reversals, volatility spikes with precision/recall, alert lead time and false alarm costs; event-level split, no lookahead.
- `validation/v3-independent-oos`: Track 3, frozen candidates G94/G106/G96/G60 and independently held-out data only. No iterative training on test outcomes.

All three branches must originate from the **V3 tag**, maintain their own planned scope and immutable evidence chain, and propose promotion back to `main` only through reviewed changes. Never merge Track 3's sealed test data into Track 1 or Track 2.

## Operational checks and boundaries

A Git tag is a reproducible **code** pointer; the backed-up SQLite snapshot and these stored content hashes are a **research data** recovery anchor. This operation must not restart services, replace the live runtime checkout, edit live session counters, change OAuth/pinned MCP URL, approve orders or unlock independent OOS.

V3 checkpoint checks: clean release worktree before edits; manifest/database consistency, governance tests, modified-source static checks, Git tag targets a unique immutable release commit, and all three branches share the same base. Report the outcome of checks accurately and distinguish baseline snapshot from live deployment.

Prior full repository MyPy/Pytest failures in the former workspace remain unresolved and are **not implied to pass** because this snapshot is tagged.
