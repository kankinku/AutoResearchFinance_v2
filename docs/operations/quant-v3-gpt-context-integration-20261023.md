# Quant AutoResearch V3 — authenticated MCP next-plan research memory integration

Date: 2026-10-23 KST
Status: **DEVELOPMENT_CODE + ISOLATED G452 CHECKPOINT PASS; LIVE GPT 10/100 NOT RUN**

## Stage / user goal / hard boundary

- Frozen stage: **T4(S4/S5) prerequisite**, Q02/Q05/Q06/Q07/Q08/Q09/Q14/Q17/Q20. This is **not** a change to the user-confirmed priority order V05 → T4 actual GPT 10 then 100 → V01–V04 external PIT/OOS → V06 non-order paper → V07.
- Goal: expose actual prior audited multi-parent **negative findings** to the next connected GPT Research Director's proposal context, so it can avoid repeating economically identical candidates and formulate a different falsifiable hypothesis.
- Hard scope: **opt-in memory-only**. No direct composite parent promotion, no overwrite of `AcademicMCPCheckpointService` normal selector, no real model provider call, no generated counted generation, no OAuth/default URL changes, no external API charges, no orders, no access to sealed OOS.

## Code changes

- `research/llm/v3_parent_sidecar.py`: `ResearchParentSidecar.read_verified_summary(path,cohort_id,dataset_hash,known_ancestor_hashes)`. SQLite `mode=ro` + explicit consistent `BEGIN` read transaction; verify complete local event chain and pinned manifest. Reject missing path/symlink, unknown cohort, mismatched QQQ dataset, source head absent from existing counted ancestors, mutated event or mismatched projection count. **Does not create/alter DB.**
- Output summary is compact and grounded: `attempt_count`, rejection-reason counts, last 12 source role tuples and their recorded rejection reasons, immutable sidecar last event SHA, sidecar provisional held-parent hash, research hypothesis guideline, `SCRIPTED_NOT_GPT` provenance and explicit `model_autonomy_verified=false`, `official_generation_increment=0`, `automatic_parent_adoption=false`, `parent_scope=SIDECAR_PROVISIONAL_ONLY_NOT_EXECUTION_PARENT`.
- `application/academic_checkpoint_service.py`: new **optional** constructor argument `v3_research_memory=(Path,cohort_id)`, default `None`. When explicitly enabled, the `AWAITING_PLAN` model context includes `v3_prior_crossover_research` only after checking dataset and that the fixed source evidence SHA actually belongs to current counted-session ancestry. Invalid/missing/mutated read receipts raise `CycleStateError` (**fail closed**), never silently select an unverified composite. This is an advisory context field, not a generated/committed GPT proposal and not a counted parent mutation.

## Real isolated checkpoint experiment

- `scripts/verify_v3_checkpoint_memory_clone.py` clones original QQQ academic research `G452/452` via SQLite backup to a disposable workspace, extends **only the disposable checkpoint** to `AWAITING_PLAN` for generation G453, explicitly activates `parent_portfolio_v2=True` and V3 memory, then calls `get({"session_id":...})` as a real existing authenticated-MCP service read. **No plan submission occurs.**
- Actual G453 planning context includes **6 prior audited development crossovers**:
  - `REJECT_RISK`: 3;
  - `REJECT_ECONOMIC_DUPLICATE`: 2;
  - `REJECT_PRIOR_CANDIDATE_DUPLICATE`: 1.
- Research memory chain head `0306222f9bc442fbd6bec3aaeb9ee404621beb51f003a633f972f14464ab9ce7`; pinned ancestor G452 evidence `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`. **The existing actual execution parent remains G68** (strategy SHA `12be5bc19a1aaff9d70fd527e315a3e0a62f7bd7b6854d4addf4272f3453306b`). Sidecar merely holds its separate provisional G192 parent and does **not** override G68.
- Repeat `get` returns the identical V3 research memory; missing/incorrect cohort ID → `CycleStateError`; without opt-in flag, old service returns **no V3 memory**. User's live server and original checkpoint remain unchanged, no external GPT calls or orders.
- The source G452 and separate G552 evidence SHA/generation counts, OAuth registrations, fixed Moon URLs, dashboards and OOS remain unchanged; verify separately before release.

## Validation status / limitations

- TDD: new `tests/research/test_v3_checkpoint_memory.py` initially failed due to missing read-only summary, now all tests passed.
- Relevant research/parent/P2/governance tests **39 PASS**; Ruff for changed files **PASS**; new `v3_parent_sidecar.py` Mypy PASS; actual disposable G452 checkpoint (G453 planning context) smoke **PASS**. Full repo Pytest / full Mypy **NOT RUN** in this slice.
- The local sidecar chain verifies self-consistency, **not cryptographic external attestation**. Inputs initially came from the independently cost-replayed runner, but an actor with full filesystem write access could rewrite the complete SQLite chain. This cannot be equated to genuine GPT model provenance.
- `get` provides research memory context only; **actual GPT next Plan→costed S2→model diagnosis→S7→next Plan→counted generation** is not executed. Cannot report GPT 10/100 completed from this feature. Existing composite C+D strategy execution in the normal counted path is still blocked on explicit type-validated mixed-genome compiler/adapters and independent regression review. The user values this verified loop, so avoid expanding new standalone diagnostics without delivering actual connected GPT execution next.

## Next confirmed task

1. Use the existing authenticated ChatGPT MCP research tool in a **permissioned isolated research session**, with opt-in V3 memory, to generate and store actual model-authored Plan/diagnosis and follow-up; verify actual model response receipts and provenance. First target **10 complete generations**, then expand to 100 only if all safety/lineage/risk gates pass.
2. Promote a V3 composite parent **only** when valid replay, nonduplicative costed result, S7 direction and the official typed academic checkpoint generation path are all independently proven. Do not use a synthetic or fixed controller to count generations or imply alpha.
3. Keep V05 → T4 → V01–V04 → V06 → V07 and off-by-default orders/OOS unchanged.
