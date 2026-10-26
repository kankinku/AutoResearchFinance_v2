"""D4 host-only Codex readiness must never invoke a model or login."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

from application.t4_codex_host_preflight import probe_codex_account


class SpyCodex:
    runs = 0
    logins = 0
    account_reads = 0

    def __init__(self, connected=False, error=False):
        self.connected = connected
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def account(self):
        type(self).account_reads += 1
        if self.error:
            raise RuntimeError("EXTERNAL_ACCOUNT_TOKEN_NOT_FOR_LOGS")
        return SimpleNamespace(
            root=SimpleNamespace(account=object() if self.connected else None)
        )

    def login_chatgpt(self):
        type(self).logins += 1
        raise AssertionError("preflight cannot login")

    def thread_start(self, **_kwargs):
        type(self).runs += 1
        raise AssertionError("preflight cannot invoke a model")


def test_account_only_not_connected_is_blocked():
    SpyCodex.runs = SpyCodex.logins = SpyCodex.account_reads = 0
    report = probe_codex_account(
        codex_factory=lambda: SpyCodex(),
        installed_version="0.163.0",
    )
    assert report["status"] == "BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED"
    assert report["next_gate"] == "USER_APPROVED_CODEX_LOGIN"
    assert report["model_turns_started"] == 0
    assert not report["can_advance_genuine_generations"]
    assert SpyCodex.account_reads == 1
    assert SpyCodex.runs == SpyCodex.logins == 0


def test_account_connected_is_not_provenance():
    report = probe_codex_account(
        codex_factory=lambda: SpyCodex(connected=True),
        installed_version="0.163.0",
    )
    assert report["account_connected"]
    assert report["status"] == "BLOCKED_PROVIDER_PROVENANCE_UNVERIFIED"
    assert not report["model_invocation_verified"]


def test_sensitive_exception_is_not_serialized():
    report = probe_codex_account(
        codex_factory=lambda: SpyCodex(error=True),
        installed_version="0.163.0",
    )
    assert report["status"] == "BLOCKED_CODEX_ACCOUNT_CHECK_FAILED"
    assert "EXTERNAL_ACCOUNT_TOKEN_NOT_FOR_LOGS" not in str(report)


def test_uninstalled_host_never_uses_factory():
    def must_not_start():
        raise AssertionError("not installed")

    report = probe_codex_account(
        codex_factory=must_not_start, installed_version=None
    )
    assert report["status"] == "BLOCKED_CODEX_SDK_NOT_INSTALLED"
    assert report["login_attempts_started"] == 0


def test_actual_cli_emits_no_account_or_credential_details():
    repo = Path(__file__).resolve().parents[2]
    import os
    import sys
    completed = subprocess.run(
        [sys.executable, "scripts/codex_account_probe.py"],
        cwd=repo, env={**os.environ, "PYTHONPATH": str(repo)},
        capture_output=True, text=True, timeout=40, check=True,
    )
    import json
    report = json.loads(completed.stdout)
    assert report["schema"] == "t4-codex-account-readiness-v1"
    assert report["model_turns_started"] == 0
    assert report["login_attempts_started"] == 0
    assert "token" not in completed.stdout.lower()
    assert "account_id" not in completed.stdout.lower()
