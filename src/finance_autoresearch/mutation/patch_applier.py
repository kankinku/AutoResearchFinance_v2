from __future__ import annotations

import ast
import py_compile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ALLOWED_TARGET_PATH = "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
MAX_STRATEGY_FILE_LINES = 400

_REQUIRED_KEYS = {
    "kind",
    "target_path",
    "hypothesis",
    "change_summary",
    "full_file_contents",
    "expected_effects",
}
_ALLOWED_STANDARD_IMPORTS = {"math", "numpy", "pandas", "typing", "dataclasses"}
_ALLOWED_PROJECT_IMPORTS = {
    "finance_autoresearch.strategy.base_contract",
    "finance_autoresearch.strategy.indicator_registry",
    "finance_autoresearch.strategy.regime_registry",
}
_FORBIDDEN_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "pathlib",
    "socket",
    "requests",
    "httpx",
    "shutil",
    "tempfile",
}
_FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__"}
_SHELL_INSTRUCTION_MARKERS = (
    "```bash",
    "```sh",
    "```powershell",
    "bash -",
    "sh -c",
    "powershell -",
    "pwsh -",
    "cmd /c",
    "git apply",
    "diff --git",
)


@dataclass(slots=True, frozen=True)
class StrategyReplacementArtifact:
    kind: str
    target_path: str
    hypothesis: str
    change_summary: str
    full_file_contents: str
    expected_effects: list[str]


def apply_strategy_artifact(
    artifact: Mapping[str, Any] | object,
    *,
    repository_root: Path | str,
) -> Path:
    validated_artifact = _validate_artifact_object(artifact)
    if validated_artifact.target_path != ALLOWED_TARGET_PATH:
        raise ValueError("target_path must exactly match the mutable strategy candidate")

    try:
        tree = ast.parse(
            validated_artifact.full_file_contents,
            filename=validated_artifact.target_path,
        )
    except SyntaxError as exc:
        raise ValueError(f"strategy source must parse as Python: {exc.msg}") from exc

    _validate_imports(tree)
    _validate_calls(tree)
    _validate_top_level_statements(tree)
    _require_top_level_build_strategy(tree)
    _validate_py_compile(validated_artifact.full_file_contents)

    if _line_count(validated_artifact.full_file_contents) > MAX_STRATEGY_FILE_LINES:
        raise ValueError("strategy source must not exceed 400 lines")

    destination = Path(repository_root) / validated_artifact.target_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(validated_artifact.full_file_contents, encoding="utf-8")
    return destination


def _validate_artifact_object(
    artifact: Mapping[str, Any] | object,
) -> StrategyReplacementArtifact:
    if not isinstance(artifact, Mapping):
        raise ValueError("artifact must be an object mapping")

    if any(key in artifact for key in ("files", "targets", "target_paths")):
        raise ValueError("multi-file targets are not allowed")

    extra_keys = set(artifact) - _REQUIRED_KEYS
    missing_keys = _REQUIRED_KEYS - set(artifact)
    if missing_keys or extra_keys:
        raise ValueError("artifact must match the strategy_replacement schema")

    kind = artifact["kind"]
    target_path = artifact["target_path"]
    hypothesis = artifact["hypothesis"]
    change_summary = artifact["change_summary"]
    full_file_contents = artifact["full_file_contents"]
    expected_effects = artifact["expected_effects"]

    if kind != "strategy_replacement":
        raise ValueError("artifact kind must be strategy_replacement")
    if not isinstance(target_path, str):
        raise ValueError("target_path must be a string")
    if not isinstance(hypothesis, str):
        raise ValueError("hypothesis must be a string")
    if not isinstance(change_summary, str):
        raise ValueError("change_summary must be a string")
    if not isinstance(full_file_contents, str):
        raise ValueError("full_file_contents must be a string")
    if (
        not isinstance(expected_effects, Sequence)
        or isinstance(expected_effects, (str, bytes))
        or any(not isinstance(effect, str) for effect in expected_effects)
    ):
        raise ValueError("expected_effects must be a list of strings")

    _reject_shell_instructions(
        hypothesis,
        change_summary,
        *expected_effects,
    )

    return StrategyReplacementArtifact(
        kind=kind,
        target_path=target_path,
        hypothesis=hypothesis,
        change_summary=change_summary,
        full_file_contents=full_file_contents,
        expected_effects=list(expected_effects),
    )


def _validate_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                root_name = module_name.split(".", 1)[0]
                if root_name in _FORBIDDEN_IMPORTS:
                    raise ValueError(f"forbidden import: {module_name}")
                if module_name in _ALLOWED_PROJECT_IMPORTS:
                    continue
                if root_name in _ALLOWED_STANDARD_IMPORTS:
                    continue
                raise ValueError(f"import not allowed: {module_name}")
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module
            if module_name is None:
                raise ValueError("relative imports are not allowed")
            root_name = module_name.split(".", 1)[0]
            if root_name in _FORBIDDEN_IMPORTS:
                raise ValueError(f"forbidden import: {module_name}")
            if module_name in _ALLOWED_PROJECT_IMPORTS:
                continue
            if root_name in _ALLOWED_STANDARD_IMPORTS:
                continue
            raise ValueError(f"import not allowed: {module_name}")


def _validate_calls(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _extract_call_name(node.func)
        if call_name in _FORBIDDEN_CALLS:
            raise ValueError(f"forbidden call: {call_name}")


def _extract_call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _require_top_level_build_strategy(tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build_strategy":
            return
    raise ValueError("strategy source must define a top-level build_strategy function")


def _validate_top_level_statements(tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.Assign) and _is_safe_literal(node.value):
            continue
        if isinstance(node, ast.AnnAssign) and (
            node.value is None or _is_safe_literal(node.value)
        ):
            continue
        raise ValueError("top-level executable statements are not allowed")


def _is_safe_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_safe_literal(node.operand)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_safe_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            (key is None or _is_safe_literal(key)) and _is_safe_literal(value)
            for key, value in zip(node.keys, node.values)
        )
    return False


def _validate_py_compile(source: str) -> None:
    with TemporaryDirectory() as temporary_directory:
        candidate_path = Path(temporary_directory) / "strategy_candidate.py"
        candidate_path.write_text(source, encoding="utf-8")
        try:
            py_compile.compile(str(candidate_path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise ValueError(f"strategy source must compile successfully: {exc.msg}") from exc


def _line_count(source: str) -> int:
    if not source:
        return 0
    return len(source.splitlines())


def _reject_shell_instructions(*values: str) -> None:
    for value in values:
        lowered = value.lower()
        if any(marker in lowered for marker in _SHELL_INSTRUCTION_MARKERS):
            raise ValueError("artifact must not contain shell instructions or diffs")
