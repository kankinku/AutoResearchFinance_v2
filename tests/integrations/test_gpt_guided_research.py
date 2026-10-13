"""GPT-guided research checkpoints and failure-boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.codex_mcp_core import create_mcp_server
from memory.evidence_store import EvidenceStore
from tests.orchestration.test_evaluation_runner import _write_inputs


def proposal() -> dict:
    return {
        "source_path": "strategy.yaml",
        "intent": {
            "mode": "structure",
            "parent_ids": ["runner-test"],
            "operations": [],
            "rationale": "External GPT decides next hypothesis",
        },
    }


def start(server: object) -> dict:
    return server._dispatch(
        "start_guided_research",
        {
            "data_path": "bars.parquet",
            "generations": 2,
            "method": "grid",
            "count": 1,
            "seed": 20,
            "min_trades": 30,
            "min_annual_trades": 30,
            "min_qqq_cagr_delta": 0.1,
        },
    )


def test_guided_two_generations_with_explicit_gpt_checkpoints(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    first = start(server)
    assert first["status"] == "AWAITING_GPT" and first["generation"] == 1
    assert EvidenceStore(tmp_path / "state").events() == []

    def args(point: dict) -> dict:
        return {
            "session_id": first["session_id"],
            "checkpoint_token": point["checkpoint_token"],
            "generation": point["generation"],
            **(
                proposal()
                if point["generation"] == 1
                else {
                    "source_path": "strategy.yaml",
                    "intent": {
                        **proposal()["intent"],
                        "rationale": "Change entry threshold after first failed Evidence",
                        "operations": [
                            {
                                "op": "REPLACE_RULE",
                                "path": "entry.conditions.0",
                                "condition": {"op": "greater_than", "left": "close", "value": 102},
                            }
                        ],
                    },
                }
            ),
        }

    after = server._dispatch("submit_guided_generation", args(first))
    assert after["status"] == "AWAITING_GPT" and after["generation"] == 2
    assert after["checkpoint_token"] != first["checkpoint_token"]
    assert after["previous_failed_gates"]
    with pytest.raises(ValueError, match="checkpoint|stale"):
        server._dispatch("submit_guided_generation", args(first))
    reopened = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    point = reopened._dispatch("get_guided_research", {"session_id": first["session_id"]})
    final = reopened._dispatch("submit_guided_generation", args(point))
    assert final["status"] == "COMPLETED" and final["completed_generations"] == 2
    assert final["checkpoint_token"] is None and final["orders_enabled"] is False
    assert final["history"][1]["previous_run_id"] == final["history"][0]["run_id"]
    runs = [e for e in EvidenceStore(tmp_path / "state").events() if e["kind"] == "run"]
    assert len(runs) == 2
    assert (
        runs[1]["payload"]["settings"]["previous_research_run_id"] == final["history"][0]["run_id"]
    )


def test_failed_preflight_does_not_consume_checkpoint(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    point = start(server)
    args = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(ValueError):
        server._dispatch(
            "submit_guided_generation",
            {**args, "intent": {**args["intent"], "parent_ids": ["invalid-parent"]}},
        )
    current = server._dispatch("get_guided_research", {"session_id": point["session_id"]})
    assert current["checkpoint_token"] == point["checkpoint_token"]
    assert EvidenceStore(tmp_path / "state").events() == []


def test_dataset_changed_and_stale_checkpoint_rejected(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    point = service.start(
        {"data_path": "bars.parquet", "generations": 2, "method": "grid", "count": 1, "seed": 3}
    )
    args = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(ValueError, match="checkpoint"):
        service.submit({**args, "checkpoint_token": "f" * 32})
    with (tmp_path / "bars.parquet").open("ab") as handle:
        handle.write(b"extra")
    with pytest.raises(ValueError, match="dataset|changed"):
        service.submit(args)
    assert service.get(point["session_id"])["completed_generations"] == 0
    assert EvidenceStore(tmp_path / "state").events() == []


def test_guided_tools_are_explicit() -> None:
    tools = {item["name"]: item for item in chatgpt_tools()}
    assert {
        "start_guided_research",
        "get_guided_research",
        "submit_guided_generation",
    } <= tools.keys()
    assert {"checkpoint_token", "intent", "source_path"} <= set(
        tools["submit_guided_generation"]["inputSchema"]["required"]
    )


def test_policy_gates_are_not_relaxed_when_starting_guided_session(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    for field, value in (("min_trades", 0), ("min_annual_trades", 0), ("min_qqq_cagr_delta", 0.0)):
        with pytest.raises(ValueError, match="must be|relaxed"):
            service.start({"data_path": "bars.parquet", "generations": 2, field: value})
    with pytest.raises(ValueError, match="generations"):
        service.start({"data_path": "bars.parquet", "generations": True})


def test_evaluation_failure_fails_closed_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from application.evaluation_service import EvaluationService

    _write_inputs(tmp_path)
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    point = service.start({"data_path": "bars.parquet", "generations": 2})

    def interrupted(*args: object, **kwargs: object) -> None:
        raise RuntimeError("test-injected evaluator outage")

    monkeypatch.setattr(EvaluationService, "run", interrupted)
    kwargs = {
        "session_id": point["session_id"],
        "checkpoint_token": point["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(RuntimeError, match="outage"):
        service.submit(kwargs)
    assert service.get(point["session_id"])["status"] == "INTERRUPTED"
    with pytest.raises(ValueError, match="checkpoint"):
        service.submit(kwargs)


def test_duplicate_strategy_is_rejected_without_spending_checkpoint_or_creating_evidence(
    tmp_path: Path,
) -> None:
    """Changing generation/seed/rationale must not re-evaluate an identical IR."""
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    first = service.start({"data_path": "bars.parquet", "generations": 2})
    initial = service.submit(
        {
            "session_id": first["session_id"],
            "checkpoint_token": first["checkpoint_token"],
            "generation": 1,
            **proposal(),
        }
    )
    assert initial["completed_generations"] == 1
    before = EvidenceStore(state).events()
    attempt = next(e["payload"] for e in before if e["kind"] == "attempt")
    original_hash = attempt["candidates"][0]["semantic_strategy_hash"]
    with pytest.raises(ValueError, match="DUPLICATE_STRATEGY"):
        service.submit(
            {
                "session_id": first["session_id"],
                "checkpoint_token": initial["checkpoint_token"],
                "generation": 2,
                "source_path": "strategy.yaml",
                "intent": {
                    **proposal()["intent"],
                    "rationale": "Updated rationale but unchanged executable IR",
                },
            }
        )
    current = service.get(first["session_id"])
    assert current["checkpoint_token"] == initial["checkpoint_token"]
    assert current["completed_generations"] == 1
    assert current["previous_evaluated_strategies"] == 1
    assert EvidenceStore(state).events() == before

    # A real change to the executable rule is novel; keep the same checkpoint.
    changed = {
        "mode": "structure",
        "parent_ids": ["runner-test"],
        "rationale": "Use different entry threshold after the earlier strategy failed gates",
        "operations": [
            {
                "op": "REPLACE_RULE",
                "path": "entry.conditions.0",
                "condition": {"op": "greater_than", "left": "close", "value": 102},
            }
        ],
    }
    done = service.submit(
        {
            "session_id": first["session_id"],
            "checkpoint_token": current["checkpoint_token"],
            "generation": 2,
            "source_path": "strategy.yaml",
            "intent": changed,
        }
    )
    assert done["status"] == "COMPLETED"
    candidate_attempts = [
        e["payload"] for e in EvidenceStore(state).events() if e["kind"] == "attempt"
    ]
    assert len(candidate_attempts) == 2
    assert candidate_attempts[1]["candidates"][0]["semantic_strategy_hash"] != original_hash


def test_reopened_guided_session_still_blocks_duplicate(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    path = tmp_path / "state"
    session = GPTGuidedResearchService(project_root=tmp_path, state_dir=path)
    first = session.start({"data_path": "bars.parquet", "generations": 2})
    second = session.submit(
        {
            "session_id": first["session_id"],
            "checkpoint_token": first["checkpoint_token"],
            "generation": 1,
            **proposal(),
        }
    )
    reopened = GPTGuidedResearchService(project_root=tmp_path, state_dir=path)
    with pytest.raises(ValueError, match="DUPLICATE_STRATEGY"):
        reopened.submit(
            {
                "session_id": first["session_id"],
                "checkpoint_token": second["checkpoint_token"],
                "generation": 2,
                **proposal(),
            }
        )
    assert reopened.get(first["session_id"])["status"] == "AWAITING_GPT"


def test_strategy_renamed_to_different_family_still_counts_as_duplicate(tmp_path: Path) -> None:
    """Source ID/family and ancestry cannot bypass executable semantic identity."""
    _write_inputs(tmp_path)
    original = (tmp_path / "strategy.yaml").read_text(encoding="utf-8")
    (tmp_path / "renamed.yaml").write_text(
        original.replace("id: runner-test", "id: renamed").replace(
            "family: trend", "family: synthetic-alias"
        ),
        encoding="utf-8",
    )
    service = GPTGuidedResearchService(project_root=tmp_path, state_dir=tmp_path / "state")
    created = service.start({"data_path": "bars.parquet", "generations": 2})
    first = service.submit(
        {
            "session_id": created["session_id"],
            "checkpoint_token": created["checkpoint_token"],
            "generation": 1,
            **proposal(),
        }
    )
    before = EvidenceStore(tmp_path / "state").events()
    with pytest.raises(ValueError, match="DUPLICATE_STRATEGY"):
        service.submit(
            {
                "session_id": created["session_id"],
                "checkpoint_token": first["checkpoint_token"],
                "generation": 2,
                "source_path": "renamed.yaml",
                "intent": {
                    "mode": "structure",
                    "parent_ids": ["renamed"],
                    "operations": [],
                    "rationale": "new label only",
                },
            }
        )
    assert EvidenceStore(tmp_path / "state").events() == before


def test_recover_completed_evaluation_after_checkpoint_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completed immutable evidence must be adopted, never evaluated twice."""
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    guided = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    first = guided.start({"data_path": "bars.parquet", "generations": 2})
    request = {
        "session_id": first["session_id"],
        "checkpoint_token": first["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    original = GPTGuidedResearchService._finalize_inflight

    def fail_commit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash after evaluator Evidence completion")

    monkeypatch.setattr(GPTGuidedResearchService, "_finalize_inflight", fail_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        guided.submit(request)
    failed = guided.get(first["session_id"])
    assert failed["status"] == "INTERRUPTED"
    assert failed["inflight_run_id"]
    assert failed["inflight_attempt_id"]
    assert failed["checkpoint_token"] is None
    before = EvidenceStore(state).events()
    assert (
        len([e for e in before if e["kind"] == "end" and e["payload"]["status"] == "COMPLETED"])
        == 1
    )
    monkeypatch.setattr(GPTGuidedResearchService, "_finalize_inflight", original)
    resumed = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    report = resumed.reconcile(first["session_id"])
    assert report["status"] == "AWAITING_GPT"
    assert report["completed_generations"] == 1
    assert report["reconciliation"] == "VERIFIED_COMPLETED_EVIDENCE"
    assert report["inflight_run_id"] is None
    assert report["history"][0]["run_id"] == failed["inflight_run_id"]
    assert EvidenceStore(state).events() == before
    repeat = resumed.reconcile(first["session_id"])
    assert repeat["status"] == "AWAITING_GPT"
    assert repeat["completed_generations"] == 1
    assert EvidenceStore(state).events() == before
    with pytest.raises(ValueError, match="checkpoint"):
        resumed.submit(request)


def test_recovery_refuses_unknown_or_incomplete_evidence_and_never_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat_directed_research_service import ChatDirectedResearchService

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    guided = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    first = guided.start({"data_path": "bars.parquet", "generations": 2})

    def crashed(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected crash before Evidence run")

    monkeypatch.setattr(ChatDirectedResearchService, "run", crashed)
    request = {
        "session_id": first["session_id"],
        "checkpoint_token": first["checkpoint_token"],
        "generation": 1,
        **proposal(),
    }
    with pytest.raises(RuntimeError, match="injected crash"):
        guided.submit(request)
    interrupted = guided.get(first["session_id"])
    assert interrupted["status"] == "INTERRUPTED"
    assert interrupted["next_action"] == "OPERATOR_REVIEW_OR_RECONCILE"
    assert interrupted["inflight_run_id"]
    assert EvidenceStore(state).events() == []
    report = GPTGuidedResearchService(project_root=tmp_path, state_dir=state).reconcile(
        first["session_id"]
    )
    assert report["status"] == "INTERRUPTED"
    assert report["reconciliation"] == "INCOMPLETE_OR_MISSING_EVIDENCE"
    assert report["completed_generations"] == 0
    assert EvidenceStore(state).events() == []
    with pytest.raises(ValueError, match="checkpoint"):
        guided.submit(request)


def test_reconciler_refuses_forged_run_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from application.chat_directed_research_service import ChatDirectedResearchService

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    guided = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    first = guided.start({"data_path": "bars.parquet", "generations": 2})

    def stopped(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulate interrupted call")

    monkeypatch.setattr(ChatDirectedResearchService, "run", stopped)
    with pytest.raises(RuntimeError):
        guided.submit(
            {
                "session_id": first["session_id"],
                "checkpoint_token": first["checkpoint_token"],
                "generation": 1,
                **proposal(),
            }
        )
    interrupted = guided.get(first["session_id"])
    run_id = interrupted["inflight_run_id"]
    # This checksum-valid but incorrect origin may not be adopted by recovery.
    store = EvidenceStore(state)
    store.append(
        "run",
        f"run:{run_id}",
        {
            "research_run_id": run_id,
            "requested_generations": 1,
            "seed": 0,
            "settings": {"guided_session_id": "attacker", "guided_generation": 1},
        },
    )
    report = guided.reconcile(first["session_id"])
    assert report["status"] == "INTERRUPTED"
    assert report["reconciliation"] == "EVIDENCE_IDENTITY_MISMATCH"
    assert report["completed_generations"] == 0


def test_mcp_reconcile_is_exposed_and_idempotent(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    point = start(server)
    tools = {item["name"]: item for item in chatgpt_tools()}
    assert "reconcile_guided_research" in tools
    assert tools["reconcile_guided_research"]["inputSchema"]["required"] == ["session_id"]
    first = server._dispatch("reconcile_guided_research", {"session_id": point["session_id"]})
    assert first["reconciliation"] == "ALREADY_SETTLED"
    assert first["status"] == "AWAITING_GPT"
    assert first["checkpoint_token"] == point["checkpoint_token"]
    assert EvidenceStore(tmp_path / "state").events() == []
    with pytest.raises(ValueError, match="session_id"):
        server._dispatch(
            "reconcile_guided_research", {"session_id": point["session_id"], "run": "extra"}
        )


def test_reconcile_stale_executing_after_uncaught_process_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hard exit skips except Exception, leaving EXECUTING; explicit reconcile adopts proof."""
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    server = create_mcp_server(state_dir=state, project_root=tmp_path)
    point = start(server)
    original = GPTGuidedResearchService._finalize_inflight

    def hard_exit(*args: object, **kwargs: object) -> None:
        raise SystemExit("test sudden process death after committed Evidence")

    monkeypatch.setattr(GPTGuidedResearchService, "_finalize_inflight", hard_exit)
    with pytest.raises(SystemExit, match="sudden process"):
        server._dispatch(
            "submit_guided_generation",
            {
                "session_id": point["session_id"],
                "checkpoint_token": point["checkpoint_token"],
                "generation": 1,
                **proposal(),
            },
        )
    assert (
        GPTGuidedResearchService(project_root=tmp_path, state_dir=state).get(point["session_id"])[
            "status"
        ]
        == "EXECUTING"
    )
    recorded = EvidenceStore(state).events()
    monkeypatch.setattr(GPTGuidedResearchService, "_finalize_inflight", original)
    reopened = create_mcp_server(state_dir=state, project_root=tmp_path)
    recovered = reopened._dispatch("reconcile_guided_research", {"session_id": point["session_id"]})
    assert recovered["reconciliation"] == "VERIFIED_COMPLETED_EVIDENCE"
    assert recovered["status"] == "AWAITING_GPT"
    assert recovered["completed_generations"] == 1
    assert EvidenceStore(state).events() == recorded


def test_legacy_guided_session_schema_migrates_without_losing_checkpoints(tmp_path: Path) -> None:
    import sqlite3

    _write_inputs(tmp_path)
    state = tmp_path / "state"
    older = GPTGuidedResearchService(project_root=tmp_path, state_dir=state)
    db_path = older.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE sessions("
            "id TEXT PRIMARY KEY, status TEXT NOT NULL, request_json TEXT NOT NULL,"
            " dataset_hash TEXT NOT NULL, file_sha256 TEXT NOT NULL,"
            " requested INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,"
            " token TEXT, previous_run_id TEXT)"
        )
    created = older.start({"data_path": "bars.parquet", "generations": 2})
    assert created["status"] == "AWAITING_GPT"
    assert created["inflight_run_id"] is None
    assert created["checkpoint_token"]
    with sqlite3.connect(db_path) as db:
        names = {col[1] for col in db.execute("PRAGMA table_info(sessions)")}
    assert {"inflight_run_id", "inflight_attempt_id", "inflight_source_sha256"} <= names
