# Quant MCP input-stream latency investigation — 2026-10-28

## Scope and evidence
- Official academic session: 200→250 generations, development-only (non-PIT), sealed 2026 OOS not evaluated, orders disabled.
- The observed UI-side “Error in input stream” is consistent with lengthy synchronous MCP calls, but the client stream failure itself was not captured in the server logs.
- From the JSONL request audit, median diagnosis duration was **106.5 seconds** (13 of 14 requests exceeded 90 seconds); plan submission was around 5.9 seconds. The HTTP server returned 200 on completed calls.
- The actual bottleneck, established using full diagnosis cProfile in a SQLite backup clone, was parent portfolio selection replaying overlapping predecessor ancestry for each shortlisted candidate. It consumed about 89.4 seconds of a 110.9-second G245 test.
- Audit hashing also used recursive dataclass deep copies for immutable Trade, DecisionObservation and FillObservation fields.

## Changes
1. research/indicator_engine/decision_audit.py: same canonical JSON-compatible dictionaries, with shallow scalar fields and nested Trade dict rather than recursive copies. Audit schema and field values unchanged.
2. application/academic_checkpoint_service.py: an **invocation-scoped** memo for previously audited inherited ancestors within one parent portfolio selection. Key includes signed generation, evidence, strategy, audit, data and measured equity identity. Entries populate only after authentic S2 audit/equity checks. No persistent cache, and immutable history/S7 gates unchanged.

## Verification (same host, cloned DB; profiler overhead included)
| Path | Before | After | Observed |
| --- | ---: | ---: | --- |
| G233 full S7 evaluation | 15.76s | 4.12s | exact regenerated report hash identical |
| G245 full diagnosis→commit→S7 | 110.87s | 40.55s | prior G244 evidence head preserved; S7 persisted; orders/OOS false |
| G245 next parent pool calculation in full-profile G245 | 89.36s | 17.12s | signed parent selection logic unchanged |
| G245 pinned parent recomputation, clone | n/a | 9.97s | exact pinned selection JSON equality; G224 counted source |

Tests: audit hash fast path, controlled experiments, P3 diagnostic preflight, inherited audit warmup, parent portfolio v2 and additional autonomous/forward diagnostics.

## Operational guardrails
- Preserve Quant MCP URL/OAuth, order switch, dataset, costs, S2/S7 metrics, immutable Evidence and independent OOS status.
- Deploy only at a stable checkpoint (not RUNNING); verify evidence head, phase, URL and OAuth identity after restart.
- GPT research director: submit one counted generation's plan and diagnosis at a time. Avoid bundling several ~40-second diagnosis calls into one code-mode invocation.
- On lost responses, read the checkpoint first. Never assume a failed stream means no server commit. Use the returned AWAITING_PLAN/AWAITING_DIAGNOSIS phase and never reuse a stale token.
- Latency optimization does not implement a background queue or eliminate every possible client disconnect. Any later queue must preserve GPT-authored research and S7-before-next-plan gating.
