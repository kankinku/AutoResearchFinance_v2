from __future__ import annotations

from pathlib import Path


def test_project_declares_mimir_script_and_explicit_package_discovery() -> None:
    contents = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'mimir = "runtime.mimir:main"' in contents
    section_start = contents.index("[tool.setuptools.packages.find]")
    section = contents[section_start:]
    include = section.split("exclude =", maxsplit=1)[0]
    assert '"core*"' in include
    assert '"runtime*"' in include
    assert '"state*"' not in include



def test_project_declares_parquet_runtime_dependency() -> None:
    import tomllib

    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = payload["project"]["dependencies"]

    assert any(
        dependency == "pyarrow" or dependency.startswith("pyarrow>=")
        for dependency in dependencies
    )



def test_codex_mcp_example_uses_locked_uv_runtime() -> None:
    contents = Path(".codex/config.toml.example").read_text(encoding="utf-8")

    assert 'command = "uv"' in contents
    assert '"run", "--locked", "python"' in contents
    assert '"integrations.codex_mcp_server"' in contents


def test_validation_profiles_use_locked_declared_runtime() -> None:
    import json

    payload = json.loads(Path("moon.config.json").read_text(encoding="utf-8"))
    commands = [
        command
        for profile in payload["validation"]["profiles"].values()
        for command in profile
    ]

    assert commands
    assert all("uv run --locked --extra dev" in command for command in commands)
    assert all("--with" not in command for command in commands)
