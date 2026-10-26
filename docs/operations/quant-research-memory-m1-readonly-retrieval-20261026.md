# Quant AutoResearch M1 — 불변 S7 조회·장기 연구 기억 검색·근거 필드 감사

**Date:** 2026-10-26 KST
**Stage ID:** `T4-MEMORY-M1-READONLY-S7-RETRIEVAL-20261026`
**Q IDs:** Q02/Q06/Q08/Q09/Q11/Q15/Q16/Q17/Q20
**Status:** `DEV_IMPLEMENTED_READONLY_REPLAY_PASS / PRODUCTION_MCP_UNCHANGED / GPT_QUALITY_UNTESTED`
**Goal:** 사용자 확정 5단계 기억개선에서 다음 세대 인계 이전에, 현재 Quant 원장에 있는 *실제 68세대*의 S7 증거를 쓰기 없이 검증하고 부모·개입·실패·가설별 검색 결과를 만들기.
**Frozen delivery:** V05 bounded cost/statistics → T4 real GPT MCP generations → V01–V04 protected PIT/OOS → V06 paper only → V07 GO/NO-GO. 이 작업은 V05와 실제 GPT E2E의 대체물이 아님.

## Delivered: three linked pieces

**1) Read-only authoritative S7 reader** — `application/research_s7_readonly.py`

- `read_committed_s7(checkpoint_dir, full_snapshot)` opens existing `cycles.sqlite` and `gateway.sqlite` with SQLite URI **`mode=ro`**, `PRAGMA query_only=ON`, short consistent read transactions and no connect-to-create. It compares the session status/count, stage phase/catalog, every serialized original generation row and its canonical source hash chain to the supplied snapshot. Reads and verifies **every already-stored** S7 record/hash/hypothesis link; rejects missing or corrupt S7 **without recomputing, repairing or persisting it**.
- `read_research_bundle_readonly(checkpoint_dir, session_id)` reconstructs **only a token-free canonical state snapshot** (session, phase, dataset, catalog, immutable history) from the existing source DBs and runs an independent read again before accepting the S7 evidence. It neither extracts nor outputs OAuth credentials/checkpoint tokens, source market data or private signing keys. Read snapshots spanning two SQLite databases are not guaranteed cross-DB atomic; a changed head/phase leads to rejection. Any later model action must **re-check** live server checkpoint freshness.
- This is an **internal local developer reader**, not a new public MCP tool, not a live server deployment, and not an alternative model provider.

**2) Deterministic exact-provenance memory retrieval** — `research/llm/evidence_memory_retrieval.py` and a small change in `application/research_handoff_builder.py`

- Adds `typed_intervention` exact/family fingerprints via the existing `research/llm/cross_generation_memory.intervention_identity` with source `parent_strategy_hash`. Parent-specific path and exact operation are distinct from approximate family grouping. Unknown typed interventions are never fabricated or automatically deduplicated.
- `search_evidence_memory(handoff, parent_hash, intervention_hash, finding, metric, generation, only_negative, limit)` uses hash-verified derived events and **exact keys only**, returns generation/evidence/S7 record IDs and measured delta/fills; no embeddings, probability-of-profit score, unauthorized system instructions or hidden research policy overrides.
- A bounded result includes `total_matches` and `more_evidence_requires_lookup`, so omitting older failures cannot be misrepresented as complete memory. Raw GPT narrative inside derived source remains untrusted data. A hash on the derived file is **not an authentic signature**; before operational use, the Quant server must fresh-reconstruct from canonical receipts.
- Caller controls whether it asks for `only_negative` or exact parent; same-family results cannot be treated as exact duplicate scientific trials from other parents/regimes.

**3) Source-grounding field audit** — `audit_evidence_grounding(...)`, `scripts/audit_research_memory_readonly.py` and regression tests

