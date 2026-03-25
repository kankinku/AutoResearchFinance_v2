from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINANCE_AUTORESEARCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str = "finance"
    workspace_root: Path = Path(".")
    state_db_path: Path = Path("runtime/finance_autoresearch.db")
    market_pack_mode: Literal["download", "cached"] = "download"
    autoresearch_max_iterations: int | None = None
    openclaw_roles_path: Path = Path("config/openclaw.roles.example.yaml")
    openclaw_gateway_url: str = "http://127.0.0.1:18789"
    openclaw_healthcheck_script: Path = Path("scripts/check-openclaw.ps1")
    openclaw_mutate_script: Path = Path("scripts/openclaw-mutate.ps1")
    openclaw_analyze_script: Path = Path("scripts/openclaw-analyze.ps1")
    openclaw_mutate_handler_path: Path | None = None
    openclaw_analyze_handler_path: Path | None = None
    openclaw_mutate_response_json: Path | None = None
    openclaw_analyze_response_json: Path | None = None
    openclaw_router_agent: str = "router"
    openclaw_research_agent: str = "research"
    openclaw_critic_agent: str = "critic"
    openclaw_builder_agent: str = "builder"
    telegram_control_token: SecretStr | None = None
    telegram_control_chat_id: str | None = None
    telegram_report_token: SecretStr | None = None
    telegram_report_chat_id: str | None = None
    telegram_report_dry_run: bool = False
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8000

    @field_validator(
        "autoresearch_max_iterations",
        "openclaw_mutate_handler_path",
        "openclaw_analyze_handler_path",
        "openclaw_mutate_response_json",
        "openclaw_analyze_response_json",
        "telegram_control_token",
        "telegram_control_chat_id",
        "telegram_report_token",
        "telegram_report_chat_id",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.startswith("<") and stripped.endswith(">"):
                return None
        return value
