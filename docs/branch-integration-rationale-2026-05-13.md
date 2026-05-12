# Branch Integration Rationale - 2026-05-13

## Scope

This integration branch was created from `master` to consolidate all branches that were not merged into the current TypeScript AF runtime line.

## Integrated as Code

- `codex/feat-20260510-224301-add-korean-display-layer`
- `codex/feat-20260511-142255-add-pine-compile-error-memory`
- `codex/feat-20260511-215614-publish-btc-best-score-return-model`

These branches extend the active runtime, dashboard, Pine preflight, compile-failure memory, and BTC strategy artifact flow. Conflicts were resolved by preserving the modular dashboard split while retaining the Korean display fields and by unioning all compile-failure classes.

## Integrated as History

- `origin/codex/finance-autoresearch-v1`

This branch has no usable common base with the current `master` line and replaces the TypeScript CLI/dashboard/runtime with a separate Python package. Content-merging it would delete the active system. It is therefore recorded with an `ours` merge so the repository history acknowledges the branch while the current TypeScript implementation remains canonical.

## Follow-up Guardrail

Compile-failure classes now use one canonical tuple for schema validation and count initialization. That reduces future merge risk when new Pine compiler failure classes are added.
