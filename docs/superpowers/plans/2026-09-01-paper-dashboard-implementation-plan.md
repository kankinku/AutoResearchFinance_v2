# Paper Trading Operations Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost FastAPI dashboard and paper-only KIS integration that reports account state, effective mode, tests, Champion strategy, improvement trend, and parallel worker availability without enabling live orders.

**Architecture:** Add a paper-only KIS REST client with injectable transport, typed sanitized dashboard contracts, a snapshot aggregator over KIS and existing state artifacts, and a FastAPI app serving local static HTML/CSS/JavaScript. State writes are atomic and append-only where appropriate; dashboard reads are read-only and live mode is rejected at the boundary.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, standard library `urllib` transport, Pydantic/dataclasses, pytest/httpx, existing JSON/JSONL state files, vanilla HTML/CSS/JavaScript.

---

### Task 1: Add paper-only KIS configuration and transport contracts

**Files:**
- Create: `integrations/kis/config.py`
- Create: `integrations/kis/client.py`
- Create: `tests/integrations/test_kis_client.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Write failing tests for configuration and request mapping**

Add tests that construct a temporary environment mapping and assert that paper configuration is accepted, live configuration is rejected by `PaperKISConfig`, missing paper keys produce a configuration error, and a fake transport records `POST /oauth2/tokenP` plus `GET /uapi/overseas-price/v1/quotations/price` with the official TR-ID `HHDFS00000300`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run `python -m pytest -q tests/integrations/test_kis_client.py`; expect import failures because the new configuration and client modules do not exist.

- [ ] **Step 3: Implement the minimal paper client**

Define `PaperKISConfig.from_env(path: Path)` to load only `KIS_PAPER_APP_KEY`, `KIS_PAPER_APP_SECRET`, `KIS_PAPER_BASE_URL`, `KIS_ACCOUNT_NO`, and `KIS_PRODUCT_CODE`. Define `HTTPTransport.request(method, url, headers, params, body)` and `KISPaperClient` with token caching, `quote(symbol, exchange='NAS')`, `daily_bars(symbol, start, end)`, `account_snapshot(exchange='NASD', currency='USD')`, and `health()`. Use the official token endpoint and overseas stock endpoints; never log request headers or response secrets. Enforce `mode == 'paper'` in the client constructor.

- [ ] **Step 4: Add dependencies and safe environment template**

Add `fastapi`, `uvicorn`, and `httpx` to the project dependencies. Add explicit paper account variables and dashboard host/port variables to `.env.example`, leaving all values empty except the documented paper base URL and `QUANT_TRADING_MODE=paper`.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m pytest -q tests/integrations/test_kis_client.py`; expect all focused tests to pass. Commit with `git add integrations/kis/config.py integrations/kis/client.py tests/integrations/test_kis_client.py pyproject.toml .env.example && git commit -m "feat: add paper-only KIS client"`.

