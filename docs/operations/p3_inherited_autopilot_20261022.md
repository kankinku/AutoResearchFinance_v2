# Quant AutoResearch — P3 inherited model research pipeline

**2026-10-22 · branch `feat/quant-parent-portfolio-20261021`**

## Scope / P3 engineering boundary

This change wires an explicitly supplied model transport to the audited P2
inherited-StrategyIR research state machine. It does **not** switch the existing
ChatGPT–MCP connector to an additional paid API, change OAuth/MCP registration,
enable paper/live orders, or create any background daemon. The production
academic session is frozen at **G452/452**, on the reused 2020–2025 QQQ
development/non-PIT dataset; the inspected 2026 period is NOT reused.

An opt-in CLI mode supports `InheritedResearchIntent` from a separate
operator-configured Responses model. **No actual paid model call has been
performed or verified in this development session.** Mocked providers prove
only the integration and cannot be counted as independent GPT reasoning.

## Implemented

- `research/llm/openai_response_transport.py`: recognizes explicit
  `InheritedResearchIntent` model context and submits its existing typed
  `ResearchIntent` JSON schema through the existing Responses HTTP transport.
  No new network endpoints, tools, credentials storage or background polling.
- `research/llm/inherited_checkpoint_autopilot.py`: bounded, explicit
  foreground runner. Verify inherited parent identity, one to six typed
  operations, S2 costed execution changes, P2 precommit child risk budget
  (configured by the service), evidence-linked model diagnosis and immutable
  counted commit followed by S7. Reject untrusted model results; no silent
  fallback to deterministic static strategy lists or lowered risk limits.
- On invalid typed plan, retry with schema repair guidance within the explicit
  model proposal budget; on precommit failure, fetch signed risk feedback from
  the same unmodified planning checkpoint and request a *different* proposal.
  Duplicate identical proposal payloads are recorded but never resubmitted
  for costly backtest. If the budget expires, stop without generation commit.
- `ModelProposalAudit`: append-only session-bound hash chain containing
  context/proposal hashes, generation, phase, committed evidence link and
  outcome, without dumping model input or API secrets. Explicit resume verifies
  each prior receipt hash, chain link and session ID; initial append never
  silently overwrites an existing audit. This is hash-integrity verification,
  not a cryptographic proof that a remote model was used.
- `scripts/run_academic_autopilot.py --p3-inherited`: explicit opt-in; only
  `--execution-mode openai-api`, explicit model, explicit
  `--confirm-paid-model-calls`, existing *waiting* session ID, and distinct
  `--p3-model-receipts` path activate the path. P3 automatically configures
  separate P2 parent + child risk gates (default max child MDD 30%, max
  increase 15pp, min 30 closed trades; may be configured explicitly). It
  requires an existing session already extended in its separate research
  state; never mutates G452 to extend production automatically.
- MCP remains the default; the presence of an API key **never** selects paid
  model execution. The previously existing academic `AlgorithmPlan` mode
  remains available without behavioral modification.

## Verification

- `tests/research/test_p3_inherited_loop.py`: mocked provider rejection,
  changed candidate retry, diagnosis and S7 handoff, evidence receipt-chain
  integrity, bounded exhaustion, unsafe-phase rejection, audit no-overwrite,
  explicit cross-session/tamper-safe resume.
- `tests/research/test_openai_response_transport.py`: mock HTTP Responses
  transport receives typed inherited schema and explicitly no server-side tools
  or storage; **network calls are mocked**.
- `tests/research/test_default_mcp_execution_policy.py`: default MCP mode
  creates no new session/API call despite possible API key, and P3 requires
  both explicit paid transport and user/operator paid-call confirmation.
- `scripts/test_p3_inherited_clone_e2e.py`: clones the 3 original G452 SQLite
  ledgers into a temporary directory, opts into P1 multi-parent and P2 parent
  and precommit child risk limits (30%, 15pp, 30 trades); injects a
  **deterministic, previously known test proposal** (change entry AND→OR)
  and a scripted evidence-bound diagnosis. The runner creates **clone G453**,
  actual costed S2 and S7, continuous evidence hashes and an append-only audit.
  Baseline G452 ledger is verified unchanged.
- Clone G453 return **+73.0338%**, MDD **27.9092%**, recorded S7 report and
  evidence hash. THESE ARE historical development results; the proposal was
  selected from a prior generation and is not a newly discovered algorithm.
- Regressions also cover legacy checkpoint-autopilot and non-P3 transport.
  No live market trial or new independent out-of-sample approval.

## Next indispensable gates

1. Exercise **one actual model-generated** inherited research proposal in a
   separate controlled, bounded operator-approved model session, persist
   transport-specific response ID, usage and the verified generation evidence
   chain. Do not claim actual GPT participation from scripted tests.
2. Replace fixed single-condition mutation limitations with a richer
   expression/regime DSL and independently reviewed compiler; do not allow
   arbitrary executable Python from model output.
3. Budget-normalized head-to-head across multiple seeds with newly acquired
   point-in-time-aware data and sealed prospective OOS; previously inspected
   2026 validation data cannot serve as fresh OOS.
4. Robust interruption recovery beyond proposal logs (e.g., interrupted S7
   after successful counted commit); require explicit checkpoint reconciliation.
5. Distinguish provider transport success, model proposal validity, verified
   S2/S7 and generalization to unseen data in dashboards and provenance logs.

## Non-executed CLI configuration example

`python -m scripts.run_academic_autopilot --project-root PATH --state-dir CLONED_STATE --session-id EXTENDED_WAITING_SESSION --execution-mode openai-api --model OPERATOR_SELECTED_MODEL --p3-inherited --confirm-paid-model-calls --p3-model-receipts NEW_RECEIPT_FILE --max-generations-this-call 1`

This example is documentation only, requires separate model API credentials and
incurs external charges when actually run. It was **not executed**.
