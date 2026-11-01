"""Opt-in, read-only bridge from the independently verified P9 DEVELOPMENT Lab.

The operator starts the separately owned, loopback-only Lab preview and calls
this helper with its loopback URL. The helper never starts servers or accesses
production state, sealed OOS, accounts, models, or orders. It writes only to a
private *non-operational* preview state directory inside this worktree.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.chart_pattern_bridge import overlay_payload

P9_RUN = "LAB_REPLAY_14626d55_G094"
P9_DATASET = "f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e"
P9_BARS = 1508
REPO = Path(__file__).resolve().parents[1]
PREVIEW = REPO / "state" / "integration-chart-p9-preview"


def validated_lab_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "http" or parts.hostname != "127.0.0.1"
        or parts.username is not None or parts.password is not None
        or parts.port is None or parts.port < 1024
        or parts.path or parts.query or parts.fragment
    ):
        raise ValueError("P9 Lab must use an exact uncredentialed loopback HTTP origin")
    return url


def verify_trace(raw: dict[str, Any]) -> None:
    if (
        raw.get("run_id") != P9_RUN
        or raw.get("status") != "VERIFIED"
        or raw.get("zone") != "development"
        or raw.get("dataset_hash") != P9_DATASET
        or raw.get("candles") != P9_BARS
        or raw.get("orders_enabled") is not False
    ):
        raise ValueError("P9 verified-development trace does not match frozen contract")


def _fetch(origin: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(origin + path, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        content_type = response.headers.get("Content-Type", "").split(";")[0]
        if response.status != 200 or content_type != "application/json":
            raise ValueError("P9 Lab response is not a valid JSON success")
        value = json.load(response)
        if not isinstance(value, dict):
            raise ValueError("P9 Lab returned non-object")
        return value


def collect_verified_p9_overlay(origin: str) -> dict[str, Any]:
    origin = validated_lab_url(origin)
    prefix = "/api/backtest/runs/" + P9_RUN
    trace = _fetch(origin, prefix + "/verification")
    verify_trace(trace)
    rows: list[dict[str, Any]] = []
    for offset in range(0, P9_BARS, 500):
        page = _fetch(origin, prefix + f"/candles?offset={offset}&limit=500")
        items = page.get("items")
        if (
            page.get("run_id") != P9_RUN
            or page.get("status") != "VERIFIED"
            or page.get("total") != P9_BARS
            or page.get("offset") != offset
            or not isinstance(items, list)
            or len(items) != min(500, P9_BARS - offset)
            or not all(isinstance(item, dict) for item in items)
        ):
            raise ValueError("P9 Lab candle page has an incomplete or altered boundary")
        rows.extend(items)
    try:
        bars = tuple(
            Bar(
                timestamp=datetime.fromisoformat(item["timestamp"]),
                symbol=item["symbol"], open=item["open"], high=item["high"],
                low=item["low"], close=item["close"], volume=item["volume"],
            )
            for item in rows
        )
        if len(bars) != P9_BARS or {bar.symbol for bar in bars} != {"QQQ"}:
            raise ValueError("unexpected P9 symbol/length")
        if bars[0].timestamp.year != 2020 or bars[-1].timestamp.year != 2025:
            raise ValueError("P9 data window differs from frozen development dataset")
        market = MarketDataSet("p9-verified-chart-replay-v1", DataZone.DEVELOPMENT, bars)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("P9 candles failed strict OHLCV validation") from error
    # Do not label generic market-derived patterns as G94's trading signals.
    overlay = cast(dict[str, Any], overlay_payload(
        market, patterns=("double_top", "double_bottom", "elliott_abc"),
        allow_research=True, data_kind="RESEARCH_DEVELOPMENT",
    ))
    overlay["external_verification"] = {
        "original_trace": P9_RUN,
        "original_dataset_hash": P9_DATASET,
        "verified_candle_count": P9_BARS,
        "original_run_independent_oos": False,
        "model_generated_signals": False,
    }
    overlay["overlay_hash"] = content_hash(
        {k: v for k, v in overlay.items() if k != "overlay_hash"}
    )
    return overlay


def write_private_preview(overlay: dict[str, Any]) -> Path:
    # Never publish to a running dashboard's canonical state directory.
    state = REPO / "state"
    state.mkdir(exist_ok=True)
    if state.is_symlink() or PREVIEW.is_symlink():
        raise ValueError("state path must not be a symlink")
    PREVIEW.mkdir(exist_ok=True)
    target = PREVIEW / "chart-research-overlay-a8.json"
    if target.exists() or target.is_symlink():
        raise FileExistsError("immutable preview already exists; refusing overwrite")
    raw = json.dumps(overlay, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(raw) > 2_000_000:
        raise ValueError("overlay exceeds dashboard safe size limit")
    temp = PREVIEW / ".pending-overlay.json"
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a verified private P9 chart preview")
    parser.add_argument("--lab-base-url", required=True)
    args = parser.parse_args()
    data = collect_verified_p9_overlay(args.lab_base_url)
    target = write_private_preview(data)
    print(
        f"PREVIEW_ONLY {target} events={len(data['events'])} "
        f"candles={len(data['series']['close'])}"
    )


if __name__ == "__main__":
    main()
