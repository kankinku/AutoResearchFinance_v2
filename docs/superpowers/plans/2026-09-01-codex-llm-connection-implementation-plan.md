# Codex LLM Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the harness to Codex Desktop and Codex CLI without putting KIS credentials into the LLM process, while preserving validated `ResearchIntent` output and paper-only execution boundaries.

**Architecture:** Codex Desktop will access a local stdio MCP server that exposes sanitized research context, feature catalog, evaluation requests, and dashboard status. Scheduled or unattended research will use `codex exec` through a subprocess adapter with stdin context and `--output-schema`; both paths return the same `ResearchIntent` model and are revalidated locally. Codex receives no order tool, live credential, raw market rows, sealed OOS data, or evaluator mutation capability.

**Tech Stack:** Python 3.10+, Pydantic v2, stdio JSON-RPC MCP protocol, Codex CLI (`codex exec`), pytest, Ruff, mypy, local JSON state files.

---

### Task 1: Define the Codex intent schema and provider boundary

**Files:**
- Create: `research/llm/codex_schema.py`
- Modify: `research/llm/provider.py`
- Modify: `research/llm/director.py`
- Test: `tests/research/test_codex_provider.py`

- [x] **Step 1: Write failing tests for schema export and provider injection**

Test that the exported JSON Schema rejects `python_patch` and `evaluator_change`, accepts a valid `ResearchIntent`, and that a provider receives only the supplied sanitized context.

- [x] **Step 2: Run the focused tests and verify the new provider symbols fail**

Run: `python -m pytest tests/research/test_codex_provider.py -q`

Expected: FAIL because the Codex schema/provider adapter does not exist.

- [x] **Step 3: Implement the schema and provider protocol**

Expose a function that returns `ResearchIntent.model_json_schema()` and a provider factory interface that returns `ResearchIntent` through the existing `ResearchDirector`. Keep all subprocess and MCP code outside the model-validation layer.

- [x] **Step 4: Run focused tests and static checks**

Run: `python -m pytest tests/research/test_codex_provider.py -q; ruff check research/llm tests/research/test_codex_provider.py; python -m mypy research`

Expected: PASS.

- [x] **Step 5: Commit the provider boundary**

```powershell
git add research/llm/codex_schema.py research/llm/provider.py research/llm/director.py tests/research/test_codex_provider.py
git commit -m "feat: define Codex intent provider boundary"
```

### Task 2: Implement the `codex exec` structured-output adapter

**Files:**
- Create: `research/llm/codex_exec.py`
- Create: `schemas/research_intent.schema.json`
- Modify: `research/llm/provider.py`
- Test: `tests/research/test_codex_exec.py`

- [x] **Step 1: Write failing subprocess tests**

Use a fake executable runner to assert the adapter invokes `codex exec -`, passes `--output-schema`, uses `-o` for a temporary output file, supplies sanitized JSON on stdin, parses the resulting object, and rejects nonzero exit codes or invalid intent JSON without exposing stderr in the exception.

- [x] **Step 2: Run the tests and verify failure**

Run: `python -m pytest tests/research/test_codex_exec.py -q`

Expected: FAIL because `CodexExecProvider` is not implemented.

- [x] **Step 3: Implement the minimal adapter**

Launch only the configured `codex` executable, use the checked-in schema, set the working directory explicitly, and create a filtered child environment containing no `KIS_*`, `OPENAI_API_KEY`, or `CODEX_API_KEY` values unless the caller explicitly supplies a dedicated Codex credential. Parse the final output through `ResearchIntent.model_validate`.

- [x] **Step 4: Generate and compare the checked-in schema**

Run a small local command that serializes the model schema and compare it with `schemas/research_intent.schema.json`; update the schema only when the model contract changes. Verify the schema has `additionalProperties: false` for the intent object.

- [x] **Step 5: Run focused tests and commit**

Run: `python -m pytest tests/research/test_codex_exec.py tests/research/test_codex_provider.py -q; ruff check .; python -m mypy .`

Expected: PASS.

```powershell
git add research/llm/codex_exec.py research/llm/provider.py schemas/research_intent.schema.json tests/research/test_codex_exec.py
git commit -m "feat: add Codex exec structured intent provider"
```

### Task 3: Add the Codex Desktop stdio MCP server

**Files:**
- Create: `integrations/codex_mcp_server.py`
- Create: `integrations/codex_mcp_protocol.py`
- Modify: `pyproject.toml`
- Test: `tests/integrations/test_codex_mcp_server.py`

- [x] **Step 1: Write failing MCP protocol tests**

Test initialize, tools/list, and tools/call for `get_research_context`, `list_features`, `get_dashboard_status`, `submit_research_intent`, and `run_evaluation`. Assert responses are JSON-RPC objects, malformed requests return errors, and the listed tools contain no order, live-account, credential, raw-market, sealed-OOS, or arbitrary-file-write tool.

- [x] **Step 2: Run the protocol tests and verify failure**

Run: `python -m pytest tests/integrations/test_codex_mcp_server.py -q`

Expected: FAIL because the stdio MCP server and protocol dispatcher do not exist.

- [x] **Step 3: Implement the local stdio server**

Read newline-delimited JSON-RPC messages from stdin and write one response per line to stdout. Return compact context from existing local builders, validate submitted intents through `ResearchDirector`, invoke only the local evaluation service for evaluation requests, and use the existing snapshot store for dashboard reads. Send diagnostics only to stderr and never include credentials in responses.

