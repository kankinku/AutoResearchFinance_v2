# ChatGPT-directed Quant Autoresearch over MCP — 2026-10-09

## Goal

ChatGPT (or another connected external LLM) writes the **ResearchIntent**, uses MCP to observe the current research state, orders one bounded research step, and reviews persisted immutable Evidence before choosing another step. The local runtime validates the Strategy IR, registered features and mutations, runs backtests and retains evidence. This mode **does not start Codex** or a local LLM subprocess. The existing autonomous `start_system`/Codex worker remains a legacy, separate mode; callers should use `run_research_step` for external-LLM-controlled research.

## Public MCP calls

- `list_strategies` / `validate_strategy`: discover valid canonical parent IDs.
- `get_research_brief`: sanitized observations, immutable Frontier summary (20 max), failure knowledge, feature catalog, explicit `llm_controller=external_mcp_client` and `orders_enabled=false`.
- `run_research_step`: `{source_path, data_path, intent, method?, count?, seed?, min_trades?, min_annual_trades?, min_qqq_cagr_delta?, series_data_path?}`. **Intent** requires `mode`, `parent_ids` (exactly one matching the source Strategy IR), `rationale`, optionally registered operations/features. Fail closed on unknown parent, invalid feature, unverified primitive proposals, direct code/evaluator edits and unapproved paths. Single step means one research run, one evaluated generation, immutable run/attempt/end records, with no autonomous LLM call. Existing experiment scoring/training boundaries remain unchanged.
- `get_research_evidence` / `get_dashboard_status`: inspect the attributable result after the step.

The tool response carries an additive public contract `orders_enabled=false`. Candidate `SURVIVOR` is a *development* research designation; it is not a sealed OOS pass or live-trading authorization. Multi-parent crossover and active Rescue sourcing are not implicitly implemented.

## Local official MCP SDK

The original 13-tool canonical public SDK interface is unchanged; the dedicated ChatGPT adapter exposes an 11-tool subset including the two new tools. The original canonical stdio command remains:

```bash
PYTHONPATH="$PWD" .venv/bin/python -m integrations.codex_mcp_server --project-root . --state-dir state
```

## Optional authenticated Streamable HTTP MCP adapter

Prepare a **unique, high-entropy** token outside source control, for example:

```bash
export QUANT_MCP_HTTP_TOKEN="$(openssl rand -hex 32)"
PYTHONPATH="$PWD" .venv/bin/python -m integrations.chatgpt_mcp_http \
  --project-root . --state-dir state --host 127.0.0.1 --port 8787
```

The local endpoint is `http://127.0.0.1:8787/mcp` (HTTP transport, not TLS). All HTTP methods require `Authorization: Bearer <token>`; the token is never printed in logs or committed to the repository. Missing/short token prevents startup. The host binds only to loopback to prevent accidental unauthenticated Internet exposure; use a separately controlled **TLS-terminating gateway** to make it remotely reachable. The Streamable HTTP session manager is the official pinned MCP SDK; the older manual protocol remains rollback-only. For a gateway hostname, pass its exact allowed HTTP host with `--allowed-host example.example` (in addition to local hosts as necessary). Do not enable a public Tailscale Funnel until authentication, HTTPS, rate limiting and client-specific authorization have been reviewed. This static bearer-token prototype is *not* an OAuth authorization server and should not be represented as a completed ChatGPT plugin registration.

## External ChatGPT plugin connection is not yet completed

ChatGPT UI/plugin registration, provider-supported OAuth/authorization behavior, network DNS/TLS reachability, host Tailscale gateway and Windows Docker acceptance depend on the actual deployment and external app settings. No plugin was installed and no remote URL was issued by this code change. **Authenticated localhost integration** is covered by tests; remote Cloud Browser/ChatGPT reachability has not been tested.

## Validation

`tests/integrations/test_chatgpt_mcp_research.py` verifies visible tools, fail-closed parent and feature validation, one real research step with immutable Evidence, and zero local Codex calls. `tests/integrations/test_chatgpt_mcp_http.py` verifies unauthorized requests are rejected and authenticated official MCP initialization, tool listing and brief retrieval. SDK/manual compatibility tests verify the updated published tool surface.
