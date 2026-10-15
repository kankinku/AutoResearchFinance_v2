# Stage 1-1: Daily idempotent QQQ archive collection — 2026-10-15

## Real Moon collection evidence

- Scope: Nasdaq QQQ public historical latest-revision daily OHLCV, 2020-01-02 to 2025-12-31.
- Existing Moon captures: 2026-10-15 11:09:47Z and 11:15:44Z, 1,508 rows each.
- New live capture: 2026-10-15 **13:55:09Z**, 1,508 rows, raw SHA256 `6ede5c3b5b9926b9d820268aa607b41c3c0cfe60141a0ace13302a42f7193f40`, replay capture hash `9c7aac93b58daf2cc50f9f7c0a1290d8f0c36a7883eff0384a6bc9466c2330b7`.
- All three captures are on **one UTC calendar date**. They do not demonstrate a multi-day vendor revision record, independent publication timestamps, or historical PIT.

## New opt-in collection command

```bash
.venv/bin/python -m research.indicator_engine.cli collect-nasdaq-qqq-daily \
  --from-date 2020-01-02 --to-date 2025-12-31 --archive-root state/vintages
```

The command takes an advisory lock, replays the entire existing collection before deciding whether to fetch, and skips network requests if that UTC date was already captured. If the prior archive is modified/corrupt, it stops instead of silently collecting into a damaged evidence chain. A new-day collection uses the existing exclusive append-only writer and audits the full archive again before returning `NEW_CAPTURE_VERIFIED`; repeated same-day requests return `ALREADY_COLLECTED_TODAY` (both results remain NON-PIT). An upstream fetch failure can be retried later on that date, without overwriting previous captures. No periodic background job is installed by this change.

The command is intended for opt-in operator execution and does not modify the existing ChatGPT 2026-10-16 one-time follow-up. On Windows, if the required Unix advisory locking primitives are unavailable, it fails safely; Moon's Linux runtime supports them.

## Remaining blockers

1. Obtain real captures on distinct UTC collection dates, then run `audit-nasdaq-archive` and compare revised bars.
2. Prove independent issuer/vendor historical publication timestamps and corporate action factors separately; local collection timestamps are insufficient.
3. Do not promote to sealed OOS, historical PIT, or live trading on the strength of these source snapshots.

This work is in a research branch only, with no change to the registered ChatGPT MCP endpoint, OAuth or live deployment.
