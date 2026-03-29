from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from finance_autoresearch.backtest.analyzer import analyze_backtest_results
from finance_autoresearch.backtest.falsifier import falsify_candidate
from finance_autoresearch.backtest.prescreener import prescreen_candidate
from finance_autoresearch.backtest.data_loader import load_market_pack
from finance_autoresearch.backtest.evaluator import evaluate_backtest_results
from finance_autoresearch.backtest.harness import run_backtests
from finance_autoresearch.brain import BrainSync, BrainWriter
from finance_autoresearch.integrations.cli import build_command_payload
from finance_autoresearch.integrations.telegram_report import (
    TelegramProgressAdapter,
    TelegramReportAdapter,
)
from finance_autoresearch.mutation.openclaw_client import OpenClawClient
from finance_autoresearch.research.lesson_capture import LessonBuilder
from finance_autoresearch.research.planner_memory import PlannerMemory
from finance_autoresearch.research.planner_search import ResearchScheduler
from finance_autoresearch.research.workspace_knowledge import WorkspaceKnowledgeLoader
from finance_autoresearch.localization import OutputLocalizer
from finance_autoresearch.settings import Settings, load_settings
from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService
from finance_autoresearch.workers.autoresearch_runner import AutoresearchRunner
from finance_autoresearch.workers.pipeline_runner import PipelineRunner
from finance_autoresearch.search.candidate_frontier import select_candidate_frontier
from finance_autoresearch.search.optuna_adapter import OptunaAdapter
from finance_autoresearch.search.trial_manager import TrialManager


CODE_ROOT = Path(__file__).resolve().parents[2]


class StrategyHarness:
    def __init__(
        self,
        *,
        cache_root: Path,
        market_pack_loader=load_market_pack,
    ) -> None:
        self._cache_root = cache_root
        self._market_pack_loader = market_pack_loader
        self._market_pack: dict[str, Any] | None = None

    def __call__(self, strategy_path: Path) -> dict[str, Any]:
        market_pack = self._load_market_pack()
        strategy_module = load_strategy_module(strategy_path)
        try:
            return run_backtests(market_pack, strategy_module)
        finally:
            sys.modules.pop(strategy_module.__name__, None)

    def smoke(self, strategy_path: Path) -> dict[str, Any]:
        market_pack = self._load_market_pack()
        strategy_module = load_strategy_module(strategy_path)
        try:
            return run_backtests(
                market_pack,
                strategy_module,
                market_keys=(
                    ("QQQ", "1d"),
                    ("IWM", "2h"),
                    ("BTC-USD", "1d"),
                    ("BTC-USD", "2h"),
                ),
            )
        finally:
            sys.modules.pop(strategy_module.__name__, None)

    def _load_market_pack(self) -> dict[str, Any]:
        if self._market_pack is None:
            self._market_pack = self._market_pack_loader(cache_root=self._cache_root)
        return self._market_pack


@dataclass(slots=True)
class DryRunTelegramBot:
    delivered_messages: list[tuple[str, str]]

    async def send_message(self, *, chat_id: str, text: str) -> None:
        self.delivered_messages.append((chat_id, text))


