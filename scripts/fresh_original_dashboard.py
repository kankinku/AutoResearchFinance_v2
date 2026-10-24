"""Existing dashboard/static UI with a read-only fresh-session SQLite API adapter.

Reuses all original HTML, JavaScript and CSS bytes at runtime (no design rewrite).
No research or account writes, no order API. nginx Basic Auth stays upstream.
"""

from __future__ import annotations

import json
import sqlite3
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dashboard.service import DashboardService
from scripts.fresh_research_dashboard import ACTIVE_STATE, STATE, DashboardHandler, snapshot

STATIC = Path(__file__).resolve().parents[1] / "dashboard/static"


def compat(view: dict[str, Any]) -> dict[str, Any]:
    when = view.get("last_end_utc") or view["fetched_at"]
    rows = [
        {
            "run_id": "fresh-G" + str(g["generation"]),
            "generation": g["generation"],
            "timestamp": when,
            "strategy_hash": g["evidence_prefix"],
            "total_return": g["return"],
            "max_drawdown": g["mdd"],
            "trade_count": g["trades"],
            "exposure": g["exposure"],
            "sharpe": g["sharpe"],
            "qqq_excess_return": g["return"] - view["qqq_dev_bh_return"],
            "strategy_cagr": g["cagr"],
            "qqq_cagr": view["qqq_dev_bh_cagr"],
            "qqq_cagr_delta": g["cagr"] - view["qqq_dev_bh_cagr"],
            "sortino": g["sortino"],
            "profit_factor": g["profit_factor"],
            "turnover": g["turnover"],
            "nasdaq_excess_return": None,
            "risk_compliant": None,
            "status": "DEVELOPMENT_ONLY",
        }
        for g in view["generations"]
    ]
    best = view["best_eligible"]
    warnings = ["NON_PIT_DEVELOPMENT_ONLY", "NO_OOS"]
    warnings.append(
        "GPT_PROVENANCE_NOT_ATTESTED"
        if view["source_kind"] == "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
        else "GPT_PER_GENERATION_NOT_VERIFIED"
    )
    if not view["proof_chain_ok"]:
        warnings.append("EVIDENCE_CHAIN_INVALID")
    if view["phase"] == "AWAITING_DIAGNOSIS":
        warnings.append("RESEARCH_AWAITING_DIAGNOSIS")
    return {
        "schema_version": 1,
        "generated_at": view["fetched_at"],
        "mode": {
            "requested_mode": "paper",
            "effective_mode": "paper",
            "live_enabled": False,
            "safety_status": "PAPER_ONLY",
        },
        "account": {
            "status": "UNKNOWN",
            "account_number": "******",
            "holdings": [],
            "equity": None,
            "cash": None,
            "buying_power": None,
            "open_orders": 0,
        },
        "tests": list(reversed(rows)),
        "strategy": {
            "status": "DEVELOPMENT_CANDIDATE_NOT_PROMOTED" if best else "EMPTY",
            "champion_hash": best["evidence_prefix"] if best else None,
            "generation": best["generation"] if best else None,
            "family": "QQQ regime vote (development only)",
            "score": None,
            "total_return": best["return"] if best else None,
            "risk_compliant": None,
            "feature_ids": [],
        },
        "trend": [
            {
                "generation": r["generation"],
                "timestamp": when,
                "total_return": r["return"],
                "score": None,
                "nasdaq_excess_return": None,
                "risk_compliant": None,
                "strategy_cagr": r["cagr"],
                "qqq_cagr": view["qqq_dev_bh_cagr"],
                "qqq_cagr_delta": r["cagr"] - view["qqq_dev_bh_cagr"],
                "max_drawdown": r["mdd"],
                "trade_count": r["trades"],
            }
            for r in view["generations"]
        ],
        "workers": [],
        "llm": {
            "provider": (
                "authenticated_chatgpt_mcp_client"
                if view["source_kind"] == "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
                else "rule_policy_not_gpt_at_every_generation"
            ),
            "status": "NOT_VERIFIED",
            "last_result": (
                "GPT_AUTHORSHIP_OBSERVED_AUTONOMY_NOT_ATTESTED"
                if view["source_kind"] == "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
                else "RULE_POLICY_NOT_PER_GENERATION_GPT"
            ),
        },
        "research": {
            "frontier_count": 0,
            "family_count": 0,
            "frontier_families": {},
            "known_good_count": 0,
            "known_bad_count": 0,
            "unexplored_count": view["completed"],
            "interactions_count": 0,
            "rescue_count": 0,
        },
        "health": {
            "status": "DEGRADED",
            "checked_at": view["fetched_at"],
            "kis_status": "UNAVAILABLE",
            "docker_status": "MOON_ONLINE",
            "online_workers": 0,
            "stale_workers": 0,
            "warnings": warnings,
        },
        "warning_codes": warnings,
    }


