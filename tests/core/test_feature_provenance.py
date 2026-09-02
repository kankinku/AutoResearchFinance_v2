from __future__ import annotations

from core.features.provenance import (
    audited_indicator_sources,
    excluded_symbol_names,
    registered_import_symbols,
)


def test_audited_sources_have_license_and_scope() -> None:
    sources = audited_indicator_sources()

    assert {source.repository for source in sources} == {
        "marketcalls/pyindicators",
        "srlcarlg/srl-python-indicators",
        "chironmind/CentaurTechnicalIndicators-Python",
        "kshlgrg/pythonpine",
    }
    pythonpine = next(source for source in sources if source.repository.endswith("pythonpine"))
    assert pythonpine.spdx == "AGPL-3.0"
    assert pythonpine.implementation_policy == "independent_reimplementation"


def test_live_order_and_network_symbols_are_never_imported() -> None:
    assert excluded_symbol_names().isdisjoint(registered_import_symbols())
    assert {"submit_order", "place_order", "MetaTrader5"} <= excluded_symbol_names()
