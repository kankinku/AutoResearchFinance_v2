from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceStatusSnapshot(BaseModel):
    """Bootstrap/configuration-plane status exposed through MCP."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    plane: Literal["BOOTSTRAP_CONFIGURATION"] = "BOOTSTRAP_CONFIGURATION"
    status: Literal["NOT_INITIALIZED", "PARTIAL", "READY"]
    initialized_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    invalid_components: list[str] = Field(default_factory=list)
    champion: str
    frontier_families: int = 0
    selected_mode: Literal["paper", "live"] = "paper"
    mode_configured: bool = False
    orders_enabled: Literal[False] = False
    audit_records: int = 0
    validated_manifests: int = 0
