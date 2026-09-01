from __future__ import annotations

import pytest

from mutation.primitive_registry import PrimitiveRegistry
from strategy_ir.primitive_proposal import PrimitiveProposal, register_proposal


def test_approved_primitive_proposal_registers_without_executable_code() -> None:
    proposal = PrimitiveProposal(
        name="custom_momentum",
        input_names=("period",),
        output_type="indicator",
        formula="close[t] / close[t-period] - 1",
        lookback=20,
        test_vectors=({"input": 100, "expected": 0.1},),
        justification="bounded momentum feature",
        reviewer_status="APPROVED",
    )

    definition = register_proposal(PrimitiveRegistry(), proposal)

    assert definition.name == "custom_momentum"


def test_primitive_proposal_rejects_code_and_unreviewed_proposals() -> None:
    with pytest.raises(ValueError, match="unsafe|APPROVED"):
        PrimitiveProposal(
            name="unsafe",
            input_names=(),
            output_type="indicator",
            formula="import requests",
            lookback=1,
            test_vectors=({"input": 1, "expected": 1},),
            justification="bad",
            reviewer_status="PENDING",
        )
