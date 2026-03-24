from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINANCE_AUTORESEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str = "finance"
    state_db_path: Path = Path("runtime/finance_autoresearch.db")
    openclaw_roles_path: Path = Path("config/openclaw.roles.example.yaml")
    openclaw_gateway_url: str = "http://127.0.0.1:18789"
    openclaw_router_agent: str = "router"
    openclaw_research_agent: str = "research"
    openclaw_critic_agent: str = "critic"
    openclaw_builder_agent: str = "builder"
    telegram_control_token: SecretStr | None = None
    telegram_control_chat_id: str | None = None
    telegram_report_token: SecretStr | None = None
    telegram_report_chat_id: str | None = None
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000
