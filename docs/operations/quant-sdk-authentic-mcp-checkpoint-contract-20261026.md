# Quant SDK ↔ native Quant MCP: authentic checkpoint and S7 response contract

**Stage:** `T4-SDK-R2-AUTHENTIC-CHECKPOINT-20261026` · **date:** 2026-10-26 KST · **Q IDs:** Q02/Q06/Q08/Q11/Q15/Q17/Q19/Q20 · **branch:** `feat/quant-unified-mcp-20261026` · **status:** `IMPLEMENTED_TESTED, HOST_DISPATCH_BLOCKED` · **non-goals:** no new provider API, no OAuth change, no operation of live orders, no 2026 sealed OOS, no live GPT generation, no change of frozen V05→T4→V01–V04→V06→V07.

## Concrete finding and repair

The previous SDK preflight used a fixture-only response shape. Production Quant `get_algorithm_research(session_id)` at phase `AWAITING_PLAN` **does not contain** `model_context.context_hash`; this hash is issued only for the sealed `AWAITING_DIAGNOSIS` context. Additionally Quant's gateway uses `status=AWAITING_DIAGNOSIS` for staged plans whereas prior fixtures used `AWAITING_PROVIDER`. During an active study `final_report=None`, even after completed individual generations: the evidence for S7 is returned by `submit_algorithm_diagnosis` as `latest_controlled_experiments` and is retrievable by the existing `evaluate_algorithm_experiments` tool.

Therefore the old `run_sdk_generation_loop` would have rejected authentic intermediate Quant responses. The code has now been adapted to this real contract, without changing the MCP server ABI or the underlying academic ledger.

- `application/sdk_quant_generation_control.py` now treats `AWAITING_PLAN` context fingerprint as **SDK-computed local transport fingerprint only** and never as an official Quant model context hash. It requires the **server-produced** 64-hex diagnosis context digest only in `AWAITING_DIAGNOSIS`, preserving the distinction in dispatch fields `context_hash`, `model_context_fingerprint` and `model_context_fingerprint_is_local`.
- Validates the existing previous_evidence_hash chain when provided, rather than checking only syntactic hash length. The Quant source gateway itself validates canonical generation row hashes.
- `verify_diagnosis_acceptance(reply, reread, prior_completed)` requires exactly +1 completed, correct session, S7 `record_hash` matching canonical `content_hash` of the response body, correct generation and original committed evidence hash, identical committed reply/reread history head, and exactly matching experiment hypothesis IDs. `final_report` is **not** used mid-study as an S7 surrogate. Result has `independent_provider_attested=False` until an actual independent provider proof is established.
- SDK's fixture dispatcher checks the **actual diagnosis tool response**, then independently re-reads `get_algorithm_research` and confirms S7 and head identity. A reply loss still stops as `BlockedHostDispatch` pending reconcile. Existing session-scoped `flock` is local only; server's original checkpoint-token `WHERE phase AND token` conditional updates and `submission_receipts` remain authoritative. No new public write tool, server policy or database table added.

## Real-Quant-code isolated tests

- `tests/integrations/test_sdk_quant_live_checkpoint_contract.py` exercises `CodexMCPServer._dispatch` and actual `AcademicMCPCheckpointService` local development storage, with fixture model only. Covers authentic planning context missing context hash, genuine diagnosis context and status, S7 response while terminal report absent, tampered S7 record/original evidence identity, wrong expected generation, and history chain tampering.
- `tests/integrations/test_sdk_quant_tool_loop_parity.py` drives **actual local Quant `submit_algorithm_plan`, `submit_algorithm_diagnosis`, `evaluate_algorithm_experiments`, `get_algorithm_research`** with the SDK state-machine and `ScriptedResearcher` **fake model**. One complete *TEST_ONLY* generation has counted S7 evidence and correct next checkpoint, while production provider-verified generation count remains **0**. A subsequent call with no host is `BLOCKED_MODEL_HOST_DISPATCH` and does not advance.
- `tests/integrations/test_sdk_quant_generation_control.py` fixtures updated to real diagnosis context digest and hash-verified S7 receipt; no terminal-report shortcut. Existing data/phase/order checks remain.

**Limitations:** This test does **not** show a Python SDK can independently schedule a new authenticated native ChatGPT model turn. It does not prove distributed lease across two machines, supplier-signed GPT invocation, 2026 OOS or net profitable trading. The supported direct ChatGPT↔Quant MCP mode remains the only current real-host research path. Full review and optional provider dispatch must honor the original 20Q scope and user approval, not silently replace with a Codex policy model. Standard client `tools/call` is not a model invocation.

## Acceptance / remaining work

- Authenticated native ChatGPT host-turn dispatch from standalone SDK: **BLOCKED** pending verified supported interface; do not simulate.
- Server duplicate/double-submit safety: existing conditional token/CAS and replay receipts retained and tested; cross-process restart cases exercised; **distributed independent lease not claimed**.
- 173 indicators and additional F4/F5/V3/19 legacy proof remain at prior partial integration level.
- Selected integration regression suite: **109/109 PASS** (105.68 s). Whole-repository Ruff PASS, mypy on modified SDK module PASS, git diff check PASS. Full repository pytest/mypy, live host-model E2E and independent OOS were NOT RUN. Git commit/remote SHA recorded in ledger after push. Next frozen work remains V05 bounded cost/statistics + T4 genuine model host controlled 1→3→10 research; do not extend preflight work indefinitely at the expense of that gate.
