from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import ALLOWED_STRATEGY_SUFFIXES, resolve_project_input
from research.policy import default_evaluation_thresholds
from runtime.docker_evaluation import docker_evaluation_container_name
from runtime.lifecycle_lock import LifecycleBusyError, lifecycle_lock
from runtime.persistent_queue import PersistentJobQueue
from runtime.process_lifecycle import (
    process_matches,
    spawn_managed_process,
    terminate_process_tree,
)
from runtime.queue import JobStatus
from runtime.recovery_state import (
    append_recovery_event,
    close_interrupted_evidence,
    mark_autoresearch_interrupted,
    runtime_interruption_origin,
)
from runtime.runtime_snapshot import build_runtime_snapshot

ProcessFactory = Callable[[list[str], Path], Any]
CommandRunner = Callable[[list[str], Path], tuple[int, str]]
ProcessProbe = Callable[[int, tuple[str, ...]], bool]
ProcessTerminator = Callable[[int, tuple[str, ...]], bool]
_EVALUATION_DEFAULTS = default_evaluation_thresholds()


@dataclass(frozen=True)
class SystemLaunchConfig:
    source_path: str
    data_path: str
    method: str = "random"
    count: int = 8
    seed: int = 0
    min_trades: int = 10
    min_annual_trades: int = _EVALUATION_DEFAULTS.min_annual_trades
    min_qqq_cagr_delta: float | None = _EVALUATION_DEFAULTS.min_qqq_cagr_delta
    series_data_path: str | None = None
    repeat_generations: int = 1
    interval_seconds: float = 0.0
    parameter_domains: tuple[ParameterDomain, ...] = ()
    dashboard_port: int = 8080
    docker_image: str = "quant-autoresearch-worker:local"
    env_file: str = ".env"


@dataclass(frozen=True)
class PreflightIssue:
    id: str
    severity: str
    message: str
    action: str


@dataclass(frozen=True)
class PreflightReport:
    status: str
    checks: tuple[dict[str, str], ...]
    issues: tuple[PreflightIssue, ...]

    def as_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": list(self.checks),
            "issues": [issue.__dict__ for issue in self.issues],
        }


