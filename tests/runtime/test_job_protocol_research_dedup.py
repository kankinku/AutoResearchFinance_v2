from pathlib import Path

from runtime.job_protocol import EvaluationJobRequest


def test_worker_request_preserves_semantic_exclusions_across_json_boundary(tmp_path: Path) -> None:
    args = {
        "source_path": "strategy.yaml",
        "data_path": "bars.parquet",
        "excluded_semantic_hashes": ("a" * 64, "b" * 64),
    }
    request = EvaluationJobRequest.from_evaluation_kwargs(tmp_path, args)
    wire = EvaluationJobRequest.model_validate_json(request.model_dump_json())
    assert wire.evaluation_kwargs(
        project_root=tmp_path, state_dir=tmp_path / "state", execution_context={}
    )["excluded_semantic_hashes"] == ("a" * 64, "b" * 64)
