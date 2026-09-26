# Verification evidence

The release gate is reproducible from the repository root using the locked project runtime:

    uv run --locked --extra dev ruff check .
    uv run --locked --extra dev mypy .
    uv run --locked --extra dev python -m pytest -q

Phase 3 also has two process-boundary acceptance checks.

MCP STDIO server verification (does not start research or enable orders):

    uv run --locked python scripts/verify_mcp_runtime.py --project-root . --state-dir state/mcp-acceptance

Docker prerequisite verification on a host with Docker Desktop and the worker image:

    uv run --locked python scripts/verify_docker_evaluation.py --project-root . --check-only

A full Docker evaluation acceptance additionally requires a real strategy source and development Parquet input.

Focused contracts cover source normalization, IR signal execution, Docker isolation, data-zone and Parquet integrity, funnel decisions, CSCV/CPCV split generation, abstract knowledge extraction, paper approval, live denial, state atomicity, managed-process recovery, durable evaluation jobs, MCP stdio transport, and CLI behavior.

External configuration must be reported separately. Tests do not fabricate KIS credentials, live data-vendor credentials, LLM credentials, or a production Docker image.
