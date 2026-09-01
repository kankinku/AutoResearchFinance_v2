from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mutation.primitive_registry import PrimitiveDefinition, PrimitiveRegistry


class PrimitiveProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    input_names: tuple[str, ...]
    output_type: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    lookback: int = Field(gt=0)
    test_vectors: tuple[dict[str, int | float], ...] = Field(min_length=1)
    justification: str = Field(min_length=1)
    reviewer_status: str = "PENDING"

    @field_validator("formula")
    @classmethod
    def reject_executable_formula(cls, value: str) -> str:
        forbidden = ("import ", "exec(", "eval(", "requests", "open(", "submit_order")
        if any(fragment in value.lower() for fragment in forbidden):
            raise ValueError("unsafe executable primitive formula")
        return value


def register_proposal(
    registry: PrimitiveRegistry, proposal: PrimitiveProposal
) -> PrimitiveDefinition:
    if proposal.reviewer_status != "APPROVED":
        raise ValueError("primitive proposal requires APPROVED reviewer status")
    return registry.register(
        proposal.name,
        input_names=proposal.input_names,
        output_type=proposal.output_type,
    )
