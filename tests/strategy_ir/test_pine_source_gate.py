from research.pine_import.source_gate import audit_pine_source


def test_source_intake_never_enables_unaudited_conversion():
    src = '//@version=5\n// SPDX-License-Identifier: MPL-2.0\nstrategy("demo")\n'
    result = audit_pine_source(src, permission_confirmed=True)
    assert result.pine_version == "5"
    assert result.declaration == "strategy"
    assert result.license_header_detected
    assert len(result.sha256) == 64
    assert not result.conversion_permitted
    assert result.issues == ("MANUAL_SEMANTIC_PARITY_REVIEW_REQUIRED",)


def test_rejects_indicator_and_ambiguous_license():
    result = audit_pine_source('//@version=6\nindicator("demo")')
    assert not result.conversion_permitted
    assert "NOT_A_PINE_STRATEGY" in result.issues
    assert "LICENSE_HEADER_NOT_VERIFIED" in result.issues


def test_flags_execution_semantics_not_represented_by_daily_ir():
    result = audit_pine_source(
        "// @version=5\n// MIT License\n"
        'strategy("demo", pyramiding=2)\nstrategy.exit("x")\n'
        'request.security(syminfo.tickerid,"D",close)'
    )
    assert set(result.unsupported_features) == {"orders", "multi_timeframe", "pyramiding"}
    assert "UNSUPPORTED_EXECUTION_SEMANTICS" in result.issues
