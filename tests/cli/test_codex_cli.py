"""Retired CLI model entrypoints must stay unavailable in the GPT-only system."""

from __future__ import annotations

import pytest

from cli import build_parser


@pytest.mark.parametrize("command", ["research-intent", "autoresearch", "terminal"])
def test_obsolete_embedded_model_commands_are_not_advertised(command: str) -> None:
    with pytest.raises(SystemExit, match="2"):
        build_parser().parse_args([command])


def test_gpt_only_cli_still_exposes_offline_deterministic_backtests() -> None:
    assert (
        build_parser()
        .parse_args(
            ["repeat-research", "--source", "a.yaml", "--data", "b.parquet", "--generations", "3"]
        )
        .generations
        == 3
    )
