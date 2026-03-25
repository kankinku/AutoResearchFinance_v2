from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

from finance_autoresearch.backtest.data_loader import (
    MarketKey,
    MarketPack,
    build_market_pack,
    validate_market_pack,
)
from finance_autoresearch.settings import Settings
from finance_autoresearch.state.repository import StateRepository

DEFAULT_BASELINE_STRATEGY_PATH = Path(
    "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
)
DEFAULT_BASELINE_SNAPSHOT_PATH = Path("runtime/baseline/accepted_strategy_candidate.py")


@dataclass(slots=True, frozen=True)
class PipelineRunResult:
    succeeded: bool
    stage: str
    message: str
    market_pack_keys: tuple[MarketKey, ...] = ()


class PipelineRunner:
    def __init__(
        self,
        *,
        state_store: StateRepository,
        settings: Settings | None = None,
        cache_root: Path | str = Path("."),
        market_pack_builder: Callable[[], MarketPack] | None = None,
        market_pack_validator: Callable[[MarketPack], object] | None = None,
        sqlite_validator: Callable[[], object] | None = None,
        baseline_snapshot_handler: Callable[[], object] | None = None,
        baseline_strategy_validator: Callable[[], object] | None = None,
        openclaw_check: Callable[[], object] | None = None,
        telegram_control_check: Callable[[], object] | None = None,
        telegram_report_check: Callable[[], object] | None = None,
        dashboard_check: Callable[[], object] | None = None,
        baseline_strategy_path: Path | str = DEFAULT_BASELINE_STRATEGY_PATH,
        baseline_snapshot_path: Path | str = DEFAULT_BASELINE_SNAPSHOT_PATH,
    ) -> None:
        self._state_store = state_store
        self._settings = settings or Settings()
        self._cache_root = Path(cache_root)
        resolved_strategy_path = Path(baseline_strategy_path)
        resolved_snapshot_path = Path(baseline_snapshot_path)

        self._market_pack_builder = market_pack_builder or (
            lambda: build_market_pack(cache_root=self._cache_root)
        )
        self._market_pack_validator = market_pack_validator or validate_market_pack
        self._sqlite_validator = sqlite_validator or self._default_sqlite_validator
        self._baseline_snapshot_handler = baseline_snapshot_handler or (
            lambda: ensure_accepted_baseline_snapshot(
                baseline_strategy_path=resolved_strategy_path,
                baseline_snapshot_path=resolved_snapshot_path,
            )
        )
        self._baseline_strategy_validator = baseline_strategy_validator or (
            lambda: validate_baseline_strategy(resolved_strategy_path)
        )
        self._openclaw_check = openclaw_check or self._default_openclaw_check
        self._telegram_control_check = telegram_control_check or (
            lambda: _validate_telegram_surface(
                token=self._settings.telegram_control_token,
                chat_id=self._settings.telegram_control_chat_id,
                surface_name="telegram control",
            )
        )
        self._telegram_report_check = telegram_report_check or (
            lambda: _validate_telegram_surface(
                token=self._settings.telegram_report_token,
                chat_id=self._settings.telegram_report_chat_id,
                surface_name="telegram report",
            )
        )
        self._dashboard_check = dashboard_check or (
            lambda: validate_dashboard_configuration(self._settings)
        )

    def run(self) -> PipelineRunResult:
        market_pack: MarketPack = {}
        self._state_store.append_outbox_event(
            event_type="pipeline_started",
            payload={"cache_root": str(self._cache_root)},
        )
        self._state_store.set_status(
            project_state="active",
            pipeline_state="running",
        )

        stages: tuple[tuple[str, Callable[[], object]], ...] = (
            ("build_market_pack", self._build_market_pack(market_pack)),
            ("validate_market_pack", lambda: self._market_pack_validator(market_pack)),
            ("validate_sqlite", self._sqlite_validator),
            ("ensure_baseline_snapshot", self._baseline_snapshot_handler),
            ("validate_baseline_strategy", self._baseline_strategy_validator),
            ("check_openclaw", self._openclaw_check),
            ("check_telegram_control", self._telegram_control_check),
            ("check_telegram_report", self._telegram_report_check),
            ("check_dashboard", self._dashboard_check),
        )

        for stage, action in stages:
            self._state_store.set_current_stage(stage)
            self._state_store.record_heartbeat("pipeline")
            try:
                action()
            except Exception as exc:
                return self._fail(stage=stage, message=str(exc), market_pack=market_pack)

        self._state_store.set_status(
            project_state="idle",
            pipeline_state="success",
            autoresearch_state="idle",
        )
        self._state_store.set_current_stage(None)
        self._state_store.clear_heartbeat("pipeline")
        market_pack_keys = _sorted_market_pack_keys(market_pack)
        self._state_store.append_outbox_event(
            event_type="pipeline_succeeded",
            payload={"market_pack_keys": _serialize_market_pack_keys(market_pack_keys)},
        )
        return PipelineRunResult(
            succeeded=True,
            stage="completed",
            message="pipeline completed",
            market_pack_keys=market_pack_keys,
        )

    def _build_market_pack(self, market_pack: MarketPack) -> Callable[[], object]:
        def run() -> None:
            market_pack.update(self._market_pack_builder())

        return run

    def _default_sqlite_validator(self) -> None:
        self._state_store.get_status()

    def _default_openclaw_check(self) -> None:
        script_path = Path(self._settings.openclaw_healthcheck_script)
        roles_path = Path(self._settings.openclaw_roles_path)
        if not script_path.exists():
            raise ValueError(f"OpenClaw health check script is missing: {script_path}")
        if not roles_path.exists():
            raise ValueError(f"OpenClaw roles file is missing: {roles_path}")

        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-RolesPath",
                str(roles_path),
                "-GatewayUrl",
                self._settings.openclaw_gateway_url,
            ],
            check=False,
            capture_output=True,
            env=self._build_openclaw_env(),
            text=True,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            raise ValueError(message or "OpenClaw health check failed")

    def _build_openclaw_env(self) -> dict[str, str]:
        env = os.environ.copy()
        optional_paths = {
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH": self._settings.openclaw_mutate_handler_path,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH": self._settings.openclaw_analyze_handler_path,
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON": self._settings.openclaw_mutate_response_json,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON": self._settings.openclaw_analyze_response_json,
        }
        for name, path_value in optional_paths.items():
            if path_value is not None:
                env[name] = str(Path(path_value).resolve())
        return env

    def _fail(
        self,
        *,
        stage: str,
        message: str,
        market_pack: MarketPack,
    ) -> PipelineRunResult:
        self._state_store.set_status(project_state="degraded", pipeline_state="failed")
        self._state_store.set_current_stage(None)
        self._state_store.clear_heartbeat("pipeline")
        market_pack_keys = _sorted_market_pack_keys(market_pack)
        self._state_store.append_outbox_event(
            event_type="pipeline_failed",
            payload={
                "stage": stage,
                "message": message,
                "market_pack_keys": _serialize_market_pack_keys(market_pack_keys),
            },
        )
        return PipelineRunResult(
            succeeded=False,
            stage=stage,
            message=message,
            market_pack_keys=market_pack_keys,
        )


