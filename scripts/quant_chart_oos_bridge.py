"""Authenticated read-only 2026 retrospective QQQ holdout chart.

Original Quant research and 2020-2025 audited development evidence are
immutable. This NEVER claims sealed prospective validation or places orders.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.integrity.hashes import content_hash

LAB = Path("/shared/moon-workspace/Quant-Backtest-Lab-20261027")
RESULT = LAB / "state/lab-d8-2026-retrospective-g124-20261027"
EXPECTED_ORIGINAL_EVIDENCE = "bcc7bdb0429134c5885fb3d9d1c580b0ddc462c06230f36667bcc74cb35d076a"
EXPECTED_FROZEN_IR = "ef12c93c77dabe397e3600e28034e2daf75060f66c6f61b3ce9ce564a4912545"
FIRST = "2026-01-02"
LAST = "2026-10-26"
MIME = "text/html; charset=utf-8"


def _json(filename: str, limit: int) -> Any:
    approved = {
        "retrospective_oos_report.json",
        "vendor_2026_qqq_chart_response.json",
        "2026_forward_equity.json",
        "2026_forward_fills.json",
    }
    if filename not in approved:
        raise ValueError("unapproved retrospective evidence path")
    path = RESULT / filename
    if (
        not path.is_file()
        or path.is_symlink()
        or not path.resolve().is_relative_to(RESULT.resolve())
        or path.stat().st_size > limit
    ):
        raise ValueError("missing/unsafe retrospective evidence")
    return json.loads(path.read_bytes())


def evidence() -> dict[str, object]:
    """Verify immutable source and derived series before serving a graph."""
    manifest = _json("retrospective_oos_report.json", 50_000)
    vendor_path = RESULT / "vendor_2026_qqq_chart_response.json"
    provider = vendor_path.read_bytes()
    if (
        manifest["study_kind"] != "RETROSPECTIVE_CHRONOLOGICAL_2026_NON_PIT_NOT_SEALED"
        or manifest["generation"] != 124
        or manifest["frozen_strategy_hash"] != EXPECTED_FROZEN_IR
        or manifest["original_evidence_hash"] != EXPECTED_ORIGINAL_EVIDENCE
        or manifest["oos_period"] != [FIRST, LAST]
        or manifest["forward_market_data"]["response_sha256"]
        != hashlib.sha256(provider).hexdigest()
        or manifest["independent_prospective_oos"] is not False
        or manifest["orders_enabled"] is not False
    ):
        raise ValueError("2026 retrospective proof does not match frozen G124")
    original = _json("vendor_2026_qqq_chart_response.json", 1_000_000)
    record = original["chart"]["result"][0]
    if record["meta"]["symbol"] != "QQQ":
        raise ValueError("unexpected 2026 ticker")
    quotes = record["indicators"]["quote"][0]
    bars: list[dict[str, object]] = []
    for item in zip(
        record["timestamp"],
        quotes["open"],
        quotes["high"],
        quotes["low"],
        quotes["close"],
        quotes["volume"],
        strict=True,
    ):
        stamp, opened, high, low, closed, vol = item
        day = datetime.fromtimestamp(stamp, ZoneInfo("America/New_York")).date().isoformat()
        if not FIRST <= day <= LAST:
            continue
        if any(x is None or not math.isfinite(float(x)) for x in item[1:]):
            raise ValueError("invalid vendor forward candle")
        if (
            not float(low)
            <= min(float(opened), float(closed))
            <= max(float(opened), float(closed))
            <= float(high)
        ):
            raise ValueError("invalid vendor OHLC")
        bars.append(
            {
                "time": day,
                "open": float(opened),
                "high": float(high),
                "low": float(low),
                "close": float(closed),
                "volume": float(vol),
            }
        )
    if (
        len(bars) != manifest["oos_days"]
        or len(bars) != 205
        or bars[0]["time"] != FIRST
        or bars[-1]["time"] != LAST
        or [str(bar["time"]) for bar in bars] != sorted({str(bar["time"]) for bar in bars})
    ):
        raise ValueError("incomplete retrospective market chart")
    daily = _json("2026_forward_equity.json", 200_000)
    trades = _json("2026_forward_fills.json", 100_000)
    if (
        len(daily) != len(bars)
        or [point["date"] for point in daily] != [bar["time"] for bar in bars]
        or len(trades) != manifest["executions_count"]
        or manifest["executions_count"] != 20
        or abs(sum(row["cost"] for row in trades) - manifest["2026_total_cost_usd"]) > 1e-7
        or abs(daily[-1]["equity"] - manifest["2026_end_equity_usd"]) > 1e-7
        or content_hash([point["equity"] for point in daily]) != manifest["forward_equity_hash"]
    ):
        raise ValueError("forward orders and mark-to-market proofs diverged")
    daybars = {str(item["time"]): item for item in bars}
    for order in trades:
        when = order["date"][:10]
        bar = daybars.get(when)
        if (
            bar is None
            or order["side"] not in ("buy", "sell")
            or order["price"] != bar["open"]
            or not all(
                math.isfinite(float(order[k])) and order[k] > 0
                for k in ("price", "quantity", "cost")
            )
        ):
            raise ValueError("unverified 2026 chart trade")
    return {
        "schema": "quant-retrospective-2026-g124-chart-v1",
        "status": "VERIFIED_RETROSPECTIVE_NON_PIT_NOT_SEALED",
        "generation": 124,
        "period_start": FIRST,
        "period_end": LAST,
        "original_strategy_hash": EXPECTED_FROZEN_IR,
        "metric_basis": "2026_FORCED_FLAT_AT_ENTRY_OOS_ONLY",
        "candles": bars,
        "equity": [{"time": row["date"], "value": row["equity"]} for row in daily],
        "fills": [
            {
                "time": item["date"][:10],
                "side": item["side"],
                "price": item["price"],
                "cost": item["cost"],
            }
            for item in trades
        ],
        "metrics": {
            "strategy_return_pct": manifest["retrospective_2026_return_pct"],
            "strategy_max_drawdown_pct": manifest["retrospective_2026_max_drawdown_pct"],
            "qqq_return_pct": manifest["qqq_buy_hold_return_pct"],
            "qqq_max_drawdown_pct": manifest["qqq_buy_hold_mdd_pct"],
            "qqq_excess_pp": manifest["qqq_excess_percentage_points"],
            "fill_count": manifest["executions_count"],
            "cost_usd": manifest["2026_total_cost_usd"],
            "end_equity_usd": manifest["2026_end_equity_usd"],
        },
        "warnings": [
            "2026년 과거 가격을 사용한 사후 시간 분리 검증이며 봉인·전향적 OOS가 아닙니다.",
            "2020~2025년 지표 워밍업만 사용했으며 2026년 구간에만 신규 체결을 허용했습니다.",
            "비PIT 최신 Yahoo QQQ 원시 가격 · 배당 제외 · 실거래 불가",
            "이 결과를 이용해 수정한 전략은 같은 2026년 구간으로 독립 검증할 수 없습니다.",
        ],
        "source_sha256": manifest["forward_market_data"]["response_sha256"],
        "orders_enabled": False,
    }


def page() -> bytes:
    """Static shell; the browser requests only the validated aggregate."""
    html = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quant | 2026 미학습 사후 검증</title>
<link rel="stylesheet" href="chart-assets/styles.css?v=d7">
<link rel="stylesheet" href="chart-assets/quant-chart-primary.css?v=d4">
<link rel="stylesheet" href="chart-assets/quant-oos-2026.css?v=d8">
<script defer src="chart-assets/vendor/lightweight-charts-5.2.1.standalone.production.js"></script>
<script defer src="chart-assets/quant-oos-2026.js?v=d8"></script>
</head><body>
<header class="topbar"><div><p class="eyebrow">Quant / 연구 운영</p>
<h1>2026년 미학습 구간 검증</h1>
<p class="lede">원본 G124 전략을 그대로 2026년 QQQ에 적용한 사후 평가</p></div>
<nav class="page-nav"><a href="./">개발기간 차트</a>
<a href="oos" class="active">2026 미학습 구간</a>
<a href="research">연구 운영</a></nav></header>
<main><section class="safety-banner"><strong>사후 OOS · 비봉인</strong>
2026년 과거 가격으로 검증했습니다. 미리 봉인한 전향적 실험이나 투자 성과가 아닙니다.</section>
<section class="panel backtest-trace-panel" id="oos-panel">
<div class="section-heading"><div><p class="eyebrow">원본 규칙 및 비용 고정 · G124</p>
<h2>2026년 QQQ 매수·매도 차트</h2>
<p class="muted">신호는 이전 봉 종가에 확정하고 이후 봉 시가에 체결했습니다.
2025년 거래는 이 결과에 포함하지 않습니다.</p>
</div><span class="badge" id="oos-status" role="status">검증 중</span></div>
<div id="oos-kpis" class="oos-kpis" aria-live="polite"></div>
<div class="trace-date-range" aria-label="2026 차트 확대 기간">
<label for="oos-start">시작일<input type="date" id="oos-start" disabled></label>
<label for="oos-end">종료일<input type="date" id="oos-end" disabled></label>
<button type="button" class="button button-small" id="oos-zoom" disabled>선택 기간 확대</button>
<button type="button" class="button button-small" id="oos-reset" disabled>전체 기간</button>
<span class="muted trace-range-note" id="oos-date-note" role="status">시장 데이터 확인 중</span>
</div>
<div class="trace-canvas-shell"><div class="trace-price-header">
<strong>QQQ 일봉 · G124 매매</strong>
<span>초록 매수 · 빨강 매도</span></div>
<div id="oos-price" class="trace-price-canvas" aria-label="2026 가격 및 매매 마커"></div>
<div class="trace-price-header"><strong>2026년 투자금 변화</strong>
<span>시작 1만 달러, 개발기간 수익 제외</span></div>
<div id="oos-equity" class="trace-equity-canvas" aria-label="2026 원본 엔진 자산곡선"></div></div>
<p class="muted" id="oos-summary" role="status"></p>
<details class="quant-chart-research-details"><summary>2026 매매 체결 내역</summary>
<div class="table-wrap scroll-table"><table><thead>
<tr><th>날짜</th><th>방향</th><th>가격(달러)</th><th>비용(달러)</th></tr></thead>
<tbody id="oos-orders"></tbody></table></div></details>
</section><section class="panel"><h2>평가 범위와 주의사항</h2>
<p class="muted">이 시험은 이미 관측된 2026년 가격으로 실시했습니다. 배당 제외 비PIT 데이터이며,
2026년 결과를 학습에 재사용하면 이후 성과를 독립 OOS로 간주할 수 없습니다.</p>
<div id="oos-warnings" class="oos-warnings"></div></section>
</main><footer class="muted">읽기 전용 과거자료 비교 · 주문 실행 기능 없음</footer>
</body></html>"""
    return html.encode("utf-8")
