from pathlib import Path


def test_settings_load_defaults(monkeypatch) -> None:
    monkeypatch.delenv("FINANCE_AUTORESEARCH_PROJECT_ID", raising=False)
    monkeypatch.delenv("FINANCE_AUTORESEARCH_STATE_DB_PATH", raising=False)
    monkeypatch.delenv("FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN", raising=False)

    from finance_autoresearch.settings import Settings

    settings = Settings(_env_file=None)

    assert settings.project_id == "finance"
    assert settings.state_db_path.name == "finance_autoresearch.db"
    assert settings.research_brain_root == Path("knowledge/vault")
    assert settings.research_brain_enabled is True
    assert settings.planner_history_window == 20
    assert settings.factor_catalog_enabled is False
    assert settings.factor_catalog_root == Path("knowledge/factors")
    assert settings.output_language == "en"
    assert settings.docs_output_language is None
    assert settings.log_output_language is None


def test_module_entrypoint_exists() -> None:
    import finance_autoresearch.__main__  # noqa: F401


def test_settings_normalize_blank_optional_values_to_none(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_AUTORESEARCH_AUTORESEARCH_MAX_ITERATIONS", "")
    monkeypatch.setenv("FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH", "")
    monkeypatch.setenv("FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON", "")
    monkeypatch.setenv("FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE", "")
    monkeypatch.setenv("FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE", "")
    monkeypatch.setenv("FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN", "<telegram-control-token>")

    from finance_autoresearch.settings import Settings

    settings = Settings(_env_file=None)

    assert settings.autoresearch_max_iterations is None
    assert settings.openclaw_mutate_handler_path is None
    assert settings.openclaw_analyze_response_json is None
    assert settings.docs_output_language is None
    assert settings.log_output_language is None
    assert settings.telegram_control_token is None
