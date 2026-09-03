# Quant Autoresearch System Integration and Cleanup

## Status

Approved for implementation by the user's request to proceed with the integration work.

## Goal

Remove operational ambiguity caused by parallel implementations and duplicated policy definitions while preserving Strategy IR, provenance, historical plans, and the Paper-only safety boundary.

## Scope

1. Declare the `dashboard/` FastAPI and static web application the active dashboard path because `cli.py dashboard` launches it.
2. Add explicit lifecycle/status metadata to dashboard design documents so historical Streamlit plans are not mistaken for the active runtime.
3. Centralize QQQ CAGR delta and annual trade-count defaults in the existing research policy model and expose a single funnel-policy factory for CLI, Mimir, MCP, and system-controller paths.
4. Consolidate small duplicate production helpers where ownership is unambiguous: UTC normalization, numeric clamping, and provenance attachment.
5. Add regression tests for policy consistency and dashboard entrypoint consistency.
6. Remove only the ignored `dashboard_backup.py` after dependency and test checks; retain `dashboard.py` until its active Streamlit tests are migrated or explicitly retired.

## Out of scope

- Deleting historical design and implementation-plan documents.
- Removing `.worktrees` without confirming that their branches are no longer needed.
- Changing Strategy IR semantics, backtest rules, KIS order behavior, or live-trading permissions.
- Claiming strategy-performance improvement from implementation tests.

## Canonical decisions

- Strategy IR remains the only strategy source.
- `dashboard/run.py` is the only CLI-launched dashboard server.
- `research/policy.yaml` is the source of default evaluation thresholds.
- Imported strategies remain provenance records; normalized strategies remain execution inputs.

## Data flow

`research/policy.yaml` -> `ResearchPolicy` -> `FunnelConfig` -> `GenerationPipeline` / selector.

`cli.py` / `runtime/mimir.py` / MCP / system controller -> canonical runner -> `dashboard/` FastAPI/static UI.

## Acceptance criteria

- Every current evaluation entrypoint resolves the same default QQQ CAGR delta and annual trade-count thresholds.
- No active CLI path launches Streamlit.
- Dashboard tests cover the FastAPI entrypoint and the legacy Streamlit surface is explicitly classified.
- Feature catalog remains 159 imported / 173 research features with zero semantic duplicate groups.
- Existing test, Ruff, and MyPy checks pass.
- No credential, state, raw market data, or unrelated user changes are staged.

## Cleanup policy

Physical deletion is limited to proven disposable artifacts. Historical documents are status-labeled rather than deleted so that recovery causes and design decisions remain auditable.
