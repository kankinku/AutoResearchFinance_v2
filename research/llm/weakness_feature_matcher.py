"""F2: bounded, non-causal weakness hypotheses matched to verified F1 profiles.

Observations, signal state, formula metadata and trade outcomes remain distinct.
No missing weakness is invented, no feature is promoted, and no trading rule is
automatically chosen. The connected GPT remains the proposal author.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.llm.feature_evidence_profile import build_verified_catalog_feature_profiles
from research.llm.loss_attribution import build_loss_attribution


class WeaknessMatcherError(ValueError):
    """Evidence is malformed, misattributed, too broad or not reproducible."""


# Human-readable hypotheses, not proven causes or mandatory remedies.
_INFORMATION_NEEDS: dict[str, str] = {
    "NO_BREAKOUT_AT_ENTRY": (
        "Does breakout context distinguish false entries from missed trend starts?"
    ),
    "EMA_TURNED_OFF_BY_EXIT": "Is a trend reversal real or only a transient EMA change?",
    "MOMENTUM_TURNED_OFF_BY_EXIT": "Is momentum weakening temporarily or the regime shifting?",
    "PARKINSON_VARIANCE_ROSE_DURING_HOLD": "Does rising range volatility change downside risk?",
    "REGIME_GATE_TURNED_OFF": "Does the transition between regimes justify different rules?",
    "EXIT_BELOW_OBSERVED_CLOSE_PEAK": (
        "Would exit timing information reduce giveback without churn?"
    ),
    "COST_EXCEEDS_POSITIVE_GROSS_PNL": (
        "Can excessive turnover fall without losing profitable opportunities?"
    ),
}


def _check_hashed(body: dict[str, Any], *, hash_field: str) -> None:
    expected = body.get(hash_field)
    if (
        not isinstance(expected, str)
        or content_hash({k: v for k, v in body.items() if k != hash_field}) != expected
    ):
        raise WeaknessMatcherError(f"tampered {hash_field}")


def match_weakness_to_profiles(
    loss_report: dict[str, Any],
    feature_report: dict[str, Any],
    *,
    max_weaknesses: int = 4,
) -> dict[str, Any]:
    """Join signed development observations by actual audit/data/strategy IDs.

    A positive signal's winning trades are counterexamples to a blanket rule
    removing positive entries; likewise wins in the non-positive state are
    counterexamples to insisting the signal must be positive for all entries.
    They do NOT establish whether a hypothetical portfolio filter is better.
    """
    if type(max_weaknesses) is not int or not 1 <= max_weaknesses <= 4:
        raise WeaknessMatcherError("unbounded weakness advice")
    _check_hashed(loss_report, hash_field="evidence_hash")
    _check_hashed(feature_report, hash_field="evidence_hash")
    if (
        loss_report.get("schema") != "observed-loss-attribution-p2-1-v1"
        or feature_report.get("schema") != "feature-evidence-profile-f1-v1"
        or feature_report.get("validation_scope") != "REUSED_DEVELOPMENT_ONLY"
        or feature_report.get("causal_status") != "NOT_ESTABLISHED"
        or loss_report.get("causal_status") != "NOT_ESTABLISHED"
        or feature_report.get("broker_executable") is not False
        or loss_report.get("broker_executable") is not False
        or feature_report.get("independent_oos_approved") is not False
        or loss_report.get("independent_oos_approved") is not False
        or any(
            loss_report.get(key) != feature_report.get(other)
            for key, other in (
                ("dataset_hash", "dataset_hash"),
                ("source_audit_hash", "source_audit_hash"),
                ("strategy_hash", "strategy_hash"),
            )
        )
    ):
        raise WeaknessMatcherError("F1/F2 sources do not share certified ancestors")

    suggestions = loss_report.get("test_suggestions")
    profiles = feature_report.get("profiles")
    if (
        not isinstance(suggestions, list)
        or len(suggestions) > 4
        or not isinstance(profiles, list)
        or len(profiles) > 5
    ):
        raise WeaknessMatcherError("unbounded/malformed evidence collection")
    for prof in profiles:
        if not isinstance(prof, dict):
            raise WeaknessMatcherError("non-object feature evidence")
        _check_hashed(prof, hash_field="profile_hash")
        if (
            prof.get("source_audit_hash") != feature_report["source_audit_hash"]
            or prof.get("dataset_hash") != feature_report["dataset_hash"]
            or prof.get("source_strategy_hash") != feature_report["strategy_hash"]
            or prof.get("broker_executable") is not False
            or prof.get("independent_oos_approved") is not False
        ):
            raise WeaknessMatcherError("feature provenance mismatch")

    source_evidence = {
        case.get("trade_id") for case in loss_report.get("loss_cases", []) if isinstance(case, dict)
    }
    weaknesses = []
    for item in suggestions[:max_weaknesses]:
        if (
            not isinstance(item, dict)
            or item.get("kind") != "RECOMMEND_TEST_ONLY"
            or item.get("test_result") != "NOT_RUN"
            or item.get("causal_status") != "NOT_ESTABLISHED"
            or not isinstance(item.get("evidence_trade_ids"), list)
            or not item["evidence_trade_ids"]
            or not set(item["evidence_trade_ids"]) <= source_evidence
        ):
            raise WeaknessMatcherError("unsupported inference or forged trade evidence")
        code = item.get("observation_code")
        if not isinstance(code, str):
            raise WeaknessMatcherError("invalid weakness code")
        proposed = {
            "observation_code": code,
            "observed_trade_ids": item["evidence_trade_ids"][:8],
            "source_indicator_or_metric": item.get("indicator_or_metric"),
            "needed_information": _INFORMATION_NEEDS.get(
                code, "Unknown mechanism; determine which information is missing."
            ),
            "observed_loss_examples": item.get("observed_loss_cases"),
            "alternative_explanation": item.get("alternative_explanation"),
            "alternatives_to_test": [
                "PARENT_UNCHANGED",
                "EXISTING_FEATURE_ABLATION",
                "REMOVE_REDUNDANT_RULE",
                "FORMULA_NEW",
                "DO_NOT_CHANGE",
            ],
            "test_result": "NOT_RUN",
            "causal_status": "NOT_ESTABLISHED",
            "parent_audit_hash": feature_report["source_audit_hash"],
        }
        weaknesses.append(
            {
                **proposed,
                "weakness_id": content_hash(proposed)[:24],
            }
        )

    features = []
    linked_features = {w["source_indicator_or_metric"] for w in weaknesses}
    for prof in profiles:
        observed = prof.get("entry_outcomes_by_observed_signal")
        if not isinstance(observed, list):
            raise WeaknessMatcherError("feature signal cohort missing")
        cohorts = {row["signal_state"]: row for row in observed}
        if not isinstance(prof.get("feature_id"), str):
            raise WeaknessMatcherError("unidentified feature")
        metadata = prof.get("formula_metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("candidate_hash"), str):
            raise WeaknessMatcherError("F2 candidate requires VERIFIED calculator identity")
        positive = cohorts.get("POSITIVE", {})
        nonpositive = cohorts.get("NON_POSITIVE", {})
        counterexamples = []
        if prof.get("binary_signal"):
            if nonpositive.get("wins", 0):
                counterexamples.append(
                    {
                        "assumption_challenged": "ALWAYS_REQUIRE_POSITIVE_SIGNAL",
                        "winning_entries_excluded_by_blanket_filter": nonpositive["wins"],
                        "losing_entries_also_excluded": nonpositive.get("losses", 0),
                        "not_portfolio_counterfactual": True,
                    }
                )
            if positive.get("losses", 0):
                counterexamples.append(
                    {
                        "assumption_challenged": "POSITIVE_SIGNAL_GUARANTEES_WIN",
                        "losing_entries_with_positive_signal": positive["losses"],
                        "winning_entries_with_positive_signal": positive.get("wins", 0),
                        "not_portfolio_counterfactual": True,
                    }
                )
        if not counterexamples:
            counterexamples.append(
                {
                    "assumption_challenged": "OBSERVATIONAL_EVIDENCE_IS_PROOF",
                    "reason": "No supported conditional effect or insufficient samples",
                    "not_portfolio_counterfactual": True,
                }
            )
        features.append(
            {
                "feature_id": prof["feature_id"],
                "formula_hash": metadata["candidate_hash"],
                "calculator": metadata.get("calculator"),
                "lookback": metadata.get("lookback"),
                "formula_identity_scope": metadata.get("verification_scope"),
                "profile_hash": prof["profile_hash"],
                "candidate_status": (
                    "OBSERVED_CONTRADICTORY_OR_INSUFFICIENT"
                    if prof["feature_id"] in linked_features
                    else "NO_DIRECT_WEAKNESS_LINK"
                ),
                "linked_weakness_ids": [
                    w["weakness_id"]
                    for w in weaknesses
                    if w["source_indicator_or_metric"] == prof["feature_id"]
                ],
                "needed_information_hypotheses": [
                    w["needed_information"]
                    for w in weaknesses
                    if w["source_indicator_or_metric"] == prof["feature_id"]
                ],
                "observed_entry_states": deepcopy(observed),
                "candidate_strength_hypotheses": [
                    "A signal state coincided with winning entries in the signed "
                    "development sample; not proof of predictive utility."
                ]
                if any(row.get("wins", 0) > 0 for row in observed)
                else [],
                "candidate_limitation_hypotheses": [
                    "A signal state also coincided with losing entries; compare "
                    "false rejections and missed winners using whole-portfolio S7."
                ]
                if any(row.get("losses", 0) > 0 for row in observed)
                else [],
                "counterexamples": counterexamples,
                "regime_observations": deepcopy(prof["signal_conditioned_regime_counts"][:8]),
                "observation_sample": {
                    "valid_bars": prof["signal_observation_count"],
                    "missing_bars": prof["missing_count"],
                    "wins": prof["winning_entry_count"],
                    "losses": prof["losing_entry_count"],
                    "no_entry_decisions": prof["no_entry_decision_count"],
                },
                "no_entry_examples": deepcopy(prof["no_entry_decision_examples"][:3]),
                "evidence_status": prof["evidence_status"],
                "evaluation_required": "S7_COSTED_PARENT_COMPARISON",
                "auto_select": False,
            }
        )

    body = {
        "schema": "weakness-feature-guidance-f2-v1",
        "source_loss_evidence_hash": loss_report["evidence_hash"],
        "feature_profile_evidence_hash": feature_report["evidence_hash"],
        "source_audit_hash": feature_report["source_audit_hash"],
        "strategy_hash": feature_report["strategy_hash"],
        "dataset_hash": feature_report["dataset_hash"],
        "weaknesses": weaknesses,
        "features": features,
        "comparison_options": [
            "PARENT_UNCHANGED",
            "FEATURE_ADD",
            "FEATURE_REPLACE",
            "FEATURE_REMOVE",
            "FORMULA_NEW",
            "DO_NOT_CHANGE",
        ],
        "recommended_auto_mutations": [],
        "researcher_instruction": (
            "Identify the information missing from the parent, examine both loss and "
            "winning-trade counterexamples, compare redundancy and availability, "
            "then write your own falsifiable hypothesis or retain the parent. "
            "The reported winners/losses are retrospective labels, not features "
            "or causal evidence; every modification needs costed S7 ablation."
        ),
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    return {**body, "guidance_hash": content_hash(body)}


def build_weakness_feature_guidance(
    catalog: ResearchCatalog,
    audit: AcademicDecisionAudit,
    market: MarketDataSet,
    *,
    max_features: int = 3,
) -> dict[str, Any]:
    """Auto-discover a few verified features, not a ranked top-173 catalog."""
    if type(max_features) is not int or not 1 <= max_features <= 5:
        raise WeaknessMatcherError("invalid candidate budget")
    losses = build_loss_attribution(audit, market)
    verified = {
        x.signal_id
        for x in catalog.list_indicators(eligible_only=True)
        if x.scope == "single_asset"
    }
    candidate_names = [
        item["indicator_or_metric"]
        for item in losses["test_suggestions"]
        if item["indicator_or_metric"] in verified
    ]
    # Coverage before arbitrary rankings; GPT is free to propose a completely
    # different expression or remove an indicator after reviewing evidence.
    candidate_names.extend(("ema_direction_20", "sma_direction", "parkinson_variance"))
    candidate_names.extend(sorted(verified))
    selected = tuple(dict.fromkeys(name for name in candidate_names if name in verified))[
        :max_features
    ]
    if not selected:
        raise WeaknessMatcherError("no verified calculator available for F2")
    evidence = build_verified_catalog_feature_profiles(
        catalog, audit, market, selected, max_examples=6
    )
    return match_weakness_to_profiles(losses, evidence)
