# Quant V3 / T4 — Authenticated MCP blocker and precommit full-signal dedup fix

Date: 2026-10-23 KST
Branch: `feat/quant-parent-portfolio-20261021`

## Scope & status

- Current approved stage **T4(S4/S5)** with research dependencies Q02/Q06/Q07/Q08/Q09/Q14/Q17. User's frozen sequence remains **V05 → T4 actual GPT 10 then 100 → V01–V04 → V06 → V07**. Not a request to weaken QQQ gates or manually optimize individual strategies.
- **Authenticated Quant MCP unavailable during this turn**: connected `mcp__Qaunt_Autoresearch__get_workspace_status({})` and `list_market_data({})` returned `The tool failed internally` before usable context. Did **not** re-register OAuth/MCP, change fixed URLs, restart live services or substitute an unauthenticated tool and call it authenticated.
- Existing Moon local source remained accessible; created only ignored disposable development clone at `state/moon-http/quant-v3-chatgpt-ten-20261023/research/academic-gpt-checkpoints` via SQLite backup of G452. Ten additional generations are **requested but zero new generations were committed (G452/462 AWAITING_PLAN)**. Local plans were authored by ChatGPT in this conversation and submitted through a **local application adapter, not the external authenticated Quant MCP transport**, and have no independent provider-authenticity receipts.
- One first plan replaced G68's breakout OR-entry with `range_low_reclaim_20`. **Plan submitted and audited**, development S2 result +8.2369% cumulative, MDD14.2185%, 50 closed trades. The model then wrote a diagnosis anchored to observed loss case `5b992c9d9a62-T-000096` (about −$599 net), hypothesizing an SMA-positive regime filter. At commit, the canonical inherited cycle raised `duplicate inherited strategy signals or semantics` because the measured full entry+exit+regime signature was **already historical G79**. Thus neither the Plan nor its diagnosis earned a completed new generation.
- Existing service formerly discovered some duplicate full signatures only **after** Plan staging and an expensive diagnostic step. This produced a `RUNNING→INTERRUPTED` gateway and wasted valid GPT-authored analysis. Explicitly recovered the disposable checkpoint with its existing audited `resume()`, no history rewrite.
- A second separate authored proposal changed both the reclaim entry and vote-score exit. The new early check correctly rejected it as same full effective signals as **historical G75**, retaining the same `AWAITING_PLAN` token and allowing a corrected proposal. **No candidate performance/alpha improvement or model 10-gen completion demonstrated**.
- Actual V3 negative research memory was present in clone: P2-risk rejects3, parent economic duplicates2, previous candidate duplicate1. The counted run's selected development parent G68 was independent of the sidecar's provisional G192; automatically promoting V3 crossover parents remains prohibited.

## Code changes / correctness

1. New `research/llm/inherited_execution_identity.py`: `inherited_effective_signal_hash(compiled,market)` computes **exactly** the prior counted cycle full entry/exit/regime boolean vector hash, based on actual registered feature replay across all aligned development bars. Rejects mismatched dataset/feature vector lengths; excludes irrelevant strategy metadata.
2. `application/academic_checkpoint_service.py`: `_stage_inherited_plan` immediately computes the above full signal signature and checks it against every counted historical generation **before P3/P2 and before consuming planning token**. On duplicate, raises retryable `DUPLICATE_EFFECTIVE_INHERITED_SIGNALS ... generation X; revise ... same checkpoint token`. Does **not** weaken any existing risk/S2/S7 or counted-level dedup rule. Existing opt-in behavior and provider transport untouched.
3. `research/llm/autonomous_cycle.py`: final counted `advance_inherited` uses the **same shared function** rather than a second copy of the algorithm, ensuring no drift; retain all existing immutable final semantic, strategy hash, signal and audit checks.
4. New `tests/research/test_inherited_signal_identity_precommit.py`: complete-vector hash changes with executable AND/OR or exit condition but not metadata; patched isolated staging test proves counted-history duplicate is rejected prior to any database or diagnosis advancement.
5. **Real QQQ 1,508 bar regression** in the new ignored experimental clone: first candidate G79 duplicate rejected *at commit in old code*, recovery; after patch same exact proposal G79 rejected *at Plan precommit*, phase `AWAITING_PLAN` and checkpoint token unchanged. Distinct alternate proposal G75 rejected at Plan precommit. The historical archive was **not** modified.

## Evidence / protection
- Original source `G452/452`: tail SHA `e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337`, SQLite `integrity_check=ok`.
- Separate existing clone `G552/552`: tail SHA `f7ba0df47a2beea697e2a7ecb6b3c178336011589029af2c1d5ddd2ac5666aab`, SQLite `integrity_check=ok`.
- Current exploratory local clone `G452/462`: **counted rows 452**, same head hash, `integrity_check=ok`; no live or paper orders, no sealed OOS, no OAuth/dashboard/Moon URL changes.
- Relevant unit/regression pytest **19 PASS**, Ruff targeted PASS, new helper Mypy PASS. All-repository suite not yet executed; source clone is isolated, never representing authenticated GPT provenance.
- Local controller scripts under ignored `state/moon-http/quant-v3-chatgpt-ten-20261023/` are **not** suitable as independent certified GPT model receipts; no synthetic or deterministic experiment is rebranded as actual 10-generation autonomous research.

## Next mandatory step

Restore **the existing authenticated Quant MCP availability** without rotating OAuth/fixed endpoints; verify it maps to the correct isolated research state and expected development dataset. Then let the real connected ChatGPT Research Director author per-generation distinct typed Plan, evaluate S2, formulate evidence-linked diagnosis, run S7 paired experiments and verify next-plan inheritance. Start 10 actual completed generations, with random same-budget control and risk/novelty rejection in the Plan preflight; only then expand to 100 if proved. Do not bypass non-PIT/OOS limitations or count the current 452/462 pending clone as research completions.