def backtest(view: dict[str, Any], dash: dict[str, Any]) -> dict[str, Any]:
    count = view["completed"]
    best = view["best_eligible"]
    return {
        "generated_at": view["fetched_at"],
        "mode": dash["mode"],
        "research": {
            "status": (
                "RUNNING"
                if view["research_running_confirmed"] and view["completed"] < view["requested"]
                else (
                    "AWAITING_PROVIDER" if view["phase"] == "AWAITING_DIAGNOSIS" else view["status"]
                )
            ),
            "requested_generations": view["requested"],
            "completed_generations": count,
            "current_generation": count + 1 if count < view["requested"] else None,
            "current_phase": view["phase"],
            "last_completed_generation": count,
            "phase_started_at": None,
            "phase_elapsed_seconds": None,
        },
        "summary": {
            "total_runs": count,
            "succeeded_runs": count,
            "rejected_runs": 0,
            "risk_compliant_runs": 0,
            "generation_count": count,
            "passing_generation_count": 0,
            "latest_run_at": view.get("last_end_utc"),
            "best_run_id": "fresh-G" + str(best["generation"]) if best else None,
            "best_total_return": best["return"] if best else None,
            "best_max_drawdown": best["mdd"] if best else None,
            "best_sharpe": best["sharpe"] if best else None,
            "best_trade_count": best["trades"] if best else None,
            "best_exposure": best["exposure"] if best else None,
            "best_sortino": best["sortino"] if best else None,
            "best_profit_factor": best["profit_factor"] if best else None,
            "best_turnover": best["turnover"] if best else None,
            "best_strategy_cagr": best["cagr"] if best else None,
            "best_qqq_cagr": view["qqq_dev_bh_cagr"],
            "best_qqq_cagr_delta": (best["cagr"] - view["qqq_dev_bh_cagr"] if best else None),
            "risk_compliance_rate": None,
        },
        "generations": [
            {
                "generation": g["generation"],
                "status": "MEASURED_DEVELOPMENT_NOT_APPROVED",
                "candidate_count": 1,
                "best_run_id": "fresh-G" + str(g["generation"]),
                "best_total_return": g["return"],
                "best_max_drawdown": g["mdd"],
                "best_sharpe": g["sharpe"],
                "best_trade_count": g["trades"],
                "best_sortino": g["sortino"],
                "best_profit_factor": g["profit_factor"],
                "best_strategy_cagr": g["cagr"],
                "best_qqq_cagr": view["qqq_dev_bh_cagr"],
                "best_qqq_cagr_delta": g["cagr"] - view["qqq_dev_bh_cagr"],
                "best_risk_compliant": None,
                "proposal": {"data_scope": "DEVELOPMENT_NON_PIT"},
            }
            for g in view["generations"]
        ],
        "runs": dash["tests"],
        "capabilities": [],
        "warning_codes": dash["warning_codes"],
    }


def page(name: str) -> bytes:
    text = (STATIC / name).read_text(encoding="utf-8")
    text = text.replace('href="/static/', 'href="static/')
    text = text.replace('src="/static/', 'src="static/')
    text = text.replace('href="/backtest"', 'href="backtest"')
    text = text.replace('href="/"', 'href="./"')
    if name == "index.html":
        assert "<main>" in text
        text = text.replace("<body>", '<body class="performance-priority">', 1)
        text = text.replace("<h1>연구 운영</h1>", "<h1>전략 성과</h1>", 1)
        text = text.replace(
            "현재 상태를 확인하고 다음 연구 행동을 결정하세요.",
            "세대별 전략 성과와 위험, 시장 대비 차이를 한눈에 확인하세요.",
            1,
        )
        text = text.replace(
            "로컬 전용 · Paper-only 안전 경계 적용", "읽기 전용 · 실거래 주문 비활성", 1
        )
        text = text.replace(
            "</head>", '<link rel="stylesheet" href="static/fresh-performance.css">\n</head>', 1
        )
        text = text.replace(
            '<button id="refresh"',
            '<button id="connection-toggle" class="button" type="button" '
            'aria-haspopup="dialog" aria-controls="connection-dialog">연결 상태</button>\n'
            '      <button id="refresh"',
            1,
        )
        panel = (STATIC / "fresh-performance.html").read_text(encoding="utf-8")
        text = text.replace("<main>", "<main>\n" + panel, 1)
        # Keep the original UI and make historical source auditable without
        # permitting dashboard-controlled research writes or exposing OAuth.
        text = text.replace(
            "<main>",
            '<main><p class="muted">현재 GPT 연구 원장 표시 중 · '
            '<a href="api/status?cohort=historical" target="_blank" '
            'rel="noopener noreferrer">기존 G453~G552 연구 원장(JSON)</a> · '
            '<a href="api/status?cohort=original" target="_blank" '
            'rel="noopener noreferrer">기존 G452 원장(JSON)</a></p>',
            1,
        )
        mark = '<section id="safety-banner"'
        assert mark in text
        text = text.replace(
            mark,
            '<details class="operations-collapse"><summary>'
            "운영 정보 · 연결 상세 · 연구 기록 펼치기</summary>\n    " + mark,
            1,
        )
        text = text.replace("  </main>", "  </details>\n  </main>", 1)
        text = text.replace(
            "</body>", '  <script src="static/fresh-performance.js"></script>\n</body>', 1
        )
    return text.encode("utf-8")


