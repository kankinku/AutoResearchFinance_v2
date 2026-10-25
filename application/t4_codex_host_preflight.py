"""D4 read-only Codex host preflight, reusing original T4 checkpoint guards.

A Codex account session is necessary, never sufficient, evidence for an
authenticated generation. This module never initiates login or a model turn.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import Any

from application.t4_model_host_preflight import CheckpointReader, audit_t4_model_host


def probe_codex_account(
    *,
    codex_factory: Callable[[], Any] | None,
    installed_version: str | None,
) -> dict[str, Any]:
    """Inspect the local SDK and account without a turn, login or secret output."""
    connected = False
    error = False
    if installed_version is not None and codex_factory is not None:
        try:
            with codex_factory() as codex:
                result = codex.account()
                value = getattr(result, "root", result)
                connected = getattr(value, "account", None) is not None
        except Exception:
            error = True
    if installed_version is None or codex_factory is None:
        status = "BLOCKED_CODEX_SDK_NOT_INSTALLED"
    elif error:
        status = "BLOCKED_CODEX_ACCOUNT_CHECK_FAILED"
    elif not connected:
        status = "BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED"
    else:
        status = "BLOCKED_PROVIDER_PROVENANCE_UNVERIFIED"
    return {
        "schema": "t4-codex-account-readiness-v1",
        "status": status,
        "sdk_installed": installed_version is not None,
        "sdk_version": installed_version,
        "account_connected": connected,
        "account_read_failed": error,
        "model_invocation_verified": False,
        "can_advance_genuine_generations": False,
        "model_turns_started": 0,
        "login_attempts_started": 0,
        "oauth_changes_performed": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "next_gate": (
            "USER_APPROVED_CODEX_LOGIN"
            if status == "BLOCKED_CODEX_ACCOUNT_NOT_CONNECTED"
            else "INDEPENDENT_PROVIDER_INVOCATION_EVIDENCE"
            if connected else "REPAIR_CODEX_HOST"
        ),
    }


def audit_codex_host(
    reader: CheckpointReader,
    *,
    session_id: str,
    codex_factory: Callable[[], Any] | None,
    installed_version: str | None,
) -> dict[str, Any]:
    """Require an authorized checkpoint before probing the model host."""
    baseline = audit_t4_model_host(reader, session_id=session_id, callback=None)
    identity = probe_codex_account(
        codex_factory=codex_factory, installed_version=installed_version,
    )
    return {**baseline, **identity, "schema": "t4-codex-host-readiness-v1"}


def probe_installed_codex_account() -> dict[str, Any]:
    """Inspect installed Codex SDK only; no Quant session or authentication."""
    try:
        version = metadata.version("openai-codex")
        from openai_codex import Codex
    except (metadata.PackageNotFoundError, ImportError):
        version, factory = None, None
    else:
        factory = Codex
    return probe_codex_account(
        codex_factory=factory, installed_version=version,
    )


def inspect_installed_codex_host(
    reader: CheckpointReader, *, session_id: str,
) -> dict[str, Any]:
    """SDK package discovery and account-only probe; no authentication mutation."""
    try:
        version = metadata.version("openai-codex")
        from openai_codex import Codex
    except (metadata.PackageNotFoundError, ImportError):
        version, factory = None, None
    else:
        factory = Codex
    return audit_codex_host(
        reader, session_id=session_id,
        codex_factory=factory, installed_version=version,
    )
