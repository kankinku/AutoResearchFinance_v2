from __future__ import annotations

import pytest

from research.llm.director import ResearchDirector, ResearchIntent
from research.llm.provider import OfflineProvider


def test_offline_director_returns_deterministic_intent_without_code_patch() -> None:
    director = ResearchDirector(OfflineProvider())
    context = {"generation": 4, "frontier": ["S1"], "unexplored": ["volatility"]}

    first = director.propose(context)
    second = director.propose(context)

    assert first == second
    assert isinstance(first, ResearchIntent)
    assert first.parent_ids == ("S1",)
    assert first.python_patch is None
    assert first.evaluator_change is None


def test_director_rejects_forbidden_intent_fields() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        ResearchIntent(
            mode="structure",
            parent_ids=("S1",),
            operations=(),
            rationale="bad",
            python_patch="write evaluator",
        )
