"""P2 is applied only to an explicitly pinned OAuth session, never to all users."""

from __future__ import annotations

import pytest

from integrations.codex_mcp_core import CodexMCPServer


def test_no_scoped_session_means_legacy_parent_selector(tmp_path, monkeypatch):
    seen = []

    class Stub:
        def __init__(self, **kwargs):
            seen.append(kwargs)

        def get(self, args):
            return {"selected": args["session_id"]}

    monkeypatch.delenv("QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID", raising=False)
    monkeypatch.setattr("integrations.codex_mcp_core.AcademicMCPCheckpointService", Stub)
    server = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    server._dispatch("get_algorithm_research", {"session_id": "a" * 32})
    assert seen[-1]["parent_portfolio_v2"] is False


def test_scoped_session_only_opted_in_even_when_requests_mix(tmp_path, monkeypatch):
    seen = []

    class Stub:
        def __init__(self, **kwargs):
            seen.append(kwargs["parent_portfolio_v2"])

        def get(self, args):
            return {"selected": args["session_id"]}

    monkeypatch.setenv("QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID", "a" * 32)
    monkeypatch.setattr("integrations.codex_mcp_core.AcademicMCPCheckpointService", Stub)
    server = CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
    assert server._dispatch("get_algorithm_research", {"session_id": "b" * 32})
    assert server._dispatch("get_algorithm_research", {"session_id": "a" * 32})
    assert seen == [False, True]


@pytest.mark.parametrize("bad", ["true", "a" * 31, "a" * 33, "../secret", "A" * 32])
def test_invalid_opt_in_config_refuses_service_startup(tmp_path, monkeypatch, bad):
    monkeypatch.setenv("QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID", bad)
    with pytest.raises(ValueError, match="invalid scoped"):
        CodexMCPServer(state_dir=tmp_path / "state", project_root=tmp_path)
