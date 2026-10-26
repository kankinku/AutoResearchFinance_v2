# Quant AutoResearch — 연구기억 L1 증거 이벤트·인계서 M0 최초 구현

- **Stage:** T4-HANDOFF-M0-EVIDENCE-BUILDER-20261026
- **Date:** 2026-10-26 KST
- **Status:** `DEVELOPMENT_CODE_ONLY; NOT_DEPLOYED; MODEL_EFFICACY_UNVERIFIED`
- **User value:** 반복 실험의 원본 해시·가설·S7 결과와 부정적 실험을 안전하게 보존·검색 가능한 최소 구조로 변환하여 다음 ChatGPT MCP 호출에서 재진입할 기반 확보.
- **Scope IDs:** Q02, Q06, Q08, Q09, Q11, Q15, Q16, Q17, Q20. Q01–Q20 기존 목표 변경 없음.
- **Frozen delivery order:** V05 비용/통계 게이트 → T4 실제 ChatGPT MCP 연구 → V01–V04 독립 PIT/OOS → V06 paper → V07 GO/NO-GO. M0는 T4에 필요한 추가 기억 구성 요소, V05나 실제 모델 호출을 완료한 것이 아님.
- **Boundaries:** original 32-tool Quant MCP, existing ChatGPT host/OAuth/fixed URL, immutable source research DBs, orders OFF, independent OOS sealed, user uncommitted work protected. A failed or incomplete source proof is never converted to a usable memory.

## Delivered code (isolated development, not live MCP tool)

- `application/research_handoff_builder.py`: `build_research_handoff(snapshot, s7_receipts)` recreates a deterministic, hash-addressed L1 event for each completed canonical generation. It **recomputes the original Quant generation evidence hash** using `AcademicCycleService._row_evidence_hash`, checks hash chain, dataset/catalog identity, scope flags and ALL S7 experiment receipt hashes and ancestor/hypothesis identities. Reuses existing `build_experiment_learning` provenance validation instead of inventing new finance acceptance rules.
- Preserves the original measured return/risk/trade metrics, each trial's measured delta, parent/child execution activity, strategy/effective-signal hashes, S7 record/experiment references, failed or inconclusive trial statuses, and `NOT_CAUSALLY_VERIFIED` distinction. Every derived event is separately content hashed. It does NOT invent independent provider attestation, causal alpha proof or 2026 independent OOS results.
- No deletion/truncation of original evidence. `brief` is a simple deterministic projection of last ≤3 measured events plus **all** negative/unresolved experiment pointers, alongside Quant's existing `experiment_learning.next_test_priority`. No LLM-generated prose summary, long-term score-tuning or vector DB is installed.
- `compact_handoff_view` returns only the derived small research view, **not** all source events; it rechecks the canonical generation chain and S7 receipts before handing back data. Missing material within the trial's configurable character budget triggers `ESCALATE_EVIDENCE_REPLAY`, not silent removal. The full typed plan schema remains accessible from original Quant tools; the small view is not yet model-validation approved and is **not** automatically passed to GPT.
- `assert_handoff_fresh` detects stale or tampered handoff against current source head/session/dataset/catalog/phase; input `checkpoint_token` is neither copied nor saved. Derived docs and hashes are non-authoritative, can be rebuilt from original records.
- `tests/research/test_evidence_handoff_m0.py`: authentic **isolated local Quant** plan→diagnosis→S7 fixture (NOT genuine model provider), deterministic/replay, no input mutation, evidence and S7 tamper, stale source, character budget fail-closed, zero new official generations, compact-view no-secret, recheck missing receipt.

## Security and present limits

1. **Production is unchanged:** no new MCP tool registered, no API or dashboard default changed, no operational research generation added, no new model calls, no additional financial data vendors, no import of sealed OOS. For real use, an authenticated read-only server-side accessor must supply existing immutable S7 receipts directly without causing re-evaluation/writes; `evaluate_algorithm_experiments` can reconstruct absent records and must NOT be called as a supposedly read-only accessor on the production store.
2. **Only M0 evidence extraction is implemented.** Old event indices are projected but do not yet perform policy-level selective retrieval, critical safety-fact recall scoring, F3→F4 durable memory, F5 same-budget ablations, full 173-indicator typed academic, V3 canonical counted S2/S7 or Pine real-GPT adoption.
3. `brief` budget is provisional serialised-character count, **not an actual model token count**. User-approved default is data-driven, not a fixed 20,000 character standard. Full-context vs compact ablation, 40–60 source-grounded QA, token quality/cost and real ChatGPT followup must precede rollout.
4. Exact frame: SDK remains the caller, Quant remains the policy/evidence owner, and a real GPT host still needs to author the plan and diagnosis. `tools/call` is not a new model turn; autonomous unattended SDK GPT turns remain `BLOCKED_MODEL_HOST_DISPATCH`.

## Tests and next sequence

**Actually executed:** 44/44 scoped tests PASS (new 7 test cases + SDK authentic MCP replay, learning, memory, original governance), whole repository Ruff `check .` PASS, changed source `mypy application/research_handoff_builder.py` PASS, `git diff --check` PASS. In a purely scripted isolated 2-generation study, derived full L1 handoff JSON is **7,713 chars**, the selective brief itself **3,670 chars**, and the returned compact view **4,451 chars**. **This is not a provider/token or 68-generation compression benchmark**; actual provider-authenticated GPT calls = 0, canonical production generations added = 0. Full repository pytest/mypy and independent PIT/OOS were NOT RUN. Models were fixture-only.

**Next 3 tasks:** (1) approved opt-in server-side **read-only** S7+canonical snapshot retrieval, existing 32-tool ABI unchanged; (2) deterministic L2 exact-parent failure/contradiction lookup with 40–60 fact questions, including retrieval quality/fail-closed checks; (3) L3 compact planning/diagnosis context comparison to full context with input/output tokens and model quality, first isolated 1→3 generation then more only if justified. Continue V05 cost/statistics gate and T4 real authenticated GPT turn verification in original frozen order.