class WorkerLauncher:
    def __init__(
        self,
        *,
        settings: Settings,
        code_root: Path = CODE_ROOT,
        python_executable: str = sys.executable,
        spawn_fn=subprocess.Popen,
    ) -> None:
        self._settings = settings
        self._code_root = code_root
        self._python_executable = python_executable
        self._spawn_fn = spawn_fn

    def launch_pipeline(self) -> subprocess.Popen[Any]:
        return self._spawn(["-m", "finance_autoresearch", "run-pipeline-worker"])

    def launch_autoresearch(self, *, run_id: str) -> subprocess.Popen[Any]:
        return self._spawn(
            [
                "-m",
                "finance_autoresearch",
                "run-autoresearch-worker",
                run_id,
            ]
        )

    def _spawn(self, argv: list[str]) -> subprocess.Popen[Any]:
        return self._spawn_fn(
            [self._python_executable, *argv],
            cwd=str(self._code_root),
            env=build_subprocess_env(self._settings),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


@dataclass(slots=True)
class ApplicationRuntime:
    settings: Settings
    store: SQLiteStateStore
    supervisor: SupervisorService
    pipeline_runner: PipelineRunner
    autoresearch_runner: AutoresearchRunner
    launcher: WorkerLauncher

    def close(self) -> None:
        self.store.close()

    def handle_command(
        self,
        *,
        command: str,
        source: str,
        requested_by: str,
        payload: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        request = build_command_payload(
            command=command,
            source=source,
            requested_by=requested_by,
            project_id=project_id or self.settings.project_id,
            payload=payload,
        )
        return self.handle_command_payload(request)

    def handle_command_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.supervisor.handle(payload)
        command = payload.get("command")
        if not response["accepted"]:
            return response

        try:
            if command == "start_pipeline":
                self.launcher.launch_pipeline()
            elif command in {"start_autoresearch", "resume_autoresearch"}:
                run_id = response["run_id"] or self.store.get_status().active_run_id
                if run_id is None:
                    raise RuntimeError(f"{command} did not produce an active run id")
                self.launcher.launch_autoresearch(run_id=run_id)
        except OSError as exc:
            return self._worker_launch_failed(command=str(command), message=str(exc))
        except RuntimeError as exc:
            return self._worker_launch_failed(command=str(command), message=str(exc))

        return response

    def run_pipeline_worker(self) -> dict[str, Any]:
        result = self.pipeline_runner.run()
        delivered = self.drain_report_outbox()
        return {
            "succeeded": result.succeeded,
            "stage": result.stage,
            "message": result.message,
            "market_pack_keys": [list(key) for key in result.market_pack_keys],
            "delivered_outbox_ids": delivered,
        }

    def run_autoresearch_worker(self, *, run_id: str) -> dict[str, Any]:
        result = self.autoresearch_runner.run(
            run_id=run_id,
            max_iterations=self.settings.autoresearch_max_iterations,
        )
        delivered_progress = self.drain_progress_outbox()
        delivered_report = self.drain_report_outbox()
        return {
            **result,
            "delivered_outbox_ids": [*delivered_progress, *delivered_report],
        }

    def drain_progress_outbox(self) -> list[str]:
        if (
            not self.settings.telegram_progress_chat_id
            or self.settings.telegram_progress_mode == "off"
        ):
            return []
        localizer = OutputLocalizer(
            output_language=self.settings.output_language,
            docs_output_language=self.settings.docs_output_language,
            log_output_language=self.settings.log_output_language,
        )
        bot = build_progress_bot(self.settings, localizer=localizer)
        return asyncio.run(
            TelegramProgressAdapter(
                store=self.store,
                bot=bot,
                chat_id=self.settings.telegram_progress_chat_id,
                mode=self.settings.telegram_progress_mode,
                localizer=localizer,
            ).drain_pending()
        )

    def drain_report_outbox(self) -> list[str]:
        if not self.settings.telegram_report_chat_id:
            return []
        localizer = OutputLocalizer(
            output_language=self.settings.output_language,
            docs_output_language=self.settings.docs_output_language,
            log_output_language=self.settings.log_output_language,
        )
        bot = build_report_bot(self.settings, localizer=localizer)
        return asyncio.run(
            TelegramReportAdapter(
                store=self.store,
                bot=bot,
                chat_id=self.settings.telegram_report_chat_id,
                exclude_event_type_prefix="progress_",
                localizer=localizer,
            ).drain_pending()
        )

    def _worker_launch_failed(self, *, command: str, message: str) -> dict[str, Any]:
        if command == "start_pipeline":
            self.store.set_status(project_state="degraded", pipeline_state="failed")
        else:
            self.store.set_status(project_state="degraded", autoresearch_state="failed")
            self.store.set_active_run(None)
            self.store.set_pending_command(None)
        self.store.append_outbox_event(
            event_type="worker_launch_failed",
            payload={"command": command, "message": message},
        )
        failed_status = self.store.get_status()
        return {
            "accepted": False,
            "project_state": failed_status.project_state,
            "pipeline_state": failed_status.pipeline_state,
            "autoresearch_state": failed_status.autoresearch_state,
            "pending_command": failed_status.pending_command,
            "message": OutputLocalizer(
                output_language=self.settings.output_language,
                docs_output_language=self.settings.docs_output_language,
                log_output_language=self.settings.log_output_language,
            ).log("runtime.failed_to_launch_worker", command=command, message=message),
            "run_id": failed_status.active_run_id,
        }


def build_runtime(settings: Settings | None = None) -> ApplicationRuntime:
    resolved_settings = settings or load_settings()
    localizer = OutputLocalizer(
        output_language=resolved_settings.output_language,
        docs_output_language=resolved_settings.docs_output_language,
        log_output_language=resolved_settings.log_output_language,
    )
    workspace_root = resolved_settings.workspace_root.resolve()
    state_db_path = _resolve_workspace_path(
        resolved_settings.state_db_path,
        workspace_root=workspace_root,
    )
    research_knowledge_root = _resolve_workspace_path(
        resolved_settings.research_knowledge_root,
        workspace_root=workspace_root,
    )
    research_brain_root = _resolve_workspace_path(
        resolved_settings.research_brain_root,
        workspace_root=workspace_root,
    )
    store = SQLiteStateStore(
        db_path=state_db_path,
        project_id=resolved_settings.project_id,
    )
    openclaw_client = OpenClawClient(
        mutate_script=resolve_code_asset_path(
            resolved_settings.openclaw_mutate_script
        ),
        analyze_script=resolve_code_asset_path(
            resolved_settings.openclaw_analyze_script
        ),
        healthcheck_script=resolve_code_asset_path(
            resolved_settings.openclaw_healthcheck_script
        ),
        workspace_root=workspace_root / "runtime" / "openclaw",
        wrapper_env=build_openclaw_wrapper_env(resolved_settings),
    )
    pipeline_runner = PipelineRunner(
        state_store=store,
        settings=resolved_settings,
        localizer=localizer,
        cache_root=workspace_root,
        market_pack_builder=_build_market_pack_builder(
            settings=resolved_settings,
            workspace_root=workspace_root,
        ),
        openclaw_check=lambda: validate_openclaw_health(
            client=openclaw_client,
            settings=resolved_settings,
            localizer=localizer,
        ),
        baseline_strategy_path=workspace_root
        / "src"
        / "finance_autoresearch"
        / "strategy"
        / "mutable"
        / "strategy_candidate.py",
        baseline_snapshot_path=workspace_root
        / "runtime"
        / "baseline"
        / "accepted_strategy_candidate.py",
    )
    planner_memory = PlannerMemory(
        state_store=store,
        history_window=resolved_settings.planner_history_window,
    )
    brain_sync = (
        BrainSync(
            store=store,
            writer=BrainWriter(root=research_brain_root, localizer=localizer),
            localizer=localizer,
        )
        if resolved_settings.research_brain_enabled
        else None
    )
    autoresearch_runner = AutoresearchRunner(
        state_store=store,
        repository_root=workspace_root,
        openclaw_client=openclaw_client,
        progress_notifier=(
            None
            if (
                not resolved_settings.telegram_progress_chat_id
                or resolved_settings.telegram_progress_mode == "off"
            )
            else lambda: asyncio.run(
                TelegramProgressAdapter(
                    store=store,
                    bot=build_progress_bot(resolved_settings, localizer=localizer),
                    chat_id=resolved_settings.telegram_progress_chat_id,
                    mode=resolved_settings.telegram_progress_mode,
                    localizer=localizer,
                ).drain_pending()
            )
        ),
        harness=StrategyHarness(cache_root=workspace_root),
        evaluator=evaluate_backtest_results,
        analyzer=lambda backtest_results, evaluation: analyze_backtest_results(
            backtest_results,
            evaluation,
            localizer=localizer,
        ),
        falsifier=(
            None
            if not resolved_settings.falsifier_enabled
            else lambda **kwargs: falsify_candidate(localizer=localizer, **kwargs)
        ),
        prescreener=lambda **kwargs: prescreen_candidate(**kwargs),
        trial_manager=TrialManager(
            optuna_adapter=OptunaAdapter(max_variants=resolved_settings.optuna_max_variants),
            frontier_candidate_limit=resolved_settings.frontier_candidate_limit,
            prescreen_max_candidates=resolved_settings.prescreen_max_candidates,
        ),
        candidate_frontier_selector=select_candidate_frontier,
        knowledge_loader=WorkspaceKnowledgeLoader(
            repository_root=workspace_root,
            patterns=_build_knowledge_patterns(
                workspace_root=workspace_root,
                research_knowledge_root=research_knowledge_root,
                factor_catalog_root=_resolve_workspace_path(
                    resolved_settings.factor_catalog_root,
                    workspace_root=workspace_root,
                ),
                factor_catalog_enabled=resolved_settings.factor_catalog_enabled,
            ),
            brain_root=research_brain_root,
            max_linked_notes=resolved_settings.planner_max_linked_notes,
            manual_notes_mode=resolved_settings.manual_brain_notes_mode,
        ),
        planner=ResearchScheduler(),
        planner_memory=planner_memory,
        lesson_builder=LessonBuilder(),
        brain_sync=brain_sync,
        brain_auto_export=resolved_settings.research_brain_auto_export,
        genome_shadow_mode=resolved_settings.genome_shadow_mode,
        frontier_promotion_limit=resolved_settings.frontier_promotion_limit,
        allow_invalid_seed_baseline=resolved_settings.allow_invalid_seed_baseline,
        localizer=localizer,
    )
    supervisor = SupervisorService(
        state_store=store,
        seed_validator=autoresearch_runner.build_seed_validator(),
        localizer=localizer,
    )
    launcher = WorkerLauncher(settings=resolved_settings)
    return ApplicationRuntime(
        settings=resolved_settings,
        store=store,
        supervisor=supervisor,
        pipeline_runner=pipeline_runner,
        autoresearch_runner=autoresearch_runner,
        launcher=launcher,
    )


def build_report_bot(settings: Settings, *, localizer: OutputLocalizer | None = None) -> Any:
    resolved_localizer = localizer or OutputLocalizer(
        output_language=settings.output_language,
        docs_output_language=settings.docs_output_language,
        log_output_language=settings.log_output_language,
    )
    if settings.telegram_report_dry_run:
        return DryRunTelegramBot(delivered_messages=[])

    if settings.telegram_report_token is None:
        raise ValueError(resolved_localizer.log("runtime.telegram_report_token_missing"))

    from telegram import Bot

    return Bot(token=settings.telegram_report_token.get_secret_value())


def build_progress_bot(settings: Settings, *, localizer: OutputLocalizer | None = None) -> Any:
    resolved_localizer = localizer or OutputLocalizer(
        output_language=settings.output_language,
        docs_output_language=settings.docs_output_language,
        log_output_language=settings.log_output_language,
    )
    if settings.telegram_progress_dry_run:
        return DryRunTelegramBot(delivered_messages=[])

    if settings.telegram_progress_token is None:
        raise ValueError(resolved_localizer.log("runtime.telegram_progress_token_missing"))

    from telegram import Bot

    return Bot(token=settings.telegram_progress_token.get_secret_value())


def build_subprocess_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    workspace_root = settings.workspace_root.resolve()
    _set_env_value(env, "FINANCE_AUTORESEARCH_PROJECT_ID", settings.project_id)
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_WORKSPACE_ROOT",
        str(workspace_root),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_STATE_DB_PATH",
        str(
            _resolve_workspace_path(
                settings.state_db_path,
                workspace_root=workspace_root,
            )
        ),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_MARKET_PACK_MODE",
        settings.market_pack_mode,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_RESEARCH_KNOWLEDGE_ROOT",
        str(
            _resolve_workspace_path(
                settings.research_knowledge_root,
                workspace_root=workspace_root,
            )
        ),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_RESEARCH_BRAIN_ROOT",
        str(
            _resolve_workspace_path(
                settings.research_brain_root,
                workspace_root=workspace_root,
            )
        ),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_RESEARCH_BRAIN_ENABLED",
        str(settings.research_brain_enabled).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_RESEARCH_BRAIN_AUTO_EXPORT",
        str(settings.research_brain_auto_export).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OUTPUT_LANGUAGE",
        settings.output_language,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_DOCS_OUTPUT_LANGUAGE",
        settings.docs_output_language,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_LOG_OUTPUT_LANGUAGE",
        settings.log_output_language,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_GENOME_SHADOW_MODE",
        str(settings.genome_shadow_mode).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_FALSIFIER_ENABLED",
        str(settings.falsifier_enabled).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_PLANNER_HISTORY_WINDOW",
        str(settings.planner_history_window),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_PLANNER_MAX_LINKED_NOTES",
        str(settings.planner_max_linked_notes),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_PRESCREEN_MAX_CANDIDATES",
        str(settings.prescreen_max_candidates),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPTUNA_MAX_VARIANTS",
        str(settings.optuna_max_variants),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_FRONTIER_CANDIDATE_LIMIT",
        str(settings.frontier_candidate_limit),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_FRONTIER_PROMOTION_LIMIT",
        str(settings.frontier_promotion_limit),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_MANUAL_BRAIN_NOTES_MODE",
        settings.manual_brain_notes_mode,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_FACTOR_CATALOG_ENABLED",
        str(settings.factor_catalog_enabled).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_FACTOR_CATALOG_ROOT",
        str(
            _resolve_workspace_path(
                settings.factor_catalog_root,
                workspace_root=workspace_root,
            )
        ),
    )
    if settings.autoresearch_max_iterations is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_AUTORESEARCH_MAX_ITERATIONS",
            str(settings.autoresearch_max_iterations),
        )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_ALLOW_INVALID_SEED_BASELINE",
        str(settings.allow_invalid_seed_baseline).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_ROLES_PATH",
        str(resolve_code_asset_path(settings.openclaw_roles_path)),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_HEALTHCHECK_SCRIPT",
        str(resolve_code_asset_path(settings.openclaw_healthcheck_script)),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_SCRIPT",
        str(resolve_code_asset_path(settings.openclaw_mutate_script)),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_SCRIPT",
        str(resolve_code_asset_path(settings.openclaw_analyze_script)),
    )
    if settings.openclaw_mutate_handler_path is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH",
            str(
                _resolve_workspace_path(
                    settings.openclaw_mutate_handler_path,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_analyze_handler_path is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH",
            str(
                _resolve_workspace_path(
                    settings.openclaw_analyze_handler_path,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_mutate_response_json is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON",
            str(
                _resolve_workspace_path(
                    settings.openclaw_mutate_response_json,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_analyze_response_json is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON",
            str(
                _resolve_workspace_path(
                    settings.openclaw_analyze_response_json,
                    workspace_root=workspace_root,
                )
            ),
        )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_GATEWAY_URL",
        settings.openclaw_gateway_url,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_ROUTER_AGENT",
        settings.openclaw_router_agent,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_RESEARCH_AGENT",
        settings.openclaw_research_agent,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_CRITIC_AGENT",
        settings.openclaw_critic_agent,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_OPENCLAW_BUILDER_AGENT",
        settings.openclaw_builder_agent,
    )
    if settings.telegram_control_token is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_TOKEN",
            settings.telegram_control_token.get_secret_value(),
        )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_CONTROL_CHAT_ID",
        settings.telegram_control_chat_id,
    )
    if settings.telegram_report_token is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_TOKEN",
            settings.telegram_report_token.get_secret_value(),
        )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_CHAT_ID",
        settings.telegram_report_chat_id,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_REPORT_DRY_RUN",
        str(settings.telegram_report_dry_run).lower(),
    )
    if settings.telegram_progress_token is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_TELEGRAM_PROGRESS_TOKEN",
            settings.telegram_progress_token.get_secret_value(),
        )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_PROGRESS_CHAT_ID",
        settings.telegram_progress_chat_id,
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_PROGRESS_DRY_RUN",
        str(settings.telegram_progress_dry_run).lower(),
    )
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_TELEGRAM_PROGRESS_MODE",
        settings.telegram_progress_mode,
    )
    _set_env_value(env, "FINANCE_AUTORESEARCH_DASHBOARD_HOST", settings.dashboard_host)
    _set_env_value(
        env,
        "FINANCE_AUTORESEARCH_DASHBOARD_PORT",
        str(settings.dashboard_port),
    )
    return env


