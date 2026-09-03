"""Keep the local paper dashboard available while research runs."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DashboardSupervisorConfig:
    project_root: Path
    state_dir: Path
    env_file: Path
    host: str = "127.0.0.1"
    port: int = 8080
    restart_delay_seconds: float = 2.0

    @property
    def log_path(self) -> Path:
        return self.state_dir / "system" / "dashboard-supervisor.log"


def dashboard_command(config: DashboardSupervisorConfig) -> list[str]:
    return [
        sys.executable,
        "cli.py",
        "dashboard",
        "--state-dir",
        str(config.state_dir),
        "--env-file",
        str(config.env_file),
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]


def run_supervisor(config: DashboardSupervisorConfig, *, once: bool = False) -> None:
    if config.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("paper dashboard supervisor must bind to localhost")
    if not 1 <= config.port <= 65535:
        raise ValueError("dashboard port must be between 1 and 65535")
    if _port_is_open(config.host, config.port):
        raise RuntimeError(f"dashboard is already listening on {config.host}:{config.port}")

    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    with config.log_path.open("a", encoding="utf-8") as log:
        while True:
            started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            log.write(f"{started} supervisor starting dashboard\n")
            log.flush()
            process = subprocess.Popen(
                dashboard_command(config),
                cwd=config.project_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            result = process.wait()
            stopped = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            log.write(f"{stopped} dashboard exited with code {result}\n")
            log.flush()
            if once:
                return
            time.sleep(config.restart_delay_seconds)


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Keep the local paper dashboard running")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--restart-delay", type=float, default=2.0)
    parser.add_argument("--once", action="store_true", help="stop after the first dashboard exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_supervisor(
            DashboardSupervisorConfig(
                project_root=args.project_root.resolve(),
                state_dir=args.state_dir,
                env_file=args.env_file,
                host=args.host,
                port=args.port,
                restart_delay_seconds=args.restart_delay,
            ),
            once=args.once,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"dashboard supervisor error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
