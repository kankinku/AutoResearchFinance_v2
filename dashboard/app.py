from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from dashboard.contracts import DashboardSnapshot
from dashboard.service import DashboardService


def create_app(service: DashboardService | None = None) -> FastAPI:
    app = FastAPI(title="Quant Autoresearch Paper Dashboard", docs_url=None, redoc_url=None)
    dashboard_service = service or DashboardService.from_environment(Path("state"), Path(".env"))
    app.state.dashboard_service = dashboard_service
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    def index() -> Response:
        index_path = static_dir / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return JSONResponse({"status": "ONLINE", "message": "dashboard assets are not installed"})

    @app.get("/backtest", include_in_schema=False, response_model=None)
    def backtest_page() -> Response:
        page_path = static_dir / "backtest.html"
        if page_path.is_file():
            return FileResponse(page_path)
        return JSONResponse({"status": "ONLINE", "message": "backtest assets are not installed"})

    @app.get("/api/health")
    def health() -> JSONResponse:
        snapshot = dashboard_service.snapshot()
        health = snapshot.health
        if health is None:
            raise HTTPException(status_code=503, detail="health unavailable")
        return JSONResponse(
            {
                "status": health.status,
                "effective_mode": snapshot.mode.effective_mode,
                "live_enabled": snapshot.mode.live_enabled,
                "safety_status": snapshot.mode.safety_status,
                "kis_status": health.kis_status,
                "docker_status": health.docker_status,
                "online_workers": health.online_workers,
                "stale_workers": health.stale_workers,
                "warnings": health.warnings,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/dashboard", response_model=DashboardSnapshot)
    def dashboard() -> DashboardSnapshot:
        return dashboard_service.snapshot()

    @app.get("/api/features/catalog")
    def feature_catalog() -> JSONResponse:
        return JSONResponse(
            dashboard_service.feature_catalog(), headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/backtest")
    def backtest() -> JSONResponse:
        return JSONResponse(
            dashboard_service.backtest_snapshot().model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/backtest/runs/{run_id}")
    def backtest_run(run_id: str) -> JSONResponse:
        record = next(
            (item for item in dashboard_service.snapshot().tests if item.run_id == run_id),
            None,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="backtest run not found")
        return JSONResponse(record.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @app.post("/api/refresh", response_model=DashboardSnapshot)
    def refresh() -> DashboardSnapshot:
        return dashboard_service.refresh()

    return app
