---
name: finance-autoresearch-control
description: Use when controlling the finance autoresearch supervisor from OpenClaw and you need to query status or send lifecycle commands without hand-writing JSON envelopes.
---

# Finance Autoresearch Control

Use `scripts/invoke_finance_command.ps1` for every supervisor command. Do not craft raw `openclaw-control` stdin JSON unless the helper script is unavailable.

## Commands

- `status`
- `start_pipeline`
- `start_autoresearch`
- `pause_autoresearch`
- `resume_autoresearch`
- `stop_autoresearch`
- `reset_project`

## Usage

```powershell
scripts/invoke_finance_command.ps1 -Command status
scripts/invoke_finance_command.ps1 -Command start_pipeline
scripts/invoke_finance_command.ps1 -Command start_autoresearch
```

## Rules

- Always check `status` before lifecycle changes if current state is unclear.
- After `start_pipeline` or `start_autoresearch`, use `finance-autoresearch-status-polling` to wait for completion.
- Prefer `stop_autoresearch` over `reset_project` when a run is active.
- Keep `ProjectId` as `finance` unless the repository explicitly changed it.

## Optional Parameters

- `-ProjectId`
- `-RequestedBy`
- `-PayloadJson`

`PayloadJson` must be a JSON object string. Most supervisor commands use `{}`.
