"""Versioned research policy target intent; not yet connected to the canonical backtester."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class PolicyDecision:
    decided_at: datetime
    executable_at: datetime
    symbol: str
    target_weight: float
    policy_id: str
    reason_hash: str
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        for timestamp in (self.decided_at, self.executable_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("timezone-aware timestamps required")
        if self.executable_at <= self.decided_at:
            raise ValueError("execution must follow decision")
        if not isfinite(self.target_weight) or not 0 <= self.target_weight <= 1:
            raise ValueError("finite long-only weight between zero and one required")
        if not self.symbol.strip() or not self.policy_id.strip():
            raise ValueError("symbol and policy identifier required")
        if re.fullmatch(r"[0-9a-f]{64}", self.reason_hash) is None:
            raise ValueError("lowercase SHA-256 reason hash required")
