# Quant AutoResearch — Unified MCP Research Source (2026-10-26)

**Stage:** T4-CROSS-FORK-CONSOLIDATION-20261026; **user value:** restore one reviewable source tree containing previously developed Quant v2, generalization, benchmark, dashboard and PythonMCP/SDK components. **Q IDs:** Q02, Q04–Q12, Q14–Q17, Q19–Q20. **Acceptance:** every relevant known Git branch tip reachable from unified source branch, 32 ChatGPT↔Quant MCP tools and 173-feature library preserved, key integrated code tests pass, original signed study ledger/OAuth/OOS/orders never touched. **Next frozen order:** V05 cost/stats → T4 authenticated ChatGPT↔Quant MCP real research → V01–V04 PIT/OOS → V06 paper-only → V07 GO/NO-GO. No change to user-approved decision files or protected core. This is *source consolidation*, not production rollout or completion of every planned runtime capability.

## What was actually integrated

A clean worktree was created from the newest `feat/quant-generalization-v2-20261024` branch at `8ec2e9c`:

`/shared/moon-workspace/AutoResearchFinance_v2-unified-20261026` → `feat/quant-unified-mcp-20261026`.

Ancestry and scope:

| Branch/source | Committed tip | Merged or already inherited | Functionality |
|---|---|---|---|
| `feat/quant-same-session-350-20261019` | `5483a1f` | inherited | original 350-generation academic research, catalog, initial Pine research |
| `feat/quant-fresh-research-20261021` | `20dcece` | inherited | original development research, costs and OOS guard evidence |
| `feat/quant-parent-portfolio-20261021` | `bfd7205` | inherited | direct MCP GPT research, P2/S7/S8, memory, F1/F2/F3, V3 development modules |
| `feat/quant-generalization-v2-20261024` | `8ec2e9c` | integration base | annual generalization, P4 model capture and strict parent/S7 quality, T4 checkpoint safety and normalized-feature units, original P5 dashboard |
| `feat/quant-benchmark-missing-gate-20261024` | `150043e` | via benchmark-preflight | distinguish missing QQQ benchmark and genuine underperformance |
| `feat/quant-benchmark-preflight-20261024` | `b34ec20` | merge `6f3da9d` | fail closed on missing mandatory QQQ benchmark, retain other evidence |
| `feat/quant-dashboard-recovery-20261024` | `936fea5` | merge `b7e7f54` | robust read-only HTTP API/status/zero-trade nullable metrics/isolated cohort views |
| `docs/quant-generalization-plan-20261024` | `49cef15` | already inherited | original generalization design and scope |
| `AutoResearchFinance_PythonMCP:main` | `d0c0862` | merge `8d467ee` | read-only separate MCP client, optional Codex SDK adapters, signed-collector handoff, SHA audits and non-PIT dataset preparation, developer tests |
| source worktree PythonMCP **uncommitted** | untracked and modified files | selected `a7445e6` patch only | fail-closed no-eligible-parent fallback back to exploration; 3 regression cases |

**Critical protection:** merged code keeps `ChatGPT GPT → Quant MCP submit_algorithm_plan/submit_algorithm_diagnosis → Quant typed backtest/S7/append-only checkpoint → ChatGPT next generation` as the main research mode. Codex structured model host is **optional isolated experiment**, not the new default or proof of independent model calls. Collector signature validates only the collector. Unattested SDK generations do **not** become canonical provider-verified generations by the merge.

Merge conflict resolution preserved both sides' dated master-ledger entries; no branch was reset, force-pushed, rebased or deleted. Production v2 and PythonMCP worktrees (including existing uncommitted changes) remained unchanged. Untracked Codex-only batch controller is intentionally NOT made a default Quant research service: it directly asks the SDK model to decide and does not follow the user-approved direct MCP GPT architecture. The experimental original remains in its original worktree.

## Broader original-v2 GitHub branch census (important qualification)

The original GitHub `AutoResearchFinance_v2` remote contains **129 visible branch heads** as fetched on 2026-10-26. **Eight** recent heads were direct ancestors of this unified branch after the merges. **121** older heads (including pre-October `codex/*`, previous `deploy/*`, early paper/V05/T4 feature branches and legacy master) are **disconnected Git histories with no merge-base at all**, likely from earlier repository bootstrap/import epochs. A missing ancestry relation **does not prove a capability is absent**: the modern v2 tree includes many similarly named modules and their tests. Blind Git merge with `--allow-unrelated-histories` would risk reverting protected core and OAuth/MCP policy, and was intentionally **not** performed. Their content must be triaged through source-file and semantic contracts separately before any further cherry-pick. **Do not label this as all 129 branch histories merged.**

