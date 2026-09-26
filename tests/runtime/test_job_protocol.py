from __future__ import annotations

from pathlib import Path

from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from runtime.job_protocol import EvaluationJobRequest
from strategy_ir.schema import StrategyIR


def _strategy() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "job-protocol",
            "family": "trend",
            "generation": 2,
            "indicators": {"fast": {"type": "SMA", "period": 5}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )


def test_evaluation_job_request_round_trips_typed_arguments(tmp_path: Path) -> None:
    (tmp_path / "strategy.yaml").write_text("fixture", encoding="utf-8")
    (tmp_path / "bars.parquet").write_bytes(b"fixture")
    (tmp_path / "series.parquet").write_bytes(b"fixture")
    strategy = _strategy()

    request = EvaluationJobRequest.from_evaluation_kwargs(
        tmp_path,
        {
            "source_path": tmp_path / "strategy.yaml",
            "data_path": "bars.parquet",
            "series_data_path": "series.parquet",
            "method": "random",
            "count": 8,
            "seed": 7,
            "min_trades": 30,
            "min_annual_trades": 31,
            "min_qqq_cagr_delta": 0.1,
            "parameter_domains": (
                ParameterDomain("indicators.fast.period", (5, 10, 20)),
            ),
            "operations": (
                MutationOperation("SET_PARAMETER", "indicators.fast.period", 10),
            ),
            "strategy_override": strategy,
            "generation": 3,
            "research_run_id": "run-1",
            "attempt_id": "attempt-1",
        },
    )

    encoded = request.model_dump_json()
    decoded = EvaluationJobRequest.model_validate_json(encoded)
    kwargs = decoded.evaluation_kwargs(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        execution_context={"execution_mode": "docker_worker"},
    )

    assert decoded.source_path == "strategy.yaml"
    assert decoded.data_path == "bars.parquet"
    assert decoded.series_data_path == "series.parquet"
    assert kwargs["parameter_domains"] == (
        ParameterDomain("indicators.fast.period", (5, 10, 20)),
    )
    operations = kwargs["operations"]
    assert isinstance(operations, tuple)
    assert operations[0].op == "SET_PARAMETER"
    assert operations[0].value == 10
    assert kwargs["strategy_override"] == strategy
    assert kwargs["execution_context"] == {"execution_mode": "docker_worker"}


def test_evaluation_job_request_rejects_path_outside_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.parquet"
    outside.write_bytes(b"fixture")
    (tmp_path / "strategy.yaml").write_text("fixture", encoding="utf-8")

    try:
        EvaluationJobRequest.from_evaluation_kwargs(
            tmp_path,
            {
                "source_path": "strategy.yaml",
                "data_path": outside,
            },
        )
    except PermissionError as exc:
        assert "outside project root" in str(exc)
    else:
        raise AssertionError("outside input path must be rejected")
