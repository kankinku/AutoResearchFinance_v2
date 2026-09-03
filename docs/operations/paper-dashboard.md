# Paper dashboard operations

## Canonical runtime

The active CLI dashboard is the FastAPI application in `dashboard/`, served by
`dashboard/run.py`. The root `dashboard.py` Streamlit application is a retained
legacy/test surface from the earlier redesign and is not launched by `python cli.py dashboard`.
New dashboard features must be added to the FastAPI/static application first.

## Start

From the repository root:

```powershell
python cli.py init --state-dir state
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/` in a local browser. The dashboard polls local JSON endpoints every 15 seconds. `dashboard-refresh` is the only dashboard action that contacts KIS, and it performs paper read-only health and account calls.

For unattended backtest research, use the supervisor in a separate PowerShell:

```powershell
.\scripts\start_dashboard.ps1
```

It keeps the localhost dashboard process alive, restarts it after an unexpected
exit, refuses duplicate listeners on the same port, and appends lifecycle events
to `state/system/dashboard-supervisor.log`. The browser refreshes research and
backtest state every 15 seconds; it does not submit orders.

## Codex research connection

For Codex Desktop, copy `.codex/config.toml.example` into the trusted Codex MCP
configuration or register the same stdio command in Desktop settings:

```powershell
python -m integrations.codex_mcp_server --state-dir state --project-root .
```

The server provides only sanitized context, selectable features, dashboard status,
intent validation/recording, and approved local evaluation. It never provides order
placement, live-account access, credentials, raw market rows, sealed OOS data, or
arbitrary file writes. The automation path is:

```powershell
python cli.py research-intent --state-dir state --env-file .env --project-root .
```

It calls the locally authenticated `codex exec` CLI, validates one `ResearchIntent`,
records only the validated intent, and writes a redacted provider status to
`state/llm/status.json`. If Codex is unavailable, the call fails closed; local
deterministic evaluation remains available.

## Safety

- The effective mode is always `paper`.
- `live_enabled` is always `false`.
- The dashboard has no order route and the paper client has no order method.
- The browser receives masked account identifiers and never receives app keys, app secrets, or bearer tokens.
- Bind only to `127.0.0.1`; the server rejects other hosts.
- Keep `.env` outside Git. Use `.env.example` as the variable list.
- The Codex child process inherits its saved Codex CLI session but receives no
  `KIS_*`, `OPENAI_API_KEY`, `CODEX_API_KEY`, or `QUANT_LLM_API_KEY` variables.

## Dashboard records

`run-generation` appends sanitized candidate results to `state/test-records.jsonl`. It stores strategy and run hashes, generation, score, return, benchmark excess return, drawdown, risk compliance, and funnel status. Raw market rows and credentials are not stored.

Worker processes can publish a heartbeat using `runtime.heartbeat.WorkerHeartbeatStore` to `state/worker-heartbeats/<worker-id>.json`. The dashboard treats running workers as `ONLINE` for 60 seconds, `STALE` through 300 seconds, and older or terminal workers as `OFFLINE`.

## Current limitations

The KIS client currently supports paper token, US quote, US daily bars, and paper account snapshot reads. Paper order placement remains intentionally absent until a separate order contract, explicit confirmation, idempotency, and cancel/reconcile procedure have been reviewed. The dashboard is an operations view, not an order-entry UI.
