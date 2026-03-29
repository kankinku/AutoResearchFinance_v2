from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from finance_autoresearch.runtime import StrategyHarness, build_runtime, build_subprocess_env
from finance_autoresearch.settings import Settings


def test_build_subprocess_env_propagates_research_knowledge_root(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_id="finance",
        workspace_root=tmp_path / "workspace",
        state_db_path=tmp_path / "runtime" / "state.db",
        research_knowledge_root=Path("knowledge/indicators"),
        research_brain_root=Path("knowledge/vault"),
        output_language="ko",
        docs_output_language="ko",
        log_output_language="en",
        factor_catalog_enabled=True,
        factor_catalog_root=Path("knowledge/factors"),
    )

    env = build_subprocess_env(settings)

    assert Path(env["FINANCE_AUTORESEARCH_RESEARCH_KNOWLEDGE_ROOT"]) == (
        settings.workspace_root / "knowledge" / "indicators"
    )
    assert Path(env["FINANCE_AUTORESEARCH_STATE_DB_PATH"]) == (
        tmp_path / "runtime" / "state.db"
    )
    assert Path(env["FINANCE_AUTORESEARCH_RESEARCH_BRAIN_ROOT"]) == (
        settings.workspace_root / "knowledge" / "vault"
    )
    assert env["FINANCE_AUTORESEARCH_FACTOR_CATALOG_ENABLED"] == "true"
    assert Path(env["FINANCE_AUTORESEARCH_FACTOR_CATALOG_ROOT"]) == (
        settings.workspace_root / "knowledge" / "factors"
    )
    assert env["FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE"] == "ko"
    assert env["FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE"] == "ko"
    assert env["FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE"] == "en"


def test_build_runtime_uses_same_resolved_paths_as_subprocess_env(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "knowledge" / "indicators").mkdir(parents=True)
    (workspace_root / "knowledge" / "indicators" / "rsi.md").write_text(
        "# RSI\nIndicator notes.\n",
        encoding="utf-8",
    )
    (workspace_root / "knowledge" / "vault" / "03 Lessons").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        project_id="finance",
        workspace_root=workspace_root,
        state_db_path=Path("runtime/state.db"),
        research_knowledge_root=Path("knowledge"),
        research_brain_root=Path("knowledge/vault"),
    )

    runtime = build_runtime(settings)
    try:
        env = build_subprocess_env(settings)
        snippets = runtime.autoresearch_runner._knowledge_loader.load()
    finally:
        runtime.close()

    assert runtime.store._db_path == Path(env["FINANCE_AUTORESEARCH_STATE_DB_PATH"])
    assert snippets[0].source_path == "knowledge/indicators/rsi.md"
    assert runtime.autoresearch_runner._brain_sync is not None


def test_strategy_harness_caches_market_pack_for_worker_lifetime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    load_calls: list[Path] = []

    def fake_loader(*, cache_root: Path) -> dict[str, object]:
        load_calls.append(cache_root)
        return {"market-pack": True}

    monkeypatch.setattr(
        "finance_autoresearch.runtime.load_strategy_module",
        lambda path: SimpleNamespace(__name__="test_strategy_module"),
    )
    monkeypatch.setattr(
        "finance_autoresearch.runtime.run_backtests",
        lambda market_pack, strategy_module: {"ok": market_pack["market-pack"]},
    )

    harness = StrategyHarness(cache_root=tmp_path, market_pack_loader=fake_loader)

    first = harness(tmp_path / "strategy.py")
    second = harness(tmp_path / "strategy.py")

    assert first == {"ok": True}
    assert second == {"ok": True}
    assert load_calls == [tmp_path]


def test_strategy_harness_smoke_uses_four_representative_combinations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_market_keys: list[tuple[tuple[str, str], ...]] = []

    monkeypatch.setattr(
        "finance_autoresearch.runtime.load_strategy_module",
        lambda path: SimpleNamespace(__name__="test_strategy_module"),
    )

    def fake_run_backtests(market_pack, strategy_module, *, market_keys=None):
        captured_market_keys.append(tuple(market_keys or ()))
        return {"ok": True}

    monkeypatch.setattr("finance_autoresearch.runtime.run_backtests", fake_run_backtests)

    harness = StrategyHarness(cache_root=tmp_path, market_pack_loader=lambda cache_root: {})

    result = harness.smoke(tmp_path / "strategy.py")

    assert result == {"ok": True}
    assert captured_market_keys == [
        (("QQQ", "1d"), ("IWM", "2h"), ("BTC-USD", "1d"), ("BTC-USD", "2h"))
    ]
