## Repository Workflow

This repository should be kept synchronized with GitHub after each completed task.

### Auto Push Rule

At the end of every task that changes repository content:

- Review `git status --short --branch`.
- Run the relevant validation before committing. For TypeScript changes, run `npm run typecheck` at minimum.
- Stage only intentional project changes. Do not commit secrets, dependency folders, build output, or local runtime telemetry.
- Commit with a conventional commit message.
- Push the resulting commit to `origin master`.

Preferred command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1 -Message "chore: update workspace"
```

If a task makes no repository changes, do not create an empty commit. If the push is rejected, fetch the remote state and report the conflict instead of overwriting it without an explicit user request.

### Local Runtime Files

Do not commit local runtime churn from `.omx/logs/`, `.omx/state/`, or `.omx/metrics.json`.
