# Quant Autoresearch — unreferenced adjusted-price event inventory (2026-10-15)

## Actual managed QQQ result (read-only)

The two preserved Tiingo QQQ daily 2020-01-02 through 2025-12-31 development datasets (raw versus total-return-adjusted; 1,508 trading rows) were read without modification. An adjustment candidate is detected when day-on-day change in adjusted/raw closing-price factor, expressed as equivalent amount per current raw share, is at least $0.01. This is a screening threshold, not a corporate-action detection guarantee.

- 25 material candidate close-factor changes across this dataset.
- 7 events independently cross-checked against selected issuer Invesco cash distribution amounts; all 7 issuer cash amounts match vendor adjustment within $0.0001.
- 18 additional candidate factor-change dates have no support from the seven issuer checkpoints. These are not proven dividends: stock splits, vendor corrections or special events may also change factors.
- 2023-12-27 is among these unverified events and warrants additional independent inquiry.
- Published date examples are capped at 24, while the full count is retained. Very small factor noise below one cent per share is ignored.

## Implementation

research/indicator_engine/issuer_distributions.py inventories all material factor changes on aligned same-vendor QQQ raw/adjusted development bars. It reports detected_adjustment_events, unreferenced_adjustment_events and unreferenced_adjustment_dates. MarketDataAuditService.audit now adds the blocker unreferenced_corporate_action_adjustment_candidates if any remain. Existing issuer result PARTIAL_ISSUER_DISTRIBUTIONS_MATCH still means selected events only.

## Limitations and next work

These adjusted/raw files share a source and are latest-revised, not independently historical PIT. Unchecked ex-dividend events, splits, adjustments under one cent per share, and past market-data vintages cannot be certified. Status remains RESEARCH_ONLY_NOT_PIT_VERIFIED; price PIT verification and all-corporate-action verification stay false; no orders are enabled. Next: acquire separately timestamped historical price vintages; independently verify the full issuer/custodian corporate-action schedule; test robust performance on unseen periods. The existing MCP URL, OAuth registration and preserved snapshots are unchanged.
