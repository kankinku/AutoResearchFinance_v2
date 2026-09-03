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
from pathlib import Path
from typing import Any

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import ALLOWED_STRATEGY_SUFFIXES, resolve_project_input
from research.policy import default_evaluation_thresholds

ProcessFactory = Callable[[list[str], Path], Any]
CommandRunner = Callable[[list[str], Path], tuple[int, str]]
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
    ) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self._process_factory = process_factory or _spawn_process
        self._command_runner = command_runner or _run_command
        self._processes: dict[str, Any] = {}
        self._container_name: str | None = None

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
            "버전 메타데이터가 있는 development/validation Parquet 데이터를 준비하세요.",
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
                        DataZone(series_data.zone) is not DataZone.SEALED_OOS,
                        "sealed_oos 외부 시계열은 연구 백테스트에 사용할 수 없습니다.",
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
                data_ok = DataZone(dataset.zone) is not DataZone.SEALED_OOS
                check(
                    "data_zone",
                    "OOS 봉인 영역 차단",
                    data_ok,
                    "sealed_oos 데이터는 연구 백테스트에 사용할 수 없습니다.",
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
        docker_available = bool(shutil.which("docker"))
        check(
            "docker_cli",
            "Docker CLI",
            docker_available,
            "Docker Desktop을 설치하고 실행하세요.",
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
                        ["docker", "image", "inspect", config.docker_image], self.project_root
                    )
                check(
                    "docker_image",
                    "Docker worker image",
                    image_name_ok and image_code == 0,
                    (
                        f"docker build -t {config.docker_image} "
                        "-f runtime/Dockerfile.worker . 를 실행하세요."
                    ),
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
        container_name = f"quant-autoresearch-backtest-{os.getpid()}"
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
            "research_worker": [
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
                str(source),
            ],
            "backtest_worker": self._docker_command(
                config, container_name, relative_source, relative_data, relative_series
            ),
        }
        started: list[dict[str, object]] = []
        try:
            for component_id, command in commands.items():
                self._processes[component_id] = self._process_factory(command, self.project_root)
                process = self._processes[component_id]
                started.append(
                    {"id": component_id, "status": "STARTED", "pid": getattr(process, "pid", None)}
                )
            self._container_name = container_name
        except OSError as exc:
            self._terminate_started()
            return {"status": "FAILED", "message": str(exc), "components": started}
        payload = {
            "status": "STARTED",
            "project_root": str(self.project_root),
            "dashboard_port": config.dashboard_port,
            "container_name": container_name,
            "components": started,
            "preflight": report.as_payload(),
        }
        self._write_state(payload)
        return payload

    def status(self) -> dict[str, object]:
        path = self.state_dir / "system" / "system.json"
        if not path.is_file():
            return {"status": "STOPPED", "components": []}
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {"status": "UNKNOWN", "components": []}
        if not isinstance(raw_payload, dict):
            return {"status": "UNKNOWN", "components": []}
        payload: dict[str, object] = raw_payload
        if self._processes:
            components = payload.get("components", [])
            if isinstance(components, list):
                for component in components:
                    if not isinstance(component, dict):
                        continue
                    component_id = component.get("id")
                    if not isinstance(component_id, str):
                        continue
                    process = self._processes.get(component_id)
                    if process is not None:
                        component["status"] = "RUNNING" if process.poll() is None else "EXITED"
        components = payload.get("components", [])
        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("id")
                if component_id not in {"research_worker", "backtest_worker"}:
                    continue
                worker_state = self._read_worker_state(str(component_id))
                if worker_state is not None:
                    component["status"] = worker_state
        return payload

    def stop(self) -> dict[str, object]:
        self._terminate_started()
        payload: dict[str, object] = {"status": "STOPPED", "components": []}
        self._write_state(payload)
        return payload

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

    def _docker_command(
        self,
        config: SystemLaunchConfig,
        container_name: str,
        source_path: str,
        data_path: str,
        series_path: str | None = None,
    ) -> list[str]:
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,source={self.project_root},target=/workspace,readonly",
            "--mount",
            f"type=bind,source={self.state_dir},target=/workspace/state",
            "--workdir",
            "/workspace",
            config.docker_image,
            "--role",
            "backtest",
            "--state-dir",
            "/workspace/state",
            "--project-root",
            "/workspace",
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
        ]
        if config.min_qqq_cagr_delta is not None:
            command.extend(["--min-qqq-cagr-delta", str(config.min_qqq_cagr_delta)])
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

    def _terminate_started(self) -> None:
        for process in self._processes.values():
            try:
                if process.poll() is None:
                    process.terminate()
            except (OSError, AttributeError):
                continue
        if self._container_name and shutil.which("docker"):
            self._command_runner(["docker", "stop", self._container_name], self.project_root)
        self._processes.clear()
        self._container_name = None

    def _write_state(self, payload: dict[str, object]) -> None:
        target = self.state_dir / "system" / "system.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)

    def _read_worker_state(self, component_id: str) -> str | None:
        path = self.state_dir / "system" / f"{component_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        status = payload.get("status") if isinstance(payload, dict) else None
        return status if isinstance(status, str) else None


def _spawn_process(command: list[str], cwd: Path) -> subprocess.Popen[Any]:
    return subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def _codex_executable() -> str:
    configured = os.environ.get("QUANT_CODEX_COMMAND", "codex")
    try:
        parts = shlex.split(configured, posix=True)
    except ValueError:
        return ""
    return parts[0] if parts else ""
