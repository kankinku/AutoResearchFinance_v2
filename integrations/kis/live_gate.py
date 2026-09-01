from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LiveApproval:
    champion_hash: str
    approved_by: str
    expires_at: datetime


def validate_live_approval(approval: LiveApproval, *, champion_hash: str) -> bool:
    if approval.champion_hash != champion_hash:
        raise PermissionError("approval champion hash does not match")
    if not approval.approved_by:
        raise PermissionError("human approval is required")
    now = datetime.now(timezone.utc)
    expires_at = approval.expires_at
    if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= now:
        raise PermissionError("live approval is expired")
    return True
