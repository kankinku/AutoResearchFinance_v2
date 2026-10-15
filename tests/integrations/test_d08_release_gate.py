"""D08 fail-closed release gate; dry-run, never starts/restarts production."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.d08_release_gate import ReleaseGateError, analyze_release, parse_pinned_launcher


def _repo(path: Path, files: dict[str, str]) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    for name, data in files.items():
        file = path / name
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_text(data)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run([
        "git", "-c", "user.email=d08@tests.invalid",
        "-c", "user.name=D08 Test", "commit", "-qm", "pin test source",
    ], cwd=path, check=True)
    return path


def _launcher(path: Path, repo: Path, sha: str) -> Path:
    file = path / "scripts" / "run_quant_moon_http.sh"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        "#!/usr/bin/env bash\n"
        f'SOURCE_ROOT="{repo}"\n'
        f'EXPECTED_SOURCE_SHA="{sha}"\n'
        "exec /some/path/python -m integrations.chatgpt_mcp_http\n"
    )
    return file


def test_pin_reader_and_closed_git_worktree(tmp_path: Path) -> None:
    old = _repo(tmp_path / "previous", {
        "integrations/chatgpt_mcp_http.py": "same",
        "integrations/quant_oauth.py": "same",
        "core/data/contracts.py": "same",
        "core/integrity/hashes.py": "same",
    })
    new = _repo(tmp_path / "candidate", {
        "integrations/chatgpt_mcp_http.py": "same",
        "integrations/quant_oauth.py": "same",
        "core/data/contracts.py": "same",
        "core/integrity/hashes.py": "same",
        "research/llm/experiment_learning.py": "new",
    })
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=old, text=True).strip()
    launcher = _launcher(tmp_path / "runtime", old, sha)
    assert parse_pinned_launcher(launcher) == (old, sha)
    report = analyze_release(launcher, new)
    assert report["status"] == "RELEASE_PRECHECK_PASSED_NOT_DEPLOYED"
    assert report["protected_modules_unchanged"] is True
    assert report["rollback_ref"] == sha
    assert report["runtime_untouched"] is True
    assert "candidate_ref" in report

    (new / "state").mkdir()
    with pytest.raises(ReleaseGateError, match="unexpected"):
        analyze_release(launcher, new)
    assert parse_pinned_launcher(launcher) == (old, sha)


def test_changed_authentication_or_core_is_no_go(tmp_path: Path) -> None:
    old = _repo(tmp_path / "old", {
        "integrations/chatgpt_mcp_http.py": "same",
        "integrations/quant_oauth.py": "same",
        "core/data/contracts.py": "same",
    })
    new = _repo(tmp_path / "new", {
        "integrations/chatgpt_mcp_http.py": "changed",
        "integrations/quant_oauth.py": "same",
        "core/data/contracts.py": "same",
    })
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=old, text=True).strip()
    with pytest.raises(ReleaseGateError, match="protected|authentication"):
        analyze_release(_launcher(tmp_path / "rt", old, sha), new)


def test_unpinned_or_modified_previous_runtime_is_no_go(tmp_path: Path) -> None:
    old = _repo(tmp_path / "old", {"integrations/quant_oauth.py": "same"})
    new = _repo(tmp_path / "new", {"integrations/quant_oauth.py": "same"})
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=old, text=True).strip()
    launcher = _launcher(tmp_path / "rt", old, "0" * 40)
    with pytest.raises(ReleaseGateError, match="pin|SHA"):
        analyze_release(launcher, new)

    _launcher(tmp_path / "rt", old, sha)
    (old / "integrations" / "quant_oauth.py").write_text("local change")
    with pytest.raises(ReleaseGateError, match="dirty|modified"):
        analyze_release(launcher, new)


def test_symlinked_candidate_is_no_go(tmp_path: Path) -> None:
    original = _repo(tmp_path / "old", {"integrations/quant_oauth.py": "same"})
    new = _repo(tmp_path / "candidate", {"integrations/quant_oauth.py": "same"})
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=original, text=True).strip()
    link = tmp_path / "new_symlink"
    link.symlink_to(new, target_is_directory=True)
    with pytest.raises(ReleaseGateError, match="symlink"):
        analyze_release(_launcher(tmp_path / "rt", original, sha), link)
