"""Bounded, evidence-derived explanation for a GPT research batch.

This is a read model: never alters candidate decisions, Evidence or OOS state.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

_REVIEW_HINTS = {
    "robustness": "비용 스트레스와 견고성 기준을 확인한 뒤 탐색할 파라미터를 하나 선택하세요.",
    "validation": "개발용 검증 구간별 성과를 확인하고 다음 가설을 정하세요.",
    "fast": "빠른 평가에서 거래 횟수와 수익률 기준을 각각 확인하세요.",
    "full": "전체 평가에서 거래 횟수와 수익률 기준을 각각 확인하세요.",
    "annual_trade_count": "연도별 거래 횟수를 살펴보고 표본이 충분한지 판단하세요.",
    "risk": "낙폭과 노출 한도에 위배된 항목을 확인하세요.",
    "qqq_cagr_delta": "비교할 QQQ 기준 수익률이 제공되었는지 확인하세요.",
}


def explain_batch_attempts(
    attempts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Summarize *evaluated instances*, not causal explanations or OOS success."""
    counts: Counter[str] = Counter()
    examples: dict[str, dict[str, object]] = {}
    hashes: set[str] = set()
    statuses: set[str] = set()
    issues: set[str] = set()
    evaluated = rejected = 0
    quality_measured = False
    independently_verified = True
    for attempt in attempts:
        quality = attempt.get("market_data_quality")
        if isinstance(quality, dict):
            quality_measured = True
            if isinstance(quality.get("status"), str):
                statuses.add(quality["status"])
            independently_verified &= quality.get("point_in_time_verified") is True
            found = quality.get("issues")
            if isinstance(found, list):
                issues.update(v for v in found if isinstance(v, str))
        candidates = attempt.get("candidates", [])
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            evaluated += 1
            candidate_hash = candidate.get("candidate_hash")
            if isinstance(candidate_hash, str):
                hashes.add(candidate_hash)
            if candidate.get("status") != "REJECT":
                continue
            rejected += 1
            failed = candidate.get("failed_gates", [])
            if not isinstance(failed, list):
                continue
            gate_records = candidate.get("gates", [])
            for gate in {g for g in failed if isinstance(g, str)}:
                counts[gate] += 1
                if gate not in examples:
                    detail = next(
                        (
                            item
                            for item in gate_records
                            if isinstance(item, dict) and item.get("name") == gate
                        ),
                        None,
                    ) if isinstance(gate_records, list) else None
                    if gate in {"fast", "full"}:
                        # This gate also checks return, but its stored actual
                        # reflects only trade count. Do not imply causality.
                        examples[gate] = {
                            "example_actual": None,
                            "example_threshold": None,
                            "measurement_note": "COMPOSITE_GATE_NOT_DISAMBIGUATED",
                        }
                    else:
                        examples[gate] = {
                            "example_actual": detail.get("actual")
                            if detail is not None else None,
                            "example_threshold": detail.get("threshold")
                            if detail is not None else None,
                        }
    leading = [
        {"gate": name, "count": count, **examples[name]}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]
    status = (
        "NOT_MEASURED"
        if not quality_measured or not statuses
        else next(iter(statuses)) if len(statuses) == 1 else "MIXED"
    )
    review_gate = str(leading[0]["gate"]) if leading else None
    return {
        "source": "immutable_evidence",
        "evaluated_candidate_instances": evaluated,
        "rejected_candidate_instances": rejected,
        "unique_candidate_hashes": len(hashes),
        "top_failed_gates": leading,
        "data_quality": {
            "status": status,
            "issues": sorted(issues),
            "point_in_time_verified": quality_measured and independently_verified,
        },
        "next_experiment": {
            "review_gate": review_gate,
            "review_hint": _REVIEW_HINTS.get(
                review_gate, "탈락한 평가 기준과 측정값을 검토하세요."
            ),
            "type": "SUGGESTION_NOT_AUTOMATIC_EXECUTION",
        } if review_gate is not None else None,
        "causal_status": "UNKNOWN",
        "sealed_oos": "NOT_MEASURED",
        "note": (
            "A candidate can fail multiple gates; counts overlap. "
            "Repeated evaluated candidate hashes are counted as instances. "
            "Review hints are not verified causal explanations."
        ),
    }
