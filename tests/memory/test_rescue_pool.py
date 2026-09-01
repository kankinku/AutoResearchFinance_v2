from __future__ import annotations

import pytest

from memory.frontier import CandidateState
from memory.rescue_pool import RescueEntry, RescuePool


def test_rescue_pool_persists_near_miss_mutations_without_duplicates() -> None:
    pool = RescuePool()
    entry = RescueEntry("c1", "parent", ("ADD_RULE",), "trade_count", "momentum")

    pool.add(entry, status=CandidateState.NEAR_MISS)
    pool.add(entry, status=CandidateState.NEAR_MISS)

    assert pool.entries() == (entry,)
    with pytest.raises(ValueError, match="NEAR_MISS"):
        pool.add(entry, status=CandidateState.REJECT)
