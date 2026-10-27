"""Read-only, same-origin Quant chart adapter for the EXISTING dashboard.

The gateway's /academic and /quant-research paths retain their existing
Basic Auth/GET-only ACL. This module never proxies OAuth, secrets, research
state, order APIs, or arbitrary client-supplied upstream URLs.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Final

LAB_ROOT: Final = Path("/shared/moon-workspace/Quant-Backtest-Lab-20261027")
STATIC: Final = LAB_ROOT / "dashboard/static"
LAB_SERVICE: Final = "http://127.0.0.1:8096"
MAX_BODY: Final = 16 * 1024 * 1024
MAX_ASSET: Final = 4 * 1024 * 1024

ASSETS: Final = {
    "styles.css": "text/css; charset=utf-8",
    "labels.js": "text/javascript; charset=utf-8",
    "backtest.js": "text/javascript; charset=utf-8",
    "backtest-chart.js": "text/javascript; charset=utf-8",
    "backtest-history.js": "text/javascript; charset=utf-8",
    "vendor/lightweight-charts-5.2.1.standalone.production.js": "text/javascript; charset=utf-8",
}
_RUN_RE = r"[A-Za-z0-9_-]{1,160}"
_RUN_ENDPOINT = re.compile(
    rf"^/api/chart/backtest/runs/({_RUN_RE})"
    r"(?:/(verification|manifest|analysis|candles|fills|signals|equity))?$"
)
_SIMPLE = {
    "/api/chart/backtest",
    "/api/chart/backtest/original-lineage",
    "/api/chart/backtest/lab-bridge",
}
_OPTION_KEYS = {"symbol", "offset", "limit"}
_COMPARE_KEYS = {"run_a", "run_b"}


def chart_page() -> bytes:
    """Render the exact Lab chart with prefixed, same-origin URLs."""
    html = (STATIC / "backtest.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/', 'href="chart-assets/')
    html = html.replace('src="/static/', 'src="chart-assets/')
    html = html.replace('href="/"', 'href="./"')
    html = html.replace('href="/backtest"', 'href="chart"')
    html = html.replace("<h1>전략 탐색 성과</h1>", "<h1>매매 체결 검증 차트</h1>")
    html = html.replace(
        "기존 PythonMCP 세대 결과는 요약 기록이며, 매매 화살표는 별도로 "
        "재실행한 전략의 실제 엔진 체결입니다.",
        "원본 Quant 전략의 계승 지표·비용·감사 해시를 재현하여 검증된 "
        "체결만 차트에 표시합니다. 독립 OOS 검증 및 실거래는 포함되지 않습니다.",
    )
    html = html.replace(
        "원본 PythonMCP 연구 세대 성과 요약 보기 · 체결 위치 없음",
        "원본 세대별 성과와 매매 증거 확인",
    )
    # Explicit link back to the original dashboard's existing backtest summary.
    html = html.replace(
        'href="chart">전략 성과</a>',
        'href="chart">매매 차트</a><a href="backtest">연구 백테스트</a>',
        1,
    )
    assert 'src="chart-assets/backtest-chart.js?v=p3"' in html
    assert 'href="chart-assets/styles.css?v=20260903"' in html
    return html.encode("utf-8")


def chart_asset(asset: str) -> tuple[str, bytes] | None:
    """Strict static allowlist; no arbitrary path or outside-file resolution."""
    mime = ASSETS.get(asset)
    if mime is None:
        return None
    path = STATIC / asset
    if (
        path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(STATIC.resolve())
    ):
        raise ValueError("unsafe chart asset")
    if path.stat().st_size > MAX_ASSET:
        raise ValueError("chart asset exceeds size bound")
    raw = path.read_bytes()
    if asset in ("backtest.js", "backtest-chart.js", "backtest-history.js"):
        # Relative to the DOCUMENT URL; works behind /academic/ and /quant-research/.
        script = raw.decode("utf-8")
        script = script.replace("/api/backtest", "api/chart/backtest")
        # Prevent leaking unrewritten API locations by build regressions.
        assert "/api/backtest" not in script
        raw = script.encode("utf-8")
    return mime, raw


def _validated_target(request_path: str) -> str:
    """Build only known GET-only Lab API paths; never relay an arbitrary URL."""
    if len(request_path) > 1200 or "#" in request_path or "\\" in request_path:
        raise ValueError("unapproved chart API target")
    parsed = urllib.parse.urlsplit(request_path)
    path = parsed.path
    if ".." in path or "%" in path or "//" in path:
        raise ValueError("noncanonical chart API path")
    route = _RUN_ENDPOINT.fullmatch(path)
    if path not in _SIMPLE and path != "/api/chart/backtest/compare" and not route:
        raise ValueError("unapproved chart API route")
    query = (
        urllib.parse.parse_qs(
            parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=6
        )
        if parsed.query
        else {}
    )
    if path == "/api/chart/backtest/compare":
        if set(query) != _COMPARE_KEYS:
            raise ValueError("comparison requires two approved run ids")
        for name in _COMPARE_KEYS:
            vals = query[name]
            if len(vals) != 1 or not re.fullmatch(_RUN_RE, vals[0]):
                raise ValueError("invalid comparison run id")
    elif route and route.group(2) in {"candles", "fills", "signals", "equity"}:
        if not set(query) <= _OPTION_KEYS:
            raise ValueError("unsupported evidence query")
        for key, values in query.items():
            if len(values) != 1:
                raise ValueError("duplicate evidence query")
            value = values[0]
            if key == "symbol" and not re.fullmatch(r"[A-Z0-9._-]{1,16}", value):
                raise ValueError("invalid chart symbol")
            if key in {"offset", "limit"} and (
                not value.isascii() or not value.isdecimal() or len(value) > 6
            ):
                raise ValueError("invalid page range")
    elif query:
        raise ValueError("chart API does not accept query parameters")
    suffix = path.removeprefix("/api/chart")
    query_string = urllib.parse.urlencode(
        [(key, val) for key, values in query.items() for val in values]
    )
    return "/api" + suffix + ("?" + query_string if query_string else "")


def chart_api(request_path: str) -> tuple[int, bytes]:
    """No client auth/header forwarding. Local, evidence-only immutable upstream."""
    target = _validated_target(request_path)
    request = urllib.request.Request(
        LAB_SERVICE + target,
        headers={"Accept": "application/json", "Host": "127.0.0.1:8096"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("chart upstream returned non-JSON payload")
            content = response.read(MAX_BODY + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code if error.code in {400, 403, 404, 405, 409, 422} else 503
        content = error.read(min(MAX_BODY, 200_000))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectionError("local chart evidence server unavailable") from exc
    if len(content) > MAX_BODY:
        raise ValueError("oversized chart evidence response")
    # Fail closed even on upstream 4xx if the payload isn't structured JSON.
    try:
        parsed = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid chart evidence JSON") from exc
    if not isinstance(parsed, (dict, list)):
        raise ValueError("invalid chart evidence structure")
    return status, content
