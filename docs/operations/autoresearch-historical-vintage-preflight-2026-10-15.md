# Quant Autoresearch — historical vintage decision-time preflight (2026-10-15)

## Outcome: timestamp screening, NOT historical PIT certification

A new read-only historical vintage preflight distinguishes a historical decision's timestamp from the date an entire price snapshot was collected. A snapshot downloaded in October 2026 cannot independently attest to the raw prices, corporate-action revisions, and data availability that existed at a past 2025 or September 2026 decision. A vendor's revision_policy=as_of text and SHA-256 file pin are not substitutes for independently authenticated historical provider release records.

The conservative US-equity daily rule treats a UTC-midnight bar as a trading-session date label, not an already-completed daily bar. Its session passes the assumed regular 16:00 America/New_York close only when the historical decision occurs strictly afterward. Time-zone/DST shifts are applied. The rule intentionally treats early-closing sessions conservatively and does not assume immediate price-provider publication at the close. The report exposes count of sessions_past_assumed_close versus unfinished_or_future_sessions, and flags retroactive capture, latest revisions, and missing independent attestation separately. Invalid daily labels, missing timestamps, non-development zones and untrustworthy inputs fail closed.

## Actual preserved Tiingo DEVELOPMENT samples, read-only

The preflight was measured with the cutoff immediately after the final covered market day and the saved unmodified managed market files:

| sample | Bars | Assumed-closed sessions | Snapshot collected after that period | Result |
|---|---:|---:|---|---|
| QQQ 2020–2025 | 1,508 | 1,508 | Yes, collected 2026-10-10 UTC | CUTOFF_CONFLICT |
| QQQ January–September 2026 | 187 | 187 | Yes, collected 2026-10-15 UTC | CUTOFF_CONFLICT |
| SPY 2020–2025 | 1,508 | 1,508 | Yes, collected 2026-10-15 UTC | CUTOFF_CONFLICT |

All samples are latest-revised, so even a cutoff after the final regular-session close cannot clear independent_publication_attestation_missing. No stored sample is an independently signed historical vintage. This does NOT imply that a trader could not see some prices at the original time; it means the retained files do not prove the contemporaneously available values.

## Change and limits

- research/indicator_engine/historical_vintage_preflight.py is a pure, read-only decision-time screening module.
- Existing MarketDataAuditService.audit retains prior fields and adds an optional, internal as_of_decision_at parameter and historical_vintage_preflight report with detailed blockers. No new MCP tool schema, endpoint, key or registration is required for this code.
- Independently verified point-in-time status, Champion promotion and trading remain false/disabled. All existing source pins, sealed OOS and model research records remain untouched.
- Next: obtain true vendor historical/as-of raw OHLCV release vintages with independently auditable publisher availability timestamps and origin integrity, then reconcile by original decision time before separate sealed OOS evaluation.

No current deployment of this development branch.
