# Quant Autoresearch — issuer cash schedule v2 reconciliation

Date: 2026-10-15. Separate verified historical issuer cash amounts from point-in-time price or stock-split verification.

## Reconciled result — saved development QQQ 2020–2025

Source: existing two unmodified Tiingo QQQ raw/total_return_adjusted datasets, 1,508 aligned trading rows. Material factor-change detector (cash-equivalent threshold $0.01) found 25 events. Pinned issuer cash reference v2 covers 25 event dates, including the December 27, 2023 SPECIAL CASH $0.21584 payment; for all 25 events, adjusted-close factor inversion matched separately published five-decimal source amounts within $0.0001. Unreferenced material factor changes: zero; mismatched amounts: zero; missing issuer event dates: zero.

The prior immutable seven-event v1 reference and corresponding v1 report are retained. v1's 18 unreferenced events remain a correct statement about **v1 evidence**, not about the separate v2 reference. The read-only audit publishes v2 reconciliation independently and removes the obsolete v1-only blocker for the full successfully corroborated 2020–2025 dataset. Remaining blockers: **corporate_action_adjustment_unverified**, **independent_historical_as_of_snapshots_missing**, **revisions_not_as_of**.

## Independent issuer sources and provenance

1. Invesco historical product distributions: https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=investors&productId=QQQ&ticker=QQQ (2020–2024 five-digit cash and event dates, indexed issuer page; the live URL may redirect and is not an immutable historical publication snapshot).
2. OCC memo #53849 dated December 26, 2023: https://infomemo.theocc.com/infomemos?number=53849 (the 2023-12-27 special distribution ex-date and $0.21584 payment, explicitly categorized as SPECIAL CASH).
3. Invesco official June 2026 QQQ Trust distribution composition (2025 quarterly per-share cash): https://www.invesco.com/content/dam/invesco/hk/zh/pdf/INV-Composition-of-dividend-payments-Invesco-QQQ-ETF.pdf (2025 Q1 0.71571, Q2 0.59111, Q3 0.69395, Q4 0.79408). Ex-dates for Q3/Q4 are independently listed at https://www.aastocks.com/en/usq/analysis/dividend.aspx?symbol=QQQ and https://www.slickcharts.com/symbol/QQQ/dividend, but the Invesco quarterly PDF alone does not establish those exact ex-dates.

The checked v2 source file is JSON pinned by SHA-256 **c3afbcf1ec20a14202a3ec2656c0b55dc5fc185320d7527210b3887074d2ca83**; any tampering fails closed. Source date, type (regular vs special), and reference ID are explicit.

## Guarantees and exclusions

The new check is a mathematical **reconciliation of historical/latest issuer cash amounts**, not a guarantee of split inventory completeness, fully independent point-in-time market prices, vendor revisions, trade execution, or profit. Factor-change detection has a $0.01 per-share threshold, so smaller events could be missed. Both price series derive from the same vendor; issuer records do not prove past price vintages. All audit responses remain RESEARCH_ONLY_NOT_PIT_VERIFIED; all_corporate_actions_verified, point_in_time_price_verified and broker_executable remain false. The existing MCP URL/OAuth/session and all research state remain unchanged; no production deployment of this code yet.

## Next gate

Get independently timestamped historical/as-of raw OHLCV releases and explicit split-event history with custody/exchange/issuer evidence, then only consider independent unseen periods with sufficient trades. Sealed OOS and real orders remain out of scope.
