from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PublicToolPlane = Literal[
    "BOOTSTRAP_CONFIGURATION",
    "CATALOG_VALIDATION",
    "EVIDENCE_STATUS",
    "EXECUTION_LIFECYCLE",
]


class PublicToolContractMetadata(BaseModel):
    """Version marker attached additively to public MCP tool responses."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    tool: str
    plane: PublicToolPlane
    orders_enabled: Literal[False] = False
