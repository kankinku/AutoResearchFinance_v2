"""Local-only academic MCP research monitor, separate from paper trading server."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from dashboard.academic_monitor import AcademicMonitorReader
from dashboard.academic_routes import register_academic_routes


def create_academic_app(checkpoint_dir: Path) -> FastAPI:
    app = FastAPI(
        title="Quant Autoresearch Research Monitor",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    register_academic_routes(app, AcademicMonitorReader(checkpoint_dir), root_page=True)
    return app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only localhost academic research monitor")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost"):
        parser.error("monitor must bind only to 127.0.0.1 or localhost")
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    app = create_academic_app(args.checkpoint_dir)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
