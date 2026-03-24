from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest


ALLOWED_TARGET_PATH = "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"


def make_artifact(source: str, **overrides: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "kind": "strategy_replacement",
        "target_path": ALLOWED_TARGET_PATH,
        "hypothesis": "Test hypothesis",
        "change_summary": "Replace mutable strategy candidate",
        "full_file_contents": source,
        "expected_effects": ["Improve behavior"],
    }
    artifact.update(overrides)
    return artifact


def valid_strategy_source(*, extra_imports: str = "", extra_body: str = "") -> str:
    return "\n".join(
        [
            extra_imports.rstrip(),
            "import pandas as pd",
            "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
            "",
            "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
            extra_body.rstrip(),
            "    regime = pd.Series('bull', index=context.close.index, dtype='object')",
            "    no_signal = context.close > (context.close + 1)",
            "    return StrategyDefinition(",
            "        long_entries=no_signal,",
            "        long_exits=no_signal,",
            "        short_entries=no_signal,",
            "        short_exits=no_signal,",
            "        regime=regime,",
            "        params={'fast_window': 20, 'slow_window': 50},",
            "        diagnostics={'regime': regime, 'summary': 'valid artifact'},",
            "    )",
            "",
        ]
    ).lstrip()


def make_context() -> object:
    from finance_autoresearch.strategy.base_contract import (
        DEFAULT_INDICATORS,
        DEFAULT_REGIMES,
        StrategyContext,
    )

    index = pd.RangeIndex(start=0, stop=260, step=1)
    close = pd.Series(range(100, 360), index=index, dtype=float)
    return StrategyContext(
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=pd.Series(1_000.0, index=index),
        symbol="QQQ",
        timeframe="1d",
        indicators=DEFAULT_INDICATORS,
        regimes=DEFAULT_REGIMES,
    )


def test_patch_applier_rejects_non_mapping_artifact(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    with pytest.raises(ValueError, match="artifact"):
        apply_strategy_artifact(["not", "an", "object"], repository_root=tmp_path)


def test_patch_applier_rejects_multi_file_targets(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(
        valid_strategy_source(),
        files=[
            {"target_path": ALLOWED_TARGET_PATH, "full_file_contents": "pass\n"},
            {"target_path": "other.py", "full_file_contents": "pass\n"},
        ],
    )

    with pytest.raises(ValueError, match="multi-file"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_forbidden_import(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(valid_strategy_source(extra_imports="import os"))

    with pytest.raises(ValueError, match="forbidden import"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_forbidden_call(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(valid_strategy_source(extra_body="    open('secret.txt')"))

    with pytest.raises(ValueError, match="forbidden call"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_target_path_mismatch(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(
        valid_strategy_source(),
        target_path="src/finance_autoresearch/strategy/base_contract.py",
    )

    with pytest.raises(ValueError, match="target_path"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_shell_instructions(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(
        valid_strategy_source(),
        change_summary="```bash\npython dangerous.py\n```",
    )

    with pytest.raises(ValueError, match="shell instructions"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_missing_build_strategy(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    artifact = make_artifact(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "def helper() -> pd.Series:",
                "    return pd.Series([True, False])",
                "",
            ]
        )
    )

    with pytest.raises(ValueError, match="build_strategy"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_rejects_files_longer_than_400_lines(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    filler = ["# filler"] * 401
    artifact = make_artifact(
        "\n".join(filler + valid_strategy_source().splitlines())
    )

    with pytest.raises(ValueError, match="400 lines"):
        apply_strategy_artifact(artifact, repository_root=tmp_path)


def test_patch_applier_replaces_file_contents_for_valid_artifact(tmp_path: Path) -> None:
    from finance_autoresearch.mutation.patch_applier import apply_strategy_artifact

    target_path = tmp_path / ALLOWED_TARGET_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("print('old')\n", encoding="utf-8")
    artifact = make_artifact(valid_strategy_source())

    written_path = apply_strategy_artifact(artifact, repository_root=tmp_path)

    assert written_path == target_path
    assert target_path.read_text(encoding="utf-8") == artifact["full_file_contents"]


def test_baseline_strategy_module_exposes_build_strategy_and_returns_definition() -> None:
    from finance_autoresearch.strategy.base_contract import StrategyDefinition

    importlib.invalidate_caches()
    module = importlib.import_module(
        "finance_autoresearch.strategy.mutable.strategy_candidate"
    )

    strategy = module.build_strategy(make_context())

    assert callable(module.build_strategy)
    assert isinstance(strategy, StrategyDefinition)


def test_regime_classifier_returns_only_bull_or_bear() -> None:
    from finance_autoresearch.strategy.regime_registry import (
        classify_ema200_regime,
        is_bear,
        is_bull,
    )

    close = pd.Series(([100.0] * 210) + ([150.0] * 10) + ([50.0] * 10), dtype=float)

    regime = classify_ema200_regime(close)

    assert set(regime.unique()) == {"bull", "bear"}
    assert is_bull(close).equals(regime.eq("bull"))
    assert is_bear(close).equals(regime.eq("bear"))
