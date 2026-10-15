# Quant Autoresearch — issuer dividend checkpoints and future price revision observations (2026-10-15)

## Decision

**7 independently issuer-sourced Invesco QQQ cash distributions exactly match the cash amounts inferred from Tiingo raw and adjusted daily closing prices.** This is a **selected historical dividend cross-check**, not a proof of every dividend, corporate split, as-of price revision or broker-realizable return. Data and strategies remain **RESEARCH_ONLY_NOT_PIT_VERIFIED / NOT_VALIDATED**, and trades are disabled.

## Verified comparison

Tiingo EOD methodology (https://www.tiingo.com/documentation/end-of-day) provides both raw OHLCV and dividend/split-adjusted OHLCV and describes `divCash`, `splitFactor` and CRSP-based adjusted values. Selected source issuer Invesco QQQ fund distributions:
- https://www.invesco.com/us/financial-products/etfs/product-detail?audienceType=investors&productId=QQQ&ticker=QQQ
- https://www.invesco.com/us/financial-products/etfs/product-detail?productId=QQQ&ticker=QQQ

| ex-date | Invesco cash USD/share | Tiingo implied USD/share | Difference |
|---|---:|---:|---:|
| 2020-03-23 | 0.36269 | 0.362690000017 | under 0.0001 |
| 2021-09-20 | 0.41391 | 0.413909999990 | under 0.0001 |
| 2022-03-21 | 0.43369 | 0.433690000051 | under 0.0001 |
| 2024-09-23 | 0.67686 | 0.676859999981 | under 0.0001 |
| 2024-12-23 | 0.83466 | 0.834660000063 | under 0.0001 |
| 2025-03-24 | 0.71571 | 0.715710000024 | under 0.0001 |
| 2025-06-23 | 0.59111 | 0.591110000064 | under 0.0001 |

Calculation for a date with an ordinary cash distribution but no split:
- `f_t = adjusted_close_t / raw_close_t`
- `implied_cash_t = raw_close_t * (f_t / f_previous_close - 1)`

The same-day close adjustment factor exactly recovers Invesco cash figures in all seven selected cases. The formulas assume no split on those selected event dates. Do not apply this simplification to split / special-distribution dates without a separate verified adjustment contract.

Actual immutable evidence: `docs/operations/evidence/quant-validation-20261015/issuer_dividend_spotcheck_results.json`, SHA-256 `327b76a4479bf2e818b9a35a42b797165177008684ff282f21c7acc4cfffad82`.

Source rows retained at `research/indicator_engine/issuer_qqq_dividends_v1.json`, SHA-256 `a8c08715ea0fe6b9e80c6e0cea99c12fba8bbed7d2fd54fffccf817a1bfdd6c4`; the verifier refuses to proceed if this pinned file changes.

## Price collection / revision tracking

`research/indicator_engine/snapshot_revisions.py` compares two **separately collected, managed** datasets with the same vendor, symbol, adjustment policy and 1-day calendar, and explicitly checks that the earlier file's declared retrieval timestamp precedes the later file. It reports how many overlapping daily OHLCV rows changed, date examples, maximum relative difference and both input hashes. Without overlap, the same vendor/policy, or strict chronology it returns a non-comparable status, not a passing verdict.

`MarketDataAuditService.audit(..., revision_comparison_path=...)` is available internally for a future second data snapshot. It is not a new MCP tool and does **not** automatically bypass the current client tool-schema cache. Different dates or source revision policies cannot be silently equated. Because the present 2020–2025 and 2026 files have **no overlapping date range**, no actual vendor price revisions can yet be measured. The revision-difference regression test uses independently constructed fixtures, not live revised prices.

We also pinned the **current four Tiingo managed dataset files** in the existing research snapshot-pin SQLite store at the time of this run. All returned `pin_status=MATCHED`; their contents remain untouched. This means future changes to the present files will be detectable; it does NOT recreate what Tiingo published in 2020, 2024 or 2025. The original files are immutable development-only inputs and must not be silently overwritten to simulate a newer as-of snapshot.

## Failing-closed safeguards

- Only matched DEVELOPMENT raw/total-return-adjusted QQQ datasets from the same declared vendor and identical timestamps are eligible for issuer spot checks. Other symbols/vendors/policies, absent ex-dates and tampered source references cannot pass.
- Additional positive issuer checkpoints alone cannot clear `independent_historical_as_of_snapshots_missing`, `revisions_not_as_of` or `corporate_action_adjustment_unverified` blocking conditions.
- `all_corporate_actions_verified=False`, `point_in_time_price_verified=False`, `broker_executable=False` throughout the new issuer and revision reports.
- The revision scanner's observed retrieval timestamps are **vendor/host metadata**, not independently signed historic publication proofs. A later snapshot that matches earlier is evidence only of no **observed** revision between those snapshots.
- Existing MCP URL, OAuth secrets, research state location and paper-only policy remain unchanged. No order, broker or unaudited price fetch added.

## Remaining required work

1. Acquire a separate, immutable historical market snapshot captured at each relevant past decision time (or a vendor product with independently verifiable vintage records), with trustworthy observation and availability timestamps.
2. Independently reconcile all distributions, splits and adjustment policies—not just the seven inspected Invesco cash events.
3. In a previously unseen period with adequate sample size and completed trades, evaluate risk and opportunity cost against the benchmark without using previously observed QQQ 2026 results as sealed OOS evidence.
4. Keep `NOT_VALIDATED`, `EMPTY` Champion and disabled orders until all independent acceptance gates pass.