def script(name: str) -> bytes:
    text = (STATIC / name).read_text(encoding="utf-8")
    text = text.replace('fetch("/api/', 'fetch("api/')
    text = text.replace("fetch('/api/", "fetch('api/")
    # Refresh is a read-only API view; the old UI's POST is denied by nginx.
    # Map its refresh action to the canonical GET, without changing original JS.
    if name == "app.js":
        old = 'fetch("api/refresh", {method: "POST"})'
        assert old in text
        text = text.replace(old, 'fetch("api/dashboard")')
    # The original backtest details fetch uses a template-literal URL.
    text = text.replace("fetch(" + chr(96) + "/api/", "fetch(" + chr(96) + "api/")
    return text.encode("utf-8")


class OriginalDashboardHandler(DashboardHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._respond(200, "text/html; charset=utf-8", page("index.html"))
        if path == "/backtest":
            return self._respond(200, "text/html; charset=utf-8", page("backtest.html"))
        if path.startswith("/static/"):
            name = path.removeprefix("/static/")
            if name not in (
                "styles.css",
                "app.js",
                "backtest.js",
                "labels.js",
                "fresh-performance.css",
                "fresh-performance.js",
            ):
                return self._respond(404, "text/plain", b"not found")
            if name.endswith(".js"):
                javascript_bytes = (
                    (STATIC / name).read_bytes() if name == "fresh-performance.js" else script(name)
                )
                return self._respond(200, "text/javascript; charset=utf-8", javascript_bytes)
            return self._respond(200, "text/css; charset=utf-8", (STATIC / name).read_bytes())
        if path in (
            "/api/status",
            "/api/health",
            "/health",
            "/api/dashboard",
            "/api/backtest",
            "/api/research-evidence",
            "/api/features/catalog",
            "/api/strategies/catalog",
        ):
            try:
                # Read-only opt-in history. The default is the live MCP
                # checkpoint, even while G3 waits for GPT input.
                cohort = self.path.partition("?")[2]
                if cohort == "cohort=historical":
                    view = snapshot(ACTIVE_STATE)
                elif cohort == "cohort=original":
                    view = snapshot(STATE)
                elif not cohort:
                    view = snapshot()
                else:
                    return self._respond(400, "application/json", b'{"error":"BAD_COHORT"}')
                dash = compat(view)
                data: Any = view
                if path == "/api/status":
                    data = view
                elif path in ("/api/health", "/health"):
                    data = {
                        "status": "DEGRADED",
                        "effective_mode": "paper",
                        "live_enabled": False,
                        "safety_status": "PAPER_ONLY",
                        "kis_status": "UNAVAILABLE",
                        "docker_status": "MOON_ONLINE",
                        "online_workers": 0,
                        "stale_workers": 0,
                        "warnings": dash["warning_codes"],
                    }
                elif path == "/api/dashboard":
                    data = dash
                elif path == "/api/backtest":
                    data = backtest(view, dash)
                elif path == "/api/research-evidence":
                    data = {
                        "status": "DEVELOPMENT_ONLY",
                        "runs": [
                            {
                                "research_run_id": view["session"],
                                "status": view["phase"],
                                "completed_generations": view["completed"],
                                "requested_generations": view["requested"],
                                "fallback_rate": None,
                                "candidate_count": view["completed"],
                                "unique_candidate_count": None,
                                "reject_count": None,
                                "pass_rate": None,
                            }
                        ],
                        "legacy": {"status": "OLD_RUNTIME_MISSING", "record_count": None},
                        "sealed_oos_survival": {"status": "NOT_MEASURED", "value": None},
                    }
                elif path == "/api/features/catalog":
                    data = DashboardService(Path("state")).feature_catalog()
                elif path == "/api/strategies/catalog":
                    data = DashboardService(Path("state")).strategy_catalog()
                else:
                    data = {}
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                return self._respond(200, "application/json; charset=utf-8", payload)
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                return self._respond(
                    503, "application/json", json.dumps({"error": type(exc).__name__}).encode()
                )
        if path.startswith("/api/backtest/runs/"):
            run = path.rsplit("/", 1)[-1]
            data = compat(snapshot())
            record = next((x for x in data["tests"] if x["run_id"] == run), None)
            if record is None:
                return self._respond(404, "application/json", b'{"error":"NOT_AVAILABLE"}')
            return self._respond(
                200,
                "application/json; charset=utf-8",
                json.dumps(record, ensure_ascii=False).encode("utf-8"),
            )
        return self._respond(404, "text/plain", b"not found")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/refresh":
            # The original UI refresh button remains functional but READ ONLY.
            try:
                data = compat(snapshot())
                return self._respond(
                    200, "application/json", json.dumps(data, ensure_ascii=False).encode("utf-8")
                )
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                return self._respond(503, "application/json", b'{"error":"not available"}')
        self._respond(405, "text/plain", b"read only")


def main() -> None:
    ThreadingHTTPServer(("127.0.0.1", 8082), OriginalDashboardHandler).serve_forever()


if __name__ == "__main__":
    main()
