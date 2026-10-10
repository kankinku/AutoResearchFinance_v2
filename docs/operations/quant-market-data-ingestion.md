# Quant market data ingestion (2026-10-10)

This is a **read-only, development-only** EOD data ingestion boundary. It neither
calls a broker order API nor changes production Champion/Frontier on ingestion.

## ChatGPT MCP flow

1. Call `list_market_data`. It shows available providers and immutable local
   `data_path` values, never provider keys or raw rows.
2. To explicitly download a supported US stock/ETF, call
   `download_market_data` with `provider` (`tiingo` or `kis`),
   uppercase `symbol`, ISO `start`, `end`, and optional
   `price_policy` (`raw` or `total_return_adjusted`). No scheduled or
   automatic data download occurs.
3. Call `validate_market_data` for the returned exact `data_path`.
   `get_research_brief.research_inputs.data_paths` also lists it.
4. Supply that exact path plus normalized strategy path and matching
   ResearchIntent parent ID to `start_research_batch`. Data ingestion itself
   does not approve an OOS result or initiate a research batch.

New data lands under
`data/market/<provider>/<SYMBOL>_<START>_<END>_<policy>.parquet`, immutable
on repeated requests (a matching path is never silently overwritten).
The stored dataset has `zone=development` and vendor-declared lineage.
Data is never labeled independently PIT verified: splits, dividends,
survivorship, calendars, and source revisions require independent checks.
For price adjustment, Tiingo's adjusted OHLCV is treated as
`total_return_adjusted` per its documented EOD fields; KIS currently supports
raw prices only. Mixing raw and dividend-adjusted data can misstate strategy
returns. Price universes consisting of one ticker are not a survivorship-free
multi-stock universe.

A basic fail-closed completeness gate rejects historical queries whose first
or last observations are more than 8 calendar days from the requested bounds,
without fabricating missing exchange sessions. KIS's currently bounded
single-response dailyprice query is only suitable for limited ranges; longer
requests should fail rather than silently pass as complete.

## Source configuration

* **Tiingo:** Set `TIINGO_API_KEY` in the Quant **server process environment**
  or in the untracked project-root `.env` (create from `.env.example`).
  The key is sent only in a request Authorization header to
  `https://api.tiingo.com/tiingo/daily/.../prices`. Never send keys to ChatGPT.
* **KIS:** Configure read-only paper KIS settings in untracked project-root
  `.env` using `PAPER_KIS_APP_KEY`, `PAPER_KIS_APP_SECRET`,
  `PAPER_KIS_BASE_URL`, and `QUANT_TRADING_MODE=paper`.
  The market-data service uses `KISPaperClient.daily_bars`, **not** order
  adapters. A single API call may be truncated; the completeness gate detects
  most capped long-range queries.
* **OpenBB:** An official separate MCP server exists, but it does not replace
  a configured underlying provider. It is not installed/enabled by this change.
  The ingestion service intentionally supports provider swapping behind one
  internal interface without granting an external MCP broad broker capabilities.

## Actual-data acceptance and repeated-candidate diagnostics

On 2026-10-10, the Tiingo read-only API returned 1,508 raw daily QQQ bars
covering 2020-01-02 through 2025-12-31; the managed development Parquet
round-trip and project-registered `mean_reversion` strategy preflight passed.
This dataset is **not independently point-in-time or corporate-action
verified** and may not be treated as sealed OOS performance evidence.

A real-data one-generation batch (`bd0499db6920402dbbae1c4a1c645b49`)
and fixed-intent five-generation batch (`62fa4863d8464272b0ca80a62e982592`)
both completed, but the latter evaluated one unique rejected candidate five
times. The batch report now exposes `evaluated_candidate_instances`,
`unique_candidate_count`, `duplicate_candidate_evaluations`,
`repeated_candidate_warning` and `promoted_successor_generations`, each
grounded in existing immutable per-attempt candidate Evidence.

To search multiple parameter values in `start_research_batch`, explicitly
provide `parameter_domains`, for example:
```json
[{"name":"indicators.disp_5.period","values":[5,7,10,14]}]
```
Up to 4 approved parameter paths with 24 values each are allowed. A
`method=random` seed can vary candidates between generations, but a small
finite search space may still repeat previously evaluated candidates. A
completed generation is **not** an independently discovered or promoted
strategy. The worker does not independently ask GPT for fresh hypotheses; it
uses the single supplied ResearchIntent for the batch.

Data files under `/data/` are ignored by Git and are never bundled with
source releases. The API key remains in a private local `.env`, not in the
repository, research request, or logs. Deployment operators should rotate
keys that have been shared in chats.

Reference: https://www.tiingo.com/documentation/end-of-day
