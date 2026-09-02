from __future__ import annotations

from pathlib import Path

import runtime.research_loop as loop_module
from runtime.research_loop import ResearchLoopConfig, run_repeated_evaluation


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