### Task 2: Add typed dashboard contracts and sanitized artifact aggregation

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/contracts.py`
- Create: `dashboard/state.py`
- Create: `tests/dashboard/test_state.py`

- [ ] **Step 1: Write failing tests for dashboard sections**

Test that an empty state returns explicit `EMPTY`/`UNKNOWN` sections, account IDs are masked, `state/mode.json` with requested `live` is represented as effective `paper` with `live_enabled=false`, Champion and Knowledge data become a strategy summary, JSONL test records become newest-first test records, and worker heartbeat age under 60 seconds is `ONLINE`, 60–300 seconds is `STALE`, and older/missing records are `OFFLINE`/`UNKNOWN`.

- [ ] **Step 2: Run focused tests and verify RED**

Run `python -m pytest -q tests/dashboard/test_state.py`; expect module import failures.

- [ ] **Step 3: Implement immutable contracts and aggregation**

Create Pydantic models for mode, account, holdings, tests, strategy, trend, workers, health, and the complete snapshot. Implement `DashboardStateReader(root)` that reads existing state files defensively, parses sanitized JSONL records, reads only `state/worker-heartbeats/*.json`, computes heartbeat status from an injected clock, derives Champion/trend summaries, and emits warnings rather than leaking parse errors or raw response text.

- [ ] **Step 4: Implement atomic snapshot persistence**

Add `SnapshotStore.write(snapshot)` using a temporary file and `os.replace`, and `SnapshotStore.read()` with schema validation. Store only `DashboardSnapshot.model_dump(mode='json')` and expose a `last_updated` timestamp.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m pytest -q tests/dashboard/test_state.py`; expect all tests to pass. Commit with `git add dashboard tests/dashboard && git commit -m "feat: add sanitized dashboard state contracts"`.

### Task 3: Add dashboard service and FastAPI endpoints

**Files:**
- Create: `dashboard/service.py`
- Create: `dashboard/app.py`
- Create: `tests/dashboard/test_api.py`

- [ ] **Step 1: Write failing API tests**

Use `fastapi.testclient.TestClient` with a temporary state directory and fake paper KIS client. Assert `GET /api/health` returns 200 with `effective_mode=paper`, `live_enabled=false`, and no credential values; `GET /api/dashboard` returns Champion/tests/workers; `POST /api/refresh` calls only fake read-only methods and writes a snapshot; and a fake KIS failure returns stale data plus a warning without throwing raw exception text.

- [ ] **Step 2: Run focused tests and verify RED**

Run `python -m pytest -q tests/dashboard/test_api.py`; expect module import failures.

- [ ] **Step 3: Implement the service**

Define `DashboardService.snapshot()` as a local read and `DashboardService.refresh()` as a throttled paper-only read of account and configured symbols. On refresh failure, preserve the previous sanitized snapshot and append a stable warning code. Never expose a method that accepts a live client or order client.

- [ ] **Step 4: Implement FastAPI application factory**

Create `create_app(service=None)` with routes `/`, `/api/health`, `/api/dashboard`, and `/api/refresh`. Bind configuration defaults to `127.0.0.1` and `8080`. Use `StaticFiles` or an explicit file response for local assets only. Add response models and `Cache-Control: no-store` to API responses.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m pytest -q tests/dashboard/test_api.py`; expect all tests to pass. Commit with `git add dashboard/service.py dashboard/app.py tests/dashboard/test_api.py && git commit -m "feat: expose paper dashboard API"`.

### Task 4: Build the local dashboard page

**Files:**
- Create: `dashboard/static/index.html`
- Create: `dashboard/static/styles.css`
- Create: `dashboard/static/app.js`
- Create: `tests/dashboard/test_static_assets.py`

- [ ] **Step 1: Write asset and safety tests**

Assert the HTML includes the paper safety banner, all six required sections, refresh control, no external `http://`/`https://` script or stylesheet references, and JavaScript requests only `/api/health`, `/api/dashboard`, and `/api/refresh`.

- [ ] **Step 2: Run focused tests and verify RED**

Run `python -m pytest -q tests/dashboard/test_static_assets.py`; expect missing asset failures.

- [ ] **Step 3: Implement accessible responsive UI**

Create a dark operations dashboard with a persistent `PAPER ONLY / LIVE DISABLED` banner, status cards, account table, test table, Champion card, generation trend list, and worker table. Use semantic headings, table captions, keyboard focus styles, `aria-live` for refresh status, and stale/error badges. Keep all rendering data-driven and escape text before DOM insertion.

- [ ] **Step 4: Mount assets and run tests**

Mount the static directory in `dashboard/app.py`, run `python -m pytest -q tests/dashboard/test_static_assets.py`, and expect all tests to pass. Commit with `git add dashboard/static dashboard/app.py tests/dashboard/test_static_assets.py && git commit -m "feat: add local paper operations dashboard"`.

### Task 5: Add CLI and Docker operations

**Files:**
- Modify: `cli.py`
- Modify: `runtime/Dockerfile.lean`
- Create: `dashboard/run.py`
- Create: `tests/cli/test_dashboard_cli.py`
- Create: `docs/operations/paper-dashboard.md`

- [ ] **Step 1: Write failing CLI tests**

Assert `python cli.py dashboard --help` exposes `--state-dir`, `--host`, and `--port`; `python cli.py dashboard-status` reports `effective_mode=paper`; and `python cli.py dashboard-refresh` cannot select live or submit an order.

- [ ] **Step 2: Run focused tests and verify RED**

Run `python -m pytest -q tests/cli/test_dashboard_cli.py`; expect argument/parser failures.

- [ ] **Step 3: Implement safe CLI commands**

Add `dashboard`, `dashboard-status`, and `dashboard-refresh`. The `dashboard` command runs Uvicorn with the app factory; the status command reads only local state; the refresh command calls paper read-only APIs and writes sanitized state. Reject `--mode live` with a non-zero result and a stable reason.

- [ ] **Step 4: Update Docker configuration and documentation**

Keep worker containers network-disabled. Add a separate local dashboard entrypoint that binds to `127.0.0.1`, and document `python cli.py dashboard --state-dir state --host 127.0.0.1 --port 8080`, the safe refresh behavior, paper-only mode, required account variables, and the exact no-order guarantee.

- [ ] **Step 5: Run CLI tests and commit**

Run `python -m pytest -q tests/cli/test_dashboard_cli.py`; expect all tests to pass. Commit with `git add cli.py dashboard/run.py runtime/Dockerfile.lean tests/cli/test_dashboard_cli.py docs/operations/paper-dashboard.md && git commit -m "feat: add paper dashboard operations commands"`.

### Task 6: Full verification and paper read-only smoke test

**Files:**
- Modify: `README.md`
- Create: `tests/dashboard/test_integration_smoke.py`

- [ ] **Step 1: Add integration smoke test with fake transport**

Exercise app creation, state aggregation, refresh, and JSON serialization using a fake token/quote/account response. Assert no live URL, order path, bearer token, app key, or app secret appears in the snapshot.

- [ ] **Step 2: Run the complete local verification suite**

Run `python -m pytest -q --cov=. --cov-report=term-missing`, `ruff check .`, `python -m mypy .`, `git diff --check`, and a changed-file secret scan. Require all tests to pass and total coverage to remain at least 80%.

- [ ] **Step 3: Run Docker and localhost smoke checks**

Run `docker info`, start the dashboard on `127.0.0.1` with a temporary state directory, request `/api/health` and `/api/dashboard`, then stop the process. Confirm the JSON reports `effective_mode=paper`, `live_enabled=false`, and sanitized account data only.

- [ ] **Step 4: Run the authorized paper read-only API check**

Load only the paper profile from the local `.env`, call token plus quote/account read-only methods, print status codes and field-presence booleans only, and never call `/trading/order` or any real-investment base URL.

- [ ] **Step 5: Update README and commit final verification documentation**

Document the dashboard start command, localhost URL, paper-only limitation, refresh behavior, and test evidence. Run the complete verification commands once more and commit with `git add README.md tests/dashboard/test_integration_smoke.py && git commit -m "docs: document paper dashboard verification"`.
