from __future__ import annotations

from pathlib import Path

import uvicorn

from dashboard.app import create_app
from dashboard.service import DashboardService


def run_dashboard(*, state_dir: Path, env_path: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("paper dashboard must bind to localhost")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    service = DashboardService.from_environment(state_dir, env_path)
    uvicorn.run(create_app(service), host=host, port=port, log_level="info")
