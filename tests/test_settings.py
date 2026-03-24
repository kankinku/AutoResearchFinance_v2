def test_settings_load_defaults(monkeypatch) -> None:
    monkeypatch.delenv("FINANCE_AUTORESEARCH_PROJECT_ID", raising=False)
    monkeypatch.delenv("FINANCE_AUTORESEARCH_STATE_DB_PATH", raising=False)
    monkeypatch.delenv("FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN", raising=False)

    from finance_autoresearch.settings import Settings

    settings = Settings()

    assert settings.project_id == "finance"
    assert settings.state_db_path.name == "finance_autoresearch.db"


def test_module_entrypoint_exists() -> None:
    import finance_autoresearch.__main__  # noqa: F401
