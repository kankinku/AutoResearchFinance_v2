"""Resume deterministic research batches only from committed, verified checkpoints."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from application.research_batch_service import BatchRequestError, ResearchBatchService
from memory.evidence_store import EvidenceStore
from runtime.evidence_session import EvidenceSession
from tests.integrations.test_gpt_research_batches import _request
from tests.orchestration.test_evaluation_runner import _write_inputs


def _queued(service: ResearchBatchService, request: dict) -> str:
    import uuid

    job = uuid.uuid4().hex
    normalized = service._validate_request(request)
    normalized["input_sha256"] = service._input_fingerprints(normalized)
    with service._connect() as db:
        db.execute(
            "INSERT INTO batches (id,status,request_json,requested,created) VALUES(?,?,?,?,?)",
            (job, "QUEUED", json.dumps(normalized), request["generations"], time.time()),
        )
    return job


def _interrupted_after_first(
    service: ResearchBatchService, job: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = EvidenceSession.evaluate

    def die_on_second(self: EvidenceSession, runner: object, **kwargs: object) -> dict:
        if kwargs["generation"] == 2:
            raise SystemExit("simulated worker death before generation two evaluation")
        return original(self, runner, **kwargs)

    with monkeypatch.context() as mp:
        mp.setattr(EvidenceSession, "evaluate", die_on_second)
        with pytest.raises(SystemExit, match="simulated worker death"):
            service.execute(job)
    with service._connect() as db:
        assert db.execute("SELECT completed FROM batches WHERE id=?", (job,)).fetchone()[0] == 1
        db.execute(
            "UPDATE batches SET status='INTERRUPTED',error_code='WORKER_GONE' WHERE id=?", (job,)
        )


def test_resumes_same_batch_and_same_run_without_replaying_finished_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=3),
        "method": "random",
        "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4, 5, 6]}],
    }
    job = _queued(svc, request)
    _interrupted_after_first(svc, job, monkeypatch)
    before = EvidenceStore(tmp_path / "state").events()
    run_ids = {ev["payload"]["research_run_id"] for ev in before}
    assert len(run_ids) == 1
    assert len([ev for ev in before if ev["kind"] == "generation"]) == 1
    assert svc.status(job)["status"] == "INTERRUPTED"
    with monkeypatch.context() as mp:
        mp.setattr(svc, "_spawn_worker", lambda jid: None)
        resumed = svc.resume(job)
    assert resumed["status"] == "QUEUED"
    svc.execute(job)
    final = svc.report(job)
    assert final["status"] == "COMPLETED"
    assert final["completed_generations"] == 3
    events = EvidenceStore(tmp_path / "state").events()
    assert {ev["payload"]["research_run_id"] for ev in events} == run_ids
    assert len([ev for ev in events if ev["kind"] == "generation"]) == 3
    assert (
        len([ev for ev in events if ev["kind"] == "attempt" and ev["payload"]["generation"] == 1])
        == 1
    )
    assert events[: len(before)] == before
    assert final["orders_enabled"] is False
    with pytest.raises(BatchRequestError, match="not interrupted"):
        svc.resume(job)


def test_refuse_resume_if_immutable_evidence_ahead_of_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(
        svc,
        {
            **_request(generations=3),
            "method": "random",
            "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4, 5]}],
        },
    )
    _interrupted_after_first(svc, job, monkeypatch)
    with svc._connect() as db:
        db.execute("DELETE FROM generation_checkpoints WHERE batch_id=? AND generation=1", (job,))
    events_before = EvidenceStore(tmp_path / "state").events()
    with pytest.raises(BatchRequestError, match="CHECKPOINT"):
        svc.resume(job)
    assert EvidenceStore(tmp_path / "state").events() == events_before
    assert svc.status(job)["status"] == "INTERRUPTED"


def test_refuse_legacy_batch_without_checkpoints(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(svc, _request(generations=3))
    with svc._connect() as db:
        db.execute("UPDATE batches SET status='INTERRUPTED',completed=1 WHERE id=?", (job,))
    with pytest.raises(BatchRequestError, match="CHECKPOINT"):
        svc.resume(job)
    assert svc.status(job)["status"] == "INTERRUPTED"


def test_resumed_mixed_batch_uses_saved_hypothesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(
        svc, {**_request(generations=3), "intent": {**_request()["intent"], "mode": "mixed"}}
    )
    _interrupted_after_first(svc, job, monkeypatch)
    before = EvidenceStore(tmp_path / "state").events()
    generations = [ev["payload"] for ev in before if ev["kind"] == "generation"]
    assert generations[0]["next_hypothesis"] is not None
    with monkeypatch.context() as mp:
        mp.setattr(svc, "_spawn_worker", lambda jid: None)
        svc.resume(job)
    svc.execute(job)
    report = svc.report(job)
    assert report["status"] == "COMPLETED"
    assert report["adaptive_applied_generations"] >= 1
    assert report["generations"][1]["applied_hypothesis"] == generations[0]["next_hypothesis"]
    assert report["orders_enabled"] is False


def test_resume_rejects_changed_strategy_bytes_even_if_executable_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=3),
        "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4, 5]}],
    }
    job = _queued(svc, request)
    _interrupted_after_first(svc, job, monkeypatch)
    before = EvidenceStore(tmp_path / "state").events()
    with (tmp_path / "strategy.yaml").open("a", encoding="utf-8") as file:
        file.write("\n# edit after initial batch\n")
    with pytest.raises(BatchRequestError) as error:
        svc.resume(job)
    assert error.value.code == "CHECKPOINT_INPUT_CHANGED"
    assert svc.status(job)["status"] == "INTERRUPTED"
    assert EvidenceStore(tmp_path / "state").events() == before


def test_resume_refuses_uncommitted_attempt_before_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_inputs(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(
        svc,
        {
            **_request(generations=3),
            "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4]}],
        },
    )
    _interrupted_after_first(svc, job, monkeypatch)
    run = svc.status(job)["research_run_id"]
    store = EvidenceStore(tmp_path / "state")
    attempt_id = "a" * 32
    store.append(
        "attempt",
        f"attempt:{attempt_id}",
        {
            "research_run_id": run,
            "attempt_id": attempt_id,
            "generation": 2,
            "status": "FAILED",
            "candidates": [],
        },
    )
    before = store.events()
    with pytest.raises(BatchRequestError) as error:
        svc.resume(job)
    assert error.value.code == "CHECKPOINT_UNCOMMITTED_ATTEMPT"
    assert store.events() == before
    assert svc.status(job)["status"] == "INTERRUPTED"
