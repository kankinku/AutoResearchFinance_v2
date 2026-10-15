"""Read-only D08 candidate gate for the EXISTING Moon OAuth launcher.

No secrets are read, no configuration is rewritten, no service is restarted.
Only identifies a pinned immutable source and the known-good rollback ref.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


class ReleaseGateError(ValueError):
    """Reject a release candidate until manually reconciled."""


_HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
_SOURCE = re.compile(r'^SOURCE_ROOT="([^"\n]+)"$', re.MULTILINE)
_SHA = re.compile(r'^EXPECTED_SOURCE_SHA="([0-9a-f]{40})"$', re.MULTILINE)
_PROTECTED_EXACT = (
    "integrations/chatgpt_mcp_http.py",
    "integrations/quant_oauth.py",
    "core/data/contracts.py",
    "core/integrity/hashes.py",
)
_CORE_DIRS = (
    "core/data", "core/backtest", "core/evaluator",
    "core/validation", "core/costs", "core/integrity",
)


def parse_pinned_launcher(path: Path) -> tuple[Path, str]:
    """Extract only declared SOURCE_ROOT and SHA from an existing launcher."""
    raw = path.read_text(encoding="utf-8")
    source = _SOURCE.findall(raw)
    commit = _SHA.findall(raw)
    if len(source) != 1 or len(commit) != 1:
        raise ReleaseGateError("launcher is not safely pinned to one source SHA")
    root = Path(source[0])
    if not root.is_absolute() or root.is_symlink():
        raise ReleaseGateError("unsafe pinned SOURCE_ROOT")
    return root, commit[0]


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True,
        text=True, check=False, timeout=20,
    )
    if done.returncode != 0:
        raise ReleaseGateError("cannot verify git checkout identity")
    return done.stdout.strip()


def _require_clean(repo: Path) -> str:
    if repo.is_symlink() or not repo.is_dir():
        raise ReleaseGateError("candidate or rollback path is symlinked or missing")
    ref = _git(repo, "rev-parse", "HEAD")
    if _HEX_SHA.fullmatch(ref) is None:
        raise ReleaseGateError("invalid immutable source commit SHA")
    if _git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ReleaseGateError("dirty or modified worktree cannot be pinned")
    return ref


def analyze_release(launcher: Path, candidate: Path) -> dict[str, Any]:
    """Fail closed on source/auth/core drift; staged code still needs T3 smoke.

    The caller MUST still test the pinned Git worktree, verify OAuth state,
    execute release smoke and separately approve a controlled restart.
    """
    rollback_path, expected_sha = parse_pinned_launcher(launcher)
    rollback_ref = _require_clean(rollback_path)
    if rollback_ref != expected_sha:
        raise ReleaseGateError("runtime pin SHA disagrees with rollback HEAD")
    if candidate.is_symlink() or (candidate / "state").exists():
        raise ReleaseGateError("candidate contains unexpected state or symlink")
    candidate_ref = _require_clean(candidate)
    if candidate.resolve() == rollback_path.resolve():
        raise ReleaseGateError("candidate must differ from active rollback runtime")
    for name in _PROTECTED_EXACT:
        old = rollback_path / name
        new = candidate / name
        if old.exists() and new.exists() and old.read_bytes() != new.read_bytes():
            raise ReleaseGateError("protected authentication or core module changed")
    # Preserving every preexisting core contract is mandatory, no deletions.
    for relative in _CORE_DIRS:
        old = rollback_path / relative
        new = candidate / relative
        if not old.exists():
            continue
        if not new.exists():
            raise ReleaseGateError("protected core package disappeared")
        for src in old.rglob("*.py"):
            dest = new / src.relative_to(old)
            if not dest.is_file() or src.read_bytes() != dest.read_bytes():
                raise ReleaseGateError("protected core module drift detected")
    return {
        "status": "RELEASE_PRECHECK_PASSED_NOT_DEPLOYED",
        "rollback_ref": rollback_ref,
        "candidate_ref": candidate_ref,
        "protected_modules_unchanged": True,
        "runtime_untouched": True,
        "original_mcp_url_oauth_preserved_if_deployed_using_pin": True,
        "requires_full_test_suite": True,
        "requires_isolated_http_oauth_smoke": True,
        "requires_manual_controlled_cutover_and_rollback": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="D08 dry-run deployment safety gate")
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze_release(args.launcher, args.candidate)
    except (OSError, ReleaseGateError) as exc:
        print(json.dumps({
            "status": "RELEASE_PRECHECK_REFUSED",
            "reason": type(exc).__name__,
            "production_restarted": False,
        }))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
