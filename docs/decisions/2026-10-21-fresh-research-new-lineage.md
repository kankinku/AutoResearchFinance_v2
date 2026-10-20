# User-authorized new Quant research lineage — 2026-10-21 KST

## Decision

The user's latest instruction **"그럼 처음부터 시작해 연구를"** after repeated failures to recover G350 operational state authorizes **a genuinely separate research lineage beginning at G1**. The previous goal of 500 total official research generations remains the intended target for the new study, but the former **G350 history is never reclassified as part of the new lineage, deleted, or overwritten**.

- Existing original T4 session `72495cc59fc147e08f4b433b98676fca` and last historically documented G350 are **unavailable as operational checkpoints**. Their GitHub reports and hashes are preserved.
- New isolated Git worktree/branch: `feat/quant-fresh-research-20261021`, separate from `feat/quant-same-session-350-20261019`.
- Separate ignored local data and academic checkpoint storage. Original fixed MCP URL and OAuth (currently unavailable), persistent credentials, prior state path, protected backtest/evaluator/integrity, sealed OOS and trading permission are **not modified**.
- Reuse the original `AcademicMCPCheckpointService` and typed StrategyIR canonical next-open engine. New human-facing ChatGPT GPT-authored plan and diagnostic submissions are executed via Moon's local Python runner, **not** via a restored authenticated Quant MCP client. Therefore `real_model_connection_verified=false`, `model_autonomy_verified=false`, and unattended continuation is **not established**.
- Development QQQ data acquisition may use a distinct openly available, publisher-claimed Yahoo-derived raw OHLCV source after its source checksum, row coverage, provenance and exact Parquet dataset hash are persisted. Do not label it the original Tiingo snapshot, official PIT data, independently certified vendor pricing or sealed OOS.
- New formal generation definition remains GPT-authored typed candidate → canonical costed backtest/trades → observation-grounded GPT diagnosis and next typed hypothesis → actual S7 controlled counterfactual → immutable Evidence hash and parent/successor eligibility. New lineage counts are separate.
- The new study's **G500** is a research target, not a promise of profitability or background auto-execution. The first completed local demonstration is G1–G2, **2/500**, with actual G2 inherited typed parent, reported independently of legacy G350.

## Frozen product contract

The original 20Q `Q01–Q20`, `V05 → T4 → V01–V04 → V06 → V07`, no live orders, no sealed OOS, no weakening costs/risk gates and no claiming independent OOS/net alpha from repeated development prices remain unchanged. Independent random baseline, PIT release timestamps, full T4 long-session authenticated bridge and valid paper-only GO/NO-GO gates are still outstanding.

## Next step

Validate recovered or newly deployed **separate** authenticated API without rotating/re-registering original Quant URL. Advance the current verified new lineage checkpoint with explicit fresh GPT input, never replay old checkpoint tokens or invent completion. The [fresh G1–G2 report](../operations/autoresearch-fresh-g1-g2-2026-10-21.md) is the new lineage's evidence summary; full SQLite Evidence and CSV/Parquet remain ignored, not in Git.
