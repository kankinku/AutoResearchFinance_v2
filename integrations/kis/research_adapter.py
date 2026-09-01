from __future__ import annotations


class ResearchKISAdapter:
    """Read-only KIS boundary exposed to research code."""

    def historical_data(self, symbol: str) -> tuple[object, ...]:
        if not symbol:
            raise ValueError("symbol is required")
        return ()
