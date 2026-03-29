from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from finance_autoresearch.localization import OutputLanguage

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProgressMode = Literal["off", "simple", "standard"]


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
    research_knowledge_root: Path = Path("knowledge")
    research_brain_root: Path = Path("knowledge/vault")
    research_brain_enabled: bool = True
    research_brain_auto_export: bool = True
    output_language: OutputLanguage = "en"
    docs_output_language: OutputLanguage | None = None
    log_output_language: OutputLanguage | None = None
    genome_shadow_mode: bool = True
    falsifier_enabled: bool = True
    planner_history_window: int = 20
    planner_max_linked_notes: int = 12
    prescreen_max_candidates: int = 3
    optuna_max_variants: int = 8
    frontier_candidate_limit: int = 3
    frontier_promotion_limit: int = 2
    manual_brain_notes_mode: Literal["reference_only"] = "reference_only"
    factor_catalog_enabled: bool = False
    factor_catalog_root: Path = Path("knowledge/factors")
    market_pack_mode: Literal["download", "cached"] = "download"
    autoresearch_max_iterations: int | None = None
    allow_invalid_seed_baseline: bool = False
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
    telegram_progress_token: SecretStr | None = None
    telegram_progress_chat_id: str | None = None
    telegram_progress_dry_run: bool = False
    telegram_progress_mode: ProgressMode = "off"
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
        "docs_output_language",
        "log_output_language",
        "telegram_progress_token",
        "telegram_progress_chat_id",
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


def resolve_settings_env_file() -> str | None:
    configured = os.environ.get("FINANCE_AUTORESEARCH_ENV_FILE")
    if configured is None:
        return ".env"

    stripped = configured.strip()
    if not stripped or stripped.lower() in {"0", "false", "none", "null"}:
        return None
    return stripped


def load_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=resolve_settings_env_file(), **overrides)