def load_strategy_module(strategy_path: Path) -> ModuleType:
    resolved_path = strategy_path.resolve()
    module_name = (
        "finance_autoresearch_candidate_"
        f"{hashlib.sha256(resolved_path.read_bytes()).hexdigest()[:12]}_"
        f"{resolved_path.stat().st_mtime_ns}"
    )
    spec = importlib.util.spec_from_file_location(module_name, resolved_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load strategy module from {resolved_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def resolve_code_asset_path(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (CODE_ROOT / candidate).resolve()


def build_openclaw_wrapper_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    workspace_root = settings.workspace_root.resolve()
    if settings.openclaw_mutate_handler_path is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_HANDLER_PATH",
            str(
                _resolve_workspace_path(
                    settings.openclaw_mutate_handler_path,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_analyze_handler_path is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_HANDLER_PATH",
            str(
                _resolve_workspace_path(
                    settings.openclaw_analyze_handler_path,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_mutate_response_json is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_MUTATE_RESPONSE_JSON",
            str(
                _resolve_workspace_path(
                    settings.openclaw_mutate_response_json,
                    workspace_root=workspace_root,
                )
            ),
        )
    if settings.openclaw_analyze_response_json is not None:
        _set_env_value(
            env,
            "FINANCE_AUTORESEARCH_OPENCLAW_ANALYZE_RESPONSE_JSON",
            str(
                _resolve_workspace_path(
                    settings.openclaw_analyze_response_json,
                    workspace_root=workspace_root,
                )
            ),
        )
    return env


def validate_openclaw_health(
    *,
    client: OpenClawClient,
    settings: Settings,
    localizer: OutputLocalizer | None = None,
) -> None:
    resolved_localizer = localizer or OutputLocalizer(
        output_language=settings.output_language,
        docs_output_language=settings.docs_output_language,
        log_output_language=settings.log_output_language,
    )
    result = client.check_health(
        roles_path=resolve_code_asset_path(settings.openclaw_roles_path),
        gateway_url=settings.openclaw_gateway_url,
    )
    if not result.ok:
        raise ValueError(
            result.message or resolved_localizer.log("runtime.openclaw_health_check_failed")
        )


def _build_market_pack_builder(
    *,
    settings: Settings,
    workspace_root: Path,
):
    if settings.market_pack_mode == "download":
        return None
    if settings.market_pack_mode == "cached":
        return lambda: load_market_pack(cache_root=workspace_root)
    raise ValueError(f"unsupported market_pack_mode: {settings.market_pack_mode}")


def _build_knowledge_patterns(
    *,
    workspace_root: Path,
    research_knowledge_root: Path,
    factor_catalog_root: Path,
    factor_catalog_enabled: bool,
) -> tuple[str, ...]:
    pattern_root = _pattern_root_for_workspace_path(
        research_knowledge_root,
        workspace_root=workspace_root,
    )
    patterns = [
        f"{pattern_root}/**/*.md",
        f"{pattern_root}/**/*.txt",
        f"{pattern_root}/**/*.json",
        f"{pattern_root}/**/*.yaml",
        f"{pattern_root}/**/*.yml",
        "docs/superpowers/specs/**/*.md",
        "docs/openclaw-setup.md",
        "src/finance_autoresearch/strategy/mutable/strategy_candidate.py",
        "runtime/baseline/accepted_strategy_candidate.py",
    ]
    if factor_catalog_enabled:
        factor_root = _pattern_root_for_workspace_path(
            factor_catalog_root,
            workspace_root=workspace_root,
        )
        patterns.extend(
            [
                f"{factor_root}/**/*.md",
                f"{factor_root}/**/*.txt",
                f"{factor_root}/**/*.json",
            ]
        )
    return tuple(patterns)


def _pattern_root_for_workspace_path(path: Path, *, workspace_root: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_workspace_path(path: Path | str, *, workspace_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (workspace_root / candidate).resolve()


def _set_env_value(env: dict[str, str], name: str, value: str | None) -> None:
    if value is None:
        return
    env[name] = value
