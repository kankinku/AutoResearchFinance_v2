from __future__ import annotations

from pathlib import Path

import pytest

from strategy_import.sources import GitHubSource, SourceSecurityError, parse_github_source


def test_parse_github_source_requires_public_https_url() -> None:
    source = parse_github_source(
        "https://github.com/example/strategies.git",
        ref="main",
    )

    assert isinstance(source, GitHubSource)
    assert source.repository_url == "https://github.com/example/strategies.git"
    assert source.ref == "main"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/strategies.git",
        "https://user:password@github.com/example/strategies.git",
        "file:///C:/secrets/repository",
    ],
)
def test_parse_github_source_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(SourceSecurityError):
        parse_github_source(url, ref="main")


def test_source_file_rejects_credentials_and_raw_source_paths(tmp_path: Path) -> None:
    from strategy_import.sources import iter_safe_source_files

    (tmp_path / "strategy.py").write_text("STRATEGY = {}", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=not-for-output", encoding="utf-8")
    (tmp_path / "raw_sources").mkdir()
    (tmp_path / "raw_sources" / "dump.py").write_text("secret", encoding="utf-8")

    files = list(iter_safe_source_files(tmp_path))

    assert [item.relative_path for item in files] == [Path("strategy.py")]
    assert all("TOKEN" not in item.content for item in files)
