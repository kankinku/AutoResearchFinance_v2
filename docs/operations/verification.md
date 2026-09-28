# Verification evidence

The release gate is reproducible from the repository root using the locked project runtime:

    uv run --locked --extra dev ruff check .
    uv run --locked --extra dev mypy .
    uv run --locked --extra dev python -m pytest -q

MCP transport verification is split between the canonical official-SDK entrypoint and
the explicit manual rollback path.

Canonical official SDK STDIO verification:

    uv run --locked --extra dev python scripts/verify_mcp_sdk_runtime.py --project-root . --state-dir state/mcp-sdk-acceptance

This launches `python -m integrations.codex_mcp_server` in real subprocesses, verifies
the current SDK handshake, 2024-11-05 compatibility, the exact 13 public tools, the
5 hidden compatibility calls, public contract v1, sanitized errors, and
`orders_enabled=false`.

Manual rollback transport verification:

    uv run --locked --extra dev python scripts/verify_mcp_runtime.py --project-root . --state-dir state/mcp-manual-rollback-acceptance

This launches `python -m integrations.codex_mcp_manual_server` and verifies the same
13/5 compatibility surface over the retained 2024-11-05 newline JSON-RPC transport.
It is a rollback gate, not the production transport.

Docker prerequisite verification on a host with Docker Desktop and the worker image:

    uv run --locked python scripts/verify_docker_evaluation.py --project-root . --check-only

A full Docker evaluation acceptance additionally requires a real strategy source and development Parquet input.

Focused contracts cover source normalization, IR signal execution, Docker isolation, data-zone and Parquet integrity, funnel decisions, CSCV/CPCV split generation, abstract knowledge extraction, paper approval, live denial, state atomicity, managed-process recovery, durable evaluation jobs, official-SDK and rollback MCP stdio transport, and CLI behavior.

External configuration must be reported separately. Tests do not fabricate KIS credentials, live data-vendor credentials, LLM credentials, or a production Docker image.