class SystemController:
    """Start and stop the local paper research system as one managed unit."""

    def __init__(
        self,
        *,
        state_dir: Path,
        project_root: Path,
        process_factory: ProcessFactory | None = None,
        command_runner: CommandRunner | None = None,
        process_probe: ProcessProbe | None = None,
        process_terminator: ProcessTerminator | None = None,
    ) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self._process_factory = process_factory or spawn_managed_process
        self._command_runner = command_runner or _run_command
        self._process_probe = process_probe or process_matches
        self._process_terminator = process_terminator or terminate_process_tree
        self._processes: dict[str, Any] = {}

    def preflight(self, config: SystemLaunchConfig) -> PreflightReport:
        checks: list[dict[str, str]] = []
        issues: list[PreflightIssue] = []

        def check(check_id: str, label: str, passed: bool, message: str = "") -> None:
            checks.append({"id": check_id, "label": label, "status": "PASS" if passed else "FAIL"})
            if not passed and message:
                issues.append(PreflightIssue(check_id, "REQUIRED", label, message))

        check(
            "repeat_config",
            "유한 반복 설정",
            config.repeat_generations >= 1
            and config.interval_seconds >= 0
            and config.min_annual_trades >= 0,
            (
                "repeat_generations는 1 이상, interval_seconds와 min_annual_trades는 "
                "0 이상이어야 합니다."
            ),
        )

        check(
            "python_runtime",
            "Python runtime",
            bool(sys.executable and Path(sys.executable).is_file()),
            "Python 실행 파일을 확인하고 가상환경을 활성화하세요.",
        )
        check(
            "state_ready",
            "Paper-only state",
            self._paper_state_ready(),
            "먼저 python cli.py init --state-dir state 를 실행하고 paper 모드를 유지하세요.",
        )
        source = self._resolve_input(
            config.source_path,
            ALLOWED_STRATEGY_SUFFIXES,
            check,
            "strategy_source",
            "전략 소스",
            "전략 파일을 프로젝트 루트 아래에 준비하세요.",
        )
        data = self._resolve_input(
            config.data_path,
            frozenset({".parquet"}),
            check,
            "market_data",
            "Parquet 데이터",
            "버전 메타데이터가 있는 development Parquet 데이터를 준비하세요.",
        )
        series = None
        if config.series_data_path is not None:
            series = self._resolve_input(
                config.series_data_path,
                frozenset({".parquet"}),
                check,
                "series_data",
                "벤치마크·외부 시계열",
                "series_data_path에 유효한 Parquet 파일을 지정하세요.",
            )
            if series is not None:
                try:
                    series_data = ParquetDataProvider.read_series(series)
                    check(
                        "series_zone",
                        "외부 시계열 영역",
                        DataZone(series_data.zone) is DataZone.DEVELOPMENT,
                        "연구 백테스트는 development 외부 시계열만 사용할 수 있습니다.",
                    )
                except (OSError, TypeError, ValueError):
                    check(
                        "series_contract",
                        "외부 시계열 계약",
                        False,
                        "series_id·timestamp·value 스키마를 확인하세요.",
                    )
        data_ok = False
        if data is not None:
            try:
                dataset = ParquetDataProvider.read(data)
                data_ok = DataZone(dataset.zone) is DataZone.DEVELOPMENT
                check(
                    "data_zone",
                    "연구 데이터 영역",
                    data_ok,
                    "연구 백테스트는 development 데이터만 사용할 수 있습니다.",
                )
            except (OSError, TypeError, ValueError):
                check(
                    "data_contract",
                    "Parquet 데이터 계약",
                    False,
                    "dataset_version·data_zone 및 OHLCV 스키마를 확인하세요.",
                )
        if source is not None and source.suffix.lower() not in ALLOWED_STRATEGY_SUFFIXES:
            data_ok = False
        check(
            "codex_cli",
            "Codex CLI",
            bool(shutil.which(_codex_executable())),
            "Codex CLI를 설치하고 codex login status로 로그인 상태를 확인하세요.",
        )
        env_path = (self.project_root / config.env_file).resolve()
        env_in_project = self.project_root in env_path.parents and env_path.name != ".env.example"
        check(
            "codex_config",
            "Codex 연구 설정",
            env_in_project and env_path.is_file(),
            f"{config.env_file}에 QUANT_CODEX_COMMAND와 모델 설정을 준비하세요.",
        )
        evaluation_execution = _evaluation_execution(
            self.project_root / config.env_file
        )
        execution_valid = evaluation_execution in {"local_scheduler", "docker_worker"}
        check(
            "evaluation_execution",
            "평가 실행 백엔드",
            execution_valid,
            (
                "QUANT_EVALUATION_EXECUTION은 local_scheduler 또는 "
                "docker_worker여야 합니다."
            ),
        )
        docker_required = evaluation_execution == "docker_worker"
        docker_available = bool(shutil.which("docker"))
        if docker_required:
            check(
                "docker_cli",
                "Docker CLI",
                docker_available,
                "Docker 평가 모드를 사용하려면 Docker Desktop을 설치하고 실행하세요.",
            )
            docker_ready = False
            if docker_available:
                return_code, _ = self._command_runner(
                    ["docker", "info", "--format", "{{.ServerVersion}}"], self.project_root
                )
                docker_ready = return_code == 0
                check(
                    "docker_engine",
                    "Docker Desktop engine",
                    docker_ready,
                    "Docker Desktop을 켠 뒤 Docker engine이 Ready 상태인지 확인하세요.",
                )
                if docker_ready:
                    image_name_ok = bool(
                        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", config.docker_image)
                    )
                    image_code = 1
                    if image_name_ok:
                        image_code, _ = self._command_runner(
                            ["docker", "image", "inspect", config.docker_image],
                            self.project_root,
                        )
                    check(
                        "docker_image",
                        "Docker evaluation worker image",
                        image_name_ok and image_code == 0,
                        (
                            f"docker build -t {config.docker_image} "
                            "-f runtime/Dockerfile.worker . 를 실행하세요."
                        ),
                    )
        else:
            checks.append(
                {
                    "id": "docker_cli",
                    "label": "Docker CLI (local_scheduler에서는 선택 사항)",
                    "status": "PASS",
                }
            )
        check(
            "dashboard_port",
            "Dashboard port",
            _port_available(config.dashboard_port),
            (
                f"포트 {config.dashboard_port}를 사용 중인 프로세스를 종료하거나 "
                "다른 포트를 지정하세요."
            ),
        )
        status = "READY" if not issues else "BLOCKED"
        return PreflightReport(status, tuple(checks), tuple(issues))

    def start(self, config: SystemLaunchConfig) -> dict[str, object]:
        try:
            with lifecycle_lock(self._lifecycle_lock_path()):
                existing = self._reconcile_state(persist=True)
                restart_origin: dict[str, object] | None = None
                if existing.get("status") == "INTERRUPTED":
                    restart_origin = runtime_interruption_origin(existing.get("runtime"))
                    failed_recovery = self._terminate_managed_processes(existing)
                    if failed_recovery:
                        return {
                            "status": "RECOVERY_FAILED",
                            "process_cleanup_failed": failed_recovery,
                            "system": existing,
                        }
                elif self._has_active_runtime(existing):
                    return {
                        "status": "ALREADY_RUNNING",
                        "system": existing,
                    }
                report = self.preflight(config)
                if report.status != "READY":
                    return {"status": "BLOCKED", "preflight": report.as_payload()}
                source = resolve_project_input(
                    self.project_root, config.source_path, ALLOWED_STRATEGY_SUFFIXES
                )
                data = resolve_project_input(
                    self.project_root, config.data_path, frozenset({".parquet"})
                )
                series = (
                    resolve_project_input(
                        self.project_root, config.series_data_path, frozenset({".parquet"})
                    )
                    if config.series_data_path is not None
                    else None
                )
                self.state_dir.mkdir(parents=True, exist_ok=True)
                relative_source = source.relative_to(self.project_root).as_posix()
                relative_data = data.relative_to(self.project_root).as_posix()
                relative_series = (
                    series.relative_to(self.project_root).as_posix() if series is not None else None
                )
                evaluation_execution = _evaluation_execution(
                    self.project_root / config.env_file
                )
                managed_run_id = uuid4().hex
                commands = {
                    "dashboard": [
                        sys.executable,
                        "cli.py",
                        "dashboard",
                        "--state-dir",
                        str(self.state_dir),
                        "--env-file",
                        str(self.project_root / config.env_file),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(config.dashboard_port),
                    ],
                    "research_worker": self._research_worker_command(
                        config,
                        relative_source,
                        relative_data,
                        relative_series,
                        evaluation_execution,
                        managed_run_id,
                    ),
                }
                started: list[dict[str, object]] = []
                try:
                    for component_id, command in commands.items():
                        self._processes[component_id] = self._process_factory(
                            command, self.project_root
                        )
                        process = self._processes[component_id]
                        pid = getattr(process, "pid", None)
                        started.append(
                            {
                                "id": component_id,
                                "status": "STARTED",
                                "pid": pid if isinstance(pid, int) else None,
                                "identity_markers": list(
                                    self._identity_markers(
                                        component_id,
                                        managed_run_id=managed_run_id,
                                        dashboard_port=config.dashboard_port,
                                    )
                                ),
                            }
                        )
                except OSError as exc:
                    self._terminate_in_memory_processes()
                    return {
                        "status": "FAILED",
                        "message": str(exc),
                        "components": started,
                    }
                started.append(
                    {
                        "id": "evaluation_backend",
                        "status": "CONFIGURED",
                        "mode": evaluation_execution,
                        "active_jobs": 0,
                        "queued_jobs": 0,
                    }
                )
                payload = {
                    "status": "STARTED",
                    "managed_run_id": managed_run_id,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "project_root": str(self.project_root),
                    "dashboard_port": config.dashboard_port,
                    "container_name": None,
                    "evaluation_execution": evaluation_execution,
                    "components": started,
                    "preflight": report.as_payload(),
                }
                if restart_origin is not None:
                    payload["restarted_from"] = {
                        "managed_run_id": _text(existing.get("managed_run_id")),
                        **restart_origin,
                    }
                self._write_state(payload)
                if restart_origin is not None:
                    append_recovery_event(
                        self.state_dir,
                        event="RESTARTED",
                        managed_run_id=_text(existing.get("managed_run_id")),
                        origin=restart_origin,
                        replacement_managed_run_id=managed_run_id,
                    )
                return payload
        except LifecycleBusyError:
            return {"status": "BUSY", "message": "system lifecycle change already in progress"}

    def status(self) -> dict[str, object]:
        return self._reconcile_state(persist=True)

    def stop(self) -> dict[str, object]:
        try:
            with lifecycle_lock(self._lifecycle_lock_path()):
                current = self._reconcile_state(persist=False)
                managed_run_id = _text(current.get("managed_run_id"))
                failed_processes = self._terminate_managed_processes(current)
                failed_cleanup = self._terminate_docker_jobs(managed_run_id)
                payload: dict[str, object] = {
                    "status": (
                        "STOPPED"
                        if not failed_processes and not failed_cleanup
                        else "STOP_FAILED"
                    ),
                    "components": [],
                }
                if managed_run_id is not None:
                    payload["managed_run_id"] = managed_run_id
                if failed_processes:
                    payload["process_cleanup_failed"] = failed_processes
                if failed_cleanup:
                    payload["cleanup_failed"] = failed_cleanup
                self._write_state(payload)
                return payload
        except LifecycleBusyError:
            return {"status": "BUSY", "message": "system lifecycle change already in progress"}


    def _research_worker_command(
        self,
        config: SystemLaunchConfig,
        source_path: str,
        data_path: str,
        series_path: str | None,
        evaluation_execution: str,
        managed_run_id: str,
    ) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "runtime.system_worker",
            "--role",
            "research",
            "--state-dir",
            str(self.state_dir),
            "--project-root",
            str(self.project_root),
            "--env-file",
            str(self.project_root / config.env_file),
            "--source-path",
            source_path,
            "--data-path",
            data_path,
            "--method",
            config.method,
            "--count",
            str(config.count),
            "--seed",
            str(config.seed),
            "--min-trades",
            str(config.min_trades),
            "--min-annual-trades",
            str(config.min_annual_trades),
            "--repeat-generations",
            str(config.repeat_generations),
            "--interval-seconds",
            str(config.interval_seconds),
            "--evaluation-execution",
            evaluation_execution,
            "--evaluation-docker-image",
            config.docker_image,
            "--managed-run-id",
            managed_run_id,
        ]
        if config.min_qqq_cagr_delta is not None:
            command.extend(
                ["--min-qqq-cagr-delta", str(config.min_qqq_cagr_delta)]
            )
        if series_path is not None:
            command.extend(["--series-data-path", series_path])
        for domain in config.parameter_domains:
            command.extend(
                [
                    "--domain",
                    json.dumps(
                        {"name": domain.name, "values": list(domain.values)},
                        ensure_ascii=False,
                    ),
                ]
            )
        return command

    def _terminate_docker_jobs(self, managed_run_id: str | None) -> list[str]:
        queue = PersistentJobQueue(self.state_dir)
        running = (
            queue.running(managed_run_id=managed_run_id)
            if managed_run_id is not None
            else tuple(
                job
                for job in queue.running()
                if "managed_run_id" not in job.payload
            )
        )
        if not running:
            return []
        if not shutil.which("docker"):
            return [job.job_id for job in running]
        failed: list[str] = []
        for job in running:
            container_name = docker_evaluation_container_name(job.job_id, job.attempt)
            return_code, _ = self._command_runner(
                ["docker", "rm", "-f", container_name],
                self.project_root,
            )
            if return_code != 0:
                failed.append(job.job_id)
                continue
            try:
                queue.cancel_running(job.job_id)
            except ValueError:
                continue
        return failed

    def _resolve_input(
        self,
        value: str,
        suffixes: frozenset[str],
        check: Callable[[str, str, bool, str], None],
        check_id: str,
        label: str,
        action: str,
    ) -> Path | None:
        try:
            path = resolve_project_input(self.project_root, value, suffixes)
        except (OSError, PermissionError, TypeError, ValueError):
            check(check_id, label, False, action)
            return None
        check(check_id, label, True, "")
        return path

    def _paper_state_ready(self) -> bool:
        path = self.state_dir / "mode.json"
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return (
            str(payload.get("selected_mode", "")).lower() == "paper"
            and payload.get("orders_enabled") is False
        )


    def _reconcile_state(self, *, persist: bool) -> dict[str, object]:
        payload = self._read_state()
        if payload is None:
            stopped: dict[str, object] = {"status": "STOPPED", "components": []}
            stopped["runtime"] = build_runtime_snapshot(
                self.state_dir,
                managed_run_id=None,
                system_state=stopped,
            )
            return stopped
        components = payload.get("components")
        if not isinstance(components, list):
            unknown: dict[str, object] = {"status": "UNKNOWN", "components": []}
            unknown["runtime"] = build_runtime_snapshot(
                self.state_dir,
                managed_run_id=_text(payload.get("managed_run_id")),
                system_state=unknown,
            )
            return unknown
        managed_run_id = _text(payload.get("managed_run_id"))
        research_alive = False
        for component in components:
            if not isinstance(component, dict):
                continue
            component_id = _text(component.get("id"))
            if component_id not in {"dashboard", "research_worker"}:
                continue
            alive = self._component_alive(component, payload)
            component["alive"] = alive
            if component_id == "research_worker":
                research_alive = alive
                worker_state = self._read_worker_state(
                    component_id,
                    managed_run_id=managed_run_id,
                )
                if worker_state in {"SUCCEEDED", "FAILED"}:
                    component["status"] = worker_state
                else:
                    component["status"] = "RUNNING" if alive else "EXITED"
            else:
                component["status"] = "RUNNING" if alive else "EXITED"

        recovery: dict[str, object] = {}
        queue = PersistentJobQueue(self.state_dir)
        if managed_run_id is not None and not research_alive:
            cancelled: list[str] = []
            for job in queue.queued(managed_run_id=managed_run_id):
                queue.cancel_queued(job.job_id)
                cancelled.append(job.job_id)
            reconciled = queue.reconcile_stale(managed_run_id=managed_run_id)
            for job_id in reconciled:
                job = queue.get(job_id)
                if job.status is not JobStatus.QUEUED:
                    continue
                queue.cancel_queued(job_id)
                cancelled.append(job_id)
            if reconciled:
                recovery["reconciled_jobs"] = list(reconciled)
            if cancelled:
                recovery["cancelled_orphaned_jobs"] = sorted(set(cancelled))

        owned_jobs = (
            queue.jobs_for_run(managed_run_id)
            if managed_run_id is not None
            else (*queue.running(), *queue.queued())
        )
        running_jobs = sum(job.status is JobStatus.RUNNING for job in owned_jobs)
        queued_jobs = sum(job.status is JobStatus.QUEUED for job in owned_jobs)
        for component in components:
            if not isinstance(component, dict):
                continue
            if component.get("id") != "evaluation_backend":
                continue
            component["active_jobs"] = running_jobs
            component["queued_jobs"] = queued_jobs
            component["status"] = (
                "RUNNING"
                if running_jobs
                else "QUEUED"
                if queued_jobs
                else "READY"
            )

        payload["runtime"] = build_runtime_snapshot(
            self.state_dir,
            managed_run_id=managed_run_id,
            system_state=payload,
            recovery_state=recovery,
        )
        if (
            managed_run_id is not None
            and not research_alive
            and running_jobs == 0
            and queued_jobs == 0
        ):
            runtime = payload.get("runtime")
            research_runtime = (
                runtime.get("research")
                if isinstance(runtime, dict)
                else None
            )
            if (
                isinstance(research_runtime, dict)
                and research_runtime.get("status") == "RUNNING"
            ):
                origin = mark_autoresearch_interrupted(self.state_dir)
                if origin is not None:
                    research_run_id = _text(origin.get("research_run_id"))
                    closed = close_interrupted_evidence(
                        self.state_dir,
                        research_run_id=research_run_id,
                    )
                    append_recovery_event(
                        self.state_dir,
                        event="INTERRUPTED",
                        managed_run_id=managed_run_id,
                        origin=origin,
                    )
                    recovery["interrupted_research_run_id"] = research_run_id
                    recovery["evidence_closed"] = closed
                    payload["runtime"] = build_runtime_snapshot(
                        self.state_dir,
                        managed_run_id=managed_run_id,
                        system_state=payload,
                        recovery_state=recovery,
                    )
        payload["status"] = self._aggregate_status(payload)
        if recovery:
            payload["recovery"] = recovery
        elif "recovery" in payload:
            payload.pop("recovery", None)
        payload["runtime"] = build_runtime_snapshot(
            self.state_dir,
            managed_run_id=managed_run_id,
            system_state=payload,
            recovery_state=recovery,
        )
        if persist:
            self._write_state(payload)
        return payload

    def _aggregate_status(self, payload: dict[str, object]) -> str:
        components = payload.get("components")
        if not isinstance(components, list):
            return "UNKNOWN"
        statuses = {
            str(component.get("id")): str(component.get("status"))
            for component in components
            if isinstance(component, dict) and component.get("id") is not None
        }
        dashboard = statuses.get("dashboard")
        research = statuses.get("research_worker")
        evaluation = statuses.get("evaluation_backend")

        runtime = payload.get("runtime")
        runtime_research = runtime.get("research") if isinstance(runtime, dict) else None
        runtime_research_status = (
            _text(runtime_research.get("status"))
            if isinstance(runtime_research, dict)
            else None
        )
        if (
            runtime_research_status == "INTERRUPTED"
            and evaluation not in {"RUNNING", "QUEUED"}
            and research != "RUNNING"
        ):
            return "INTERRUPTED"
        if research == "FAILED":
            return "FAILED"
        if research == "RUNNING" or evaluation in {"RUNNING", "QUEUED"}:
            if dashboard == "EXITED" or research == "EXITED":
                return "DEGRADED"
            return "RUNNING"
        if research == "SUCCEEDED":
            return "COMPLETED" if dashboard != "EXITED" else "DEGRADED"
        if dashboard == "RUNNING":
            return "DEGRADED"
        original = _text(payload.get("status"))
        if original == "STOP_FAILED":
            return "STOP_FAILED"
        return "STOPPED"

    def _has_active_runtime(self, payload: dict[str, object]) -> bool:
        components = payload.get("components")
        if not isinstance(components, list):
            return False
        for component in components:
            if not isinstance(component, dict):
                continue
            component_id = component.get("id")
            if component_id in {"dashboard", "research_worker"} and component.get("alive") is True:
                return True
            if component_id == "evaluation_backend":
                if _nonnegative_int(component.get("active_jobs")) > 0:
                    return True
                if _nonnegative_int(component.get("queued_jobs")) > 0:
                    return True
        return False

    def _component_alive(
        self,
        component: dict[str, object],
        payload: dict[str, object],
    ) -> bool:
        component_id = _text(component.get("id"))
        if component_id is None:
            return False
        process = self._processes.get(component_id)
        if process is not None:
            try:
                return process.poll() is None
            except (OSError, AttributeError):
                return False
        pid = _positive_pid(component.get("pid"))
        if pid is None:
            return False
        markers = self._component_markers(component, payload)
        return bool(markers) and self._process_probe(pid, markers)

    def _component_markers(
        self,
        component: dict[str, object],
        payload: dict[str, object],
    ) -> tuple[str, ...]:
        raw = component.get("identity_markers")
        if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
            markers = tuple(item for item in raw if item)
            if markers:
                return markers
        component_id = _text(component.get("id"))
        managed_run_id = _text(payload.get("managed_run_id"))
        dashboard_port = _nonnegative_int(payload.get("dashboard_port"))
        if component_id is None:
            return ()
        return self._identity_markers(
            component_id,
            managed_run_id=managed_run_id,
            dashboard_port=dashboard_port,
        )

    def _identity_markers(
        self,
        component_id: str,
        *,
        managed_run_id: str | None,
        dashboard_port: int,
    ) -> tuple[str, ...]:
        if component_id == "dashboard":
            return (
                "cli.py",
                "dashboard",
                "--state-dir",
                str(self.state_dir),
                "--port",
                str(dashboard_port),
            )
        if component_id == "research_worker":
            markers = [
                "runtime.system_worker",
                "--role",
                "research",
                "--state-dir",
                str(self.state_dir),
            ]
            if managed_run_id:
                markers.extend(["--managed-run-id", managed_run_id])
            return tuple(markers)
        return ()

    def _terminate_managed_processes(
        self,
        payload: dict[str, object],
    ) -> list[str]:
        components = payload.get("components")
        if not isinstance(components, list):
            self._terminate_in_memory_processes()
            return []
        failed: list[str] = []
        for component in components:
            if not isinstance(component, dict):
                continue
            component_id = _text(component.get("id"))
            if component_id not in {"dashboard", "research_worker"}:
                continue
            pid = _positive_pid(component.get("pid"))
            if pid is None or not self._component_alive(component, payload):
                continue
            markers = self._component_markers(component, payload)
            if self._process_terminator(pid, markers):
                continue
            process = self._processes.get(component_id)
            try:
                if process is not None and process.poll() is None:
                    process.terminate()
                    continue
            except (OSError, AttributeError):
                pass
            failed.append(component_id)
        self._processes.clear()
        return failed

    def _terminate_in_memory_processes(self) -> None:
        for process in self._processes.values():
            try:
                if process.poll() is None:
                    process.terminate()
            except (OSError, AttributeError):
                continue
        self._processes.clear()

    def _lifecycle_lock_path(self) -> Path:
        return self.state_dir / "system" / "lifecycle.lock"

    def _write_state(self, payload: dict[str, object]) -> None:
        target = self.state_dir / "system" / "system.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)

    def _read_state(self) -> dict[str, object] | None:
        path = self.state_dir / "system" / "system.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return {str(key): value for key, value in payload.items()}

    def _read_worker_state(
        self,
        component_id: str,
        *,
        managed_run_id: str | None,
    ) -> str | None:
        path = self.state_dir / "system" / f"{component_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        recorded_run_id = _text(payload.get("managed_run_id"))
        if managed_run_id is not None and recorded_run_id != managed_run_id:
            return None
        status = payload.get("status")
        return status if isinstance(status, str) else None



def _run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, f"{result.stdout}\n{result.stderr}"


def _port_available(port: int) -> bool:
    if not 1 <= port <= 65535:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _positive_pid(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _evaluation_execution(env_file: Path | None = None) -> str:
    configured = os.environ.get("QUANT_EVALUATION_EXECUTION")
    if configured is not None:
        return configured.strip()
    if env_file is not None and env_file.is_file():
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() != "QUANT_EVALUATION_EXECUTION":
                continue
            raw_value = value.strip()
            if (
                len(raw_value) >= 2
                and raw_value[0] == raw_value[-1]
                and raw_value[0] in {'"', "'"}
            ):
                raw_value = raw_value[1:-1]
            return raw_value.strip()
    return "local_scheduler"


def _codex_executable() -> str:
    configured = os.environ.get("QUANT_CODEX_COMMAND", "codex")
    try:
        parts = shlex.split(configured, posix=True)
    except ValueError:
        return ""
    return parts[0] if parts else ""