The targeted source integration addressed all local modern branches with shared common ancestry, plus PythonMCP `main` with shared source lineage. Tracked features like 173 generic indicators, direct 32-tool MCP, F1–F3/S7/S8, V3 development adapters and QQQ benchmark repair were preserved. The disconnected old Git histories are now listed as an **outstanding review scope**, not as missing/stolen/deleted project work.

## Capability levels are separate

1. **Code presence / executable unit tests**: 173 generic feature specifications, V3 compositional crossover and regime shared-NAV simulation, Pine import research modules, F1/F2/F3 weakness/contribution, generalization P4 and normalized-unit gates are retained.
2. **Active typed GPT↔MCP generation**: 32 registered tools including start/get/plan/diagnosis/S7/reconcile; actual production 68/100 separate GPT-assisted research ledger documented. Academic verified indicator catalog has **8 verified** out of 11 curated research candidates; other 173 generic indicators are not automatically eligible. Parent V2 and F2/experiment memory are active in the academic model context.
3. **Unfinished E2E integration**: validated registry expansion to safe typed academic calculator, F3→F4 failure/contribution long-memory automatic injection, user-Pine P1–P7 final original-replication/LLM-use, V3 role-based parent crossover→canonical S2/S7→counted parent promotion, V3 multi-sleeve regime shared-NAV→canonical counted research, independent GPT attribution, true unsealed PIT/OOS and deployment. A source merge **does not** close these gates.

## Testing and deployment

- Original v2 development Python environment lacks optional `openai_codex`, so an early mixed test run produced failures due to optional dependency and was interrupted at the execution time cap. **Do not claim it passed.** A separate optional `PythonMCP/.venv` interpreter was used only for unified workspace offline testing. No login or network model request.
- Verified **95 passed** core MCP/academic/benchmark/P4/security tests and **241 passed, 4 skipped** F1–F3, V3, dashboard, registry and generalization tests, under the optional SDK-equipped PythonMCP virtual environment. Independently **42 passed** Codex SDK adapter/data tests; **3 passed** newly merged P4 parent eligibility regression; and **5 passed** new cross-fork capability contract. These scoped successful runs sum to **386 passed, 4 skipped** across individual successful runs; some tests overlap and this is **not** a unique repository-wide test count. A prior v2-only environment showed missing optional `openai_codex` (8 failures reported before the run timed out); the cause was verified and its corresponding 42 SDK tests passed with the correct isolated interpreter. New tests initially failed (as expected) for the P4 no-parent bug and for an initially incorrect test-signature assumption, then were fixed and re-run. All these failures are documented instead of silently erased.
- Full repository `ruff check .`: **PASS**; `mypy` targeted **10 source files PASS**; `git diff --check`: PASS. Full repo pytest/mypy, production re-deployment and 2026 OOS **NOT RUN**.
- Preservation smoke: shared baseline interview SHA256 `ab41bbb68bf410ae9914c628d38915678472d5a906ee75e2cf2dae9ad8bfb801`; 32 original MCP tools; >=173 feature descriptors. Orders remain disabled, OOS sealed in the operational service. No original runtime state or market series copied into Git; an ignored single development data fixture was copied locally to allow tests. No service restart, no OAuth/token access, no real broker, no new official generations.
- The unified source exists in a *separate, reviewable Git branch*, not the live Quant MCP code. Production cutover requires review of pending end-to-end gates, full test and restore checks, and separate explicit approval. The integrated branch itself can be pushed without altering any production branch or MCP/OAuth settings.

## Safe follow-on (not falsely counted done)

1. Validate canonical typed adapter coverage for the 173 registry features; register only mathematically/time verified candidates, report eligible count and reject others.
2. Bind F3 audited S7 parent/child contributions to F4 evidence memory with explicit source/equity/hash verification, and verify a real MCP model uses them in 3→10 new generations.
3. Integrate V3 crossover and regime multi-sleeve adapters with original strategy IR and full costed S2/S7, shared portfolio accounting and parent provenance before counted academic promotion.
4. Preserve all original session IDs and evidence-chain hashes; never sum P5 28, v2 68, isolated PythonMCP 33, original 452, deterministic 552 into one `completed` count.
5. Only after those gates pass evaluate an opt-in replacement of the production Quant code, retaining existing fixed URL, ChatGPT OAuth and read-only recoverable immutable state.
