# Quant Autoresearch Harness Threat Model

Snapshot status: frozen; approval status: not established.

Date: 2026-09-02

Baseline: pre-Task-0 commit `7e9c45daa769cd0ad099d432d3f74b498a982f82` on
branch `codex/quant-autoresearch-harness`.

This document records the security boundary for the paper-only research harness. It
does not authorize live trading, add an order capability, or replace the approved
architecture in `docs/architecture/quant-autoresearch-architecture-v1.0.md`.

## Scope and upstream references

The harness adapts the research-loop idea from
[`karpathy/autoresearch` README.md at pinned commit
228791f](https://raw.githubusercontent.com/karpathy/autoresearch/228791fb499afffb54b46200aca536f79142f117/README.md)
and its pinned
[`program.md`](https://raw.githubusercontent.com/karpathy/autoresearch/228791fb499afffb54b46200aca536f79142f117/program.md).
The README describes the three-file layout and fixed five-minute experiment budget
(lines 11–17), and its design choices describe the single-file, fixed-budget
workflow (lines 55–58). The pinned `program.md` defines the experiment loop at
line 80, including the literal `LOOP FOREVER` instruction at line 80 and
`NEVER STOP` instruction at line 94; the file ends at line 97. The local harness does not adopt
those unbounded instructions; it treats them as a hazard requiring explicit local
resource and exhaustion controls.

The related skill/workflow material is the community-derived
[`multica-ai/andrej-karpathy-skills` README.md at pinned commit
2c60614](https://raw.githubusercontent.com/multica-ai/andrej-karpathy-skills/2c606141936f1eeef17fa3043a72095b4765b9c2/README.md),
not authoritative upstream. Its README identifies itself as derived guidance and
lists the four principles (lines 7, 23–30); its install guidance references
[`forrestchang/andrej-karpathy-skills` `CLAUDE.md` at immutable commit
8462496](https://raw.githubusercontent.com/forrestchang/andrej-karpathy-skills/8462496b34419f20b32778610571ac723e91f94c/CLAUDE.md)
(Multica README lines 90–113; referenced file sections 1–4, lines 7–59).
The pinned snapshots identify what the audit reviewed; they are not live
verification, security authority, or evidence that this repository can trade.

Research is paper-only. The research process has no live order capability, does not
receive KIS credentials, and the repository does not submit live orders. Any future
order-capable deployment must remain a separate process and trust boundary with an
explicit, current human approval.

## Upstream guidance and safe adaptation

The upstream references inform workflow shape, not security authority:

The upstream `karpathy/autoresearch` layout is an adaptation/reference for this
boundary, not a claim that this repository literally executes the upstream file
layout. In that reference, the fixed, read-only `prepare.py` controls the data,
evaluation, and preparation boundary, while the experimenter may edit `train.py`.
Here, that separation maps conceptually to protected data/evaluation/preparation
controls versus candidate changes expressed in validated Strategy IR; this
repository does not treat upstream `prepare.py` or `train.py` as its own
execution files.

The upstream `LOOP FOREVER` / `NEVER STOP` instruction describes an intentionally
unbounded overall experiment loop. Only each individual experiment's metric and
time budget is fixed; the upstream overall loop is not bounded. This repository
must therefore enforce bounded generations, queue size, concurrency, retries,
timeouts, and CPU/memory/process resources, with explicit exhaustion behavior.
The whole upstream loop must not be described as bounded or adopted without
those local limits.

| Upstream guidance | Concrete local adaptation | Hazard if copied without controls |
|---|---|---|
| `karpathy/autoresearch`: fixed/read-only `prepare.py` controls the data, evaluation, and preparation boundary; `train.py` is editable, while the overall `LOOP FOREVER` / `NEVER STOP` loop is intentionally unbounded | Adapt the boundary conceptually: keep candidate changes in validated Strategy IR, compile generated artifacts, and run a locally bounded evaluation loop; protected evaluator/data/cost/integrity paths remain outside Research Director writes | Copying the editable-worker split without controls can cross the worker boundary; copying the unbounded overall loop can consume resources; an untrusted metric can reward unsafe or manipulated behavior |
| `multica-ai/andrej-karpathy-skills`: Think Before Coding | Require an explicit research intent and validated inputs before local mutation/execution | Planning language alone does not authenticate inputs or prevent prompt injection |
| `multica-ai/andrej-karpathy-skills`: Simplicity First | Prefer the smallest Strategy IR mutation and the narrowest allowed worker interface | Simplicity does not enforce least privilege, isolation, or data integrity |
| `multica-ai/andrej-karpathy-skills`: Surgical Changes | Restrict changes to declared mutable strategy/artifact areas and review the resulting hashes | A surgical change can still target the wrong file or evaluator unless path and hash checks reject it |
| `multica-ai/andrej-karpathy-skills`: Goal-Driven Execution | Define acceptance through bounded tests, evaluator outputs, and explicit promotion gates | A goal does not make a metric trustworthy or authorize live orders |

These four principles and the autoresearch workflow are process guidance, not trust
boundaries. Safe adaptation therefore requires independent validation, isolation,
authenticated evidence, resource bounds, and fail-closed promotion controls.

## Required design invariants

1. **DESIGN REQUIREMENT:** Strategy IR is the canonical strategy source. Generated
   Python/Lean is an execution artifact and must never become an alternate source of
   truth.
   **CURRENT EVIDENCE:** The repository contract names Strategy IR as canonical.
   **BLOCKED:** End-to-end enforcement against every generated-artifact write path is
   not established by this document.
2. **DESIGN REQUIREMENT:** The Research Director and generated strategy artifacts
   cannot write to or mutate `core/data`, `core/backtest`, `core/evaluator`,
   `core/validation`, `core/costs`, or `core/integrity`.
   **CURRENT EVIDENCE:** Protected paths and component-aware path matching are
   declared in the repository contract and local guard tests.
   **BLOCKED:** End-to-end Research Director import/write enforcement is not proven.
3. **DESIGN REQUIREMENT:** Development, validation, and sealed-OOS data are separate
   zones. Research cannot directly read sealed-OOS data; promotion is the only
   permitted gate.
   **CURRENT EVIDENCE:** Policy and architecture documents declare the zones and
   promotion gate.
   **BLOCKED:** A sealed-OOS process-level access audit is not available.
4. **DESIGN REQUIREMENT:** Reproducibility and promotion decisions bind the Strategy
   IR, data, engine, evaluator, cost model, compiler, and relevant artifact hashes.
   **CURRENT EVIDENCE:** Hashing and lineage policy contracts are present.
   **BLOCKED:** Complete artifact binding and authenticated promotion evidence are not
   established.
5. **DESIGN REQUIREMENT:** Signed data manifests and signed approval artifacts are
   required assumptions for any promotion or deployment boundary. Missing, invalid,
   expired, or mismatched signatures/approvals fail closed.
   **BLOCKED:** Production signing, key management, and signature-verification
   evidence are not supplied.
6. **DESIGN REQUIREMENT:** Live order permission defaults to `DENY`. A paper result
   or Champion status is not a live-trading approval.
   **CURRENT EVIDENCE:** Policy, the research adapter, deployment gates, and local
   tests provide current paper-only/order-rejection evidence.
   **BLOCKED:** No live-order capability or separate live deployment has been
   verified or authorized.
7. **DESIGN REQUIREMENT:** Credentials, account identifiers, raw market-data dumps,
   untracked runtime-local state, caches, logs, and runtime output remain outside Git
   and outside research context. Tracked canonical state remains versioned and subject
   to its own integrity controls.
   **CURRENT EVIDENCE:** Ignore rules and the tracked-path contract cover the stated
   repository boundary; canonical `state/*.json` remains trackable.
   **BLOCKED:** Historical filesystem cleanup and a full secret-history scan are not
   part of this evidence.

## Actors and trust levels

| Actor | Trust level | Allowed responsibility | Security concern |
|---|---|---|---|
| Human maintainer | trusted but fallible | Change reviewed source, policy, and tests | Accidental boundary weakening or secret commit |
| Human approver | trusted decision maker | Sign and approve a specific, hashed paper/live artifact | Social engineering, stale approval, wrong Champion |
| Research Director / LLM | untrusted execution input | Emit research intent and interpret compact results | Prompt injection, arbitrary code/imports, evaluator gaming |
| Local planner and mutation engine | constrained trusted code | Validate and mutate Strategy IR | Candidate escape, path traversal, policy bypass |
| Isolated worker | sandboxed/untrusted runtime | Run approved candidate against allowed data | Network access, protected-path writes, data leakage |
| Evaluator and integrity components | protected | Produce immutable checks and hashes | Tampering to improve a score or invalidate lineage |
| Data/provider boundary | external/untrusted source | Supply approved versioned data | Poisoning, look-ahead leakage, malformed data |
| Paper deployment | constrained | Simulate fills after exact approval | Drift, incorrect hash, accidental live endpoint |
| Live deployment | out of current scope | Would require separate process and secrets | Unauthorized real orders; denied by default |
| Attacker or malicious dependency | untrusted | No legitimate access | Supply-chain compromise, credential theft, exfiltration |

## Trust boundaries

```text
Human review/signature
        |
        v
Research policy + Strategy IR --validate/hash--> local planner/mutation
        |                                           |
        |                                           v
        |                                  isolated paper worker
        |                                           |
        v                                           v
protected data/backtest/evaluator/cost/integrity <-- immutable evaluation
        |
        v
promotion gate: signed manifests + exact hashes + expiry + human approval
        |
        v
paper boundary (current scope) ---- separate, denied-by-default ----> live orders
```

The LLM, imported strategies, generated artifacts, workers, external data, and
runtime providers are not allowed to cross into protected evaluator/data/integrity
mutation or into a live order process. `.omx/` is local orchestration state and is
ignored by Git; it is not application state, canonical strategy input, or evidence.

## Assets and required protection

| Asset | Required protection |
|---|---|
| Strategy IR and lineage | Canonical serialization, validation, stable hash, reviewable history |
| Market data and zone metadata | Versioning, provenance, read-only worker access, signed manifest assumption |
| Evaluator, cost, validation, integrity code | Protected paths, immutable/versioned hashes, no Research Director writes |
| Champion, Frontier, Rescue Pool, and experiment state | Atomic/checksum-protected persistence and provenance |
| Paper approvals and deployment manifests | Exact artifact hashes, signer identity, expiry, fail-closed validation |
| KIS credentials and account identifiers | Separate secret store/process; never Git or research context |
| Logs, caches, raw sources, and untracked runtime-local state | Local-only storage, ignored patterns, redaction, bounded retention |
| Research hypotheses and generated code | Treat as untrusted; validate before execution and isolate workers |

## Abuse cases and controls

| Abuse case | Expected control | Evidence status |
|---|---|---|
| LLM changes evaluator or cost logic to improve a score | Protected core paths and evaluator hash | **CURRENT EVIDENCE:** Limited to component-aware path matching in `core/evaluator/immutable_guard.py` and repository-contract path declarations. **BLOCKED:** End-to-end Research Director import/write enforcement |
| Candidate imports arbitrary code, opens files, or calls an order API | Strategy IR validation, restricted primitive proposals, isolated worker | **CURRENT EVIDENCE:** Primitive/feature restrictions and tests. **BLOCKED:** Full sandbox/network proof |
| Research process obtains KIS credentials or order permission | Research permissions reject both; read-only research adapter exposes no order method | **CURRENT EVIDENCE:** `integrations/kis/permissions.py`, `integrations/kis/research_adapter.py`, and isolation tests |
| Sealed-OOS data leaks into exploration | Separate data zones and promotion-only access | **DESIGN REQUIREMENT:** Policy/architecture assumption. **BLOCKED:** Sealed-OOS process and access audit evidence |
| Data or evaluator is replaced after a result is cached | Bind hashes to experiment and promotion records; signed manifests | **CURRENT EVIDENCE:** Hashing and policy contracts. **BLOCKED:** Cryptographic signing and key-management evidence |
| Expired, unsigned, or wrong-Champion approval enables deployment | Require signer, expiry, exact hashes, and explicit human approval; reject by default | **CURRENT EVIDENCE:** Local tests cover research credential/order rejection and exact-Champion, validation, and expiry checks. **BLOCKED:** Signature, manifest, risk-limit, and process-separation evidence |
| Local secrets or logs enter Git | Explicit ignore rules, secret scan, no raw dumps in artifacts | **CURRENT EVIDENCE:** `.gitignore` and tracked-path contract. **BLOCKED:** Historical filesystem cleanup |
| Paper mode is mistaken for live permission | Keep paper-only adapter separate; live order permission remains `DENY` | **CURRENT EVIDENCE:** Policy, README, deployment gates, and paper adapter; live deployment is intentionally absent |
| Upstream content or a dependency supplies malicious instructions | Treat upstream references and imported sources as untrusted; validate outputs | **DESIGN REQUIREMENT:** Treat references and imports as untrusted. **BLOCKED:** Dependency provenance and runtime supply-chain audit |
| LLM provider receives full caller-supplied context or sends secrets to an arbitrary endpoint | `research/llm/provider.py` must require HTTPS, an explicit host allowlist, private-network/link-local blocking, projected/redacted context, and strict request-size limits; API keys stay in headers and never enter context | **CURRENT EVIDENCE:** Provider accepts arbitrary `http://` or `https://` endpoints, forwards supplied context, and has no host/network or size policy; `context_builder.py` drops raw-market and sealed-OOS inputs. **DESIGN REQUIREMENT:** Endpoint validation, full redaction, and bounded projection |
| Provider response or transport becomes a remote code/data exfiltration path | Keep the provider contract JSON-only, expose only compact approved context, reject untrusted endpoint configuration, and retain offline mode as the default test path | **CURRENT EVIDENCE:** JSON response parsing and offline provider behavior. **BLOCKED:** HTTPS/allowlist/private-network enforcement |
| Docker worker reads or writes arbitrary host paths, runs mutable/root image, or escapes through output mount | `runtime/docker_runner.py` must use fixed workspace/output roots, read-only input mounts, non-root execution, pinned image digests, no network, dropped capabilities, and explicit CPU/memory/process limits | **CURRENT EVIDENCE:** `--network none`, read-only container/input, dropped capabilities, no-new-privileges, PID/CPU/memory limits, and an RW output mount. **DESIGN REQUIREMENT:** Fixed roots, non-root execution, and digest pinning. **BLOCKED:** Caller-supplied path/image validation |
| Same-bar signal/fill or incomplete risk enforcement inflates backtest safety | `core/backtest/engine.py` must use next-bar fills; `strategy_ir/schema.py` risk fields and `evaluation/risk.py` checks must be connected to enforced position, exposure, and daily-loss limits | **CURRENT EVIDENCE:** Current engine signals and fills at the same bar close; risk evaluation is observational and enforcement is incomplete beyond position size/stop/take-profit. **DESIGN REQUIREMENT:** Next-bar fills and enforced limits. **BLOCKED:** Implementation evidence |
| State, cache, or audit records are tampered with or replayed | Bind state/cache/audit records to authenticated integrity metadata, chained audit entries, and the full Strategy IR/data/evaluator/cost/image lineage; reject mismatch | **CURRENT EVIDENCE:** `memory/state_files.py` calculates a checksum; `experiments/cache.py` keys SQLite rows by experiment hash; `core/integrity/audit.py` hashes inputs. **DESIGN REQUIREMENT:** Authenticated integrity, chain, and binding. **BLOCKED:** Evidence of those controls |
| Search, queue, or resource use becomes unbounded or runs a `NEVER STOP` loop | Enforce policy budgets for candidate count/depth/generations, queue size, retries, concurrency, timeout, CPU, and memory; stop on exhaustion or require explicit bounded continuation | **CURRENT EVIDENCE:** `research/policy.yaml` supplies candidate target, retries, timeout, and concurrency; `runtime/queue.py` has leases/retry exhaustion; `runtime/resource_manager.py` limits concurrency. **BLOCKED:** Depth, queue, CPU/memory, and global budget enforcement; no unbounded `NEVER STOP` loop is authorized |

## Current evidence at freeze

- `AGENTS.md` defines Strategy IR as canonical, preserves the architecture source,
  names all protected core paths, and excludes credentials, account identifiers,
  session logs, and raw market-data dumps.
- `research/policy.yaml` sets `live_order_permission: deny`, requires human approval,
  and separates development, validation, and sealed-OOS zones.
- `integrations/kis/research_adapter.py` is read-only and has no order method;
  `integrations/kis/permissions.py` rejects order permission and credential refs.
- `docs/operations/deployment-gates.md` records that the repository does not submit
  orders and that live requirements are external to local unit-test PASS.
- `tests/test_repository_contract.py`, the KIS isolation tests, protected-boundary
  tests, and paper-gate tests provide current local contract evidence.
- The repository baseline is the `codex/quant-autoresearch-harness` branch at
  pre-Task-0 commit `7e9c45daa769cd0ad099d432d3f74b498a982f82`, recorded by Git
  before the Task-0 documentation commit. The existing untracked `.omx/` directory is
  preserved and is not evidence or application state.

## Blocked or not-yet-confirmed evidence

The following must not be reported as PASS based only on this document or local unit
tests:

- A production key-management system, signer identity, signature verification
  implementation, signed data manifest, or signed approval artifact. These are
  explicit assumptions of the deployment boundary, not supplied credentials or
  operational proof in this task.
- A real KIS account, live data vendor, production calendar, pinned worker image
  digest, or external LLM endpoint. No such external configuration is authorized or
  required for paper-only research.
- A sealed-OOS process-level access audit, hostile-worker sandbox escape test, network
  egress audit, dependency provenance audit, or full secret-history scan.
- Any live order capability. It is absent from the research package and remains
  denied; enabling it would require a separately reviewed task and explicit human
  authorization.

## Fail-closed requirements

Implementations extending this harness must reject, rather than guess, when any of
the following is missing or inconsistent: canonical Strategy IR, policy version,
data/evaluator/cost/engine hashes, signed data or approval evidence, signer identity,
approval expiry, Champion hash, data-zone permission, process separation, or order
permission. A blocked external prerequisite is a blocked gate, not a successful
simulation. The threat model is frozen until a reviewed change updates this file and
its evidence.