- [x] **Step 4: Add a safe CLI entry point**

Add a `codex-mcp` command or module entry point that accepts only `--state-dir` and `--project-root`, binds to stdio, and does not start a network listener. Keep KIS account refresh out of MCP tool calls unless the request explicitly uses the existing paper-only read-only service.

- [x] **Step 5: Run focused tests and commit**

Run: `python -m pytest tests/integrations/test_codex_mcp_server.py -q; ruff check .; python -m mypy .`

Expected: PASS.

```powershell
git add integrations/codex_mcp_server.py integrations/codex_mcp_protocol.py pyproject.toml tests/integrations/test_codex_mcp_server.py
git commit -m "feat: expose safe Codex Desktop MCP server"
```

### Task 4: Connect the research loop and dashboard heartbeat

**Files:**
- Modify: `cli.py`
- Modify: `orchestration/generation.py`
- Modify: `runtime/heartbeat.py`
- Modify: `dashboard/contracts.py`
- Modify: `dashboard/state.py`
- Modify: `dashboard/static/index.html`
- Modify: `dashboard/static/app.js`
- Test: `tests/cli/test_codex_cli.py`
- Test: `tests/dashboard/test_llm_status.py`

- [x] **Step 1: Write failing integration tests**

Test an explicit `research-intent` command using a fake Codex executable, assert the sanitized context is written to no persistent credential-bearing location, the returned intent is stored only after validation, and the dashboard reports Codex worker state as `ONLINE`, `STALE`, or `OFFLINE` from heartbeat files.

- [x] **Step 2: Run focused tests and verify failure**

Run: `python -m pytest tests/cli/test_codex_cli.py tests/dashboard/test_llm_status.py -q`

Expected: FAIL because the CLI command, provider wiring, and dashboard LLM status do not exist.

- [x] **Step 3: Preserve trigger policy and expose the provider call path**

The existing `GenerationRunner` and `should_call_llm` policy gates remain the
generation trigger authority. The Desktop path is operator-driven through MCP, while
the explicit `research-intent` command provides the local `codex exec` call path. Both
paths preserve offline/local evaluation behavior when Codex is unavailable; provider
status is written as a redacted heartbeat for the dashboard.

- [x] **Step 4: Add dashboard status fields and rendering**

Show provider (`codex_desktop`), last call time, last result (`VALIDATED`, `FAILED`, `OFFLINE`), and online worker state. Do not show prompts, tokens, raw responses, or account secrets.

- [x] **Step 5: Run focused tests and commit**

Run: `python -m pytest tests/cli/test_codex_cli.py tests/dashboard/test_llm_status.py -q; ruff check .; python -m mypy .`

Expected: PASS.

```powershell
git add cli.py orchestration/generation.py runtime/heartbeat.py dashboard/contracts.py dashboard/state.py dashboard/static/index.html dashboard/static/app.js tests/cli/test_codex_cli.py tests/dashboard/test_llm_status.py
git commit -m "feat: wire Codex research calls into operations state"
```

### Task 5: Configure Desktop MCP and complete security verification

**Files:**
- Create: `.codex/config.toml.example`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/operations/paper-dashboard.md`
- Modify: `docs/operations/deployment-gates.md`
- Test: `tests/security/test_codex_boundary.py`

- [x] **Step 1: Write failing boundary tests**

Assert Codex context excludes KIS app keys/secrets, bearer tokens, raw market rows, sealed OOS data, and real KIS URLs; MCP tool listings exclude order operations; the child Codex environment excludes KIS credentials; and a submitted intent containing code-change fields is rejected.

- [x] **Step 2: Run the boundary tests and verify failure**

Run: `python -m pytest tests/security/test_codex_boundary.py -q`

Expected: FAIL until all redaction and tool-list checks are implemented.

- [x] **Step 3: Add the project-scoped MCP example**

Document a stdio server entry with the repository Python interpreter, `codex-mcp` module, state directory, and `default_tools_approval_mode = "prompt"`. Keep the example free of credentials and bind no network port.

- [x] **Step 4: Document both connection modes**

Document Desktop MCP setup, `codex exec` automation, authentication choices, paper-only guarantees, failure behavior, and the fact that the exact Desktop conversation is not implicitly reused by a separate `codex exec` process.

- [x] **Step 5: Run the complete verification suite**

Run:

```powershell
python -m pytest --cov=. --cov-report=term-missing
ruff check .
python -m mypy .
git diff --check
docker info --format 'DOCKER_SERVER={{.ServerVersion}}'
```

Expected: all tests pass, coverage remains at least 80%, Ruff and mypy pass, the Docker daemon is reachable, and no changed tracked file contains credentials.

- [x] **Step 6: Commit the configuration and security documentation**

```powershell
git add .codex/config.toml.example .env.example README.md docs/operations/paper-dashboard.md docs/operations/deployment-gates.md tests/security/test_codex_boundary.py
git commit -m "docs: configure Codex Desktop research connection"
```

---

## Self-review checklist

- The Desktop and automation paths share one Pydantic `ResearchIntent` validator.
- Codex receives compact summaries only; raw market and sealed OOS data remain local.
- The LLM cannot modify Python, evaluator code, or order state through the exposed tools.
- KIS remains paper-only; no MCP order tool and no real KIS endpoint are reachable from the research bridge.
- Codex unavailability degrades the research loop but does not bypass local evaluation gates.
- The exact interactive Desktop conversation is not assumed to be available to `codex exec`; App Server remains a separate future integration if session continuity is required.
