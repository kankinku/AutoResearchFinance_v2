from __future__ import annotations

from pathlib import Path

import runtime.research_loop as loop_module
from runtime.research_loop import ResearchLoopConfig, run_repeated_evaluation


def test_research_runs_have_independent_evidence_ids(tmp_path: Path) -> None:
    from memory.research_evidence import research_evidence

    config = ResearchLoopConfig(project_root=tmp_path, state_dir=tmp_path / "state",
                                source_path="unused", data_path="unused", generations=2)
    def evaluator(**kwargs: object) -> dict[str, object]:
        return {"status": "COMPLETED", "candidate_count": 99}

    first = run_repeated_evaluation(config, evaluator=evaluator)
    second = run_repeated_evaluation(config, evaluator=evaluator)
    assert first["research_run_id"] != second["research_run_id"]
    runs = research_evidence(config.state_dir)["runs"]
    assert len(runs) == 2
    assert all(run["completed_generations"] == 2 for run in runs)
    # An injected evaluator's unsupported aggregate is not verified candidate evidence.
    assert all(run["candidate_count"] == 0 and run["pass_rate"] is None for run in runs)


def test_failed_attempt_then_fallback_records_one_final_generation(tmp_path: Path) -> None:
    import pytest

    from memory.evidence_store import EvidenceStore
    from memory.research_evidence import research_evidence
    from runtime.evidence_session import EvidenceSession

    session = EvidenceSession(tmp_path, requested_generations=1, seed=0)
    def failed(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("private provider output must not be copied")
    with pytest.raises(RuntimeError):
        session.evaluate(failed, generation=1)
    result = session.evaluate(lambda **kwargs: {"status": "COMPLETED"}, generation=1)
    session.finish_generation(1, "FALLBACK", result)
    session.finish_run("COMPLETED_WITH_FALLBACKS")
    run = research_evidence(tmp_path)["runs"][0]
    assert run["completed_generations"] == 1
    assert run["failed_evaluation_attempt_count"] == 1
    assert run["evaluation_attempt_count"] == 2
    assert run["fallback_rate"] == 1.0
    assert "private provider output" not in str(EvidenceStore(tmp_path).events())


def test_research_loop_repeats_with_deterministic_seed_and_persists_status(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[int] = []

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        calls.append(int(kwargs["seed"]))
        return {"status": "COMPLETED", "candidate_count": 1}

    monkeypatch.setattr(loop_module, "run_local_evaluation", fake_evaluation)
    config = ResearchLoopConfig(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        source_path="strategy.yaml",
        data_path="data.parquet",
        seed=7,
        generations=3,
        min_annual_trades=30,
    )

    result = run_repeated_evaluation(config)

    assert calls == [7, 8, 9]
    assert result["status"] == "COMPLETED"
    assert result["completed_generations"] == 3
    assert result["orders_enabled"] is False
    payload = (tmp_path / "state" / "system" / "research_loop.json").read_text(
        encoding="utf-8"
    )
    assert '"status": "COMPLETED"' in payload
    assert '"min_annual_trades": 30' in payload


def test_research_loop_passes_generation_to_evaluator(tmp_path: Path, monkeypatch) -> None:
    generations: list[int] = []

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        generations.append(int(kwargs["generation"]))
        return {"status": "COMPLETED", "candidate_count": 1}

    monkeypatch.setattr(loop_module, "run_local_evaluation", fake_evaluation)
    run_repeated_evaluation(
        ResearchLoopConfig(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            source_path="strategy.yaml",
            data_path="data.parquet",
            generations=3,
        )
    )

    assert generations == [1, 2, 3]


def test_research_loop_rejects_unbounded_or_zero_generation() -> None:
    config = ResearchLoopConfig(
        project_root=Path("."),
        state_dir=Path("state"),
        source_path="strategy.yaml",
        data_path="data.parquet",
        generations=0,
    )

    try:
        run_repeated_evaluation(config)
    except ValueError as exc:
        assert "generations" in str(exc)
    else:
        raise AssertionError("zero-generation loop must be rejected")
