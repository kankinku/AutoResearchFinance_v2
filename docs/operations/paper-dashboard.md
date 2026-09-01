# Paper dashboard operations

## Start

From the repository root:

```powershell
python cli.py init --state-dir state
python cli.py dashboard-refresh --state-dir state --env-file .env
python cli.py dashboard --state-dir state --env-file .env --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/` in a local browser. The dashboard polls local JSON endpoints every ten seconds. `dashboard-refresh` is the only dashboard action that contacts KIS, and it performs paper read-only health and account calls.

## Safety

- The effective mode is always `paper`.
- `live_enabled` is always `false`.
- The dashboard has no order route and the paper client has no order method.
- The browser receives masked account identifiers and never receives app keys, app secrets, or bearer tokens.
- Bind only to `127.0.0.1`; the server rejects other hosts.
- Keep `.env` outside Git. Use `.env.example` as the variable list.

## Dashboard records

`run-generation` appends sanitized candidate results to `state/test-records.jsonl`. It stores strategy and run hashes, generation, score, return, benchmark excess return, drawdown, risk compliance, and funnel status. Raw market rows and credentials are not stored.

Worker processes can publish a heartbeat using `runtime.heartbeat.WorkerHeartbeatStore` to `state/worker-heartbeats/<worker-id>.json`. The dashboard treats running workers as `ONLINE` for 60 seconds, `STALE` through 300 seconds, and older or terminal workers as `OFFLINE`.

## Current limitations

The KIS client currently supports paper token, US quote, US daily bars, and paper account snapshot reads. Paper order placement remains intentionally absent until a separate order contract, explicit confirmation, idempotency, and cancel/reconcile procedure have been reviewed. The dashboard is an operations view, not an order-entry UI.
