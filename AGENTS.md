## Repository Workflow

This repository should be kept synchronized with GitHub after each completed task.

### Codex Automation Policy

At the end of every task that changes repository content:

- Review `git status --short --branch`.
- Run the relevant validation before committing. For TypeScript changes, run `npm run typecheck` at minimum.
- Stage only intentional project changes. Do not commit secrets, dependency folders, build output, or local runtime telemetry.
- Commit with a conventional commit message.
- Push the resulting commit to GitHub.

Preferred command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1 -Message "chore: update workspace" -TaskSize auto
```

If a task makes no repository changes, do not create an empty commit. If the push is rejected, fetch the remote state and report the conflict instead of overwriting it without an explicit user request.

### Branch Strategy

Use the smallest workflow that still matches the risk of the work:

- Small tasks: documentation, configuration, narrow bug fixes, or one-module edits with low risk. Commit directly on `master` and push to `origin master`.
- Medium tasks: multi-file module upgrades, new CLI flows, state schema changes, or behavior that needs review. Create a branch named `codex/<type>-<timestamp>-<slug>`, commit there, and push it to origin.
- Large tasks: cross-module refactors, migrations, autonomous-loop changes, or work that changes public behavior across the system. Split into separate `codex/` branches by module or concern, validate each branch independently, and avoid combining unrelated upgrades in one commit.
- Hotfixes: use the direct `master` path only for urgent, low-risk fixes. Otherwise use a `codex/fix-*` branch.

The automation script supports this policy:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1 -Message "feat(research): upgrade source ranking" -TaskSize medium
powershell -ExecutionPolicy Bypass -File scripts/auto-push.ps1 -Message "refactor(loop): split scheduler state" -TaskSize large -BranchName "codex/refactor-loop-scheduler-state"
```

When `-TaskSize auto` is used, the script stages only allowed project paths, measures the staged change size, commits small changes to `master`, and uses a `codex/` branch for medium or large changes.

### Local Runtime Files

Do not commit local runtime churn from `.omx/logs/`, `.omx/state/`, `.omx/metrics.json`, local Playwright state, dashboard logs, build output, or autonomous-run scratch artifacts.
