from __future__ import annotations

from pathlib import Path

import pytest

from integrations.codex_mcp_server import CodexMCPServer
from research.llm.codex_exec import CodexExecProvider, sanitize_context
from research.llm.director import ResearchDirector
from research.llm.provider import CodexIntentProvider


def test_codex_context_redacts_credentials_market_rows_and_sealed_oos() -> None:
    sanitized = sanitize_context(
        {
            "KIS_PAPER_APP_KEY": "placeholder",
            "KIS_PAPER_APP_SECRET": "placeholder",
            "authorization": "Bearer secret",
            "raw_market_rows": [{"close": 100}],
            "sealed_oos": [{"close": 200}],
            "feature_catalog": [{"name": "vix_percentile"}],
        }
    )

    assert sanitized == {"feature_catalog": [{"name": "vix_percentile"}]}


def test_codex_child_environment_has_no_trading_or_llm_api_secrets(monkeypatch) -> None:
    monkeypatch.setenv("KIS_PAPER_APP_SECRET", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("CODEX_API_KEY", "secret")
    monkeypatch.setenv("QUANT_LLM_API_KEY", "secret")

    provider = CodexExecProvider(workdir=Path.cwd())
    environment: dict[str, str] = {}

    def runner(command, prompt, cwd, env, timeout):
        del command, prompt, cwd, timeout
        environment.update(env)
        from research.llm.codex_exec import CodexExecResult

        return CodexExecResult(1, "", "not returned")

    provider._runner = runner  # type: ignore[method-assign]
    with pytest.raises(ValueError):
        provider.propose({})

    assert "KIS_PAPER_APP_SECRET" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "CODEX_API_KEY" not in environment
    assert "QUANT_LLM_API_KEY" not in environment




def _schema_property_names(value: object) -> set[str]:
    if isinstance(value, dict):
        names: set[str] = set()
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(str(key).lower() for key in properties)
        for nested in value.values():
            names.update(_schema_property_names(nested))
        return names
    if isinstance(value, list):
        names: set[str] = set()
        for nested in value:
            names.update(_schema_property_names(nested))
        return names
    return set()


def test_mcp_tool_surface_has_no_order_or_credential_capability(tmp_path: Path) -> None:
    server = CodexMCPServer(state_dir=tmp_path, project_root=tmp_path)
    response = server.handle({"id": 1, "method": "tools/list", "params": {}})
    names = {
        str(item["name"])
        for item in response["result"]["tools"]  # type: ignore[index]
    }

    assert names == {
        "initialize_research_state",
        "get_workspace_status",
        "set_research_mode",
        "validate_research_cache",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "plan_generation",
        "get_research_context",
        "list_features",
        "get_dashboard_status",
        "get_research_evidence",
        "submit_research_intent",
        "run_evaluation",
        "check_system",
        "start_system",
        "get_system_status",
        "stop_system",
    }
    forbidden_names = (
        "order",
        "credential",
        "approval",
        "promote",
        "paper_order",
        "live_account",
        "direct_edit",
    )
    assert not any(
        forbidden in name
        for name in names
        for forbidden in forbidden_names
    )

    tools = response["result"]["tools"]  # type: ignore[index]
    sensitive_fields = {
        "api_key",
        "secret",
        "token",
        "credential",
        "account_number",
        "order_id",
    }
    for tool in tools:
        schema = tool["inputSchema"]
        assert not (_schema_property_names(schema) & sensitive_fields)


def test_research_director_rejects_code_change_intent() -> None:
    director = ResearchDirector(
        CodexIntentProvider(
            lambda context: {
                "mode": "structure",
                "parent_ids": ["champion"],
                "rationale": "test",
                "python_patch": "delete evaluator",
            }
        )
    )

    with pytest.raises(ValueError, match="code/evaluator"):
        director.propose({})
