from evaluation.selector import FunnelResult, GateDecision
from orchestration.evidence import candidate_evidence


def test_candidate_evidence_preserves_missing_benchmark_gate_reason() -> None:
    result = FunnelResult(
        candidate_hash="candidate-missing-benchmark",
        family="trend",
        status="REJECT",
        score=0.5,
        gates=(GateDecision("qqq_cagr_delta", False, 0.0, None, "benchmark_not_measured"),),
    )
    record = candidate_evidence(result)
    assert record["failed_gates"] == ["qqq_cagr_delta"]
    assert record["gates"][0]["passed"] is False
    assert record["gates"][0]["actual"] is None
    assert record["gates"][0]["reason"] == "benchmark_not_measured"


def test_candidate_evidence_preserves_measured_benchmark_failure_reason() -> None:
    result = FunnelResult(
        candidate_hash="candidate-measured-benchmark",
        family="trend",
        status="REJECT",
        score=0.5,
        gates=(GateDecision("qqq_cagr_delta", False, 0.1, -0.05, "qqq_target_not_met"),),
    )
    record = candidate_evidence(result)
    assert record["gates"][0]["actual"] == -0.05
    assert record["gates"][0]["reason"] == "qqq_target_not_met"
