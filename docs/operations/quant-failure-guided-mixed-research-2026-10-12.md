# Failure-guided local research replanning — MVP vertical slice (2026-10-12)

## Why this work takes precedence

The product goal is *natural-language research → evaluate → interpret failed gate evidence → generate a different strategy hypothesis → evaluate again → auditable result*. Further DSR/CPCV research does not itself close the research feedback loop.

Before this change, the GPT batch executor froze one initial ResearchIntent and searched fixed parameter domains for N generations. When every candidate was rejected, the parent remained unchanged and later generations could repeat the same effective strategy.

## Delivered scope

- Existing validated `ResearchIntent.mode="mixed"` opts into **bounded evidence-guided local replanning**. No new MCP tool or input schema is necessary. Existing `parameter` and `structure` requests keep their old behavior.
- After an actual, completed, non-injected evaluation attempt, the system reads **checksum-validated immutable Evidence** and only considers a new experiment when **all** evaluated candidates are `REJECT`. No verified attempt, empty/unknown failure gates, survivors or fabricated return values yield no failure-led plan.
- The small deterministic hypothesis menu currently covers risk sizing, stop-loss, take-profit and simple numeric entry-threshold mutations. The most frequent failed gate influences which experiment is tried first. These are *hypotheses*, not claims that the gate failure was caused by that parameter.
- New candidates use the existing typed Strategy IR mutation engine, generation backend, recorded initial operations and bounded parameter domains. The preview rejects already evaluated **executable semantic hashes** and candidate spaces lacking novel strategies. Changes do not waive any risk/performance thresholds, allow a protected market data zone, or authorize orders.
- Each generation's immutable Evidence records `next_hypothesis` and `applied_hypothesis`, with the triggering attempt ID, method, touched paths, novelty preview, `HYPOTHESIS_NOT_VERIFIED_CAUSE`, and `REUSED_DEVELOPMENT_DATA_NOT_INDEPENDENT_OOS` caution. Failed/no-verified-feedback replanning is recorded explicitly. No historical Evidence is overwritten.
- Existing batch report adds `adaptive_replanned_generations`, `adaptive_applied_generations`, and read-only per-generation annotations, with `research_intent_mode=mixed_evidence_guided_local`. Legacy batch records without an `intent` remain readable. The brief input catalog and mixed-mode preflight state that a preflight only previews the **initial** fixed plan, not unknown future failures.

## Honest limits

- This is **locally rule-based replanning** under a fixed GPT-authored hypothesis envelope, NOT a new per-generation LLM call. It improves the failed-generation feedback loop but does not yet autonomously select new strategy families, infer economic causal mechanisms, combine multiple Frontier parents or revive RescuePool candidates.
- Reusing development-validation failures to design new candidates contaminates those reused development holdouts as an **adaptive training signal**. It must **never** be called an independent OOS or a promotion. Sealed OOS is still denied and `orders_enabled=false` stays unchanged.
- An experiment that changed a risk setting is only a newly evaluated candidate, never a verified **improvement**. Report unique candidate counts, actual evaluated instances and rejection gates; do not imply successes.
- The product can now provide the bounded mixed-mode "failure → alternative → reevaluate" flow. A fully autonomous multi-family research director, independent PIT-grade data validation, Windows Docker host acceptance and five-user MVP UX test remain separate work.

## MVP usage

In ChatGPT, request *"QQQ 평균회귀 전략을 mixed 모드로 3세대 시험하고, 탈락하면 Evidence에 근거해 다음 실험을 선택해 줘"*. The GPT selects registered source and development data, runs the existing `preflight_research_batch`, then `start_research_batch`, `get_research_batch_status`, and `get_research_batch_report`. Never supply live-order credentials. The initial ResearchIntent remains signed and bounded; the worker cannot independently contact an external model.

## Required checks

- Pytest focused and full regression, Ruff, Mypy.
- End-to-end temporary-state batch test checks a real rejected attempt produces a next hypothesis, the next attempt evaluates previously unseen strategy semantics, Evidence captures both trigger and application, and legacy non-mixed reports remain backward compatible.
- Deploy only with zero active Quant research batches; preserve OAuth, pinned URL and Moon service; read the connected GPT report after restart.