- Independently compares event metadata, a standard 11-field actual return/risk/trade metric group per generation and each experiment's S7/parent/child measurements to the raw accepted Quant source. User-visible CLI produces **summary statistics only**, not model text, full history, financial account IDs or raw checkpoint tokens.
- **Real operational research, read-only result** for existing session prefix `14626d55` using original Quant v2 deployed research state (`.../state/moon-http/research/academic-gpt-checkpoints`): **68/100 `AWAITING_PLAN`**; 68/68 pre-existing canonical S7 receipts located; **1,972 atomic field comparisons, zero mismatches**; 15 negative/uncertain S7 trials under current status classifier; derived `brief` 10,304 serialized characters and compact view 11,091 characters; no data truncated; 8 latest-negative search entries selected with `more_evidence_requires_lookup=true` because 15 total matches. Source evidence head `eef0a48870dddcbc…`. **No write**, model call 0, provider token count NOT RUN, GPT policy quality/causal profitability NOT MEASURED. 1,972 assertions are **correlated fields in 68 generations**, not 1,972 independent statistical tests or 1,972 long-context questions.
- Existing earlier model context baseline was **113,581 characters** (same source but different content scope); these 11,091 characters **do not include the entire original typed model contract/schemas** and may require separate retrieval. Therefore no legitimate claim of ~90% actual paid-model token cost reduction, model learning effectiveness or non-inferior quality can yet be made.

Reproduce on the integrated development worktree with existing Python environment:

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_research_memory_readonly.py \
  --academic-checkpoint-dir /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021/state/moon-http/research/academic-gpt-checkpoints \
  --session-id 14626d55fb2b461faa485df911920071 --char-budget 20000
```

## Verification details and security

- Dedicated regression files: `tests/research/test_readonly_s7_store.py`, `tests/research/test_evidence_memory_retrieval_m1.py`, plus existing `tests/research/test_evidence_handoff_m0.py`. Include actual isolated local Quant plan+diagnosis+S7, read-only byte-preserving record counts, missing/corrupt journal fail-closed, stale session/phase, symlink refusal, exact-parent/finding filter, negative-only, bounded lookup flags, event/handoff tamper and atomic field QA.
- **Executed integrated regression:** 91/91 PASS in 121.34 seconds, covering 21 tests in the three focused handoff/read-only/retrieval modules (included within 91) plus academic MCP/checkpoint/experiment learning/memory/scope governance. Whole-repository `ruff check .` PASS; changed source `mypy` 4/4 files PASS; `git diff --check` PASS. Full repository pytest/mypy, independent retrieval-scenario quality sample, native ChatGPT model-token A/B and real 1→3 model research were **NOT RUN**. Git remote commit SHA is captured in the master progress ledger after push.
- **Preservation:** original live Quant host remains deployed from `/shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021`; integrated dev worktree was not installed or restarted. All S7/data/OAuth/stage token/parent stores unchanged, orders remain OFF and independent 2026 OOS stays sealed.

## Next work / actual unblocks

1. **Gate M1b:** create a separately reviewed authenticated/opt-in server-side *read-only* compact research tool with explicit scope control, no exposure of full SQLite path or credentials, zero replay writes, backwards compatibility with existing 32-tool ABI.
2. **Gate M2:** 40–60 independent *retrieval scenarios* deliberately covering old failures, regime switches, same family/different parent, known bad strategy, stale parent and unanswered hypothesis. The **1,972 atomic assertions are NOT this test**. Measure exact fact recall, `UNKNOWN` refusals, presence of trade proof and false relevant hits; compare FULL vs compact response, including typed schemas and real provider token bills.
3. **Gate T4/continuous learning:** user-triggered GPT MCP 1→3→10 generations with checkpoint safe restart, plan→S2→diagnosis→S7→parent→memory→next GPT actual usage; F3→F4 and F5 ablation only when the memory quality guard is met. Still blocked for *unattended* standalone SDK-driven native ChatGPT model turns (`BLOCKED_MODEL_HOST_DISPATCH`). V3, 173 academic feature parity, PineCode and legacy 19 paths remain separately tracked. Cost/stat V05 and OOS locks not relaxed.
