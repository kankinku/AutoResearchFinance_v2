from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ExperimentPlan, ResearchBrief


@dataclass(slots=True, frozen=True)
class FamilyMemoryDraft:
    family: str
    symbol_scope: str
    timeframe_scope: str
    regime_scope: str
    outcome: str
    novelty_score: float


def build_family_memory(
    *,
    research_plan: ExperimentPlan | ResearchBrief,
    decision: str,
    analysis_output: dict[str, Any],
) -> FamilyMemoryDraft:
    signal_text = " ".join(
        [
            str(analysis_output.get("summary", "")),
            " ".join(str(item) for item in analysis_output.get("regime_observations", [])),
            " ".join(str(item) for item in analysis_output.get("weaknesses", [])),
        ]
    ).lower()
    return FamilyMemoryDraft(
        family=research_plan.experiment_type,
        symbol_scope=_first_match(signal_text, ("qqq", "iwm", "btc-usd"), default="all"),
        timeframe_scope=_first_match(signal_text, ("1d", "2h"), default="all"),
        regime_scope=_first_match(signal_text, ("bull", "bear"), default="mixed"),
        outcome=decision,
        novelty_score=1.0 if decision == "keep" else 0.5,
    )


def _first_match(signal_text: str, candidates: tuple[str, ...], *, default: str) -> str:
    for candidate in candidates:
        if candidate in signal_text:
            return candidate.upper() if candidate in {"qqq", "iwm"} else candidate
    return default
