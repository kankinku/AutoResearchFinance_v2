"""Do not let read-only parent preview run on operational in-tree state."""
from datetime import date
from pathlib import Path

import pytest

from application.generalization_parent_preview import preview_counted_parent_generalization
from research.indicator_engine.catalog import ResearchCatalogError
from tests.research.test_academic_inherited_historical_robustness import _market


def test_in_tree_operational_state_rejected_before_ledger_read(tmp_path: Path) -> None:
    class FakeService:
        root = tmp_path
        state = tmp_path / "state" / "academic-gpt-checkpoints"

        @property
        def cycle(self):
            raise AssertionError("must not touch operational cycle")

    with pytest.raises(ResearchCatalogError, match="isolated state"):
        preview_counted_parent_generalization(
            FakeService(), None, _market(),
            session_id="a" * 32, generations=(64,),
            years=(2021, 2022), last_development_date=date(2022,12,31),
            next_generation=69,
        )