def ensure_accepted_baseline_snapshot(
    *,
    baseline_strategy_path: Path | str,
    baseline_snapshot_path: Path | str,
) -> Path:
    strategy_path = validate_baseline_strategy(baseline_strategy_path)
    snapshot_path = Path(baseline_snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    if snapshot_path.exists():
        if snapshot_path.is_dir():
            raise ValueError("accepted baseline snapshot must be a file")
        if not snapshot_path.read_text(encoding="utf-8").strip():
            raise ValueError("accepted baseline snapshot must not be empty")
        return snapshot_path

    shutil.copyfile(strategy_path, snapshot_path)
    return snapshot_path


def validate_baseline_strategy(path: Path | str) -> Path:
    strategy_path = Path(path)
    if not strategy_path.exists():
        raise ValueError("baseline strategy file is missing")
    if not strategy_path.is_file():
        raise ValueError("baseline strategy path must be a file")
    if not strategy_path.read_text(encoding="utf-8").strip():
        raise ValueError("baseline strategy file must not be empty")
    return strategy_path


def validate_dashboard_configuration(settings: Settings) -> None:
    if not settings.dashboard_host.strip():
        raise ValueError("dashboard host is not configured")
    if settings.dashboard_port <= 0 or settings.dashboard_port > 65_535:
        raise ValueError("dashboard port must be between 1 and 65535")


def _validate_telegram_surface(
    *,
    token,
    chat_id: str | None,
    surface_name: str,
) -> None:
    token_value = token.get_secret_value() if token is not None else ""
    if not token_value.strip() or not (chat_id or "").strip():
        raise ValueError(f"{surface_name} credentials are not configured")


def _sorted_market_pack_keys(market_pack: MarketPack) -> tuple[MarketKey, ...]:
    return tuple(sorted(market_pack.keys()))


def _serialize_market_pack_keys(keys: tuple[MarketKey, ...]) -> list[str]:
    return [f"{symbol}:{timeframe}" for symbol, timeframe in keys]
