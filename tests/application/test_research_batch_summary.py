"""A small read-only explanation projection from immutable candidate Evidence."""
from __future__ import annotations

from application.research_batch_summary import explain_batch_attempts


def _candidate(*, status: str, failed: list[str], ident: str) -> dict[str, object]:
    gates: list[dict[str, object]] = [
        {"name": gate, "passed": False, "actual": 0, "threshold": 10}
        for gate in failed
    ]
    return {
        "candidate_hash": ident,
        "status": status,
        "failed_gates": failed,
        "gates": gates,
    }


def test_explain_batch_attempts_aggregates_real_gates_without_inventing_numbers() -> None:
    attempts: list[dict[str, object]] = [
        {"candidates": [
            _candidate(status="REJECT", failed=["validation", "robustness"], ident="x"),
            _candidate(status="REJECT", failed=["validation"], ident="y"),
        ], "market_data_quality": {
            "status": "UNVERIFIED", "issues": ["revisions_not_as_of"],
            "point_in_time_verified": False,
        }},
        {"candidates": [
            _candidate(status="REJECT", failed=["robustness"], ident="x"),
            _candidate(status="SURVIVOR", failed=[], ident="z"),
        ], "market_data_quality": {
            "status": "UNVERIFIED", "issues": ["revisions_not_as_of"],
            "point_in_time_verified": False,
        }},
    ]
    report = explain_batch_attempts(attempts)
    assert report["source"] == "immutable_evidence"
    assert report["evaluated_candidate_instances"] == 4
    assert report["rejected_candidate_instances"] == 3
    assert report["unique_candidate_hashes"] == 3
    assert report["data_quality"]["status"] == "UNVERIFIED"
    assert report["data_quality"]["point_in_time_verified"] is False
    assert report["top_failed_gates"] == [
        {"gate": "robustness", "count": 2, "example_actual": 0,
         "example_threshold": 10},
        {"gate": "validation", "count": 2, "example_actual": 0,
         "example_threshold": 10},
    ]
    assert report["next_experiment"]["review_gate"] in {"validation", "robustness"}
    assert report["causal_status"] == "UNKNOWN"
    assert report["sealed_oos"] == "NOT_MEASURED"


def test_explain_batch_attempts_preserves_missing_and_explicit_zero_values() -> None:
    a = _candidate(status="REJECT", failed=["annual_trade_count"], ident="a")
    a["gates"] = [{"name": "annual_trade_count", "passed": False,
                   "actual": None, "threshold": 0}]
    report = explain_batch_attempts([{"candidates": [a]}])
    assert report["top_failed_gates"][0]["example_actual"] is None
    assert report["top_failed_gates"][0]["example_threshold"] == 0
    assert report["data_quality"]["status"] == "NOT_MEASURED"
    assert report["next_experiment"]["review_gate"] == "annual_trade_count"


def test_explain_batch_attempts_never_claims_success_without_candidates() -> None:
    report = explain_batch_attempts([])
    assert report["evaluated_candidate_instances"] == 0
    assert report["top_failed_gates"] == []
    assert report["next_experiment"] is None
    assert report["sealed_oos"] == "NOT_MEASURED"
