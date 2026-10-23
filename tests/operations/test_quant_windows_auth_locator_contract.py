"""Read-only Windows OAuth discovery script static contract checks.

PowerShell host execution is separately required and is not claimed here.
"""

from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "scripts/find_original_quant_oauth.ps1"


def test_quant_auth_triplet_must_share_same_state_root():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'Join-Path $MoonHttp.FullName "oauth/approval-key"' in source
    assert 'Join-Path $MoonHttp.FullName "oauth/public-base-url"' in source
    assert 'Join-Path $MoonHttp.FullName "research/oauth/quant-oauth.sqlite"' in source
    assert '$MoonHttp.Parent.Name -ne "state"' in source


def test_scoped_docker_bind_and_explicit_roots():
    source = SOURCE.read_text(encoding="utf-8")
    assert ' $Container = "project-moon-local"' in source
    assert '$mount.Destination -ne "/shared"' in source
    assert '$mount.Type -ne "bind"' in source
    assert "$SearchRoots = @()" in source
    assert "MaxDirectories" in source
    assert "MaxDepth" in source
    assert "ReparsePoint" in source


def test_does_not_publish_contents_or_claim_restoration():
    source = SOURCE.read_text(encoding="utf-8")
    assert "CANDIDATE_TRIPLET_PRESENT_UNVERIFIED" in source
    assert "PARTIAL_IDENTITY_DO_NOT_START" in source
    assert "STATUS=CANDIDATE_FOUND_NOT_RESTORED" in source
    assert "STATUS=BLOCKED_ORIGINAL_QUANT_OAUTH_NOT_FOUND" in source
    assert "STATUS=INCOMPLETE_SCAN_INCREASE_MAXDIRECTORIES" in source
    assert "APPROVAL_KEY_PRESENT=" in source
    assert "PUBLIC_URL_PIN_PRESENT=" in source
    assert "OAUTH_DB_PRESENT=" in source


def test_windows_locator_has_no_automatic_recovery_flow():
    source = SOURCE.read_text(encoding="utf-8")
    assert "[CmdletBinding()]" in source
    assert "[ValidateRange(100, 100000)]" in source
    assert "Read-DockerBindRoots" in source
    assert "Inspect-StateRoot" in source
    assert "exit 2" in source
    assert "exit 3" in source
    assert "exit 0" in source


def test_windows_docker_mount_json_is_flattened_and_vm_host_source_translated():
    source = SOURCE.read_text(encoding="utf-8")
    assert "Convert-DockerDesktopHostPath" in source
    assert "run/desktop/mnt/host" in source
    assert "host_mnt" in source
    assert "mnt/host" in source
    assert "foreach ($element in @($mounts))" in source
    assert "foreach ($mount in @($element))" in source
    assert "$mountJson -eq '[]'" in source
    assert "$sharedBindCount -gt 0 -and $result.Count -eq 0" in source
    assert "if (-not (Test-Path -LiteralPath $hostPath -PathType Container))" in source
