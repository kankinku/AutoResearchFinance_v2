# Quant Autoresearch — QQQ split and revision residual screen (2026-10-15)

## Measured, research-only result

The unmodified managed Tiingo QQQ 2020-01-02—2025-12-31 DEVELOPMENT raw/total-return-adjusted pair (1,508 aligned daily bars) was checked. Adjacent day changes in adjusted/raw closing-price factor were expressed in cash-equivalent USD per share and **25 issuer-referenced cash distributions** subtracted. A residual >= $0.01/share on a non-cash date becomes an unexplained split/revision candidate, not a proven split.

Measured **25 issuer cash dates matched, zero material unexplained adjustment events**, maximal absolute residual **1.02e-10 USD/share** (floating-point noise). This is an internal consistency result and cannot rule out small events, revised historical prices, or corporate actions missing from source data.

## Split catalog provenance and scope

Two different secondary market-data directories list one historical QQQ split, March 20, 2000, 2-for-1, and no listed split in 2020–2025:

- https://twelvedata.com/markets/958673/etf/nasdaq/qqq/historical-data/splits
- https://swingtradebot.com/equities/QQQ/splits

The source claims are pinned in research/indicator_engine/qqq_split_history_secondary_v1.json (SHA-256 7282cc697081ce1861688acd3c1fad373db79c4bf44d37e341b525a6f6473a45) with evidence class SECONDARY_AGGREGATOR_ONLY. They are **not primary issuer/exchange/custodian proof** or archived historical publication dates.

Tiingo documents splitFactor, divCash and raw/adjusted OHLCV: https://www.tiingo.com/documentation/end-of-day. The two stored files do **not** retain independently timestamped corporate-action publication revisions or an authoritative primary full split-event inventory.

## Implementation

research/indicator_engine/qqq_split_residual_audit.py validates the pinned secondary history and computes a conservative cash-factor residual report, distinguishing missing issuer dates, mismatched issuer amounts, unknown adjustment events and non-comparable sources. application/market_data_audit.py optionally adds qqq_split_adjustment_residuals and specific blockers: unexplained_split_or_adjustment_candidates, split_residual_reconciliation_incomplete, and always independent_primary_split_history_missing. The original issuer v1 and v2 references are unchanged.

Existing MCP resource URL/OAuth/session, stored raw data, sealed core and trading permissions were unchanged. No deployment. Persist RESEARCH_ONLY_NOT_PIT_VERIFIED and non-executable reporting. Independent_historical_as_of_snapshots_missing, corporate_action_adjustment_unverified, revisions_not_as_of and no broker order continue.

## Next gate

Acquire exchange/issuer/custodian primary split archive and genuinely historical as-of/vintage raw OHLCV with provable publication timestamps. Reconcile corporate-action release times without retroactive adjusted prices before any PIT or separate sealed OOS assessment.
