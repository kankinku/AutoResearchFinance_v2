# Paper Trading Operations Dashboard Design

## Goal

Provide a local, read-only operations dashboard for the paper-only Quant Autoresearch Harness. The dashboard must show the effective trading mode, paper account snapshot, test history, current champion strategy, strategy improvement trend, and parallel worker online state without exposing credentials or enabling live orders.

## Fixed safety boundary

- The effective deployment mode is always `paper` for this phase.
- `live` configuration is rejected by the paper service and no live KIS endpoint is called.
- The dashboard binds to `127.0.0.1` by default.
- Dashboard GET requests read local snapshots; they do not submit orders.
- Paper KIS requests are limited to token, quote, daily bars, account read-only, and order-history APIs.
- Any future paper order command remains a separate explicit action and is not part of dashboard polling.

## Architecture

The KIS client is a small transport-aware adapter that loads only the paper profile from `.env`, obtains and caches an OAuth token, and maps KIS responses into typed snapshots. A dashboard snapshot service combines KIS account/market health with local `state/`, `runs/`, and worker heartbeat artifacts. FastAPI exposes that service through JSON endpoints and serves a static single-page dashboard. The browser polls the read-only snapshot endpoint and never receives secrets or bearer tokens.

```text
KIS paper REST API ──> PaperKISClient ──> DashboardSnapshotService
                                      ├── state/*.json
                                      ├── runs/*/records
                                      └── worker heartbeats
                                                    │
                                      FastAPI 127.0.0.1
                                                    │
                                      static HTML/CSS/JS dashboard
```

## Data contracts

`dashboard/contracts.py` defines JSON-safe immutable records:

- `ModeStatus`: requested mode, effective mode, live enabled flag, last mode change.
- `AccountSnapshot`: account status, masked account, equity, cash, buying power, holdings, open orders, captured time, and error state.
- `TestRecord`: run ID, strategy hash, generation, timestamp, total return, Nasdaq/QQQ excess return, max drawdown, risk compliance, status.
- `StrategySummary`: champion hash/status, family, score, generation, selected feature IDs, and key metrics.
- `TrendPoint`: generation/time, champion score, total return, Nasdaq excess return, and risk state.
- `WorkerStatus`: worker ID, job ID, role, status, last heartbeat, age seconds, online state, attempt, and error.
- `DashboardSnapshot`: schema version, generated time, all sections above, KIS health, and warnings.

All account identifiers are masked before serialization. Raw KIS response bodies, access tokens, app keys, and app secrets never enter state or API responses.

## API

- `GET /` serves the dashboard.
- `GET /api/health` returns process health, paper-only effective mode, KIS last-check metadata, and Docker/worker summary.
- `GET /api/dashboard` returns the latest snapshot and warnings.
- `POST /api/refresh` refreshes paper read-only account/market data with a server-side throttle and writes a snapshot. It has no order capability.

The service returns stale-but-usable local data with a warning when KIS is temporarily unavailable. It returns HTTP 503 only when no valid snapshot exists and the first refresh fails.

## Local artifacts

- `state/mode.json`: existing mode selection, normalized to paper-only effective mode.
- `state/dashboard.json`: latest sanitized snapshot, atomically written and checksum-addressable.
- `state/test-records.jsonl`: append-only sanitized evaluation records.
- `state/worker-heartbeats/*.json`: heartbeat records with TTL-based online classification.

Existing Champion, Frontier, Knowledge, Rescue Pool, and experiment artifacts remain authoritative. The dashboard reads them and does not mutate them.

## UI

The page uses a dark, high-contrast operations layout with a top safety banner, six responsive cards, compact tables, and a trend chart drawn with SVG/Canvas-free DOM elements. It has visible stale/error badges, keyboard-accessible controls, responsive two-column-to-one-column layout, and a refresh button. No external CDN or remote asset is required.

## Testing and acceptance

- Unit tests cover `.env` loading, paper-only rejection, token cache, KIS endpoint/TR-ID/parameter mapping, response redaction, account mapping, stale heartbeat classification, state aggregation, and dashboard JSON serialization.
- FastAPI tests use a fake KIS transport and temporary state directory; they never call the broker.
- CLI smoke starts the dashboard on localhost, fetches `/api/health` and `/api/dashboard`, and confirms `effective_mode=paper` and `live_enabled=false`.
- The final verification includes pytest with coverage, Ruff, mypy, secret scan, Docker daemon check, and one paper read-only token/quote/account health test. No order endpoint is invoked.
