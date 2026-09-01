from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchPermissions:
    order_permission: bool
    credential_ref: str | None


def validate_research_permissions(permissions: ResearchPermissions) -> None:
    if permissions.order_permission:
        raise PermissionError("research process cannot have order permission")
    if permissions.credential_ref is not None:
        raise PermissionError("research process cannot receive KIS credentials")
