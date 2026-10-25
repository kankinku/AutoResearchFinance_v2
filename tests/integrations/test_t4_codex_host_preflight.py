"""D4: pinned Codex SDK account readiness, with zero model turns by design."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.t4_codex_host_preflight import audit_codex_host


class Reader:
    def __init__(self):
        self.calls = 0
        self.state = {
            "session_id": "a" * 32,
            "completed_generations": 0,
            "requested_generations": 100,
            "checkpoint_phase": "AWAITING_PLAN",
            "orders_enabled": False,
            "independent_oos_approved": False,
        }

    def get(self, request):
        assert request == {"session_id": "a" * 32}
        self.calls += 1
        return dict(self.state)


class FakeCodex:
    opens = 0
    account_reads = 0
    thread_runs = 0
    logins = 0

    def __init__(self, *, connected=False):
        self.connected = connected

    def __enter__(self):
        type(self).opens += 1
        return self

    def __exit__(self, *args):
        return None

    def account(self):
        type(self).account_reads += 1
        return SimpleNamespace(
            root=SimpleNamespace(
                account=SimpleNamespace(identity="DO_NOT_LOG")
                if self.connected else None
            )
        )

    def thread_start(self, **kwargs):
        type(self).thread_runs += 1
        raise AssertionError("account probe MUST NOT start a turn")

    def login_chatgpt(self):
        type(self).logins += 1
        raise AssertionError("preflight MUST NOT start login")


def _reset():
    FakeCodex.opens = FakeCodex.account_reads = 0
    FakeCodex.thread_runs = FakeCodex.logins = 0


def test_d4_absent_login_is_blocked_and_safe():
    _reset()
    reader = Reader()
    report = audit_codex_host(
        reader,
        session_id="a" * 32,
        codex_factory=lambda: FakeCodex(connected=False),
        installed_version="0.163.0",
    )
    assert report["status"] == "BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED"
    assert report["sdk_installed"] is True
    assert report["account_connected"] is False
    assert report["can_advance_genuine_generations"] is False
    assert report["oauth_changes_performed"] is False
    assert report["model_turns_started"] == 0
    assert FakeCodex.account_reads == 1
    assert FakeCodex.thread_runs == FakeCodex.logins == 0
    assert reader.calls == 1
    assert "DO_NOT_LOG" not in str(report)


def test_d4_connected_account_not_equivalent_to_model_provenance():
    _reset()
    report = audit_codex_host(
        Reader(), session_id="a" * 32,
        codex_factory=lambda: FakeCodex(connected=True),
        installed_version="0.163.0",
    )
    assert report["status"] == "BLOCKED_PROVIDER_PROVENANCE_UNVERIFIED"
    assert report["account_connected"] is True
    assert report["model_invocation_verified"] is False
    assert report["can_advance_genuine_generations"] is False
    assert FakeCodex.thread_runs == FakeCodex.logins == 0


def test_d4_no_sdk_dependency_does_not_attempt_to_launch_login():
    _reset()
    report = audit_codex_host(
        Reader(), session_id="a" * 32,
        codex_factory=None,
        installed_version=None,
    )
    assert report["status"] == "BLOCKED_CODEX_SDK_NOT_INSTALLED"
    assert report["sdk_installed"] is False
    assert FakeCodex.opens == 0


def test_d4_rejects_unsafe_checkpoint_before_accessing_sdk():
    _reset()
    reader = Reader()
    reader.state["orders_enabled"] = True
    with pytest.raises(ValueError, match="protected"):
        audit_codex_host(
            reader, session_id="a" * 32,
            codex_factory=FakeCodex,
            installed_version="0.163.0",
        )
    assert FakeCodex.opens == 0


def test_d4_sdk_account_read_failure_does_not_disclose_secrets():
    class FailingCodex(FakeCodex):
        def account(self):
            raise RuntimeError("SENSITIVE_TOKEN_NEVER_COPY_THIS")

    result = audit_codex_host(
        Reader(), session_id="a" * 32,
        codex_factory=FailingCodex,
        installed_version="0.163.0",
    )
    assert result["status"] == "BLOCKED_CODEX_ACCOUNT_CHECK_FAILED"
    assert "SENSITIVE_TOKEN_NEVER_COPY_THIS" not in str(result)
    assert result["model_turns_started"] == 0
