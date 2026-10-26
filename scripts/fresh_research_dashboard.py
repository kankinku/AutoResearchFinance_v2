# ruff: noqa: E501  # Static HTML/CSS/JS inside multiline string literals.
"""Read-only status UI for the new, isolated Quant AutoResearch academic session.

Only bind 127.0.0.1. The nginx public route must enforce HTTP Basic auth.
No write connection or hidden research/OAuth keys are exposed to browsers.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"  # Preserved original academic ledger.
ACTIVE_STATE = ROOT / "state/moon-http/quant-moon-bounded-100-20261023"
ACTIVE_COHORT_ID = "G453-G552-20261023-moon-stress"
# Pinned from actual authenticated ChatGPT MCP 10-generation cohort. The GPT
# worker writes this *separate* root while historical G452/G552 stay immutable.
# This is a model-authored checkpoint channel, not unattended model attestation.
LIVE_STATE = ROOT / "state/moon-http"
LIVE_SESSION_ID = "14626d55fb2b461faa485df911920071"
# Pin the opt-in 100-generation GPT checkpoint by ID, never by latest DB file.
P5_STATE = Path("/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024")
P5_SESSION_ID = "3b44e05e52b3497db6fa035681ed0a5d"
QQQ_DEV_RETURN = 1.8777241068917014
# Price-only benchmark over the same development window (2020-01-02 to 2025-12-31).
QQQ_DEV_YEARS = (date(2025, 12, 31) - date(2020, 1, 2)).days / 365.2425
QQQ_DEV_CAGR = (1 + QQQ_DEV_RETURN) ** (1 / QQQ_DEV_YEARS) - 1


def _measured_metric(m: dict[str, Any], k: str) -> float | None:
    v = m.get(k)
    return None if v is None else float(v)


def _read_db(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError("missing read-only research DB")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def _controller_running(state: Path = STATE) -> bool:
    """Prove a matching local research Python PID exists; no network or mutation."""
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            argv = (item / "cmdline").read_bytes().split(bytes([0]))
            if len(argv) < 3 or b"python" not in Path(argv[0].decode()).name.encode():
                continue
            # A former study's worker must never masquerade as this cohort.
            known = (
                (b"state/moon-http/quant-moon-bounded-100-20261023/run_bounded_100.py",)
                if state == ACTIVE_STATE
                else (
                    b"state/tools/fresh_batch_controller_20261021.py",
                    b"scripts/fresh_development_cohort_controller_20261021.py",
                    b"scripts.run_academic_cohort",
                    b"scripts/run_academic_cohort.py",
                )
            )
            if not any(arg.endswith(path) for arg in argv[1:] for path in known):
                continue
            if (item / "cwd").resolve() == ROOT:
                return True
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return False


def _measured_metric(metrics: dict[str, Any], key: str) -> float | None:
    """Preserve unavailable statistical estimates instead of fabricating zero."""
    value = metrics.get(key)
    return None if value is None else float(value)


def snapshot(state: Path | None = None) -> dict[str, Any]:
    # Preserve the historical G452 study; promote only the explicitly pinned,
    # locally verified 100-generation clone to the dashboard's *default* view.
    if state is None:
        state = (
            P5_STATE
            if (P5_STATE / "academic-gpt-checkpoints/cycles.sqlite").is_file()
            else (
                LIVE_STATE
                if (LIVE_STATE / "research/academic-gpt-checkpoints/cycles.sqlite").is_file()
                else ACTIVE_STATE
                if ACTIVE_STATE.is_dir()
                else STATE
            )
        )
    baseline = 52
    label = "기존 개발 연구 (보존 원장)"
    if state == P5_STATE:
        baseline = 0
        label = "P5 신규 GPT 연구 (목표 100세대, 개발 전용)"
    if state == LIVE_STATE:
        baseline = 0
        label = "현재 GPT 작성 MCP 전략 연구 · 실측 체크포인트 (독립 개발 검증)"
    if state == ACTIVE_STATE:
        manifest = json.loads((state / "start-manifest.json").read_text(encoding="utf-8"))
        cohort = json.loads(
            (state / "cohorts" / (ACTIVE_COHORT_ID + ".json")).read_text(encoding="utf-8")
        )
        baseline = 452
        if (
            manifest.get("source_generation") != baseline
            or manifest.get("target_final_generation") != 552
            or manifest.get("source_evidence_hash") != cohort.get("evidence_head_at_start")
            or cohort.get("id") != ACTIVE_COHORT_ID
            or cohort.get("expected_start") != baseline
            or cohort.get("target") != 552
        ):
            raise ValueError("active cohort manifest does not match the trusted research clone")
        label = "현재 G453~G552 · 신규 100세대 연구 (고정 규칙 기반)"
    sid = (
        P5_SESSION_ID
        if state == P5_STATE
        else (
            LIVE_SESSION_ID
            if state == LIVE_STATE
            else (state / "session-id.txt").read_text(encoding="ascii").strip()
        )
    )
    if len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid):
        raise ValueError("invalid session id")
    base = state / (
        "academic-gpt-checkpoints" if state == P5_STATE else "research/academic-gpt-checkpoints"
    )
    with _read_db(base / "cycles.sqlite") as cycle, _read_db(base / "gateway.sqlite") as gate:
        row = cycle.execute(
            "SELECT requested,completed,status,dataset_hash FROM sessions WHERE id=?", (sid,)
        ).fetchone()
        phase = gate.execute("SELECT phase FROM stages WHERE session_id=?", (sid,)).fetchone()
        recs = cycle.execute(
            "SELECT generation,evidence_json,evidence_hash FROM generations "
            "WHERE session_id=? ORDER BY generation",
            (sid,),
        ).fetchall()
        timings = gate.execute(
            "SELECT start_utc,end_utc FROM generation_timings WHERE session_id=?", (sid,)
        ).fetchall()
    if row is None or phase is None:
        raise ValueError("session not found")
    seen = []
    prev = None
    proof = True
    for i, rec in enumerate(recs, 1):
        ev = json.loads(rec["evidence_json"])
        m = ev["metrics"]
        if (
            rec["generation"] != i
            or ev.get("previous_evidence_hash") != prev
            or (ev.get("evidence_hash") is not None and ev["evidence_hash"] != rec["evidence_hash"])
        ):
            proof = False
        prev = rec["evidence_hash"]
        seen.append(
            {
                "generation": i,
                "return": float(m["total_return"]),
                "mdd": float(m["max_drawdown"]),
                "trades": int(m["trade_count"]),
                "exposure": float(m["exposure"]),
                "sharpe": _measured_metric(m, "sharpe"),
                "cagr": float(m["cagr"]),
                "sortino": _measured_metric(m, "sortino"),
                "profit_factor": _measured_metric(m, "profit_factor"),
                "turnover": _measured_metric(m, "turnover"),
                "win_rate": _measured_metric(m, "win_rate"),
                "evidence_prefix": prev[:12],
                "eligible": int(m["trade_count"]) >= 30,
            }
        )
    if len(seen) != int(row["completed"]):
        proof = False
    if state == ACTIVE_STATE and (
        int(row["requested"]) != 552
        or len(recs) < baseline
        or recs[baseline - 1]["evidence_hash"] != manifest["source_evidence_hash"]
    ):
        raise ValueError("active cohort ledger has diverged from pinned G452 source")
    elapsed = []
    last_finished = None
    for rec in timings:
        if rec["end_utc"] is None:
            continue
        try:
            start = datetime.fromisoformat(rec["start_utc"])
            end = datetime.fromisoformat(rec["end_utc"])
            d = (end - start).total_seconds()
            if 0 < d < 7200:
                elapsed.append(d)
            if last_finished is None or end > last_finished:
                last_finished = end
        except (ValueError, TypeError):
            pass
    eligible = [g for g in seen if g["eligible"]]
    n = int(row["requested"])
    completed = int(row["completed"])
    return {
        "session": sid[:8],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "completed": completed,
        "requested": n,
        # Running cohorts show *new* generations, not their archived ancestors.
        "additional_completed": max(0, completed - baseline),
        "additional_target": max(0, n - baseline),
        "cohort_start_generation": baseline + 1,
        "cohort_label": label,
        "source_kind": (
            "GPT_AUTHORED_MCP_CHECKPOINT_DEVELOPMENT"
            if state in (LIVE_STATE, P5_STATE)
            else "ISOLATED_100_GENERATION_DEVELOPMENT"
            if state == ACTIVE_STATE
            else "ORIGINAL_ACADEMIC_DEVELOPMENT"
        ),
        "status": row["status"],
        "phase": phase["phase"],
        "proof_chain_ok": proof,
        "head_evidence_prefix": prev[:12] if prev else None,
        "last_end_utc": last_finished.isoformat() if last_finished else None,
        "avg_generation_seconds": round(statistics.mean(elapsed), 1) if elapsed else None,
        "last": seen[-1] if seen else None,
        "best_eligible": max(eligible, key=lambda g: g["return"]) if eligible else None,
        "avg_return": statistics.mean(g["return"] for g in seen) if seen else None,
        "avg_mdd": statistics.mean(g["mdd"] for g in seen) if seen else None,
        "positive_count": sum(g["return"] > 0 for g in seen),
        "qqq_dev_bh_return": QQQ_DEV_RETURN,
        "qqq_dev_bh_cagr": QQQ_DEV_CAGR,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "model_autonomy_verified": False,
        "data_scope": "NON_PIT_DEVELOPMENT_ONLY",
        "research_running_confirmed": _controller_running(state),
        "controller_note": (
            "ChatGPT-authored proposals via MCP, NOT unattended model-autonomy attestation"
            if state in (LIVE_STATE, P5_STATE)
            else "G4+ deterministic rule exploration (NOT 1 GPT decision per generation)"
        ),
        "generations": seen,
    }


HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quant AutoResearch — 연구 대시보드</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;color:#e6ebf3;background:#101827}
body{max-width:1190px;margin:auto;padding:28px}header{display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px}
h1{font-size:1.65rem;margin:0}h2{margin-top:28px;font-size:1.1rem}.muted,small{color:#a6b4ca}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:#1a2638;border:1px solid #34465a;padding:16px;border-radius:12px}
.value{font-size:1.7rem;font-weight:740;margin:5px 0}
progress{width:100%;height:13px;accent-color:#80c3fc}
.warning{padding:14px;border:1px solid #64728b;border-radius:9px;margin:21px 0;line-height:1.6}
.good{color:#89ddbb}.bad{color:#f7a8a8}.scroll{overflow:auto;max-height:500px;border:1px solid #34465a}
table{width:100%;border-collapse:collapse;font-size:.9rem;font-variant-numeric:tabular-nums}
td,th{padding:9px;text-align:right;border-bottom:1px solid #34465a}td:first-child,th:first-child{text-align:left}
svg{background:#1a2638;border-radius:10px;width:100%;height:180px}
footer{padding-top:24px;line-height:1.8;color:#a6b4ca;font-size:.82rem}
</style></head><body>
<header><div><h1>Quant AutoResearch</h1>
<p class="muted">새 독립 연구 세션 · QQQ 일봉 · SQLite 실시간 증거</p></div>
<div><div id="online">연결 확인 중</div><small id="updated"></small></div></header>
<div class="warning">개발용 NON-PIT 데이터 · 실거래 비활성 · 독립 OOS 검증 없음.
G4 이후는 GPT가 매 세대 별도로 연구한 것이 아니라 규칙 기반 탐색입니다.</div>
<p id="error" class="bad"></p>
<section class="cards">
<div class="card"><small>완료 / 목표</small><div class="value" id="progress">—</div>
<progress max="1" value="0" id="bar"></progress><small id="additional"></small></div>
<div class="card"><small>연구 체크포인트</small><div class="value" id="phase">—</div>
<small id="phaseNote"></small></div>
<div class="card"><small>30건 이상 거래 최고</small><div class="value" id="best">—</div>
<small id="bestInfo"></small></div>
<div class="card"><small>최근 완료 전략</small><div class="value" id="last">—</div>
<small id="lastInfo"></small></div>
<div class="card"><small>전체 세대 평균 수익률</small><div class="value" id="avg">—</div>
<small id="positive"></small></div>
<div class="card"><small>평균 최대낙폭 (MDD)</small><div class="value" id="avgMdd">—</div>
<small id="proof"></small></div>
</section>
<h2>세대별 누적 수익률 (%)</h2>
<svg id="graph" viewBox="0 0 1000 180" preserveAspectRatio="none" role="img" aria-label="세대별 수익률 차트"></svg>
<p class="muted">QQQ 단순보유 개발 비교: <span id="qqq">—</span>.
각 점은 동일 기간 개별 전략 백테스트이며 세대 수익률을 합산하지 않습니다.</p>
<h2>세대별 평가 원장</h2>
<div class="scroll"><table><thead><tr><th>세대</th><th>수익률</th><th>MDD</th>
<th>거래</th><th>노출률</th><th>적격</th><th>증거 해시</th></tr></thead>
<tbody id="body"></tbody></table></div>
<footer>자동 업데이트 5초 · 평균 세대 소요 <span id="seconds">—</span> ·
마지막 완료 시각 <span id="time">—</span> · 연구 실행 상태는 체크포인트만으로 판단하지 않음.
세션 <span id="session">—</span></footer>
<script src="app.js" defer></script></body></html>"""

