# Quant Autoresearch — ChatGPT client workflow acceptance (2026-10-13 KST)

## Trust boundary

This is an operator runbook for **external ChatGPT-to-Moon orchestration**. The remote worker does not call an LLM, cannot enter live trading, and does not certify sealed OOS or point-in-time market data. The ChatGPT client may hold a stale cached MCP tool schema after the server deploys new tools. A server-side tool count is **not** proof that this particular ChatGPT session exposes all tool actions.

## Startup and schema sanity

1. Ask `get_workspace_status` to verify `READY` and `orders_enabled=false`.
2. Ask `get_research_brief` for `research_inputs` and `mcp_capabilities.server_tool_count`, `schema_sha256`, and `required_client_tools`. Current server-side expectation: **24 tools**.
3. Compare the tool names in the active ChatGPT client with `required_client_tools`. A mismatch indicates **client tool-metadata refresh is still required**; do not silently call the Moon dispatcher and describe it as a ChatGPT connector call. The user must refresh/reconnect the plugin in ChatGPT or open a newly connected session; it cannot be forced by the remote MCP server.
4. Read `data_path` from `research_inputs`; if `point_in_time_verified=false`, explain this before presenting any results.

## Five scripted user-request journeys

The automated tests in `tests/integrations/test_quant_workflow_ux.py` are **five distinct scripts**, **not five recruited human users**.

| User request (Korean) | MCP sequence | Decision / report contract |
|---|---|---|
| “QQQ 모의연구를 시작할 수 있나?” | `get_research_brief` | Identify dataset, registered source and server tools. Discovery alone must not launch any batch |
| “입력을 검토하고 맞으면 사전검사만 해줘” | `preflight_research_batch` | Missing data returns `DATA_FILE_NOT_FOUND` plus a `get_research_brief` correction; valid request returns `preview_only=true`; no research journal created |
| “2세대 실행하고 실패 이유까지 보고해줘” | `start_research_batch` → `get_research_batch_status(job_id)` → `get_research_batch_report(job_id)` → `get_research_evidence(research_run_id)` | Poll only when `next_action=POLL_STATUS`. After `COMPLETED`, `READ_FINAL_REPORT` and `final_report_ready=true`. No OOS/profit claims. A cancellation after completion must **not** claim a new cancellation was requested |
| “중단된 연구를 남은 세대부터 이어줘” | `get_research_batch_status(job_id)` → `resume_research_batch(job_id)` → poll and report | `INTERRUPTED` means `REVIEW_AND_RESUME`, **not automatically safe to resume**. Backend must verify dead worker, preserved input bytes, contiguous checkpoints and immutable Evidence; no re-evaluation of previous generations. Completed batches return `BATCH_NOT_INTERRUPTED` |
| “GPT가 1세대 결과를 보고 가설을 바꿔 다음 세대를 평가해줘” | `start_guided_research` → `get_guided_research` → `submit_guided_generation` → repeat until completed | Every generation requires a **fresh checkpoint token** and external GPT decision. Duplicate executable IR rejected without token consumption; new strategy must differ semantically. Preserve previous run ID and immutable Evidence. Never describe deterministic local worker as a GPT model |

## Error recovery semantics

- `DATA_FILE_NOT_FOUND`, `SOURCE_FILE_NOT_FOUND`, and `PARENT_ID_MISMATCH`: use real registered paths and IDs from `get_research_brief`, then redo preflight.
- `BATCH_NOT_INTERRUPTED`: do not issue another resume; read status and final report.
- `CHECKPOINT_MISSING`, `CHECKPOINT_MISMATCH`, `CHECKPOINT_INPUT_CHANGED` or incomplete Evidence: **do not replay** the ambiguous generation. Keep interrupted, inspect Evidence and system logs. Old batches without checkpoints are not silently reconstructable.
- `DUPLICATE_STRATEGY` in GPT-guided mode: submit a *different validated executable IR* using the current valid token. Merely changing the rationale, name or parent metadata is insufficient.
- `QUEUED` / `RUNNING` next action: `POLL_STATUS`; cancellation requested and not yet effective: `WAIT_FOR_CANCELLATION`. `COMPLETED`: `READ_FINAL_REPORT`. `FAILED`: `REVIEW_FAILURE`. `CANCELLED`: terminal, not a resumable interruption.
- Stop/Cancel is not synonymous with interruption/restart. A cancel after completion returns `cancellation_request_accepted=false` and must not falsely report success.
- Suppress detailed internal paths, OAuth tokens, secret inputs, market rows, order payloads and sealed OOS from user-visible tool errors.

## Verified and unverified

Verified: isolated SDK-level five-journey integration; authenticated HTTP OAuth tools/list and get_research_brief; server capability fingerprint; QQQ paper-mode legacy calls; no-order invariants. See repository test summaries and handoff.

Still pending: active ChatGPT connector exposing all updated tools **after user reconnect**; true multi-person human usability testing; Windows Docker/host restart lifecycle; independent historical PIT market-data certification.
