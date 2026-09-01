from __future__ import annotations

from pathlib import Path, PurePosixPath

_PROTECTED_ROOTS = (
    PurePosixPath("core/data"),
    PurePosixPath("core/backtest"),
    PurePosixPath("core/evaluator"),
    PurePosixPath("core/validation"),
    PurePosixPath("core/costs"),
    PurePosixPath("core/integrity"),
)


def protected_roots() -> tuple[Path, ...]:
    return tuple(Path(root.as_posix()) for root in _PROTECTED_ROOTS)


def is_protected_path(path: Path) -> bool:
    normalized = PurePosixPath(path.as_posix().lstrip("./"))
    return any(normalized == root or root in normalized.parents for root in _PROTECTED_ROOTS)


def assert_research_write_allowed(path: Path) -> None:
    if is_protected_path(path):
        raise PermissionError(f"research agent cannot write protected path: {path}")