JS = """'use strict';
const e=id=>document.getElementById(id);
const pct=n=>n===null||n===undefined?'—':(n*100).toFixed(2)+'%';
function show(d){
e('online').textContent='읽기 전용 데이터 연결 정상';
e('updated').textContent=new Date(d.fetched_at).toLocaleString('ko-KR');
e('progress').textContent=d.completed+' / '+d.requested;
e('bar').max=Math.max(1,d.requested);e('bar').value=d.completed;
e('additional').textContent='추가 '+d.additional_completed+' / '+d.additional_target;
e('phase').textContent=d.phase;e('phase').style.fontSize='1.1rem';
e('phaseNote').textContent=d.status+' · 자동 연구 실행 확인 안 됨';
e('best').textContent=d.best_eligible?pct(d.best_eligible.return):'없음';
e('bestInfo').textContent=d.best_eligible?'G'+d.best_eligible.generation+
', MDD '+pct(d.best_eligible.mdd)+', 거래 '+d.best_eligible.trades+'건':'거래 30건 이상 필요';
e('last').textContent=d.last?pct(d.last.return):'—';
e('lastInfo').textContent=d.last?'G'+d.last.generation+', MDD '+pct(d.last.mdd):'';
e('avg').textContent=pct(d.avg_return);
e('positive').textContent='양수 세대 '+d.positive_count+'/'+d.completed;
e('avgMdd').textContent=pct(d.avg_mdd);
e('proof').textContent=d.proof_chain_ok?'Evidence 체인 정상':'Evidence 확인 필요';
e('proof').className=d.proof_chain_ok?'good':'bad';
e('qqq').textContent=pct(d.qqq_dev_bh_return);
e('seconds').textContent=d.avg_generation_seconds===null?'미측정':d.avg_generation_seconds+'초';
e('time').textContent=d.last_end_utc?new Date(d.last_end_utc).toLocaleString('ko-KR'):'—';
e('session').textContent=d.session+'…';
const body=e('body');body.replaceChildren();
for(const g of [...d.generations].reverse()){
let tr=document.createElement('tr');
[g.generation,pct(g.return),pct(g.mdd),g.trades,pct(g.exposure),
g.eligible?'예':'아니오',g.evidence_prefix].forEach((v,i)=>{
let cell=document.createElement('td');cell.textContent=v;
if(i===1)cell.className=g.return>=0?'good':'bad';tr.appendChild(cell);
});body.appendChild(tr);
}
let svg=e('graph');svg.replaceChildren();
if(d.generations.length){
let rates=d.generations.map(g=>100*g.return);
let lo=Math.min(-5,...rates),hi=Math.max(5,...rates),delta=hi-lo;
const ns='http://www.w3.org/2000/svg';
let z=document.createElementNS(ns,'line'),zy=165-150*(0-lo)/delta;
for(const [k,v] of Object.entries({x1:10,x2:990,y1:zy,y2:zy,stroke:'#8fa0b0','stroke-dasharray':'5 6'}))z.setAttribute(k,v);
svg.appendChild(z);
let line=document.createElementNS(ns,'polyline');
let points=rates.map((v,i)=>(15+i*970/Math.max(1,rates.length-1))+','+(165-150*(v-lo)/delta)).join(' ');
for(const [k,v] of Object.entries({points:points,fill:'none',stroke:'#80c3fc','stroke-width':'2.5'}))line.setAttribute(k,v);
svg.appendChild(line);
}
}
async function poll(){
try{
const r=await fetch('api/status',{cache:'no-store',credentials:'same-origin'});
if(!r.ok)throw new Error('HTTP '+r.status);
show(await r.json());e('error').textContent='';
}catch(err){e('online').textContent='연결 실패';e('error').textContent=String(err);}
}
poll();setInterval(poll,5000);
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._respond(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
        elif path == "/app.js":
            self._respond(200, "text/javascript; charset=utf-8", JS.encode("utf-8"))
        elif path in ("/api/status", "/health"):
            try:
                view = snapshot()
                if path == "/health":
                    view = {
                        "status": "ok",
                        "completed": view["completed"],
                        "requested": view["requested"],
                    }
                self._respond(
                    200,
                    "application/json; charset=utf-8",
                    json.dumps(view, ensure_ascii=False).encode("utf-8"),
                )
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                self._respond(
                    503,
                    "application/json",
                    json.dumps(
                        {"error": "research_data_unavailable", "kind": type(exc).__name__}
                    ).encode("utf-8"),
                )
        else:
            self._respond(404, "text/plain", b"not found")

    def _respond(self, code: int, mime: str, content: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        parser.error("dashboard can only bind to loopback")
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()
