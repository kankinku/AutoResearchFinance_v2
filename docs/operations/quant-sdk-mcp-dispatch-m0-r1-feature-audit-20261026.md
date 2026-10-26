# Quant SDK → Quant MCP Phase M0/R1 + feature compiler audit

**Date:** 2026-10-26 KST
**Work ID:** T4-SDK-QUANT-M0-R1-S6-READONLY-20261026
**Status:** `PARTIAL_IMPLEMENTATION; BLOCKED_MODEL_HOST_DISPATCH` (not genuine GPT generations)
**Q IDs:** Q02/Q05/Q06/Q07/Q08/Q10/Q11/Q12/Q15/Q17/Q19/Q20
**Value:** verify the user's intended topology, introduce SDK-only run state/stop/budget guard without another strategy-designing GPT, and measure actual available indicators in both Quant catalogs.
**Boundaries:** original ChatGPT→Quant MCP remains primary; no broker, no sealed OOS read, no genuine LLM calls, no new counted generations, no change to OAuth, fixed URL, research history, user scope, production server. Preserved frozen sequence V05→T4→V01–V04→V06→V07; V05 is not silently counted done.

## A. Real SDK → Quant MCP IO and model host truth

- `scripts/probe_sdk_quant_mcp_host.py` launches a **separate isolated read-only ChatGPT-surface Quant STDIO server** using the pre-existing PythonMCP MCP client. No production HTTP auth or current operational original session is modified.
- Observed: `mcp_tool_count=32`, `feature_count=173`, `orders_enabled=false`, `model_calls=0`, `quant_status=NOT_INITIALIZED` for isolated STDIO state. **`native_chatgpt_model_turn_dispatch_verified=false`**, and `sdk_repeat_controller_status=BLOCKED_MODEL_HOST_DISPATCH`. This is client-tool IO proof **not** proof of a Python SDK scheduling a live ChatGPT model turn.
- Separately, connected production Quant MCP `get_algorithm_research` read showed session prefix `14626d55`, 68/100, `AWAITING_PLAN`, orders OFF and OOS sealed, last head `eef0a48870dddcbc5f7c5bd4d90bf391ce8400f123de3918e8763e82c4306c7e`. Purely read-only; this **does not use the new SDK preflight**.
- MCP tool `tools/call` alone cannot create model reasoning. No publicly verified SDK→native ChatGPT automated-turn scheduling adapter was discovered here. Never use optional CodexStructuredDecisionHost to silently replace the user-selected native MCP model-controller topology.

## B. SDK-only generation state-machine safety work

- `application/sdk_quant_generation_control.py` provides a **preflight/read-only controller** accepting Quant state; rejects invalid session, dataset hash, OOS/order flags, phases, completion counts, history and checkpoint tokens.
- Missing host returns `BLOCKED_MODEL_HOST_DISPATCH`, no new generations. The only dispatch-capable path requires **explicit test fixture mode with marked fake host**, and **always records `official_verified_generations=0`**. It contains no live MCP write client, LLM policy, automatic retry, server deployment or trading execution.
- Every fixture phase is re-read from authoritative service; plan only goes to diagnosis, diagnosis only adds exactly one counted generation, head and previous evidence protected. Missing hash-verified S7 report or unmatched experiment count blocks next fixture generation; changed source hash / same checkpoint token / generation jump / model transport failure stop. Model transport uncertainty requires manual `reconcile`, not an automatic replay.
- `tests/integrations/test_sdk_quant_generation_control.py` includes host missing, 1→3 budget, completed no-op, uncertain callback, untrusted host, order/OOS/session/dataset corruption, S7 absent and original head tamper. **These are test-only fake host simulations, never authentic research.**
- Remaining real R1: acquire *supported* GPT host-turn dispatch interface or prove another direct ChatGPT orchestration interface, integrate host authentication, true checkpoint locking/fencing, and exact idempotent real MCP writes before a genuine new generation. The current class must not be advertised as real automatic 100-generation production execution.

## C. Read-only 173-feature ↔ academic compiler inventory

`application/quant_feature_bridge_audit.py` and `scripts/audit_quant_feature_bridge.py` read `ResearchCatalog` SQLite using `mode=ro`, verify every academic indicator's payload hash and status, then classify `research_feature_specs()` without writing/approving any feature. Machine-readable evidence: [173-line CSV](evidence/quant-173-feature-academic-bridge-20261026.csv), [full JSON](evidence/quant-173-feature-academic-bridge-20261026.json).

| Observation | Real value | Interpretation |
|---|---:|---|
| Generic feature catalog | **173**, registered | Registered ≠ academic VERIFIED ≠ real tradable |
| Current academic candidate catalog | **11** | ResearchCatalog separate from generic FeatureRegistry |
| Academic VERIFIED | **8** | Can be considered by current typed academic compiler (still subject to data and role gates) |
| Academic PROPOSED | **3** | Not eligible; no auto-promotion |
| Generic feature exact-name match to VERIFIED | **0** | Generic `parkinson` is not automatically identical to academic `parkinson_variance`; semantic adapter and unit tests required |
| Local generic features requiring typed academic bridge | **147** | Candidate input classification only; not evidence of causal signal pass |
| Additional aligned/external data needed | **21** | Requires dated/legally usable data and PIT alignment |
| Specialized data alignment needed | **5** | Requires market microstructure/profile/session schema alignment |

The report is based on current production **read-only** `state/moon-http/research/academic-gpt-checkpoints/catalog-s6-v2.sqlite`, so it is not silently promoted into the development worktree. The classifications are *static risk buckets*, not 147 verified calculator implementations. Market transaction replay/cost/stochastic lookahead and alternate symbol formal mapping remain future development.

Repro (in unified development worktree):

```bash
PYTHONPATH=. .venv/bin/python scripts/probe_sdk_quant_mcp_host.py --state-dir state/sdk-quant-host-probe --project-root .
PYTHONPATH=. .venv/bin/python scripts/audit_quant_feature_bridge.py --catalog /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/research/academic-gpt-checkpoints/catalog-s6-v2.sqlite
```

## D. Tests and next unblock

- Feature audit and SDK preflight module tests: **12/12 PASS** (9 controller, 3 bridge). Controller S7/head-tamper regression tests were RED before patch, GREEN after.
- New isolated controller/feature tests **12/12 PASS**; expanded SDK, direct MCP, academic submission/replay, parent, scope-lock and feature comparison regression **94/94 PASS** (1 minute 41 seconds). Ruff **full repo PASS**, mypy **4 new source files PASS**, `git diff --check` PASS. This is NOT a full repository test nor native model host E2E. No new real GPT generations or production deployment.
- **Next three concrete work items:** (1) prove permitted authenticated native ChatGPT model-host turn dispatch (otherwise leave `BLOCKED_MODEL_HOST_DISPATCH` and demonstrate existing human-chat/MCP turn limitations explicitly), (2) add server-backed lease/idempotent `reconcile → read → stage` for the real host only after (1), (3) incrementally implement typed/causal adapters for an *evidence-verified* local indicator subset and verify their exact S2/S7/replay, without bulk auto-verifying 173.
- Subsequent agreed integrations: F3→F4 durable weakness/experiment outcome memory; F5 paired same-budget random comparator; V3 canonical parent crossover/regime shared portfolio; 19 legacy semantic parity rows. Hold V01–V04 PIT/OOS, V06 paper, V07 GO/NO-GO behind original gates.
