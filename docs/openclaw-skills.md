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

## Portability model

The packaged `.skill` files no longer bake in an absolute repository path.

Resolution order is:

1. explicit `-RepositoryRoot`
2. `FINANCE_AUTORESEARCH_REPOSITORY_ROOT`
3. upward search from the current working directory for a valid repo root
4. installed `finance-autoresearch` CLI or `python -m finance_autoresearch`

Runner selection is:

1. `uv run python -m finance_autoresearch openclaw-control` when a repo root is known and `uv` exists
2. installed `finance-autoresearch openclaw-control`
3. `python -m finance_autoresearch openclaw-control`
4. `py -m finance_autoresearch openclaw-control`

If the script falls back to `python` or `py` and a repo root is known, it temporarily prepends `<repo>\src` to `PYTHONPATH` so editable installation is not required.

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

If you are not running from the repository root, add:

```powershell
-RepositoryRoot "C:\path\to\finance-autoresearch"
```

or set:

```powershell
$env:FINANCE_AUTORESEARCH_REPOSITORY_ROOT = "C:\path\to\finance-autoresearch"
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

If a command needs a payload, you can either inline JSON:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/invoke-openclaw-control.ps1 `
  -Command status `
  -PayloadJson '{"note":"example"}'
```

or point to a JSON file:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/invoke-openclaw-control.ps1 `
  -Command status `
  -PayloadPath "C:\path\to\payload.json"
```

The payload must resolve to a JSON object. Omit it for commands that do not need one.

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

- The installed `.skill` files are portable across different checkout paths because they resolve the repository at runtime.
- If you use source checkout mode instead of an installed package, the most reliable setup is to set `FINANCE_AUTORESEARCH_REPOSITORY_ROOT`.
- These skills only control the supervisor. Mutation and analysis still use the existing OpenClaw wrapper contract in [openclaw-setup.md](C:\Users\hanji\Desktop\Finance\AutoResearchFinance_v2\.worktrees\finance-autoresearch-v1\docs\openclaw-setup.md).
