# OpenClaw Control Skills

This project ships two installable OpenClaw skills that wrap the existing `openclaw-control` supervisor surface.

## Included skills

- `finance-autoresearch-control`
  - sends `status`, `start_pipeline`, `start_autoresearch`, `pause_autoresearch`, `resume_autoresearch`, `stop_autoresearch`, `reset_project`
- `finance-autoresearch-status-polling`
  - waits for target states such as pipeline success or autoresearch completion

The source templates live in:

- `openclaw-skills/finance-autoresearch-control`
- `openclaw-skills/finance-autoresearch-status-polling`

## Repository helper scripts

The skills delegate to these repository scripts:

- [invoke-openclaw-control.ps1](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\scripts\invoke-openclaw-control.ps1)
- [wait-finance-status.ps1](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\scripts\wait-finance-status.ps1)

You can use these directly even without installing the OpenClaw skills.

## Install the skills

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-openclaw-skills.ps1
```

Default behavior:

- generates `.skill` bundles in the system temp directory
- copies them into `C:\Users\hanji\.openclaw\workspace`

Optional parameters:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-openclaw-skills.ps1 `
  -RepositoryRoot "C:\path\to\repo" `
  -OutputRoot "C:\path\to\skill-bundles" `
  -OpenClawWorkspace "C:\Users\hanji\.openclaw\workspace"
```

If you only want to build bundles and not install them:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-openclaw-skills.ps1 `
  -SkipInstall `
  -OutputRoot "C:\path\to\skill-bundles"
```

## Direct helper usage

Check supervisor status:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/invoke-openclaw-control.ps1 -Command status
```

Start the pipeline:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/invoke-openclaw-control.ps1 -Command start_pipeline
```

Wait for the pipeline to finish:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/wait-finance-status.ps1 `
  -ProjectState idle `
  -PipelineState success `
  -AutoresearchState idle `
  -TimeoutSeconds 900 `
  -PollIntervalSeconds 5 `
  -StopOnTerminalFailure
```

Start autoresearch:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/invoke-openclaw-control.ps1 -Command start_autoresearch
```

Wait for autoresearch completion:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/wait-finance-status.ps1 `
  -ProjectState idle `
  -PipelineState success `
  -AutoresearchState success `
  -TimeoutSeconds 3600 `
  -PollIntervalSeconds 10 `
  -StopOnTerminalFailure
```

## Recommended OpenClaw usage pattern

1. Use `finance-autoresearch-control` to send `status`.
2. If the project is `idle` and pipeline is not ready, send `start_pipeline`.
3. Use `finance-autoresearch-status-polling` to wait for `idle/success/idle`.
4. Send `start_autoresearch`.
5. Use `finance-autoresearch-status-polling` to wait for `idle/success/success`.
6. Only use `reset_project` when the project is already `idle` or `degraded`.

## Notes

- The installed `.skill` files contain the absolute repository path at install time.
- If you move the repository, run the install script again so the skill wrappers point to the new location.
- These skills only control the supervisor. Mutation and analysis still use the existing OpenClaw wrapper contract in [openclaw-setup.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\docs\openclaw-setup.md).
