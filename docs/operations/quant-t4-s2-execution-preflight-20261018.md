# T4 S2 execution identity guard (2026-10-18)

Branch `feat/t4-s2-execution-identity-20261018`, based on deployed `e36d258`, **NOT DEPLOYED**. Current production pin and OAuth unchanged.

## Change

An optional `require_execution_change: true` property is now available in `submit_algorithm_plan` (SDK tool schema + typed server request). When the candidate is an inherited StrategyIR plan, the service replays the selected parent using canonical DEVELOPMENT execution auditing and compares `(execution_timestamp, side)` of every canonical fill against the inherited candidate S2 audit. If buy/sell timing is identical despite a changed StrategyIR hash, fail with `UNCHANGED_INHERITED_EXECUTIONS` before claiming the session checkpoint. Invalid nonboolean values are rejected. The comparison does **not** touch private OOS, source generation rows, existing OAuth URL, or broker APIs. Current inherited duplicate StrategyIR hash check remains separately enforced. Option defaults **false** for backwards compatibility with the old 33-generation historical tests; opt-in is required until a separately validated prospective rollout allows it to become mandatory.

A changed timestamp/side schedule is only proof that *executions changed*; it does not establish return improvement, causality, sound finance or OOS robustness. Equal timestamp+side sequences are flagged despite possible hypothetical size differences; the current canonical inherited setting uses fixed 100% cash sizing, so this is a controlled first gate. Future execution-identity work could explicitly include fill sizes and equity/cost calculations.

## Validation

- Two new original G33 immutable historical fixture tests verify identical-execution rejection leaves token, phase, number of generations and **all prior evidence hashes unchanged**, and that nonboolean request flag fails before any write.
- After preserving the legacy default behavior, relevant inheritance/MCP integration regression: **36 passed / 0 failed**. Before this compatibility correction a mandatory guard had caused two legacy historical tests to fail. Discarded the mandatory behavior; no relaxation of the live S7 signal-change gate.
- Ruff and targeted MyPy `application/academic_checkpoint_service.py` + `integrations/chatgpt_mcp_sdk.py`: PASS. All 1,729 full-suite tests **NOT RE-RUN** after these modifications: **no operating deployment approved**.

## Actual G181 status

At work start, authenticated existing `get_algorithm_research` already reported local **81/100** (global **181/300**) in `AWAITING_PLAN`, so this task **did not submit any new plan/diagnosis or alter the real research history**. The user may have advanced G181 in another active session. G181 latest generation had development net return about **32.08%**, MDD **9.43%** and a S7 experimental child improved final equity by approximately **$3,140** relative to that G181 studied parent. These are development comparisons, not independently evaluated OOS return or permission for promotion.

Next: verify enhanced MCP tool schema and test end-to-end with a *new* isolated HTTP + OAuth fixture, run all 1,729+ tests, then pin a new immutable release with backup/rollback while retaining the original `/quant/mcp` URL and existing credentials. For actual GPT research, pass `require_execution_change=true` on G182+ plan submissions only after deployed schema accepts it; runtime flag false until then. Document separately from the pinned running SHA.
