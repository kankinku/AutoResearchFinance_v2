---
name: finance-autoresearch-status-polling
description: Use when waiting for finance autoresearch pipeline or autoresearch to reach a target state and you want structured polling instead of repeated manual status calls.
---

# Finance Autoresearch Status Polling

Use `scripts/wait_finance_status.ps1` whenever a command starts background work and you need to wait for a target state.

## Common waits

Wait for pipeline completion:

```powershell
scripts/wait_finance_status.ps1 -ProjectState idle -PipelineState success -AutoresearchState idle -TimeoutSeconds 900 -PollIntervalSeconds 5 -StopOnTerminalFailure
```

Wait for autoresearch completion:

```powershell
scripts/wait_finance_status.ps1 -ProjectState idle -PipelineState success -AutoresearchState success -TimeoutSeconds 3600 -PollIntervalSeconds 10 -StopOnTerminalFailure
```

## Rules

- Use `-StopOnTerminalFailure` when waiting for `success`.
- If the script exits `2`, inspect the returned JSON and stop retrying blindly.
- Polling is for observation only. State changes still go through `finance-autoresearch-control`.
