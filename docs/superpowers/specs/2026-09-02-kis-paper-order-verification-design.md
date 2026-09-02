# KIS Paper Order Verification Design

## Goal

Add a separately permissioned KIS paper-order path that can submit one US-stock order, verify the resulting fill, submit the matching exit order, and prove the final position is flat without exposing an order tool to research or Codex MCP.

## Scope and fixed assumptions

- Paper account only; the configured base URL must be the KIS virtual-trading host and `PaperKISConfig.mode` must be `paper` or `demo`.
- The first smoke test uses QQQ, one whole share, NASD, and market orders.
- The buy is submitted first. The sell is submitted only for the actually filled buy quantity; an unfilled buy is never followed by a sell.
- The smoke test is an explicit CLI operation, not part of autoresearch, dashboard refresh, MCP, or unattended loops.
- Live credentials, live base URLs, live TR IDs, arbitrary symbols, fractional quantities, and persistent order enablement are rejected.

## Architecture

`KISPaperClient` remains read-only. A new `KISPaperOrderClient` composes it and owns only paper order operations. It uses the official overseas-stock order endpoint and paper TR IDs, and a read-only fill query (`VTTS3035R`) to determine filled quantity. A `paper-order-smoke` CLI command performs the bounded buy/fill/sell/flat sequence and emits sanitized JSON; it does not alter `state/mode.json` or the research MCP surface.

## Data flow

1. Load `.env` through `PaperKISConfig.from_env` and reject non-paper configuration, missing account, invalid product code, or non-virtual KIS host.
2. Fetch a quote only for evidence and display; submit a market buy with `OVRS_ORD_UNPR=0`.
3. Poll paper order executions for a bounded timeout using today’s date and the required paper query parameters.
4. If the filled quantity is positive, submit a market sell for that exact quantity.
5. Poll executions and account holdings until the QQQ position is flat or the timeout expires.
6. Return a structured result with no secret, full account number, token, or raw payload.

## Failure handling

- Token, account inquiry, order, execution query, or final-flat verification failures stop the sequence and state exactly whether a buy or sell request was sent.
- A buy request accepted but not filled leaves no sell request and is reported as `BUY_NOT_FILLED`.
- A sell failure reports the filled buy quantity and requires manual reconciliation; it never retries automatically.
- HTTP/API errors are retained as status code plus KIS message code only; secrets and raw response bodies are excluded.

## Testing and verification

- Unit tests use a fake transport to assert paper TR IDs, endpoint, uppercase request body, market-order fields, fill parsing, exact sell quantity, and live-mode rejection.
- CLI tests assert the command is opt-in and does not enable live orders or alter the research MCP tool list.
- Before any real request: `python -m pytest -q`, `ruff check .`, `python -m mypy .`, and `git diff --check` must pass.
- The live smoke run is performed once, only after the local checks pass, and is followed by a sanitized result and workspace status report.
