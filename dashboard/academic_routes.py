"""FastAPI read-only local UI for academic MCP generations; no control routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from dashboard.academic_monitor import (
    AcademicMonitorReader,
    ResearchMonitorUnavailable,
    ResearchSessionNotFound,
)

_STATIC = Path(__file__).parent / "static"
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
}


def register_academic_routes(
    app: FastAPI,
    reader: AcademicMonitorReader,
    *,
    root_page: bool = False,
) -> None:
    def page() -> Response:
        return FileResponse(
            _STATIC / "academic.html",
            headers=_SECURITY_HEADERS,
            media_type="text/html",
        )

    app.add_api_route("/academic", page, methods=["GET"], include_in_schema=False)
    if root_page:
        app.add_api_route("/", page, methods=["GET"], include_in_schema=False)

    @app.get("/api/academic/sessions", include_in_schema=False)
    def sessions() -> Response:
        try:
            result = reader.sessions()
        except ResearchMonitorUnavailable:
            return JSONResponse(
                {"status": "RESEARCH_STATE_UNAVAILABLE"}, status_code=503, headers=_SECURITY_HEADERS
            )
        return JSONResponse(
            {"sessions": result, "orders_enabled": False}, headers=_SECURITY_HEADERS
        )

    @app.get("/api/academic/overview", include_in_schema=False)
    def overview() -> Response:
        try:
            payload = reader.snapshot()
        except ResearchMonitorUnavailable:
            return JSONResponse(
                {"status": "RESEARCH_STATE_UNAVAILABLE"}, status_code=503, headers=_SECURITY_HEADERS
            )
        return JSONResponse(payload, headers=_SECURITY_HEADERS)

    @app.get("/api/academic/sessions/{session_id}", include_in_schema=False)
    def session(session_id: str) -> Response:
        try:
            payload = reader.snapshot(session_id)
        except ResearchSessionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ResearchMonitorUnavailable:
            return JSONResponse(
                {"status": "RESEARCH_EVIDENCE_INTEGRITY_ERROR"},
                status_code=503,
                headers=_SECURITY_HEADERS,
            )
        return JSONResponse(payload, headers=_SECURITY_HEADERS)
