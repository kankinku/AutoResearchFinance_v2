from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.mimir import MimirCommand, ResearchPaths, parse_mimir_command, resolve_research_paths


def test_parse_mimir_command_accepts_direct_slash_syntax() -> None:
    assert parse_mimir_command(["/research", "20"]) == MimirCommand("research", ("20",))
    assert parse_mimir_command(["/status"]) == MimirCommand("status", ())


def test_parse_mimir_command_rejects_invalid_research_count() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        parse_mimir_command(["/research", "forever"])


def test_resolve_research_paths_prefers_explicit_then_env_then_state(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_path = state_dir / "system" / "research_loop.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "config": {
                    "source_path": "state-source.json",
                    "data_path": "state-data.parquet",
                    "series_data_path": "state-series.parquet",
                }
            }
        ),
        encoding="utf-8",
    )

    env_paths = resolve_research_paths(
        source=None,
        data=None,
        series_data=None,
        env_values={
            "MIMIR_SOURCE": "env-source.json",
            "MIMIR_DATA": "env-data.parquet",
            "MIMIR_SERIES_DATA": "env-series.parquet",
        },
        state_dir=state_dir,
    )
    assert env_paths == ResearchPaths("env-source.json", "env-data.parquet", "env-series.parquet")

    explicit_paths = resolve_research_paths(
        source="explicit-source.json",
        data="explicit-data.parquet",
        series_data=None,
        env_values={
            "MIMIR_SOURCE": "env-source.json",
            "MIMIR_DATA": "env-data.parquet",
            "MIMIR_SERIES_DATA": "env-series.parquet",
        },
        state_dir=state_dir,
    )
    assert explicit_paths == ResearchPaths(
        "explicit-source.json", "explicit-data.parquet", "env-series.parquet"
    )


def test_resolve_research_paths_reports_missing_required_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MIMIR_SOURCE.*MIMIR_DATA"):
        resolve_research_paths(
            source=None,
            data=None,
            series_data=None,
            env_values={},
            state_dir=tmp_path / "state",
        )


def test_mimir_module_exposes_main_entrypoint() -> None:
    import runtime.mimir as mimir

    assert callable(mimir.main)
