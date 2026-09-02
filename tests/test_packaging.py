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
