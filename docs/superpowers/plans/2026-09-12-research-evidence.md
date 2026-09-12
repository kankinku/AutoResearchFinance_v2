# Research Evidence Implementation Plan

> Execute with subagent-driven-development for independent interfaces and TDD locally.

**Goal:** Persist attributable research results and feed accumulated failures to the next proposal.
**Architecture:** Immutable SQLite events are canonical evidence; Knowledge JSON is a recoverable projection preserving pre-existing fields. All reader interfaces share one summary function.
**Tech Stack:** Python, SQLite, pytest, existing FastAPI/static dashboard and MCP.

## Task 1: Journal and summary
- [x] Write tests/memory/test_research_evidence.py for run isolation, immutable/idempotent events, conflicts, incomplete attempts, mismatched comparison conditions and missing denominators.
- [x] Run `python -m pytest tests/memory/test_research_evidence.py -q` and observe RED.
- [x] Implement memory/evidence_store.py, memory/research_evidence.py and memory/evidence_knowledge.py. Store only constructed profiles; exclude raw prices and provider errors. Use transactions and content digests to reject damaged/conflicting events.
- [x] Verify GREEN with rollback, replay and preservation of unknown Knowledge fields.

## Task 2: Pipeline and runtime
- [x] Write tests/orchestration/test_research_evidence_integration.py: rejected real evaluation must persist knowledge and reach next context without dropping older entries.
- [x] Write runtime tests for independent loops, evaluation failure/retry and changed manifest input rejection; run to RED.
- [x] Implement orchestration/evidence.py and runtime/evidence_session.py. Freeze input/policy/code comparison conditions, link attempts to final generations, and journal failed evaluations using exception class only.
- [x] Integrate run_local_evaluation and both loops; integrity errors must abort instead of fallback. Preserve legacy ledger consumers with additive identifiers.
- [x] Verify GREEN; final-generation curves count selected attempts only while the immutable journal retains all attempts.

## Task 3: Reader interfaces
- [x] Write focused tests for CLI research-evidence, GET /api/research-evidence and MCP get_research_evidence; observe RED.
- [x] Use memory.research_evidence.research_evidence(state_dir, run_id=None) everywhere. Implement CLI JSON export and a compact static-dashboard evidence section.
- [x] Verify identical payloads, empty states and sanitized errors.

## Task 4: Delivery
- [x] Review against approved design, document unavailable metrics as NOT_MEASURED.
- [x] Run synthetic multigeneration smoke, then a bounded real development-data smoke in ignored output storage. No LLM or sealed OOS required for plumbing validation.
- [x] Run `python -m pytest -q`, `ruff check .`, `python -m mypy .`; verify protected architecture bytes unchanged.
- [x] Review and scan changed files, commit only this work, preserve dirty main workspace and local data, and report exact scope and paths.
