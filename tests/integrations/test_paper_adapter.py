from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from integrations.kis.paper_adapter import PaperApproval, PaperTradingAdapter


def _approval() -> PaperApproval:
    return PaperApproval(
        champion_hash="champion-1",
        validated=True,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )


def test_paper_adapter_requires_validated_exact_champion() -> None:
    adapter = PaperTradingAdapter("champion-1", initial_cash=10_000)
    with pytest.raises(PermissionError, match="paper"):
        adapter.submit_order("TEST", "buy", quantity=10, price=100)

    adapter.enable(_approval())
    fill = adapter.submit_order("TEST", "buy", quantity=10, price=100)

    assert fill.notional == 1000
    assert adapter.cash == 9000
    assert adapter.positions["TEST"] == 10


def test_paper_adapter_rejects_mismatched_or_expired_validation() -> None:
    adapter = PaperTradingAdapter("champion-1", initial_cash=1000)
    with pytest.raises(PermissionError, match="champion"):
        adapter.enable(PaperApproval("other", True, _approval().expires_at))
    with pytest.raises(PermissionError, match="expired"):
        adapter.enable(
            PaperApproval("champion-1", True, datetime.now(timezone.utc) - timedelta(seconds=1))
        )
